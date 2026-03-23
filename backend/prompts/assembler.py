from backend.prompts.library import (
    PROMPT_BASE,
    PROMPT_TAX,
    PROMPT_EQUITY,
    PROMPT_RISK,
    PROMPT_DOC,
    PROMPT_GENERAL,
    PROMPT_INJECTION_SHIELD,
    FORMAT_TABLE,
    FORMAT_STEPS,
)
# Note 1: All prompt string constants are defined in library.py so they can be
# reviewed, edited, and version-controlled independently from the assembly logic
# here. This separation of prompt content from assembly code is a best practice
# in AI engineering — it is easy to A/B test prompt changes without touching logic.


class PromptAssembler:
    """Assembles system prompt from base + domain + optional format + injection shield."""
    # Note 2: The assembled prompt follows a strict order:
    # 1. PROMPT_BASE    — core identity and citation rules (always present)
    # 2. Domain prompt  — domain-specific rules (e.g. PROMPT_TAX for tax queries)
    # 3. Format hint    — optional table/steps formatting instruction
    # 4. PROMPT_INJECTION_SHIELD — security rules (always last, hardest to override)

    DOMAIN_PROMPTS: dict[str, str] = {
        # Note 3: The domain key matches the output of QueryRouter.route().
        # If an unknown domain is passed, PROMPT_GENERAL is used as a safe default.
        "tax":     PROMPT_TAX,
        "equity":  PROMPT_EQUITY,
        "risk":    PROMPT_RISK,
        "doc":     PROMPT_DOC,
        "general": PROMPT_GENERAL,
    }

    def build(
        self,
        domain: str,
        format_hint: str | None = None,
    ) -> str:
        # Note 4: "\n\n".join(parts) produces a single string with double newlines
        # between each section. Large language models respond better to clearly
        # separated instruction blocks than to a single dense paragraph.
        parts = [
            PROMPT_BASE,
            self.DOMAIN_PROMPTS.get(domain, PROMPT_GENERAL),
        ]
        # Note 5: Format hints are optional and only added when explicitly requested.
        # They instruct the model to structure its response in a specific way —
        # e.g. "table" for comparative questions, "steps" for procedural answers.
        if format_hint == "table":
            parts.append(FORMAT_TABLE)
        if format_hint == "steps":
            parts.append(FORMAT_STEPS)
        # Note 6: PROMPT_INJECTION_SHIELD is always the LAST section. This position
        # matters — later instructions in a system prompt generally take precedence
        # over earlier ones, so placing the security rules at the end makes them
        # harder for adversarial user messages to override.
        parts.append(PROMPT_INJECTION_SHIELD)
        return "\n\n".join(parts)
