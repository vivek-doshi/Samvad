import re
from typing import Literal

DomainType = Literal["tax", "equity", "risk", "doc", "general"]
# Note 1: Literal["tax", "equity", ...] is a Python type hint that restricts
# the return type to one of these specific string values. It acts like an enum
# but uses plain strings — useful for JSON serialisation and dictionary keys.

# Note 2: The keyword sets below encode domain expertise as Python sets.
# Sets provide O(1) lookup ('in' operator), which matters when scanning all
# keywords for every incoming query. Using sets instead of lists is a small but
# important performance optimisation called at the start of every chat request.
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
    # Note 3: DOC_KEYWORDS detect when the user is asking about an uploaded
    # document ("summarise this", "what does the document say") rather than
    # asking a general finance question. Phrases like "this document", "the pdf",
    # "uploaded" are strong signals that the user wants document-specific analysis.
    "this document", "the report", "uploaded", "the file",
    "contract", "agreement", "clause", "attached", "the pdf",
    "summarise this", "summarize this", "extract from",
    "what does the document", "this balance sheet",
    "this annual report", "this filing",
}


class QueryRouter:
    """Keyword-based deterministic domain classifier."""
    # Note 4: Why keyword-based routing instead of an ML classifier?
    # - Zero latency: pure Python dict lookups, no model inference
    # - Deterministic: same query always routes to the same domain
    # - Explainable: easy to debug and extend the keyword sets
    # - Sufficient precision for this domain-restricted application
    # A neural router could be added later if keyword matching proves insufficient.

    def route(
        self, query: str, has_uploaded_docs: bool = False
    ) -> DomainType:
        query_lower = query.lower()
        # Note 5: sum(1 for kw in keywords if kw in query_lower) counts how many
        # domain keywords appear in the query. The domain with the highest count
        # wins. This "bag of keywords" scoring is simple but works well because
        # finance domains use very distinct vocabulary (80C vs stock vs risk vs clause).
        scores: dict[str, float] = {
            "tax":    sum(1 for kw in TAX_KEYWORDS    if kw in query_lower),
            "equity": sum(1 for kw in EQUITY_KEYWORDS if kw in query_lower),
            "risk":   sum(1 for kw in RISK_KEYWORDS   if kw in query_lower),
            "doc":    sum(1 for kw in DOC_KEYWORDS     if kw in query_lower),
        }
        # Note 6: If the user has uploaded documents but the query doesn't contain
        # explicit DOC_KEYWORDS, we give the doc domain a small 0.5 bonus. This
        # biases towards document analysis when a document is available —
        # usually the user's intent is to ask about what they just uploaded.
        if has_uploaded_docs and scores["doc"] == 0:
            scores["doc"] += 0.5
        max_domain = max(scores, key=lambda k: scores[k])
        # Note 7: If no domain keywords matched at all, default to "general".
        # This prevents routing to a domain with score 0 just because it happens
        # to beat the others (all at 0) via max(). "general" is the safest fallback.
        if scores[max_domain] == 0:
            return "general"
        return max_domain  # type: ignore[return-value]
