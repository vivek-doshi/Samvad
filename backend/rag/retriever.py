import chromadb
import asyncio
import logging
# Note 1: These imports bring together all four retrieval components:
# Embedder   — converts text to vectors for semantic (meaning-based) search
# BM25Index  — keyword-based search using the BM25Okapi algorithm
# Reranker   — cross-encoder that scores (query, chunk) pairs for precision
# QueryExpander — expands finance abbreviations to improve recall
from backend.rag.chunkers import Chunk
from backend.rag.embedder import Embedder
from backend.rag.bm25_index import BM25Index
from backend.rag.reranker import Reranker
from backend.rag.query_expander import QueryExpander

logger = logging.getLogger(__name__)

# Note 2: DOMAIN_COLLECTIONS maps the query domain (determined by QueryRouter)
# to the ChromaDB collection names to search. This is the "retrieval scope" —
# a tax query only searches income tax collections; a general query searches all.
# "user_docs" is a placeholder — the actual collection names are per-document
# UUIDs (e.g. "user_abc123") resolved at query time from session_documents table.
DOMAIN_COLLECTIONS: dict[str, list[str]] = {
    "tax":        ["it_act_2025_leaves", "it_act_2025_parents"],
    "equity":     ["user_docs"],
    "risk":       ["user_docs", "it_act_2025_leaves"],
    "doc":        ["user_docs"],
    "general":    [
        "it_act_2025_leaves", "sebi_regulations_leaves",
        "fema_leaves", "companies_act_leaves",
    ],
    "regulatory": [
        "sebi_regulations_leaves", "fema_leaves",
        "dtaa_leaves", "companies_act_leaves",
    ],
}


class Retriever:
    """Orchestrates: vector search + BM25 → RRF fusion → rerank → parent promotion."""
    # Note 3: This class is the heart of the RAG (Retrieval-Augmented Generation)
    # pipeline. RAG works by finding relevant passages from a knowledge base and
    # injecting them into the LLM prompt. The multi-stage pipeline here maximises
    # both RECALL (finding all relevant passages) and PRECISION (returning only the
    # most relevant ones). Each stage:
    # 1. Expand query  — add finance synonyms for better recall
    # 2. Retrieve      — cast wide net: vector + BM25, across multiple collections
    # 3. Fuse          — RRF merges two ranked lists into one without score normalisation
    # 4. Rerank        — cross-encoder gives a more accurate relevance score
    # 5. Promote       — return parent chunks for richer LLM context

    def __init__(
        self,
        chroma_client: chromadb.Client,
        embedder: Embedder,
        bm25: BM25Index,
        reranker: Reranker,
        expander: QueryExpander,
        top_k_retrieval: int = 10,
        top_k_rerank: int = 5,
        rrf_k: int = 60,
    ):
        self.chroma_client = chroma_client
        self.embedder = embedder
        self.bm25 = bm25
        self.reranker = reranker
        self.expander = expander
        self.top_k_retrieval = top_k_retrieval
        self.top_k_rerank = top_k_rerank
        self.rrf_k = rrf_k

    async def retrieve(
        self,
        query: str,
        domain: str,
        session_id: str | None = None,
        user_doc_collections: list[str] = [],
    ) -> list[Chunk]:
        # STEP 1 — Query expansion
        expanded = self.expander.expand(query)
        section_refs = self.expander.extract_section_numbers(query)

        # STEP 2 — Determine collections
        base_collections = DOMAIN_COLLECTIONS.get(domain, DOMAIN_COLLECTIONS["general"])
        if user_doc_collections:
            expanded_base = [c for c in base_collections if c != "user_docs"]
            collections = expanded_base + user_doc_collections
        else:
            collections = [c for c in base_collections if c != "user_docs"]

        # STEP 3 — Parallel vector + BM25 retrieval
        # Note 4: asyncio.gather() runs both searches concurrently. Vector search
        # in ChromaDB is I/O-bound (a DB call), so it benefits from async.
        # BM25 is CPU-bound (pure Python computation), so it runs in a thread pool
        # via asyncio.to_thread() to avoid blocking the async event loop.
        vector_results, bm25_results = await asyncio.gather(
            self._vector_search(expanded, collections, self.top_k_retrieval),
            asyncio.to_thread(self._bm25_search, expanded, collections, self.top_k_retrieval),
        )

        # STEP 4 — Definitions boost for tax + section refs
        if "tax" in domain and section_refs:
            boost_chunks = self._get_sections_by_number(section_refs)
            if boost_chunks:
                # Prepend boosted chunks at high rank positions
                boosted = [(c, 1.0, 0) for c in boost_chunks]
                vector_results = boosted + vector_results
                bm25_results = [(c, 1.0) for c in boost_chunks] + bm25_results

        # STEP 5 — Reciprocal Rank Fusion
        # Note 5: RRF (Reciprocal Rank Fusion) is a simple but effective technique
        # for combining two ranked lists. Each item's score is 1/(k + rank), where
        # k=60 is a constant that dampens rank differences. RRF outperforms score-
        # based fusion because it doesn't require normalising scores from different
        # retrieval systems (vector distances and BM25 scores are not comparable).
        fused = self._rrf(vector_results, bm25_results, k=self.rrf_k)

        # STEP 6 — Rerank in thread pool (CPU bound)
        # Note 6: run_in_executor(None, ...) runs the blocking function in the
        # default thread pool executor. The lambda captures 'fused' from the outer
        # scope and passes it to rerank(). This pattern is the standard way to
        # call synchronous CPU-bound code from async code without blocking the loop.
        loop = asyncio.get_event_loop()
        reranked = await loop.run_in_executor(
            None,
            lambda: self.reranker.rerank(query, fused, self.top_k_rerank),
        )

        # STEP 7 — Parent promotion
        return self._promote_to_parent([chunk for chunk, _ in reranked])

    async def _vector_search(
        self, query: str, collections: list[str], top_k: int
    ) -> list[tuple[Chunk, float, int]]:
        embedding = self.embedder.embed_query(query)
        results: list[tuple[Chunk, float, int]] = []
        for collection_name in collections:
            try:
                col = self.chroma_client.get_collection(collection_name)
                res = col.query(
                    query_embeddings=[embedding],
                    n_results=top_k,
                    include=["documents", "metadatas", "distances"],
                )
                docs = res["documents"][0] if res["documents"] else []
                metas = res["metadatas"][0] if res["metadatas"] else []
                dists = res["distances"][0] if res["distances"] else []
                for rank, (doc, meta, dist) in enumerate(zip(docs, metas, dists)):
                    chunk = Chunk(
                        chunk_id=meta.get("chunk_id", f"vec_{rank}"),
                        text=doc,
                        chunk_level=meta.get("chunk_level", "leaf"),
                        parent_chunk_id=meta.get("parent_chunk_id"),
                        doc_type=meta.get("doc_type", ""),
                        source_name=meta.get("source_name", ""),
                        chroma_collection=collection_name,
                        metadata=dict(meta),
                    )
                    results.append((chunk, 1.0 - float(dist), rank))
            except Exception as exc:
                logger.warning("Vector search failed for %s: %s", collection_name, exc)
                continue
        results.sort(key=lambda x: x[1], reverse=True)
        return results

    def _bm25_search(
        self, query: str, collections: list[str], top_k: int
    ) -> list[tuple[Chunk, float]]:
        results: list[tuple[Chunk, float]] = []
        for name in collections:
            results.extend(self.bm25.query(query, name, top_k))
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    def _rrf(
        self,
        vector_results: list[tuple[Chunk, float, int]],
        bm25_results: list[tuple[Chunk, float]],
        k: int = 60,
    ) -> list[Chunk]:
        # Note 7: RRF works by accumulating 1/(k+rank) scores for each chunk ID
        # across both ranked lists. A chunk that appears in BOTH lists (top of
        # vector search AND top of BM25) gets double credit and rises to the top.
        # The k parameter (60) prevents top-1 results from dominating too strongly.
        # Reference: Cormack, Clarke, Buettcher (2009) — "Reciprocal Rank Fusion
        # outperforms Condorcet and individual Rank Learning Methods" — SIGIR 2009.
        scores: dict[str, float] = {}
        chunk_map: dict[str, Chunk] = {}

        for rank, (chunk, _, _) in enumerate(vector_results):
            scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0.0) + 1.0 / (k + rank + 1)
            chunk_map[chunk.chunk_id] = chunk

        for rank, (chunk, _) in enumerate(bm25_results):
            scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0.0) + 1.0 / (k + rank + 1)
            chunk_map[chunk.chunk_id] = chunk

        sorted_ids = sorted(scores.keys(), key=lambda cid: scores[cid], reverse=True)
        return [chunk_map[cid] for cid in sorted_ids[: self.top_k_retrieval]]

    def _promote_to_parent(self, chunks: list[Chunk]) -> list[Chunk]:
        # Note 8: Parent promotion improves response quality by returning broader
        # context around a matched leaf chunk. If a leaf about "Section 80C proviso"
        # matches the query, we return the full "Section 80C" parent chunk to the LLM
        # so it has the complete statutory context, not just the isolated proviso.
        promoted: dict[str, Chunk] = {}
        for chunk in chunks:
            if chunk.chunk_level in ("leaf", "child") and chunk.parent_chunk_id:
                parent_id = chunk.parent_chunk_id
                if parent_id in promoted:
                    continue
                # Try to fetch parent from ChromaDB
                parent_collection = chunk.chroma_collection.replace("_leaves", "_parents")
                try:
                    col = self.chroma_client.get_collection(parent_collection)
                    res = col.get(ids=[parent_id], include=["documents", "metadatas"])
                    if res["documents"]:
                        meta = res["metadatas"][0]
                        parent_chunk = Chunk(
                            chunk_id=parent_id,
                            text=res["documents"][0],
                            chunk_level="parent",
                            parent_chunk_id=None,
                            doc_type=meta.get("doc_type", ""),
                            source_name=meta.get("source_name", ""),
                            chroma_collection=parent_collection,
                            metadata=dict(meta),
                        )
                        promoted[parent_id] = parent_chunk
                        continue
                except Exception:
                    pass
                # Fallback: use the leaf itself
                promoted[chunk.chunk_id] = chunk
            else:
                promoted[chunk.chunk_id] = chunk

        return list(promoted.values())

    def _get_sections_by_number(self, section_refs: list[str]) -> list[Chunk]:
        results: list[Chunk] = []
        for col_name in ["it_act_2025_leaves", "it_act_2025_parents"]:
            try:
                col = self.chroma_client.get_collection(col_name)
                res = col.get(
                    where={"section_number": {"$in": section_refs}},
                    include=["documents", "metadatas"],
                )
                for doc, meta in zip(res["documents"], res["metadatas"]):
                    results.append(Chunk(
                        chunk_id=meta.get("chunk_id", ""),
                        text=doc,
                        chunk_level=meta.get("chunk_level", "leaf"),
                        parent_chunk_id=meta.get("parent_chunk_id"),
                        doc_type=meta.get("doc_type", ""),
                        source_name=meta.get("source_name", ""),
                        chroma_collection=col_name,
                        metadata=dict(meta),
                    ))
            except Exception:
                continue
        return results
