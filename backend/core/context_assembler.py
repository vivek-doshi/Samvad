import json
import logging
from backend.core.token_manager import TokenManager
from backend.prompts.assembler import PromptAssembler
from backend.rag.chunkers import Chunk

logger = logging.getLogger(__name__)


class ContextAssembler:
    """
    Assembles the final prompt sent to Arthvidya.
    Combines: system prompt + session summary + history +
              retrieved chunks + current query.
    Respects the 32K token budget from TokenManager.
    """

    def __init__(
        self,
        token_manager: TokenManager,
        prompt_assembler: PromptAssembler,
    ):
        self.token_manager = token_manager
        self.prompt_assembler = prompt_assembler

    def assemble(
        self,
        query: str,
        domain: str,
        retrieved_chunks: list[Chunk],
        session_summary: str | None,
        history_turns: list[dict],
        session_id: str | None = None,
    ) -> tuple[list[dict], dict]:
        """Returns (messages_list, budget_breakdown)."""

        # STEP 1 — Build system prompt
        system_prompt = self.prompt_assembler.build(domain)

        # STEP 2 — Format retrieved chunks as context string
        context_str = self._format_chunks(retrieved_chunks)

        # STEP 3 — Build session summary string
        summary_str = session_summary or ""

        # STEP 4 — Allocate token budget
        budget = self.token_manager.allocate_budget(
            system_prompt=system_prompt,
            session_summary=summary_str,
            history_turns=history_turns,
            retrieved_chunks=[c.text for c in retrieved_chunks],
            query=query,
        )

        # STEP 5 — Assemble messages
        messages: list[dict] = [
            {"role": "system", "content": budget["system_prompt"]},
        ]

        if budget.get("session_summary"):
            messages.append({
                "role": "system",
                "content": f"[PRIOR CONTEXT]\n{budget['session_summary']}",
            })

        for turn in budget.get("history_turns", []):
            messages.append({"role": turn["role"], "content": turn["content"]})

        if budget.get("retrieved_chunks"):
            context_block = self._format_chunks_for_prompt(budget["retrieved_chunks"])
            messages.append({
                "role": "system",
                "content": f"[REFERENCE CONTEXT]\n{context_block}",
            })

        messages.append({"role": "user", "content": query})

        return messages, budget.get("budget_breakdown", {})

    def _format_chunks(self, chunks: list[Chunk]) -> str:
        parts: list[str] = []
        for chunk in chunks:
            meta = chunk.metadata
            source = chunk.source_name
            section = meta.get("section_number", "")
            page = meta.get("page_number", "")
            tag = f'<context source="{source}"'
            if section:
                tag += f' section="{section}"'
            if page:
                tag += f' page="{page}"'
            tag += ">"
            parts.append(f"{tag}\n{chunk.text}\n</context>")
        return "\n\n".join(parts)

    def _format_chunks_for_prompt(self, chunk_texts: list[str]) -> str:
        return "\n\n".join(
            f"[{i + 1}] {text}" for i, text in enumerate(chunk_texts)
        )
