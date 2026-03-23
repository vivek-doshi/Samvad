# DuckDuckGo fallback, sanitises results
# Note 1: This module is reserved for a web search fallback using the DuckDuckGo
# Search API (no API key required). It is triggered when the local RAG corpus
# does not have sufficient information to answer a query.
#
# Note 2: Web search introduces risks that must be handled carefully:
# - Results may contain prompt-injection attempts embedded in web pages
# - Financial information from the web may be outdated or incorrect
# - Search result snippets must be sanitised before being passed to the LLM
#
# Note 3: The planned implementation flow:
# 1. Query DuckDuckGo using the duckduckgo_search Python library
# 2. Fetch top N result snippets
# 3. Pass each snippet through input_sanitiser.py (Layer 1) to strip
#    any injected instructions embedded in the web content
# 4. Return the sanitised snippets as additional context chunks to the Retriever
#
# Note 4: Web search is marked as a future enhancement. In the current version,
# the system falls back to "I don't have enough information" rather than
# searching the web. This avoids hallucination risks from untrusted web content.
