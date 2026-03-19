# Layer 4: response validation
# Note 1: This module is reserved for OutputValidator (Security Layer 4) which
# checks the LLM's RESPONSE after generation, before sending it to the frontend.
#
# Note 2: Even with a strong system prompt, an LLM may occasionally:
# - Include personally identifiable information (PII) leaked from context
# - Expose internal system instructions if directly asked
# - Generate content that contradicts its own declared rules
# - Hallucinate regulatory details despite grounding instructions
#
# Note 3: Planned validation checks:
# - PII detection: regex patterns for Aadhaar numbers, PAN cards, phone numbers,
#   email addresses that should not appear in AI-generated responses
# - System prompt leakage: detect if the response contains verbatim fragments
#   from the system prompt (which the user should never see)
# - Disclaimer presence: ensure the required disclaimer is included in
#   responses to tax and investment queries (as required by PROMPT_TAX/EQUITY)
# - Empty response detection: catch cases where the model returns an empty string
#
# Note 4: The validator should log anomalies to audit_log with
# event_type='output_anomaly' and severity='warning'. It should NOT silently
# drop responses — instead replace problematic content with a safe fallback message.
