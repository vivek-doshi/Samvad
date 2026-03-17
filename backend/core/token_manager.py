# 32K budget allocator

import logging

import tiktoken

logger = logging.getLogger(__name__)


class TokenManager:
    """Manage the 32K context-window budget across all prompt components."""

    def __init__(self, config: dict) -> None:
        budget = config.get("token_budget", {})
        self.total_context: int = budget.get("total", 32768)
        self.system_prompt_max: int = budget.get("system_prompt_max", 500)
        self.session_summary_max: int = budget.get("session_summary_max", 350)
        self.history_max_turns: int = budget.get("history_verbatim_turns", 2)
        self.generation_reserved: int = budget.get("generation_reserved", 2048)

        # history token cap — 800 tokens for the last N turns
        self.history_token_max: int = 800

        self._enc = tiktoken.get_encoding("cl100k_base")

    # -- counting ---------------------------------------------------------------

    def count_tokens(self, text: str) -> int:
        """Return token count for *text* plus 4-token chat-format overhead."""
        return len(self._enc.encode(text)) + 4

    def fits_in_budget(self, text: str, max_tokens: int) -> bool:
        return self.count_tokens(text) <= max_tokens

    # -- truncation -------------------------------------------------------------

    def truncate_to_budget(self, text: str, max_tokens: int) -> str:
        """Truncate *text* from the end to fit within *max_tokens*."""
        tokens = self._enc.encode(text)
        # subtract overhead (4) & space for the "... [truncated]" suffix (~5)
        effective_max = max_tokens - 4 - 5
        if len(tokens) <= effective_max:
            return text
        truncated = self._enc.decode(tokens[:effective_max])
        return truncated + "... [truncated]"

    # -- chunk selection --------------------------------------------------------

    def select_chunks_for_budget(
        self,
        chunks: list[str],
        available_tokens: int,
    ) -> list[str]:
        """Greedily select chunks (highest-priority first) within budget."""
        selected: list[str] = []
        remaining = available_tokens
        for chunk in chunks:
            cost = self.count_tokens(chunk)
            if cost > remaining:
                break
            selected.append(chunk)
            remaining -= cost
        return selected

    # -- main budget allocation -------------------------------------------------

    def allocate_budget(
        self,
        system_prompt: str,
        session_summary: str,
        history_turns: list[dict],
        retrieved_chunks: list[str],
        query: str,
    ) -> dict:
        """Allocate the context-window budget across all prompt components.

        Returns a dict with the (possibly truncated) components, token counts,
        and a breakdown suitable for logging.
        """
        breakdown: dict[str, int] = {}

        # 1. System prompt
        if not self.fits_in_budget(system_prompt, self.system_prompt_max):
            logger.warning(
                "System prompt (%d tokens) exceeds budget (%d) — truncating",
                self.count_tokens(system_prompt),
                self.system_prompt_max,
            )
            system_prompt = self.truncate_to_budget(system_prompt, self.system_prompt_max)
        sys_tokens = self.count_tokens(system_prompt)
        breakdown["system"] = sys_tokens

        # 2. Session summary
        if not self.fits_in_budget(session_summary, self.session_summary_max):
            session_summary = self.truncate_to_budget(session_summary, self.session_summary_max)
        summary_tokens = self.count_tokens(session_summary) if session_summary else 0
        breakdown["summary"] = summary_tokens

        # 3. History — keep last N turns that fit within history_token_max
        kept_turns: list[dict] = []
        history_tokens = 0
        for turn in reversed(history_turns):
            cost = self.count_tokens(turn.get("content", ""))
            if history_tokens + cost > self.history_token_max:
                break
            kept_turns.insert(0, turn)
            history_tokens += cost
        breakdown["history"] = history_tokens

        # 4. Query (always included)
        query_tokens = self.count_tokens(query)
        breakdown["query"] = query_tokens

        # 5. Generation reserved
        breakdown["generation_reserved"] = self.generation_reserved

        # 6. Retrieval gets whatever remains
        used_so_far = sys_tokens + summary_tokens + history_tokens + query_tokens + self.generation_reserved
        available_for_chunks = max(self.total_context - used_so_far, 0)
        selected_chunks = self.select_chunks_for_budget(retrieved_chunks, available_for_chunks)
        chunk_tokens = sum(self.count_tokens(c) for c in selected_chunks)
        breakdown["chunks"] = chunk_tokens

        total_used = used_so_far + chunk_tokens
        tokens_remaining = max(self.total_context - total_used, 0)

        return {
            "system_prompt": system_prompt,
            "session_summary": session_summary,
            "history_turns": kept_turns,
            "retrieved_chunks": selected_chunks,
            "query": query,
            "tokens_used": total_used,
            "tokens_remaining_for_generation": tokens_remaining,
            "budget_breakdown": breakdown,
        }
