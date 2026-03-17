# POST /chat — SSE streaming endpoint

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.core.context_assembler import ContextAssembler
from backend.core.llm_client import LLMClient
from backend.core.token_manager import TokenManager
from backend.db.db_client import DBClient
from backend.prompts.router import QueryRouter
from backend.rag.retriever import Retriever
from backend.security.auth import decode_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["chat"])


# -- request / response models -------------------------------------------------

class ChatRequest(BaseModel):
    query: str = Field(..., max_length=2000)
    session_id: str | None = None
    domain: str | None = None  # "tax"|"equity"|"risk"|"doc"|"general"


# -- helpers -------------------------------------------------------------------

async def _get_next_turn_number(db: DBClient, session_id: str) -> int:
    row = await db.fetchone(
        "SELECT MAX(turn_number) as max_turn FROM turns WHERE session_id=?",
        (session_id,),
    )
    return (row["max_turn"] or 0) + 1


# -- SSE generator -------------------------------------------------------------

async def generate_response(
    request: ChatRequest,
    llm_client: LLMClient,
    token_manager: TokenManager,
    config: dict,
    retriever: Retriever | None,
    context_assembler: ContextAssembler | None,
    query_router: QueryRouter | None,
    db: DBClient | None,
    user_id: str | None,
) -> AsyncGenerator[str, None]:
    """Yield SSE events: token chunks followed by a done sentinel."""
    start = time.perf_counter()

    # 1. Validate
    if not request.query or not request.query.strip():
        yield f"data: {json.dumps({'error': 'Query must not be empty', 'done': True})}\n\n"
        return

    # 2. Route the query
    domain = "general"
    if query_router:
        domain = query_router.route(
            request.query,
            has_uploaded_docs=bool(request.session_id),
        )

    # 3. Get user doc collections for this session
    user_doc_collections: list[str] = []
    if request.session_id and db:
        rows = await db.fetchall(
            """SELECT ud.chroma_collection
               FROM session_documents sd
               JOIN user_documents ud ON sd.doc_id = ud.doc_id
               WHERE sd.session_id = ?
               AND ud.sanitisation_status != 'quarantined'""",
            (request.session_id,),
        )
        user_doc_collections = [r["chroma_collection"] for r in rows if r["chroma_collection"]]

    # 4. Get session summary and history
    session_summary: str | None = None
    history_turns: list[dict] = []
    if request.session_id and db:
        summary_row = await db.fetchone(
            """SELECT summary_text FROM session_summaries
               WHERE session_id = ? AND is_current = 1""",
            (request.session_id,),
        )
        if summary_row:
            session_summary = summary_row["summary_text"]

        turn_rows = await db.fetchall(
            """SELECT role, content FROM turns
               WHERE session_id = ?
               ORDER BY turn_number DESC LIMIT 4""",
            (request.session_id,),
        )
        history_turns = list(reversed([dict(r) for r in turn_rows]))

    # 5. RAG retrieval
    retrieved_chunks = []
    if retriever:
        try:
            retrieved_chunks = await retriever.retrieve(
                query=request.query,
                domain=domain,
                session_id=request.session_id,
                user_doc_collections=user_doc_collections,
            )
        except Exception as exc:
            logger.warning("RAG retrieval failed: %s", exc)
            # Continue without RAG — degraded but functional

    # 6. Assemble context
    if context_assembler:
        messages, budget = context_assembler.assemble(
            query=request.query,
            domain=domain,
            retrieved_chunks=retrieved_chunks,
            session_summary=session_summary,
            history_turns=history_turns,
            session_id=request.session_id,
        )
    else:
        # Fallback: minimal prompt
        messages = [
            {"role": "system", "content": "You are Samvad, a finance assistant. Answer clearly and accurately."},
            {"role": "user", "content": request.query},
        ]
        budget = {}

    # 7. Save user turn to DB (before streaming)
    turn_number = 1
    if request.session_id and db and user_id:
        turn_id_user = str(uuid.uuid4())
        turn_number = await _get_next_turn_number(db, request.session_id)
        await db.execute(
            """INSERT INTO turns
               (turn_id, session_id, user_id, turn_number, role,
                content, domain, tokens_input, retrieval_used, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                turn_id_user,
                request.session_id,
                user_id,
                turn_number,
                "user",
                request.query,
                domain,
                budget.get("query_tokens", 0),
                1 if retrieved_chunks else 0,
                datetime.now(timezone.utc).isoformat(),
            ),
        )

    # 8. Stream response + accumulate full text
    full_response = ""
    try:
        model_cfg = config.get("model", {})
        async for token in llm_client.stream_chat(
            messages,
            max_tokens=model_cfg.get("max_tokens_generation", 1024),
            temperature=model_cfg.get("temperature", 0.3),
            top_p=model_cfg.get("top_p", 0.95),
            repeat_penalty=model_cfg.get("repeat_penalty", 1.1),
        ):
            full_response += token
            yield f"data: {json.dumps({'token': token, 'done': False})}\n\n"

    except GeneratorExit:
        logger.info("Client disconnected (session_id=%s)", request.session_id)
    except Exception as exc:
        logger.exception("Stream error (session_id=%s): %s", request.session_id, exc)
        yield f"data: {json.dumps({'error': str(exc), 'done': True})}\n\n"
        return
    finally:
        latency_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "chat session_id=%s query_len=%d domain=%s latency_ms=%.1f",
            request.session_id,
            len(request.query),
            domain,
            latency_ms,
        )

    # 9. Build sources for response
    sources = [
        {
            "document": c.source_name,
            "section": c.metadata.get("section_number"),
            "page": c.metadata.get("page_number"),
        }
        for c in retrieved_chunks[:5]
    ]

    # 10. Send done event with sources
    yield f"data: {json.dumps({'token': '', 'done': True, 'sources': sources})}\n\n"

    # 11. Save assistant turn to DB (after streaming)
    if request.session_id and db and user_id:
        turn_id_asst = str(uuid.uuid4())
        await db.execute(
            """INSERT INTO turns
               (turn_id, session_id, user_id, turn_number, role,
                content, domain, tokens_output, sources_cited,
                retrieval_used, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                turn_id_asst,
                request.session_id,
                user_id,
                turn_number + 1,
                "assistant",
                full_response,
                domain,
                budget.get("generation_budget", 0),
                json.dumps(sources),
                1 if retrieved_chunks else 0,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        # Update session last_active_at and total_turns
        await db.execute(
            """UPDATE sessions SET
               last_active_at = ?, total_turns = total_turns + 2,
               domain_last = ?
               WHERE session_id = ?""",
            (
                datetime.now(timezone.utc).isoformat(),
                domain,
                request.session_id,
            ),
        )


# -- endpoints -----------------------------------------------------------------

@router.post("/chat")
async def chat(request: Request, body: ChatRequest):
    llm_client: LLMClient = request.app.state.llm_client
    token_manager: TokenManager = request.app.state.token_manager
    config: dict = request.app.state.config
    retriever: Retriever | None = getattr(request.app.state, "retriever", None)
    context_assembler: ContextAssembler | None = getattr(request.app.state, "context_assembler", None)
    query_router: QueryRouter | None = getattr(request.app.state, "query_router", None)
    db: DBClient | None = getattr(request.app.state, "db", None)

    # Extract user_id from JWT if present
    user_id: str | None = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        try:
            payload = decode_token(auth_header[7:])
            user_id = payload.get("sub")
        except Exception:
            pass  # Phase 1 compat — no auth required yet

    return StreamingResponse(
        generate_response(
            body,
            llm_client,
            token_manager,
            config,
            retriever,
            context_assembler,
            query_router,
            db,
            user_id,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/chat/health")
async def chat_health(request: Request):
    llm_client: LLMClient = request.app.state.llm_client
    return await llm_client.health_check()


# -- request / response models -------------------------------------------------

class ChatRequest(BaseModel):
    query: str = Field(..., max_length=2000)
    session_id: str | None = None
    domain: str | None = None  # "tax"|"equity"|"risk"|"doc"|"general"


# -- SSE generator --------------------------------------------------------------

async def generate_response(
    request: ChatRequest,
    llm_client: LLMClient,
    token_manager: TokenManager,
    config: dict,
) -> AsyncGenerator[str, None]:
    """Yield SSE events: token chunks followed by a done sentinel."""
    start = time.perf_counter()

    # Validate
    if not request.query or not request.query.strip():
        yield f"data: {json.dumps({'error': 'Query must not be empty', 'done': True})}\n\n"
        return

    # TODO: [PHASE 2] Validate JWT auth token
    # TODO: [PHASE 3] Run RAG retrieval to get context chunks
    # TODO: [PHASE 3] Load session summary from session_manager

    system_prompt = "You are Samvad, a finance assistant. Answer clearly and accurately."

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": request.query},
    ]
    # TODO: [PHASE 2] Add session history from token_manager.allocate_budget()

    try:
        model_cfg = config.get("model", {})
        async for token in llm_client.stream_chat(
            messages,
            max_tokens=model_cfg.get("max_tokens_generation", 1024),
            temperature=model_cfg.get("temperature", 0.3),
            top_p=model_cfg.get("top_p", 0.95),
            repeat_penalty=model_cfg.get("repeat_penalty", 1.1),
        ):
            yield f"data: {json.dumps({'token': token, 'done': False})}\n\n"

        yield f"data: {json.dumps({'token': '', 'done': True})}\n\n"

    except GeneratorExit:
        logger.info("Client disconnected (session_id=%s)", request.session_id)
    except Exception as exc:
        logger.exception("Stream error (session_id=%s): %s", request.session_id, exc)
        yield f"data: {json.dumps({'error': str(exc), 'done': True})}\n\n"
    finally:
        latency_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "chat session_id=%s query_len=%d domain=%s latency_ms=%.1f",
            request.session_id,
            len(request.query),
            request.domain,
            latency_ms,
        )


# -- endpoints ------------------------------------------------------------------

@router.post("/chat")
async def chat(request: Request, body: ChatRequest):
    llm_client: LLMClient = request.app.state.llm_client
    token_manager: TokenManager = request.app.state.token_manager
    config: dict = request.app.state.config

    return StreamingResponse(
        generate_response(body, llm_client, token_manager, config),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/chat/health")
async def chat_health(request: Request):
    llm_client: LLMClient = request.app.state.llm_client
    return await llm_client.health_check()
