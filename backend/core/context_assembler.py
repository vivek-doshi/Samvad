import json
import logging
# Note 1: These imports bring in the three collaborators this class depends on.
# ContextAssembler is a coordinator — it does not do any AI computation itself;
# it delegates counting to TokenManager and prompt construction to PromptAssembler.
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
    # Note 2: This class implements the "RAG context assembly" pattern:
    # retrieved knowledge is injected as [REFERENCE CONTEXT] into the prompt
    # so the model answers ONLY from that content, not from its training memory.
    # The combination of system, summary, history, context, and query is called
    # the "message list" — each item has a 'role' (system/user/assistant) and
    # 'content' field, matching the OpenAI chat API format.

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
        # Note 3: The function returns a TUPLE of two things:
        # 1. messages_list — the list of role/content dicts sent to the LLM
        # 2. budget_breakdown — a dict of token counts for each component,
        #    logged after every request so you can see how budget is being used.

        # STEP 1 — Build system prompt
        # Note 4: The system prompt sets the AI's persona and ground rules.
        # It is domain-specific — a tax query gets PROMPT_TAX injected, an
        # equity query gets PROMPT_EQUITY, etc. The injection shield is always
        # appended last to prevent prompt-injection attacks.
        system_prompt = self.prompt_assembler.build(domain)

        # STEP 2 — Format retrieved chunks as context string
        # Note 5: _format_chunks wraps each chunk in XML-style <context> tags
        # with source metadata. This structured format makes it easy for the LLM
        # to cite sources accurately in its response.
        context_str = self._format_chunks(retrieved_chunks)

        # STEP 3 — Build session summary string
        # Note 6: The session summary is a compressed text of earlier turns
        # created once the conversation exceeds a threshold. Using a summary
        # instead of the full history drastically reduces token usage.
        summary_str = session_summary or ""

        # STEP 4 — Allocate token budget
        # Note 7: allocate_budget() may truncate components if they are too long.
        # We pass the raw text and get back (possibly truncated) text plus counts.
        budget = self.token_manager.allocate_budget(
            system_prompt=system_prompt,
            session_summary=summary_str,
            history_turns=history_turns,
            retrieved_chunks=[c.text for c in retrieved_chunks],
            query=query,
        )

        # STEP 5 — Assemble messages
        # Note 8: The OpenAI chat API format uses a list of messages, each with
        # 'role' (system/user/assistant) and 'content'. The model is instructed
        # by 'system' messages and converses through 'user'/'assistant' alternation.
        messages: list[dict] = [
            {"role": "system", "content": budget["system_prompt"]},
        ]

        if budget.get("session_summary"):
            # Note 9: The session summary is injected as a second system message
            # labelled [PRIOR CONTEXT]. Using a separate system message (rather
            # than prepending to the first one) keeps the system prompt clean and
            # makes it easier to control token budgets for each component.
            messages.append({
                "role": "system",
                "content": f"[PRIOR CONTEXT]\n{budget['session_summary']}",
            })

        for turn in budget.get("history_turns", []):
            messages.append({"role": turn["role"], "content": turn["content"]})

        if budget.get("retrieved_chunks"):
            # Note 10: Retrieved context is labelled [REFERENCE CONTEXT] to signal
            # to the model that it MUST ground its answer in this content. The
            # injection shield in the system prompt reinforces that instructions
            # embedded inside these chunks should be treated as data, not commands.
            context_block = self._format_chunks_for_prompt(budget["retrieved_chunks"])
            messages.append({
                "role": "system",
                "content": f"[REFERENCE CONTEXT]\n{context_block}",
            })

        messages.append({"role": "user", "content": query})

        return messages, budget.get("budget_breakdown", {})

    def _format_chunks(self, chunks: list[Chunk]) -> str:
        # Note 11: Each chunk is wrapped in XML-like <context> tags with metadata
        # attributes. XML-style tags are commonly used in RAG systems because they
        # are easy for LLMs to parse and they visually separate context from query.
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
        # Note 12: The [1], [2], [3]... numbering lets the LLM cite specific
        # chunks in its answer using index references. The model's prompt instructs
        # it to use [Source: ...] citations, which the frontend can later parse.
        return "\n\n".join(
            f"[{i + 1}] {text}" for i, text in enumerate(chunk_texts)
        )
