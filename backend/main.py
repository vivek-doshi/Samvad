# Samvad Backend — FastAPI Application Entry Point

import logging
import os
from contextlib import asynccontextmanager

import yaml
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import chromadb
from backend.api.middleware.auth_middleware import get_current_user_id
from backend.api.routes import auth as auth_router
from backend.api.routes import chat, health
from backend.api.routes import sessions as sessions_router
from backend.api.routes import upload as upload_router
from backend.core.context_assembler import ContextAssembler
from backend.core.llm_client import LLMClient
from backend.core.token_manager import TokenManager
from backend.db.db_client import DBClient
from backend.prompts.assembler import PromptAssembler
from backend.prompts.router import QueryRouter
from backend.rag.bm25_index import BM25Index
from backend.rag.embedder import Embedder
from backend.rag.ingestion import DocumentIngester
from backend.rag.query_expander import QueryExpander
from backend.rag.reranker import Reranker
from backend.rag.retriever import Retriever

logger = logging.getLogger(__name__)

SAMVAD_ENV = os.getenv("SAMVAD_ENV", "development")
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:4200")


def _load_config() -> dict:
    with open("config/samvad.yaml") as f:
        return yaml.safe_load(f)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # -- startup ----------------------------------------------------------------
    from pathlib import Path

    config_path = Path("config/samvad.yaml")
    if not config_path.exists():
        config_path = Path(__file__).parent.parent / "config" / "samvad.yaml"

    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    app.state.config = config

    db_path = os.getenv("SQLITE_PATH", "runtime/sqlite/samvad.db")
    db = DBClient(db_path)
    await db.connect()
    await db.init_schema()
    app.state.db = db
    logger.info("SQLite connected: %s", db_path)

    server_cfg = config.get("model", {})
    llm_client = LLMClient(
        base_url=f"http://{os.getenv('LLAMA_SERVER_HOST', 'localhost')}:{os.getenv('LLAMA_SERVER_PORT', '8080')}",
        timeout=server_cfg.get("timeout_seconds", 120),
    )
    await llm_client.__aenter__()
    app.state.llm_client = llm_client

    app.state.token_manager = TokenManager(config=config)

    # ChromaDB
    chroma_path = os.getenv("CHROMADB_PATH", "runtime/chromadb")
    chroma_client = chromadb.PersistentClient(path=chroma_path)
    app.state.chroma = chroma_client

    # Embedder
    embedder = Embedder(
        model_name_or_path=os.getenv("EMBEDDING_MODEL_PATH", "BAAI/bge-small-en-v1.5"),
        device=os.getenv("EMBEDDING_DEVICE", "cpu"),
    )
    app.state.embedder = embedder

    # BM25 — load all pre-built indices
    bm25 = BM25Index(index_dir=os.getenv("BM25_INDEX_PATH", "runtime/bm25_index"))
    bm25.load_all()
    app.state.bm25 = bm25

    # Reranker (CPU)
    reranker = Reranker()
    app.state.reranker = reranker

    # Query expander
    expander = QueryExpander()
    app.state.expander = expander

    # Retriever
    retriever = Retriever(
        chroma_client=chroma_client,
        embedder=embedder,
        bm25=bm25,
        reranker=reranker,
        expander=expander,
        top_k_retrieval=config.get("rag", {}).get("top_k_retrieval", 10),
        top_k_rerank=config.get("rag", {}).get("top_k_rerank", 5),
        rrf_k=config.get("rag", {}).get("rrf_k", 60),
    )
    app.state.retriever = retriever

    # Prompt assembler + router
    app.state.prompt_assembler = PromptAssembler()
    app.state.query_router = QueryRouter()

    # Context assembler
    app.state.context_assembler = ContextAssembler(
        token_manager=app.state.token_manager,
        prompt_assembler=app.state.prompt_assembler,
    )

    # Document ingester
    app.state.ingester = DocumentIngester(
        embedder=embedder,
        chroma_client=chroma_client,
        bm25=bm25,
    )

    logger.info("RAG pipeline initialised — ChromaDB: %s", chroma_path)

    logger.info(
        "Samvad started — env=%s llm=%s context_window=%d",
        SAMVAD_ENV,
        llm_client.base_url,
        config.get("model", {}).get("context_window", 32768),
    )

    yield

    # -- shutdown ---------------------------------------------------------------
    await llm_client.__aexit__(None, None, None)
    await app.state.db.close()
    logger.info("Samvad shut down cleanly")


app = FastAPI(
    title="Samvad API",
    description="Samvad finance assistant backend",
    version="0.1.0",
    lifespan=lifespan,
)

# -- CORS ----------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in CORS_ORIGINS.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -- routers -------------------------------------------------------------------
app.include_router(chat.router)
app.include_router(auth_router.router)
app.include_router(sessions_router.router)
app.include_router(health.router)
app.include_router(upload_router.router)
# TODO: [PHASE 4] app.include_router(corpus.router)


# -- global exception handler --------------------------------------------------
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception: %s", exc)
    detail = str(exc) if SAMVAD_ENV == "development" else "An internal error occurred"
    return JSONResponse(
        status_code=500,
        content={"error": "internal_server_error", "detail": detail},
    )


# -- liveness probe ------------------------------------------------------------
@app.get("/health", tags=["health"])
async def root_health():
    return {"status": "ok", "version": "0.1.0", "env": SAMVAD_ENV}
