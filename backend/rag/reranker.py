from sentence_transformers import CrossEncoder
# Note 1: CrossEncoder is different from the bi-encoder used in Embedder. A bi-encoder
# encodes query and passage SEPARATELY (fast but less accurate). A cross-encoder
# encodes them TOGETHER in one pass, so the model can look for fine-grained semantic
# matches between the two texts. This makes cross-encoders much more accurate but
# too slow to use for the initial retrieval (hence they are used for reranking only).
import logging
from backend.rag.chunkers import Chunk

logger = logging.getLogger(__name__)


class Reranker:
    """Cross-encoder reranker. Scores (query, chunk) pairs on CPU."""
    # Note 2: ms-marco-MiniLM-L-6-v2 is trained on the MS MARCO passage ranking
    # dataset, which includes question-answering over financial and general web text.
    # L-6 means 6 transformer layers — small enough to run quickly on CPU.

    def __init__(
        self,
        model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
        device: str = "cpu",
        max_length: int = 512,
        # Note 3: max_length=512 truncates the (query + passage) input to 512 tokens.
        # Cross-encoders are expensive — longer inputs mean longer inference time.
        # Truncating to 512 covers most passages without sacrificing speed significantly.
    ):
        logger.info("Loading reranker model: %s on %s", model_name, device)
        self.model = CrossEncoder(model_name, device=device, max_length=max_length)

    def rerank(
        self, query: str, chunks: list[Chunk], top_k: int = 5
    ) -> list[tuple[Chunk, float]]:
        if not chunks:
            return []
        # Note 4: We truncate each chunk text to 1000 characters (not tokens)
        # before passing it to the cross-encoder. This is a safety measure for
        # very long parent chunks where the full text would exceed max_length.
        pairs = [(query, chunk.text[:1000]) for chunk in chunks]
        scores = self.model.predict(pairs)
        # Note 5: scores is a numpy array of floats. zip(chunks, scores.tolist())
        # pairs each chunk with its relevance score. We sort descending (highest
        # score = most relevant) and return the top_k (k, chunk) pairs.
        scored = list(zip(chunks, scores.tolist()))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]
