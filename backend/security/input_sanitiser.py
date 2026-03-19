# Layer 1: user input cleaning
# Note 1: This module is reserved for InputSanitiser (Security Layer 1) which
# cleans user query text BEFORE it is processed by the chat pipeline.
#
# Note 2: Layer 1 is the first line of defence against prompt injection in the
# user's direct input. Unlike document scanning (Layer 2) which deals with
# uploaded file content, this layer handles the live chat message text.
#
# Note 3: Planned cleaning operations:
# - Detect and strip common injection phrases:
#   "ignore previous instructions", "you are now", "act as", "system:"
# - Strip Unicode homoglyphs (e.g. Cyrillic 'a' that looks like Latin 'a')
# - Truncate input to max_input_chars (from samvad.yaml, default 2000)
#   before any further processing
# - Log injection attempts to audit_log with event_type='injection_attempt'
#
# Note 4: Input sanitisation should be applied in the chat route
# (backend/api/routes/chat.py) BEFORE calling the RAG retrieval pipeline.
# Even if an injection attempt bypasses this layer, the PROMPT_INJECTION_SHIELD
# in the system prompt provides a second layer of defence inside the LLM.
