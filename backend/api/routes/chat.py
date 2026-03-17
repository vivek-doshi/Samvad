# POST /chat — SSE streaming endpoint

import json
import logging
import time
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.core.llm_client import LLMClient
from backend.core.token_manager import TokenManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["chat"])


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
