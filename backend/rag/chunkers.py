import re
import uuid
import logging
from dataclasses import dataclass, field
# Note 1: 'dataclass' is a Python decorator that auto-generates __init__, __repr__,
# and __eq__ from class attributes. Using it for Chunk avoids writing 8+ parameter
# constructors by hand and makes the class self-documenting through its fields.
from typing import Optional
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class Chunk:
    # Note 2: Chunk is the core data unit in the RAG pipeline. Every piece of
    # text that gets embedded and stored in ChromaDB is a Chunk. The fields
    # capture both the text content and the provenance (where it came from),
    # which is needed for generating accurate source citations in responses.
    chunk_id: str
    text: str
    chunk_level: str          # "leaf" | "child" | "parent"
    # Note 3: The three-level hierarchy (parent/child/leaf) reflects legal document
    # structure: parent = section, child = subsection, leaf = clause/sentence.
    # This hierarchy is used in "parent promotion" — when a relevant leaf is found,
    # the retriever returns its parent for richer context around the matched clause.
    parent_chunk_id: Optional[str]
    doc_type: str             # "income_tax_act"|"regulation"|"dtaa"|"user_doc"
    source_name: str
    chroma_collection: str
    # Note 4: 'field(default_factory=dict)' creates a NEW empty dict for each
    # Chunk instance. Using a mutable default like 'metadata={}' directly would
    # share ONE dict across ALL instances — a classic Python gotcha with dataclasses.
    metadata: dict = field(default_factory=dict)


class HierarchicalChunker:
    """Splits legal text into parent → child → leaf hierarchy."""
    # Note 5: Legal documents (Income Tax Act, SEBI Regulations) have a strict
    # hierarchical structure: Chapter -> Section -> Subsection -> Clause.
    # This chunker mirrors that hierarchy so the retriever can surface either
    # a precise leaf clause or a broader parent section depending on the query.

    def __init__(
        self,
        source_name: str,
        doc_type: str,
        chroma_collection_prefix: str,
        max_parent_tokens: int = 1800,
        max_leaf_tokens: int = 400,
        # Note 6: 400 tokens per leaf keeps each chunk small enough for accurate
        # vector similarity — long chunks "dilute" the embedding with unrelated
        # sentences. Parent chunks at 1800 tokens give the model broader context
        # once a relevant leaf is found via parent promotion.
    ):
        self.source_name = source_name
        self.doc_type = doc_type
        self.chroma_collection_prefix = chroma_collection_prefix
        self.max_parent_tokens = max_parent_tokens
        self.max_leaf_tokens = max_leaf_tokens

    def chunk_document(self, text: str, metadata: dict = {}) -> list[Chunk]:
        chunks: list[Chunk] = []
        sections = self._split_into_sections(text)

        for header, body in sections:
            section_meta = {**metadata}
            parent = self._make_parent_chunk(header, body, section_meta)
            chunks.append(parent)

            subsections = self._split_into_subsections(body)
            for sub_header, sub_body in subsections:
                sub_meta = {**metadata}
                child = self._make_child_chunk(sub_header, sub_body, parent.chunk_id, sub_meta)
                chunks.append(child)

                clauses = self._split_into_clauses(sub_body)
                for clause_text in clauses:
                    clause_meta = {**metadata}
                    clause_meta["cross_references"] = self._extract_cross_references(clause_text)
                    leaf = self._make_leaf_chunk(clause_text, parent.chunk_id, child.chunk_id, clause_meta)
                    chunks.append(leaf)

        return chunks

    def _split_into_sections(self, text: str) -> list[tuple[str, str]]:
        # Note 7: These four regex patterns cover the main structural markers found
        # in Indian legal documents. The order matters — more specific patterns
        # (Section X) are listed before more general ones (numbered headings) to
        # avoid false matches from numbered paragraphs inside section bodies.
        patterns = [
            re.compile(r'^(Section\s+\d+[A-Z]?\s*[\.\-\u2013]?\s+\w[\w\s,]+)', re.MULTILINE),
            re.compile(r'^(Regulation\s+\d+[\.\(])', re.MULTILINE),
            re.compile(r'^(CHAPTER\s+[IVXLC\d]+|PART\s+[IVXLC\d A-Z]+)', re.MULTILINE),
            re.compile(r'^(\d+[\.\)]\s+[A-Z][A-Za-z\s]{5,50})$', re.MULTILINE),
        ]

        boundaries: list[tuple[int, str]] = []
        for pat in patterns:
            for m in pat.finditer(text):
                boundaries.append((m.start(), m.group(1)))

        if not boundaries:
            return [(self.source_name, text)]

        boundaries.sort(key=lambda x: x[0])
        sections: list[tuple[str, str]] = []
        for i, (pos, header) in enumerate(boundaries):
            next_pos = boundaries[i + 1][0] if i + 1 < len(boundaries) else len(text)
            body = text[pos + len(header):next_pos].strip()
            sections.append((header.strip(), body))

        return sections if sections else [(self.source_name, text)]

    def _split_into_subsections(self, text: str) -> list[tuple[str, str]]:
        pattern = re.compile(
            r'^(\(\d+\)\s|\([a-z]\)\s|\([ivx]+\)\s)',
            re.MULTILINE,
        )
        boundaries: list[tuple[int, str]] = []
        for m in pattern.finditer(text):
            boundaries.append((m.start(), m.group(0)))

        if not boundaries:
            return [("", text)]

        subsections: list[tuple[str, str]] = []
        for i, (pos, header) in enumerate(boundaries):
            next_pos = boundaries[i + 1][0] if i + 1 < len(boundaries) else len(text)
            body = text[pos + len(header):next_pos].strip()
            subsections.append((header.strip(), body))

        return subsections if subsections else [("", text)]

    def _split_into_clauses(self, text: str) -> list[str]:
        if len(text) < 100:
            return [text]
        markers = [
            "Provided further that",
            "Provided that",
            "EXPLANATION",
            "Explanation.\u2014",
            "Explanation",
        ]
        result: list[str] = []
        remaining = text
        for marker in markers:
            parts = remaining.split(marker)
            if len(parts) > 1:
                result.append(parts[0].strip())
                remaining = (" " + marker + " ").join(parts[1:])
        result.append(remaining.strip())
        return [c for c in result if c]

    def _make_parent_chunk(self, header: str, body: str, section_meta: dict) -> Chunk:
        cid = f"parent_{uuid.uuid4().hex[:8]}"
        return Chunk(
            chunk_id=cid,
            text=(header + "\n" + body).strip(),
            chunk_level="parent",
            parent_chunk_id=None,
            doc_type=self.doc_type,
            source_name=self.source_name,
            chroma_collection=f"{self.chroma_collection_prefix}_parents",
            metadata=section_meta,
        )

    def _make_child_chunk(self, sub_header: str, sub_body: str, parent_id: str, sub_meta: dict) -> Chunk:
        cid = f"child_{uuid.uuid4().hex[:8]}"
        return Chunk(
            chunk_id=cid,
            text=(sub_header + " " + sub_body).strip(),
            chunk_level="child",
            parent_chunk_id=parent_id,
            doc_type=self.doc_type,
            source_name=self.source_name,
            chroma_collection=f"{self.chroma_collection_prefix}_leaves",
            metadata=sub_meta,
        )

    def _make_leaf_chunk(self, clause_text: str, parent_id: str, child_id: str, clause_meta: dict) -> Chunk:
        cid = f"leaf_{uuid.uuid4().hex[:8]}"
        return Chunk(
            chunk_id=cid,
            text=clause_text.strip(),
            chunk_level="leaf",
            parent_chunk_id=parent_id,
            doc_type=self.doc_type,
            source_name=self.source_name,
            chroma_collection=f"{self.chroma_collection_prefix}_leaves",
            metadata=clause_meta,
        )

    def _extract_cross_references(self, text: str) -> list[str]:
        pattern = re.compile(r'[Ss]ection\s+(\d+[A-Z]?(?:\(\d+\))?)')
        return list(set(pattern.findall(text)))

    def _estimate_tokens(self, text: str) -> int:
        # Note 10: Rough token count: words * 1.3 is a common approximation
        # for English text with BPE sub-word tokenization. This avoids loading
        # the full tiktoken encoder just for size estimation, keeping ingestion fast.
        return int(len(text.split()) * 1.3)


class SemanticChunker:
    """Splits user-uploaded documents by structural markers and paragraphs."""
    # Note 8: Unlike HierarchicalChunker (for known regulatory documents),
    # SemanticChunker handles arbitrary user uploads — balance sheets, reports,
    # contracts. It detects headings heuristically and falls back to paragraph
    # splitting. The 'overlap' parameter carries the last N words of one chunk
    # into the next to preserve context across chunk boundaries.

    def __init__(self, chunk_size: int = 512, overlap: int = 64):
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk_document(
        self,
        text: str,
        filename: str,
        session_id: str,
        doc_id: str,
    ) -> list[Chunk]:
        chunks: list[Chunk] = []
        collection = f"user_{doc_id}"

        # Detect structural sections
        heading_pat = re.compile(
            r'^(?:[A-Z][A-Z\s]{3,}|(?:\d+\.\s+[A-Z][^\n]{0,60}))\s*$',
            re.MULTILINE,
        )
        boundaries = [(m.start(), m.group(0)) for m in heading_pat.finditer(text)]

        if not boundaries:
            sections = [("", text)]
        else:
            sections: list[tuple[str, str]] = []
            for i, (pos, heading) in enumerate(boundaries):
                next_pos = boundaries[i + 1][0] if i + 1 < len(boundaries) else len(text)
                body = text[pos + len(heading):next_pos].strip()
                sections.append((heading.strip(), body))

        for section_heading, section_text in sections:
            # Detect tables (lines with | or tab separators)
            # Note 9: Tables are emitted as a single chunk rather than being split
            # by the paragraph chunker. This keeps table rows together — splitting
            # a table mid-row would produce meaningless chunks that confuse the model.
            lines = section_text.split("\n")
            table_lines: list[str] = []
            prose_lines: list[str] = []
            for line in lines:
                if "|" in line or "\t" in line:
                    table_lines.append(line)
                else:
                    prose_lines.append(line)

            # Emit table as single chunk
            if table_lines:
                table_text = "\n".join(table_lines).strip()
                if table_text:
                    chunks.append(Chunk(
                        chunk_id=f"leaf_{uuid.uuid4().hex[:8]}",
                        text=table_text,
                        chunk_level="leaf",
                        parent_chunk_id=None,
                        doc_type="user_doc",
                        source_name=filename,
                        chroma_collection=collection,
                        metadata={
                            "filename": filename,
                            "section_heading": section_heading,
                            "chunk_type": "table",
                            "upload_session_id": session_id,
                        },
                    ))

            # Split prose by paragraphs
            prose_text = "\n".join(prose_lines)
            paragraphs = [p.strip() for p in re.split(r'\n\s*\n', prose_text) if p.strip()]

            prev_tail: list[str] = []
            for para in paragraphs:
                para_tokens = self._estimate_tokens(para)
                if para_tokens <= self.chunk_size:
                    # Add overlap from previous
                    combined = (" ".join(prev_tail) + " " + para).strip()
                    chunks.append(Chunk(
                        chunk_id=f"leaf_{uuid.uuid4().hex[:8]}",
                        text=combined,
                        chunk_level="leaf",
                        parent_chunk_id=None,
                        doc_type="user_doc",
                        source_name=filename,
                        chroma_collection=collection,
                        metadata={
                            "filename": filename,
                            "section_heading": section_heading,
                            "chunk_type": "text",
                            "upload_session_id": session_id,
                        },
                    ))
                    # Store tail for next overlap
                    words = para.split()
                    prev_tail = words[-self.overlap:] if len(words) > self.overlap else words
                else:
                    # Split by sentences
                    sentences = re.split(r'(?<=\. )', para)
                    current: list[str] = list(prev_tail)
                    for sent in sentences:
                        current.append(sent)
                        if self._estimate_tokens(" ".join(current)) >= self.chunk_size:
                            chunk_text = " ".join(current).strip()
                            chunks.append(Chunk(
                                chunk_id=f"leaf_{uuid.uuid4().hex[:8]}",
                                text=chunk_text,
                                chunk_level="leaf",
                                parent_chunk_id=None,
                                doc_type="user_doc",
                                source_name=filename,
                                chroma_collection=collection,
                                metadata={
                                    "filename": filename,
                                    "section_heading": section_heading,
                                    "chunk_type": "text",
                                    "upload_session_id": session_id,
                                },
                            ))
                            all_words = chunk_text.split()
                            current = all_words[-self.overlap:]
                    if current:
                        chunk_text = " ".join(current).strip()
                        if chunk_text:
                            chunks.append(Chunk(
                                chunk_id=f"leaf_{uuid.uuid4().hex[:8]}",
                                text=chunk_text,
                                chunk_level="leaf",
                                parent_chunk_id=None,
                                doc_type="user_doc",
                                source_name=filename,
                                chroma_collection=collection,
                                metadata={
                                    "filename": filename,
                                    "section_heading": section_heading,
                                    "chunk_type": "text",
                                    "upload_session_id": session_id,
                                },
                            ))
                        prev_tail = []

        return chunks

    def _estimate_tokens(self, text: str) -> int:
        return int(len(text.split()) * 1.3)
