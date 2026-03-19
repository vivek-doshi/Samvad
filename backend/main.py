# Samvad Backend — FastAPI Application Entry Point
# Note 1: This file is the heart of the Samvad backend. It wires together every
# component — database, LLM client, embedder, retriever, routers — and starts
# the FastAPI web server. Junior tip: read this file top-to-bottom like a recipe
# for assembling the whole application.

import logging
# Note 2: 'logging' is Python's built-in module for printing structured messages
# to the console or a log file. Unlike print(), it supports log levels (DEBUG,
# INFO, WARNING, ERROR) so you can silence verbose output in production.
import os
# Note 3: 'os' gives access to environment variables via os.getenv(). Environment
# variables are a secure way to pass secrets (DB paths, tokens) to an app without
# hard-coding them. Docker and Kubernetes inject them at container start.
from contextlib import asynccontextmanager
# Note 4: 'asynccontextmanager' converts a generator function into an async context
# manager. FastAPI uses it to run startup code when the server boots and shutdown
# code when it stops — without any extra class boilerplate.

import yaml
# Note 5: PyYAML parses .yaml files into Python dicts. Config settings (model
# parameters, token budgets, RAG settings) live in config/samvad.yaml so they
# can be tuned without touching code. yaml.safe_load() is always preferred over
# yaml.load() because it blocks code execution inside YAML files (a security risk).
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
# Note 6: CORS (Cross-Origin Resource Sharing) is a browser security feature.
# By default, a browser blocks JavaScript on one origin (e.g. localhost:4200)
# from calling an API on a different origin (e.g. localhost:8000). Adding
# CORSMiddleware tells the browser "this other origin is allowed".
from fastapi.responses import JSONResponse
# Note 7: JSONResponse constructs an HTTP response with a JSON body and lets us
# set a custom status code. Used here in the global error handler to return a
# consistent error format when something unexpected goes wrong.

import chromadb
# Note 8: ChromaDB is an open-source vector database. It stores document
# embeddings (numerical representations of text) and supports fast approximate
# nearest-neighbour search — the backbone of semantic (meaning-based) retrieval.
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

# Note 9: '__name__' resolves to the dotted module path (e.g. 'backend.main').
# Naming loggers this way creates a hierarchy — you can silence all 'backend.*'
# logs in one config change without touching any other module.
logger = logging.getLogger(__name__)

# Note 10: os.getenv(key, default) reads the variable from the process environment
# at runtime. If SAMVAD_ENV is not set, we fall back to "development" which
# enables more verbose error messages (see the global exception handler below).
SAMVAD_ENV = os.getenv("SAMVAD_ENV", "development")
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:4200")


# Note 11: This helper reads samvad.yaml and returns its contents as a Python dict.
# yaml.safe_load is safe for untrusted input — it only creates basic Python objects
# (dicts, lists, strings, numbers) and never executes embedded code.
def _load_config() -> dict:
    with open("config/samvad.yaml") as f:
        return yaml.safe_load(f)


# Note 12: The @asynccontextmanager + 'lifespan' pattern is FastAPI's recommended
# way to run startup and shutdown logic. Code BEFORE 'yield' runs once when the
# server starts; code AFTER 'yield' runs once when the server stops (e.g. CTRL+C
# or container shutdown). This ensures resources are always cleaned up properly.
@asynccontextmanager
async def lifespan(app: FastAPI):
    # -- startup ----------------------------------------------------------------
    from pathlib import Path
    # Note 13: Path() creates a cross-platform filesystem path object. Unlike
    # string concatenation, Path objects handle OS differences (/ vs \) automatically
    # and provide helpful methods like .exists(), .parent, and .read_text().

    config_path = Path("config/samvad.yaml")
    if not config_path.exists():
        config_path = Path(__file__).parent.parent / "config" / "samvad.yaml"

    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    # Note 14: 'app.state' is a FastAPI-provided namespace for storing objects
    # that need to be shared across requests. Think of it as a global dict that
    # is attached to the app. Routes access it via 'request.app.state.db' etc.
    app.state.config = config

    db_path = os.getenv("SQLITE_PATH", "runtime/sqlite/samvad.db")
    # Note 15: DBClient wraps aiosqlite to provide async (non-blocking) SQLite
    # access. Async DB calls are critical in a web server — a synchronous
    # (blocking) query would stall ALL other incoming requests while waiting.
    db = DBClient(db_path)
    await db.connect()
    await db.init_schema()
    app.state.db = db
    logger.info("SQLite connected: %s", db_path)

    # Note 16: LLMClient is an async HTTP wrapper around the llama-cpp-python
    # model server (which runs Arthvidya, the local LLM). '__aenter__' opens
    # a persistent httpx connection pool so each request reuses existing TCP
    # connections rather than opening a new one for every inference call.
    server_cfg = config.get("model", {})
    llm_client = LLMClient(
        base_url=f"http://{os.getenv('LLAMA_SERVER_HOST', 'localhost')}:{os.getenv('LLAMA_SERVER_PORT', '8080')}",
        timeout=server_cfg.get("timeout_seconds", 120),
    )
    await llm_client.__aenter__()
    app.state.llm_client = llm_client

    app.state.token_manager = TokenManager(config=config)

    # ChromaDB
    # Note 17: PersistentClient stores vector embeddings on disk so they survive
    # restarts. The alternative is chromadb.EphemeralClient() (in-memory only),
    # which would require re-embedding all documents every time the server starts.
    chroma_path = os.getenv("CHROMADB_PATH", "runtime/chromadb")
    chroma_client = chromadb.PersistentClient(path=chroma_path)
    app.state.chroma = chroma_client

    # Embedder
    # Note 18: The Embedder loads a pre-trained sentence transformer model that
    # converts text strings into dense 384-dimensional vectors. Texts with similar
    # meanings produce vectors that are close together in this high-dimensional
    # space — enabling "find me passages similar to this question" queries.
    embedder = Embedder(
        model_name_or_path=os.getenv("EMBEDDING_MODEL_PATH", "BAAI/bge-small-en-v1.5"),
        device=os.getenv("EMBEDDING_DEVICE", "cpu"),
    )
    app.state.embedder = embedder

    # BM25 — load all pre-built indices
    # Note 19: BM25 (Best Match 25) is a classical keyword ranking algorithm.
    # It complements vector search by rewarding exact keyword matches that
    # semantic search might miss. Both results are later combined via RRF.
    # load_all() reads pre-built BM25 pickle files from disk into memory.
    bm25 = BM25Index(index_dir=os.getenv("BM25_INDEX_PATH", "runtime/bm25_index"))
    bm25.load_all()
    app.state.bm25 = bm25

    # Reranker (CPU)
    # Note 20: A cross-encoder reranker scores every (query, passage) pair
    # together, giving more accurate relevance scores than the embedder's
    # approximate nearest-neighbour search. It runs on CPU to leave the GPU
    # exclusively for the LLM (Arthvidya), which is more compute-intensive.
    reranker = Reranker()
    app.state.reranker = reranker

    # Query expander
    expander = QueryExpander()
    app.state.expander = expander

    # Retriever
    # Note 21: The Retriever is the brain of the RAG pipeline. It combines:
    # 1. Vector search (semantic similarity via ChromaDB + embedder)
    # 2. BM25 keyword search
    # 3. RRF (Reciprocal Rank Fusion) to merge both ranked lists
    # 4. Reranker to pick the best top_k_rerank chunks
    # 5. Parent promotion to surface richer context around matched chunks
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
    # Note 22: PromptAssembler builds the LLM system prompt by combining a base
    # prompt with a domain-specific overlay (tax / equity / risk / doc / general)
    # and a security injection shield that prevents prompt-injection attacks.
    app.state.prompt_assembler = PromptAssembler()
    # Note 23: QueryRouter classifies each user query into a domain using keyword
    # matching. The chosen domain determines which ChromaDB collections are searched
    # and which prompt overlay is used, keeping responses domain-appropriate.
    app.state.query_router = QueryRouter()

    # Context assembler
    app.state.context_assembler = ContextAssembler(
        token_manager=app.state.token_manager,
        prompt_assembler=app.state.prompt_assembler,
    )

    # Document ingester
    # Note 24: DocumentIngester handles the full upload pipeline in one call:
    # parse file format (PDF/DOCX/CSV/XLSX/TXT) -> sanitise for dangerous content
    # -> chunk into overlapping pieces -> embed -> store in ChromaDB + BM25.
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

    # Note 25: 'yield' is the boundary between startup and shutdown in a lifespan
    # context manager. FastAPI pauses here while serving requests. When the server
    # receives a shutdown signal, execution resumes at the code below.
    yield

    # -- shutdown ---------------------------------------------------------------
    # Note 26: Closing resources in reverse order of creation is good practice.
    # The LLM client closes its HTTP connection pool, and the DB flushes any
    # pending writes. This prevents data corruption on unexpected shutdowns.
    await llm_client.__aexit__(None, None, None)
    await app.state.db.close()
    logger.info("Samvad shut down cleanly")


# Note 27: FastAPI is an ASGI (Asynchronous Server Gateway Interface) framework.
# The 'lifespan' argument registers our startup/shutdown generator.
# The auto-generated interactive API docs are at http://localhost:8000/docs
# (Swagger UI) and http://localhost:8000/redoc (ReDoc).
app = FastAPI(
    title="Samvad API",
    description="Samvad finance assistant backend",
    version="0.1.0",
    lifespan=lifespan,
)

# -- CORS ----------------------------------------------------------------------
# Note 28: allow_origins is a list of trusted origins. In production, this should
# be the exact domain(s) of your frontend. 'allow_credentials=True' is required
# when the Angular app sends the 'Authorization' header with Bearer tokens.
# 'allow_methods=["*"]' and 'allow_headers=["*"]' permit all HTTP methods/headers
# — acceptable for internal apps but should be tightened for public APIs.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in CORS_ORIGINS.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -- routers -------------------------------------------------------------------
# Note 29: Each 'include_router' call mounts all endpoints from that module onto
# the app. Routers are defined in backend/api/routes/ and grouped by feature.
# The chat router handles /api/chat, auth handles /api/auth, etc.
# Keeping routes in separate files makes the codebase easier to navigate
# as it grows — you know exactly which file to open for each API endpoint.
app.include_router(chat.router)
app.include_router(auth_router.router)
app.include_router(sessions_router.router)
app.include_router(health.router)
app.include_router(upload_router.router)
# TODO: [PHASE 4] app.include_router(corpus.router)


# -- global exception handler --------------------------------------------------
# Note 30: @app.exception_handler(Exception) is a catch-all for any unhandled
# Python exception that bubbles up through the request processing stack.
# In 'development' mode, the real error detail is returned to help debugging.
# In 'production', only a generic message is returned — never expose stack traces
# or internal paths to users, as this helps attackers find vulnerabilities.
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception: %s", exc)
    detail = str(exc) if SAMVAD_ENV == "development" else "An internal error occurred"
    return JSONResponse(
        status_code=500,
        content={"error": "internal_server_error", "detail": detail},
    )


# -- liveness probe ------------------------------------------------------------
# Note 31: /health is a minimal endpoint that returns 200 OK immediately.
# Container orchestrators (Docker Compose healthcheck, Kubernetes liveness probe)
# call this repeatedly. If it stops returning 200, the container is restarted.
# This endpoint is separate from /api/health which checks DB and LLM status.
@app.get("/health", tags=["health"])
async def root_health():
    return {"status": "ok", "version": "0.1.0", "env": SAMVAD_ENV}
