# 32K budget allocator
# Note 1: This module solves a fundamental LLM constraint: models have a fixed
# "context window" — the maximum number of tokens they can process in one call.
# For Arthvidya, this limit is 32,768 tokens. TokenManager decides how to share
# that budget among: system prompt, session summary, conversation history,
# retrieved knowledge chunks, and the user's current query.

import logging
# Note 2: tiktoken is OpenAI's tokenizer library. It encodes text into tokens
# (the units LLMs process). 'cl100k_base' is the encoding used by GPT-4 and
# many open-source models. Using the same tokenizer ensures our budget calculations
# are accurate — different tokenizers can give very different counts for the same text.
import tiktoken

logger = logging.getLogger(__name__)


class TokenManager:
    """Manage the 32K context-window budget across all prompt components."""
    # Note 3: All budget values come from the 'token_budget' section of samvad.yaml.
    # Storing them as instance attributes (self.total_context, etc.) instead of
    # re-reading the config every call avoids repeated dict lookups at request time.

    def __init__(self, config: dict) -> None:
        budget = config.get("token_budget", {})
        # Note 4: .get(key, default) returns the config value if present, otherwise
        # the fallback. This means the code still works even if some keys are missing
        # from the YAML — the defaults give a sensible starting configuration.
        self.total_context: int = budget.get("total", 32768)
        self.system_prompt_max: int = budget.get("system_prompt_max", 500)
        self.session_summary_max: int = budget.get("session_summary_max", 350)
        self.history_max_turns: int = budget.get("history_verbatim_turns", 2)
        self.generation_reserved: int = budget.get("generation_reserved", 2048)

        # history token cap — 800 tokens for the last N turns
        # Note 5: We cap history at 800 tokens rather than N turns alone because
        # a single long turn could exhaust the entire history budget by itself.
        # The combination of turn count AND token count provides a tighter bound.
        self.history_token_max: int = 800

        # Note 6: tiktoken.get_encoding returns a tokenizer object. Encoding
        # is done at module level once (not per-request) to avoid reloading the
        # tokenizer vocabulary file (~1MB) on every incoming query.
        self._enc = tiktoken.get_encoding("cl100k_base")

    # -- counting ---------------------------------------------------------------
    # Note 7: Every public method in this class calls count_tokens() internally.
    # The +4 overhead accounts for the OpenAI chat message envelope tokens that
    # the model sees but are not part of the raw text content itself.

    def count_tokens(self, text: str) -> int:
        """Return token count for *text* plus 4-token chat-format overhead."""
        return len(self._enc.encode(text)) + 4

    def fits_in_budget(self, text: str, max_tokens: int) -> bool:
        # Note 8: A simple convenience wrapper that returns True/False. Used as
        # a guard before deciding whether to truncate or pass text through as-is.
        return self.count_tokens(text) <= max_tokens

    # -- truncation -------------------------------------------------------------
    # Note 9: Truncation keeps the most recent (rightmost) content and removes
    # text from the START of the string. This is important for conversation history
    # — if we must trim, we prefer to lose older context rather than recent messages.

    def truncate_to_budget(self, text: str, max_tokens: int) -> str:
        """Truncate *text* from the end to fit within *max_tokens*."""
        tokens = self._enc.encode(text)
        # subtract overhead (4) & space for the "... [truncated]" suffix (~5)
        # Note 10: We reserve 9 extra token positions (4 overhead + 5 suffix)
        # so the truncated text plus its "... [truncated]" marker still fits
        # within max_tokens without accidentally going over budget.
        effective_max = max_tokens - 4 - 5
        if len(tokens) <= effective_max:
            return text
        truncated = self._enc.decode(tokens[:effective_max])
        return truncated + "... [truncated]"

    # -- chunk selection --------------------------------------------------------
    # Note 11: select_chunks_for_budget implements a greedy knapsack algorithm.
    # Chunks are already ranked by relevance (highest first) when passed in.
    # We add chunks one by one until we would exceed the remaining token budget.
    # This is O(n) and simple — a good trade-off given chunk lists are small (<20).

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
            # Note 12: We break (not continue) when a chunk is too large. This
            # preserves the relevance ordering — once the budget is exceeded we
            # stop, rather than skipping large chunks and taking smaller later ones.
            if cost > remaining:
                break
            selected.append(chunk)
            remaining -= cost
        return selected

    # -- main budget allocation -------------------------------------------------
    # Note 13: allocate_budget() is the central function — it is called once per
    # chat request and decides how to divide the 32K token window. The priority
    # order (highest to lowest) is:
    #   1. System prompt      (defines the AI's persona and rules)
    #   2. Session summary    (compressed history of the conversation so far)
    #   3. Conversation turns (most recent N messages, verbatim)
    #   4. User query         (always included — never truncated)
    #   5. Generation budget  (reserved for the model's response)
    #   6. Retrieved chunks   (gets whatever space remains)

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
        # Note 14: We iterate in REVERSE order (newest first) so that if we must
        # drop turns due to budget, we drop the oldest ones — the most recent
        # messages are usually the most relevant to the current query.
        kept_turns: list[dict] = []
        history_tokens = 0
        for turn in reversed(history_turns):
            cost = self.count_tokens(turn.get("content", ""))
            if history_tokens + cost > self.history_token_max:
                break
            kept_turns.insert(0, turn)
            # Note 15: insert(0, turn) rebuilds the list in chronological order
            # as we iterate in reverse. An alternative would be to reverse the
            # final list, but insert(0) keeps the intent explicit and readable.
            history_tokens += cost
        breakdown["history"] = history_tokens

        # 4. Query (always included)
        query_tokens = self.count_tokens(query)
        breakdown["query"] = query_tokens

        # 5. Generation reserved
        breakdown["generation_reserved"] = self.generation_reserved

        # 6. Retrieval gets whatever remains
        # Note 16: max(..., 0) ensures available_for_chunks is never negative.
        # If earlier components have consumed more than total_context (rare but
        # possible if config values are set too high), we give chunks 0 tokens
        # rather than passing a negative budget to select_chunks_for_budget().
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
