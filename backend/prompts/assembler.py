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


class PromptAssembler:
    """Assembles system prompt from base + domain + optional format + injection shield."""

    DOMAIN_PROMPTS: dict[str, str] = {
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
        parts = [
            PROMPT_BASE,
            self.DOMAIN_PROMPTS.get(domain, PROMPT_GENERAL),
        ]
        if format_hint == "table":
            parts.append(FORMAT_TABLE)
        if format_hint == "steps":
            parts.append(FORMAT_STEPS)
        parts.append(PROMPT_INJECTION_SHIELD)
        return "\n\n".join(parts)
