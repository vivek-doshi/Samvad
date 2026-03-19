# Multi-turn injection detection
# Note 1: This module is reserved for the ConversationGuard class (Security Layer 3)
# that detects prompt-injection attempts ACROSS multiple conversation turns.
#
# Note 2: Single-turn injection (e.g. "ignore previous instructions" in one message)
# is handled by the PROMPT_INJECTION_SHIELD in the system prompt. Multi-turn attacks
# are more sophisticated — an attacker might use several innocent-looking messages
# to gradually redirect the AI's behaviour.
#
# Note 3: Planned detection strategies:
# - Track the count of injection-like patterns across all turns in a session
# - Flag the session if the count exceeds the threshold from samvad.yaml
#   (security.injection_threshold, default 2)
# - Log a 'injection_attempt' event to the audit_log with the session_id
# - Optionally refuse to respond until the session is reset
#
# Note 4: This layer works in concert with input_sanitiser.py (Layer 1) which
# cleans individual messages, and the LLM's own instruction-following behaviour
# reinforced by the PROMPT_INJECTION_SHIELD prompt component.
