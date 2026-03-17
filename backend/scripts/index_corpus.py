"""
ONE-TIME script: parse corpus PDFs → chunk → embed → store in ChromaDB + BM25.

Usage:
    python backend/scripts/index_corpus.py
    python backend/scripts/index_corpus.py --source income_tax_act
    python backend/scripts/index_corpus.py --force
    python backend/scripts/index_corpus.py --dry-run
"""

import sys
import os
import asyncio
import argparse
import logging
from pathlib import Path
from datetime import datetime, timezone

# Allow running as a standalone script from the project root
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import yaml
import chromadb
import pdfplumber
from tqdm import tqdm

from backend.rag.chunkers import HierarchicalChunker
from backend.rag.embedder import Embedder
from backend.rag.bm25_index import BM25Index
from backend.db.db_client import DBClient

logger = logging.getLogger("index_corpus")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def _parse_pdf(path: str) -> str:
    parts: list[str] = []
    with pdfplumber.open(path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            parts.append(f"\n[Page {page_num}]\n")
            text = page.extract_text() or ""
            parts.append(text)
            for table in (page.extract_tables() or []):
                rows = ["|" + "|".join(str(c or "") for c in row) + "|" for row in table]
                parts.append("\n".join(rows))
    return "\n".join(parts)


SOURCE_DIR_MAP: dict[str, str] = {
    "income_tax_act": "data/corpus/income_tax_act_2025",
    "sebi":           "data/corpus/sebi_regulations",
    "fema":           "data/corpus/fema",
    "dtaa":           "data/corpus/dtaa",
    "companies_act":  "data/corpus/companies_act",
}


async def index_source(
    source_key: str,
    source_cfg: dict,
    chroma_client: chromadb.Client,
    embedder: Embedder,
    bm25: BM25Index,
    db: DBClient,
    force: bool = False,
    dry_run: bool = False,
) -> None:
    source_name = source_cfg["name"]
    doc_type = source_cfg["type"]
    chroma_leaf = source_cfg["chroma_leaf"]
    chroma_parent = source_cfg["chroma_parent"]
    regulator = source_cfg.get("regulator", "")
    source_dir = Path(SOURCE_DIR_MAP.get(source_key, f"data/corpus/{source_key}"))

    if not source_dir.exists():
        logger.warning("Source dir not found: %s — skipping", source_dir)
        return

    # Check if already indexed
    if not force:
        row = await db.fetchone(
            "SELECT index_status FROM corpus_index WHERE source_name=? AND index_status='active'",
            (source_name,),
        )
        if row:
            logger.info("Already indexed: %s — use --force to re-index", source_name)
            return

    pdf_files = list(source_dir.glob("**/*.pdf"))
    if not pdf_files:
        logger.warning("No PDFs found in %s", source_dir)
        return

    all_leaf_chunks = []
    all_parent_chunks = []
    total_start = datetime.now(timezone.utc)

    for pdf_path in tqdm(pdf_files, desc=source_name):
        try:
            text = _parse_pdf(str(pdf_path))
        except Exception as exc:
            logger.warning("Failed to parse %s: %s", pdf_path.name, exc)
            continue

        chunker = HierarchicalChunker(
            source_name=source_name,
            doc_type=doc_type,
            chroma_collection_prefix=chroma_leaf.replace("_leaves", ""),
        )
        chunks = chunker.chunk_document(text, metadata={"source_file": pdf_path.name})
        leaves = [c for c in chunks if c.chunk_level in ("leaf", "child")]
        parents = [c for c in chunks if c.chunk_level == "parent"]
        all_leaf_chunks.extend(leaves)
        all_parent_chunks.extend(parents)

    if dry_run:
        logger.info(
            "[DRY RUN] %s — leaf chunks: %d, parent chunks: %d",
            source_name, len(all_leaf_chunks), len(all_parent_chunks),
        )
        return

    if not all_leaf_chunks:
        logger.warning("No chunks generated for %s", source_name)
        return

    # Embed leaves in batches and add to ChromaDB
    leaf_col = chroma_client.get_or_create_collection(chroma_leaf)
    logger.info("Embedding %d leaf chunks for %s ...", len(all_leaf_chunks), source_name)
    batch_size = 500
    for i in tqdm(range(0, len(all_leaf_chunks), batch_size), desc=f"{source_name} embed leaves"):
        batch = all_leaf_chunks[i : i + batch_size]
        embeddings = embedder.embed_texts([c.text for c in batch])
        leaf_col.add(
            ids=[c.chunk_id for c in batch],
            embeddings=embeddings,
            documents=[c.text for c in batch],
            metadatas=[{**c.metadata,
                        "chunk_id": c.chunk_id,
                        "chunk_level": c.chunk_level,
                        "parent_chunk_id": c.parent_chunk_id or "",
                        "doc_type": c.doc_type,
                        "source_name": c.source_name} for c in batch],
        )

    # Store parent chunks in ChromaDB (with embeddings for potential retrieval)
    if all_parent_chunks:
        parent_col = chroma_client.get_or_create_collection(chroma_parent)
        logger.info("Embedding %d parent chunks for %s ...", len(all_parent_chunks), source_name)
        for i in tqdm(range(0, len(all_parent_chunks), batch_size), desc=f"{source_name} embed parents"):
            batch = all_parent_chunks[i : i + batch_size]
            embeddings = embedder.embed_texts([c.text for c in batch])
            parent_col.add(
                ids=[c.chunk_id for c in batch],
                embeddings=embeddings,
                documents=[c.text for c in batch],
                metadatas=[{**c.metadata,
                            "chunk_id": c.chunk_id,
                            "chunk_level": c.chunk_level,
                            "parent_chunk_id": c.parent_chunk_id or "",
                            "doc_type": c.doc_type,
                            "source_name": c.source_name} for c in batch],
            )

    # Build BM25 index for leaves
    bm25.build_for_collection(chroma_leaf, all_leaf_chunks)

    # Upsert into corpus_index table
    now = datetime.now(timezone.utc).isoformat()
    elapsed = (datetime.now(timezone.utc) - total_start).total_seconds()
    await db.execute(
        """INSERT INTO corpus_index
               (source_name, source_type, regulator, chunk_count,
                embedding_model, chroma_collection, index_status, indexed_at)
           VALUES (?, ?, ?, ?, ?, ?, 'active', ?)
           ON CONFLICT(source_name) DO UPDATE SET
               chunk_count=excluded.chunk_count,
               embedding_model=excluded.embedding_model,
               chroma_collection=excluded.chroma_collection,
               index_status='active',
               indexed_at=excluded.indexed_at""",
        (source_name, doc_type, regulator, len(all_leaf_chunks),
         "bge-small-en-v1.5", chroma_leaf, now),
    )

    logger.info(
        "Indexed %s — %d leaf chunks, %d parents, %.1fs",
        source_name, len(all_leaf_chunks), len(all_parent_chunks), elapsed,
    )


async def main() -> None:
    parser = argparse.ArgumentParser(description="Index corpus PDFs into ChromaDB and BM25")
    parser.add_argument("--source", help="Only index this source key (e.g. income_tax_act)")
    parser.add_argument("--force", action="store_true", help="Re-index even if already indexed")
    parser.add_argument("--dry-run", action="store_true", help="Count chunks without writing")
    args = parser.parse_args()

    # Load config
    config_path = Path("config/samvad.yaml")
    with open(config_path) as f:
        config = yaml.safe_load(f)

    corpus_cfg = config.get("corpus", {}).get("collections", {})
    rag_cfg = config.get("rag", {})
    emb_cfg = config.get("embedding", {})

    # Initialise ChromaDB
    chroma_path = os.environ.get("CHROMA_PATH", "runtime/chromadb")
    chroma_client = chromadb.PersistentClient(path=chroma_path)

    # Initialise Embedder
    model_path = os.environ.get("EMBEDDING_MODEL_PATH", emb_cfg.get("model", "BAAI/bge-small-en-v1.5"))
    device = os.environ.get("EMBEDDING_DEVICE", "cuda")
    embedder = Embedder(
        model_name_or_path=model_path,
        device=device,
        batch_size=emb_cfg.get("batch_size", 32),
    )

    # Initialise BM25Index
    bm25 = BM25Index(index_dir=os.environ.get("BM25_INDEX_PATH", "runtime/bm25_index"))

    # Initialise DB
    db_path = os.environ.get("SQLITE_PATH", "runtime/sqlite/samvad.db")
    db = DBClient(db_path=db_path)
    await db.connect()
    await db.init_schema()

    try:
        sources_to_index = (
            {args.source: corpus_cfg[args.source]}
            if args.source and args.source in corpus_cfg
            else corpus_cfg
        )

        for source_key, source_cfg in tqdm(sources_to_index.items(), desc="Overall"):
            await index_source(
                source_key, source_cfg, chroma_client, embedder, bm25, db,
                force=args.force, dry_run=args.dry_run,
            )
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
