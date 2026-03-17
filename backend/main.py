# Samvad Backend — FastAPI Application Entry Point

import logging
import os
from contextlib import asynccontextmanager

import yaml
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api.routes import chat, health
from backend.core.llm_client import LLMClient
from backend.core.token_manager import TokenManager

logger = logging.getLogger(__name__)

SAMVAD_ENV = os.getenv("SAMVAD_ENV", "development")
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:4200")


def _load_config() -> dict:
    with open("config/samvad.yaml") as f:
        return yaml.safe_load(f)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # -- startup ----------------------------------------------------------------
    config = _load_config()
    app.state.config = config

    llm_client = LLMClient(timeout=config.get("model", {}).get("timeout_seconds", 120))
    await llm_client.__aenter__()
    app.state.llm_client = llm_client

    app.state.token_manager = TokenManager(config)

    # TODO: [PHASE 2] Initialise SQLite db_client
    # TODO: [PHASE 3] Load BM25 index
    # TODO: [PHASE 3] Connect ChromaDB

    logger.info(
        "Samvad started — env=%s llm=%s context_window=%d",
        SAMVAD_ENV,
        llm_client.base_url,
        config.get("model", {}).get("context_window", 32768),
    )

    yield

    # -- shutdown ---------------------------------------------------------------
    await llm_client.__aexit__(None, None, None)
    # TODO: [PHASE 2] Close db connection
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
app.include_router(health.router)
# TODO: [PHASE 2] app.include_router(auth.router)
# TODO: [PHASE 2] app.include_router(sessions.router)
# TODO: [PHASE 3] app.include_router(upload.router)
# TODO: [PHASE 3] app.include_router(corpus.router)


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
