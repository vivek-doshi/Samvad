import re
from typing import Literal

DomainType = Literal["tax", "equity", "risk", "doc", "general"]

TAX_KEYWORDS = {
    "income tax", "section", "deduction", "80c", "80d", "tds",
    "assessment year", "financial year", "itr", "return filing",
    "capital gains", "ltcg", "stcg", "tax slab", "rebate",
    "surcharge", "advance tax", "pan", "form 16", "form 26as",
    "exemption", "proviso", "assessee", "old regime", "new regime",
    "tax act", "cess", "huf", "clubbing", "set off", "carry forward",
}

EQUITY_KEYWORDS = {
    "buy", "sell", "hold", "stock", "share", "equity", "nifty",
    "sensex", "portfolio", "pe ratio", "eps", "dividend", "roe",
    "roce", "debt", "market cap", "valuation", "fundamental",
    "mutual fund", "etf", "sip", "nav", "bull", "bear",
    "moving average", "rsi", "macd", "ebitda", "revenue",
    "profit", "margin", "balance sheet", "cash flow",
}

RISK_KEYWORDS = {
    "risk", "exposure", "default", "credit risk", "market risk",
    "liquidity risk", "compliance", "regulatory", "audit", "fraud",
    "due diligence", "concentration", "stress test", "contingent",
    "liability", "litigation", "npa", "provision",
}

DOC_KEYWORDS = {
    "this document", "the report", "uploaded", "the file",
    "contract", "agreement", "clause", "attached", "the pdf",
    "summarise this", "summarize this", "extract from",
    "what does the document", "this balance sheet",
    "this annual report", "this filing",
}


class QueryRouter:
    """Keyword-based deterministic domain classifier."""

    def route(
        self, query: str, has_uploaded_docs: bool = False
    ) -> DomainType:
        query_lower = query.lower()
        scores: dict[str, float] = {
            "tax":    sum(1 for kw in TAX_KEYWORDS    if kw in query_lower),
            "equity": sum(1 for kw in EQUITY_KEYWORDS if kw in query_lower),
            "risk":   sum(1 for kw in RISK_KEYWORDS   if kw in query_lower),
            "doc":    sum(1 for kw in DOC_KEYWORDS     if kw in query_lower),
        }
        if has_uploaded_docs and scores["doc"] == 0:
            scores["doc"] += 0.5
        max_domain = max(scores, key=lambda k: scores[k])
        if scores[max_domain] == 0:
            return "general"
        return max_domain  # type: ignore[return-value]
