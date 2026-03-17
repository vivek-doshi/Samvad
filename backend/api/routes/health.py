# GET /health — model + DB + ChromaDB status

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/api/health")
async def api_health():
    # TODO: [PHASE 2] Check DB connectivity
    # TODO: [PHASE 3] Check ChromaDB + BM25 index status
    return {"status": "ok"}
