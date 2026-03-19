import re
from typing import Literal
# Note 1: QueryExpander improves RAG recall through query expansion — adding
# domain-specific synonyms and related terms to the user's query before
# sending it to the retrieval stage. For example, "HRA" expands to include
# "house rent allowance", "section 10(13A)", "exemption" etc., so the vector
# search and BM25 index can find relevant passages that don't use the acronym.


class QueryExpander:
    """Rule-based query expansion for Indian finance/tax domain."""
    # Note 2: Rule-based expansion is preferred over neural expansion here because:
    # (a) Indian finance acronyms (80C, HRA, TDS) are very domain-specific
    # (b) Rules are deterministic — no risk of hallucinated expansions
    # (c) Zero inference latency — just dictionary lookups

    SECTION_EXPANSIONS: dict[str, str] = {
        # Note 3: Each key is a common acronym or short form a user might type.
        # The value is a space-separated string of related terms that improves
        # both BM25 keyword matching AND vector semantic similarity.
        "80c":  "section 80C deduction investment life insurance provident fund ELSS",
        "80d":  "section 80D medical insurance health premium deduction",
        "hra":  "house rent allowance HRA exemption section 10(13A)",
        "tds":  "tax deducted at source TDS section 194 194A 194C 194H",
        "ltcg": "long term capital gains LTCG section 112 112A",
        "stcg": "short term capital gains STCG section 111A",
        "gst":  "goods and services tax GST input tax credit",
        "mat":  "minimum alternate tax MAT section 115JB book profit",
        "nri":  "non resident Indian NRI FEMA RBI remittance",
        "dtaa": "double taxation avoidance agreement DTAA treaty relief",
        "sebi": "Securities Exchange Board India SEBI regulation compliance",
        "pe ratio":       "price earnings ratio PE valuation equity analysis",
        "roe":            "return on equity ROE profitability ratio",
        "roce":           "return on capital employed ROCE efficiency",
        "ebitda":         "earnings before interest tax depreciation amortisation EBITDA",
        "working capital": "current assets current liabilities liquidity",
    }

    def expand(self, query: str) -> str:
        # Note 4: We check the LOWERCASE version of the query against lowercase keys.
        # This ensures "TDS" and "tds" both trigger the same expansion, but the
        # original query casing is preserved in the final expanded string.
        query_lower = query.lower()
        expansions: list[str] = []
        for key, expansion in self.SECTION_EXPANSIONS.items():
            if key in query_lower:
                expansions.append(expansion)
        if expansions:
            return query + " " + " ".join(expansions)
        return query

    def extract_section_numbers(self, query: str) -> list[str]:
        # Note 5: This extracts explicit and implicit section references for the
        # BM25 boost in the Retriever. Two patterns are matched:
        # - Explicit: "Section 80C", "Section 194A(1)" — labelled references
        # - Implicit: bare numbers like "80C", "194A" — common user shorthand
        results: set[str] = set()
        # Explicit "Section X" references
        for m in re.finditer(r'[Ss]ection\s+(\d+[A-Z]?(?:\(\d+\))?)', query):
            results.add(m.group(1))
        # Bare numbers like "80C", "194A"
        for m in re.finditer(r'\b(\d{2,3}[A-Z]?)\b', query):
            results.add(m.group(1))
        return list(results)
