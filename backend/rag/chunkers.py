import re
import uuid
import logging
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class Chunk:
    chunk_id: str
    text: str
    chunk_level: str          # "leaf" | "child" | "parent"
    parent_chunk_id: Optional[str]
    doc_type: str             # "income_tax_act"|"regulation"|"dtaa"|"user_doc"
    source_name: str
    chroma_collection: str
    metadata: dict = field(default_factory=dict)


class HierarchicalChunker:
    """Splits legal text into parent → child → leaf hierarchy."""

    def __init__(
        self,
        source_name: str,
        doc_type: str,
        chroma_collection_prefix: str,
        max_parent_tokens: int = 1800,
        max_leaf_tokens: int = 400,
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
        return int(len(text.split()) * 1.3)


class SemanticChunker:
    """Splits user-uploaded documents by structural markers and paragraphs."""

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
