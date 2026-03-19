from sentence_transformers import SentenceTransformer
# Note 1: sentence-transformers provides pre-trained models that map sentences
# to dense vector embeddings. Unlike word2vec (which gives per-word embeddings),
# sentence transformers produce a single fixed-size vector for the whole input,
# making it ideal for semantic similarity search.
import numpy as np
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# Note 2: BGE (BAAI General Embedding) models from BAAI include a special query
# prefix that improves retrieval quality. For asymmetric search (short query vs
# long passage), the query prefix helps the model distinguish "question to answer"
# from "passage to be searched" even though both are encoded by the same model.
BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


class Embedder:
    """Wrapper around BGE-small-en-v1.5 sentence transformer."""
    # Note 3: BGE-small-en-v1.5 is chosen because it is small (33M parameters)
    # and fast enough to run on CPU while still achieving near state-of-the-art
    # retrieval quality on financial/legal text. The 384-dimensional output is a
    # good balance between expressiveness and storage/search speed in ChromaDB.

    def __init__(
        self,
        model_name_or_path: str = "BAAI/bge-small-en-v1.5",
        device: str = "cuda",
        batch_size: int = 32,
    ):
        logger.info("Loading embedder model: %s on %s", model_name_or_path, device)
        self.model = SentenceTransformer(model_name_or_path, device=device)
        # Note 4: batch_size=32 means 32 texts are embedded together in one
        # forward pass through the model. Larger batches are more efficient on
        # GPU (better parallelism) but use more VRAM. 32 is safe for most GPUs.
        self.batch_size = batch_size
        self.dimensions = 384

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Batch embed texts. Returns list of float lists for ChromaDB."""
        # Note 5: normalize_embeddings=True makes all vectors unit-length (L2 norm
        # = 1). This is essential for cosine similarity search — without it, longer
        # documents would dominate search results simply by having larger magnitude.
        # convert_to_numpy=True ensures the output is a 2D numpy array before .tolist().
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
        # Note 6: The query prefix is prepended ONLY to query strings, not to
        # passage (document chunk) strings. This asymmetric encoding is a design
        # choice of BGE models — it improves retrieval accuracy compared to using
        # the same encoding for both queries and documents.
        prefixed = BGE_QUERY_PREFIX + query
        return self.embed_texts([prefixed])[0]
