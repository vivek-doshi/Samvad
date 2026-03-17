from sentence_transformers import SentenceTransformer
import numpy as np
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


class Embedder:
    """Wrapper around BGE-small-en-v1.5 sentence transformer."""

    def __init__(
        self,
        model_name_or_path: str = "BAAI/bge-small-en-v1.5",
        device: str = "cuda",
        batch_size: int = 32,
    ):
        logger.info("Loading embedder model: %s on %s", model_name_or_path, device)
        self.model = SentenceTransformer(model_name_or_path, device=device)
        self.batch_size = batch_size
        self.dimensions = 384

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Batch embed texts. Returns list of float lists for ChromaDB."""
        embeddings = self.model.encode(
            texts,
            batch_size=self.batch_size,
            show_progress_bar=len(texts) > 100,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        return embeddings.tolist()

    def embed_query(self, query: str) -> list[float]:
        """Embed a single query with BGE query prefix."""
        prefixed = BGE_QUERY_PREFIX + query
        return self.embed_texts([prefixed])[0]
