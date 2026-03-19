from rank_bm25 import BM25Okapi
# Note 1: BM25Okapi is the "Okapi BM25" variant, the industry-standard keyword
# ranking formula. It scores documents against a query by combining term frequency
# (how often the query word appears in the document) with inverse document frequency
# (how rare the word is across all documents), plus length normalisation.
import pickle
# Note 2: pickle serialises Python objects to binary files. BM25Okapi indices and
# the chunk maps are saved as .pkl files so they persist between server restarts.
# Security warning: never unpickle files from untrusted sources — pickle can
# execute arbitrary Python code during deserialization (a known attack vector).
# For Samvad, pickle files are generated internally by index_corpus.py and stored
# in a server-controlled directory, so the trust boundary is maintained.
# Future enhancement: consider msgpack or JSON serialisation for better portability.
import logging
import re
from pathlib import Path
from backend.rag.chunkers import Chunk

logger = logging.getLogger(__name__)


class BM25Index:
    """Build and query BM25 keyword index. Persists to disk as pickle."""
    # Note 3: This class maintains TWO parallel dicts keyed by collection name:
    # - self.indices     : the BM25Okapi index object (contains term statistics)
    # - self.chunk_maps  : the list of Chunk objects in the same order as the corpus
    # The chunk_map is needed to return Chunk objects (not just text scores) from queries.

    def __init__(self, index_dir: str = "runtime/bm25_index"):
        self.index_dir = Path(index_dir)
        self.indices: dict[str, BM25Okapi] = {}
        self.chunk_maps: dict[str, list[Chunk]] = {}

    def build_for_collection(
        self, collection_name: str, chunks: list[Chunk]
    ) -> None:
        corpus = [self._tokenise(c.text) for c in chunks]
        index = BM25Okapi(corpus)
        self.indices[collection_name] = index
        self.chunk_maps[collection_name] = chunks
        self._save(collection_name)
        logger.info("BM25 built: %s (%d chunks)", collection_name, len(chunks))

    def query(
        self, query_text: str, collection_name: str, top_k: int = 10
    ) -> list[tuple[Chunk, float]]:
        if collection_name not in self.indices:
            # Note 4: Lazy loading — if the index is not in memory, try loading it
            # from disk. This handles the case where a user doc was indexed in a
            # previous server run and its pickle file exists but wasn't loaded at
            # startup (only the corpus indices are loaded at startup via load_all()).
            loaded = self._load(collection_name)
            if not loaded:
                return []
        tokens = self._tokenise(query_text)
        scores = self.indices[collection_name].get_scores(tokens)
        # Note 5: sorted() with a lambda key is a Pythonic way to get the top-K
        # indices by score. We filter out scores <= 0 to avoid returning chunks
        # with no keyword overlap at all — zero-score matches add noise.
        top_indices = sorted(
            range(len(scores)), key=lambda i: scores[i], reverse=True
        )[:top_k]
        return [
            (self.chunk_maps[collection_name][i], float(scores[i]))
            for i in top_indices
            if scores[i] > 0
        ]

    def query_multiple(
        self,
        query_text: str,
        collection_names: list[str],
        top_k: int = 10,
    ) -> list[tuple[Chunk, float]]:
        all_results: list[tuple[Chunk, float]] = []
        for name in collection_names:
            all_results.extend(self.query(query_text, name, top_k))
        all_results.sort(key=lambda x: x[1], reverse=True)
        return all_results[:top_k]

    def load_all(self) -> None:
        if not self.index_dir.exists():
            logger.info("BM25 index dir does not exist: %s", self.index_dir)
            return
        count = 0
        for pkl_path in self.index_dir.glob("*.pkl"):
            collection_name = pkl_path.stem
            if self._load(collection_name):
                count += 1
        logger.info("BM25 loaded %d indices from %s", count, self.index_dir)

    def _tokenise(self, text: str) -> list[str]:
        text = text.lower()
        # Remove punctuation except hyphens, forward slashes, digits, parentheses
        # Note 6: We PRESERVE hyphens (80-C, tax-free), slashes (80C/80D), and
        # parentheses because Indian finance terms often include them as part of
        # the section number or financial metric name (e.g. "Section 10(13A)").
        text = re.sub(r"[^\w\s\-/()]", " ", text)
        tokens = text.split()
        # Note 7: Filtering tokens shorter than 2 characters removes single-letter
        # noise (e.g. "a", "I") that has high document frequency and low information
        # value in BM25 scoring. This is a lightweight alternative to stopword removal.
        return [t for t in tokens if len(t) >= 2]

    def _save(self, collection_name: str) -> None:
        self.index_dir.mkdir(parents=True, exist_ok=True)
        path = self.index_dir / f"{collection_name}.pkl"
        with open(path, "wb") as f:
            pickle.dump(
                {
                    "index": self.indices[collection_name],
                    "chunks": self.chunk_maps[collection_name],
                },
                f,
            )

    def _load(self, collection_name: str) -> bool:
        path = self.index_dir / f"{collection_name}.pkl"
        if not path.exists():
            return False
        with open(path, "rb") as f:
            data = pickle.load(f)
        self.indices[collection_name] = data["index"]
        self.chunk_maps[collection_name] = data["chunks"]
        return True
