import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from backend.api.middleware.auth_middleware import get_current_user_id

# Note 1: The sessions router handles the full lifecycle of a conversation:
# create -> read turns -> rename -> archive. Each session is a named thread
# of conversation turns (user messages + assistant replies) stored in SQLite.
# The sidebar in the Angular frontend lists all sessions for the current user.
router = APIRouter(prefix="/api/sessions", tags=["sessions"])


class SessionResponse(BaseModel):
	# Note 2: Pydantic response models serve two purposes:
	# 1. They validate that the data being returned matches the declared shape.
	# 2. They appear in the OpenAPI schema at /docs, documenting the API contract.
	session_id: str
	title: str
	status: str
	total_turns: int
	domain_last: str | None
	created_at: str
	last_active_at: str


class TurnResponse(BaseModel):
	turn_id: str
	session_id: str
	turn_number: int
	role: str
	content: str
	domain: str | None
	sources_cited: list | None
	created_at: str


class UpdateSessionRequest(BaseModel):
	title: str | None = None


def _now_iso() -> str:
	return datetime.now(timezone.utc).isoformat()


def _to_session_response(row: dict) -> SessionResponse:
	return SessionResponse(
		session_id=row["session_id"],
		title=row.get("title") or "Untitled",
		status=row["status"],
		total_turns=row["total_turns"],
		domain_last=row.get("domain_last"),
		created_at=row["created_at"],
		last_active_at=row["last_active_at"],
	)


async def _ensure_owner(db_client, session_id: str, user_id: str) -> dict:
	# Note 3: This guard function is called at the start of every session endpoint
	# that takes a session_id path parameter. It checks two things:
	# 1. The session exists in the database (returns 404 if not)
	# 2. The session belongs to the requesting user (returns 403 if not)
	# This prevents "Insecure Direct Object Reference" (IDOR) — a vulnerability
	# where a user guesses another user's session_id and accesses their history.
	session = await db_client.fetchone(
		"SELECT * FROM sessions WHERE session_id = ?",
		(session_id,),
	)
	if not session:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
	if session["user_id"] != user_id:
		raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
	return session


@router.get("", response_model=list[SessionResponse])
async def list_sessions(request: Request, user_id: str = Depends(get_current_user_id)):
	db_client = request.app.state.db
	rows = await db_client.fetchall(
		"""
		SELECT session_id, title, status, total_turns, domain_last, created_at, last_active_at
		FROM v_session_history
		WHERE user_id = ?
		ORDER BY last_active_at DESC
		""",
		(user_id,),
	)
	return [_to_session_response(row) for row in rows]


@router.post("", response_model=SessionResponse)
async def create_session(request: Request, user_id: str = Depends(get_current_user_id)):
	db_client = request.app.state.db
	now = _now_iso()

	# Note 4: Before creating a new session, we close any currently active one.
	# The schema enforces that each user can have at most one active session
	# (via a partial unique index). This UPDATE does nothing if there is no
	# active session, which is safe — it is a no-op when the user has no prior history.
	await db_client.execute(
		"""
		UPDATE sessions
		SET is_active = 0,
			status = 'closed',
			closed_at = ?
		WHERE user_id = ? AND is_active = 1
		""",
		(now, user_id),
	)

	session_id = str(uuid.uuid4())
	# Note 5: The title includes the current time so the user can identify sessions
	# in the sidebar at a glance. "Chat - 14 Mar 09:30" is more useful than "Session 1".
	title = f"Chat - {datetime.now(timezone.utc).strftime('%d %b %H:%M')}"

	await db_client.execute(
		"""
		INSERT INTO sessions (session_id, user_id, title, status, is_active, created_at, last_active_at)
		VALUES (?, ?, ?, 'active', 1, ?, ?)
		""",
		(session_id, user_id, title, now, now),
	)

	row = await db_client.fetchone(
		"""
		SELECT session_id, title, status, total_turns, domain_last, created_at, last_active_at
		FROM sessions
		WHERE session_id = ?
		""",
		(session_id,),
	)
	return _to_session_response(row)


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(
	session_id: str,
	request: Request,
	user_id: str = Depends(get_current_user_id),
):
	db_client = request.app.state.db
	await _ensure_owner(db_client, session_id, user_id)
	row = await db_client.fetchone(
		"""
		SELECT session_id, title, status, total_turns, domain_last, created_at, last_active_at
		FROM sessions
		WHERE session_id = ?
		""",
		(session_id,),
	)
	return _to_session_response(row)


@router.patch("/{session_id}", response_model=SessionResponse)
async def update_session(
	session_id: str,
	body: UpdateSessionRequest,
	request: Request,
	user_id: str = Depends(get_current_user_id),
):
	db_client = request.app.state.db
	await _ensure_owner(db_client, session_id, user_id)

	if body.title is not None:
		await db_client.execute(
			"UPDATE sessions SET title = ?, last_active_at = ? WHERE session_id = ?",
			(body.title.strip(), _now_iso(), session_id),
		)

	row = await db_client.fetchone(
		"""
		SELECT session_id, title, status, total_turns, domain_last, created_at, last_active_at
		FROM sessions
		WHERE session_id = ?
		""",
		(session_id,),
	)
	return _to_session_response(row)


@router.delete("/{session_id}")
async def archive_session(
	session_id: str,
	request: Request,
	user_id: str = Depends(get_current_user_id),
):
	db_client = request.app.state.db
	await _ensure_owner(db_client, session_id, user_id)

	# Note 6: Sessions are ARCHIVED, not deleted. This is a deliberate design
	# choice — conversation history has audit and compliance value. An archived
	# session is hidden from the sidebar but preserved in the database for
	# future export, investigation, or compliance review if needed.
	await db_client.execute(
		"""
		UPDATE sessions
		SET status = 'archived',
			is_active = 0,
			closed_at = ?
		WHERE session_id = ?
		""",
		(_now_iso(), session_id),
	)

	return {"message": "Session archived"}


@router.get("/{session_id}/turns", response_model=list[TurnResponse])
async def list_turns(
	session_id: str,
	request: Request,
	user_id: str = Depends(get_current_user_id),
):
	db_client = request.app.state.db
	await _ensure_owner(db_client, session_id, user_id)

	rows = await db_client.fetchall(
		"""
		SELECT turn_id, session_id, turn_number, role, content, domain, sources_cited, created_at
		FROM turns
		WHERE session_id = ?
		ORDER BY turn_number ASC
		""",
		(session_id,),
	)

	result: list[TurnResponse] = []
	for row in rows:
		sources = None
		if row.get("sources_cited"):
			try:
				sources = json.loads(row["sources_cited"])
			except json.JSONDecodeError:
				sources = None

		result.append(
			TurnResponse(
				turn_id=row["turn_id"],
				session_id=row["session_id"],
				turn_number=row["turn_number"],
				role=row["role"],
				content=row["content"],
				domain=row.get("domain"),
				sources_cited=sources,
				created_at=row["created_at"],
			)
		)

	return result
