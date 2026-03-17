import re
from typing import Literal


class QueryExpander:
    """Rule-based query expansion for Indian finance/tax domain."""

    SECTION_EXPANSIONS: dict[str, str] = {
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
        query_lower = query.lower()
        expansions: list[str] = []
        for key, expansion in self.SECTION_EXPANSIONS.items():
            if key in query_lower:
                expansions.append(expansion)
        if expansions:
            return query + " " + " ".join(expansions)
        return query

    def extract_section_numbers(self, query: str) -> list[str]:
        results: set[str] = set()
        # Explicit "Section X" references
        for m in re.finditer(r'[Ss]ection\s+(\d+[A-Z]?(?:\(\d+\))?)', query):
            results.add(m.group(1))
        # Bare numbers like "80C", "194A"
        for m in re.finditer(r'\b(\d{2,3}[A-Z]?)\b', query):
            results.add(m.group(1))
        return list(results)
