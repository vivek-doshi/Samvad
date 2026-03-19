# Two-store: SQLite (persistent) + dict (active)
# Note 1: This module is reserved for the SessionManager class that manages
# conversation session state across two storage layers:
#
# 1. SQLite (persistent store) — All sessions and their turns are saved to the
#    database via DBClient. This ensures conversation history survives server
#    restarts and can be exported or audited later.
#
# 2. In-memory dict (active store) — The currently active session's latest
#    state (e.g. most recent turn, streaming status) is cached in a Python dict
#    for fast access without hitting the database on every token.
#
# Note 2: The session summary compression logic (compressing old turns into a
# shorter summary after N turns) is also expected to live here. Summary compression
# is triggered when total_turns exceeds the 'summarise_after_turns' threshold
# in samvad.yaml (default: 6 turns).
#
# Note 3: This class is a planned component. Current session logic is handled
# inline within the chat route (backend/api/routes/chat.py). Moving it here
# will improve separation of concerns and make the code easier to test.
