from sentence_transformers import CrossEncoder
import logging
from backend.rag.chunkers import Chunk

logger = logging.getLogger(__name__)


class Reranker:
    """Cross-encoder reranker. Scores (query, chunk) pairs on CPU."""

    def __init__(
        self,
        model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
        device: str = "cpu",
        max_length: int = 512,
    ):
        logger.info("Loading reranker model: %s on %s", model_name, device)
        self.model = CrossEncoder(model_name, device=device, max_length=max_length)

    def rerank(
        self, query: str, chunks: list[Chunk], top_k: int = 5
    ) -> list[tuple[Chunk, float]]:
        if not chunks:
            return []
        pairs = [(query, chunk.text[:1000]) for chunk in chunks]
        scores = self.model.predict(pairs)
        scored = list(zip(chunks, scores.tolist()))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]
