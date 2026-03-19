import aiosqlite
# Note 1: aiosqlite is an async wrapper around Python's built-in sqlite3 module.
# The key difference: sqlite3 blocks the entire thread while executing a query,
# whereas aiosqlite runs queries in a background thread pool and uses 'await'
# to yield control, so FastAPI can handle other requests during a slow query.
from contextlib import asynccontextmanager
from pathlib import Path


class DBClient:
	# Note 2: DBClient is a thin abstraction layer over aiosqlite. Centralising
	# all database access here means: (a) the connection settings are in one place,
	# (b) PRAGMA settings (foreign keys, WAL mode) are always applied consistently,
	# and (c) swapping SQLite for PostgreSQL in the future only requires changes
	# to this file — none of the route handlers need to change.
	def __init__(self, db_path: str):
		self.db_path = db_path
		# Note 3: The connection is stored as None until connect() is called.
		# This lazy-connection pattern is safe because FastAPI's lifespan context
		# calls connect() before any request is handled.
		self._conn: aiosqlite.Connection | None = None

	async def connect(self) -> None:
		# Note 4: mkdir(parents=True, exist_ok=True) creates the full directory
		# tree (e.g. runtime/sqlite/) if it doesn't exist yet. Without this,
		# aiosqlite.connect() would raise FileNotFoundError on a fresh install.
		Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
		self._conn = await aiosqlite.connect(self.db_path)
		# Note 5: Row factory returns dict-like rows so we can access columns
		# by name (row["username"]) instead of index (row[1]). This makes the
		# code much more readable and resilient to column order changes.
		self._conn.row_factory = aiosqlite.Row
		# Note 6: These three PRAGMAs are SQLite performance and safety settings:
		# PRAGMA foreign_keys = ON  — enforces FK constraints (off by default!)
		# PRAGMA journal_mode = WAL — Write-Ahead Logging enables concurrent reads
		#                             while a write is in progress (much faster)
		# PRAGMA synchronous = NORMAL — balances durability vs write speed
		await self._conn.execute("PRAGMA foreign_keys = ON")
		await self._conn.execute("PRAGMA journal_mode = WAL")
		await self._conn.execute("PRAGMA synchronous = NORMAL")
		await self._conn.commit()

	async def close(self) -> None:
		if self._conn:
			await self._conn.close()
			self._conn = None

	async def init_schema(self) -> None:
		if not self._conn:
			raise RuntimeError("Database is not connected")
		# Note 7: executescript() runs a multi-statement SQL script in a single
		# call. All CREATE TABLE IF NOT EXISTS statements in schema.sql are
		# idempotent — they succeed whether the table exists or not — so this
		# is safe to run on every startup without wiping existing data.
		schema_path = Path(__file__).parent / "schema.sql"
		schema = schema_path.read_text(encoding="utf-8")
		await self._conn.executescript(schema)
		await self._conn.commit()

	async def fetchone(self, sql: str, params: tuple = ()) -> dict | None:
		if not self._conn:
			raise RuntimeError("Database is not connected")
		# Note 8: 'async with self._conn.execute(...)' opens a cursor, runs the
		# query, and closes the cursor automatically — even if an exception occurs.
		# Using a context manager for cursors is important to avoid cursor leaks.
		async with self._conn.execute(sql, params) as cur:
			row = await cur.fetchone()
			# Note 9: 'dict(row)' converts the aiosqlite.Row (which is dict-like
			# but not a plain dict) into a standard Python dict. This lets callers
			# use row["column_name"] syntax safely throughout the application.
			return dict(row) if row else None

	async def fetchall(self, sql: str, params: tuple = ()) -> list[dict]:
		if not self._conn:
			raise RuntimeError("Database is not connected")

		async with self._conn.execute(sql, params) as cur:
			rows = await cur.fetchall()
			return [dict(row) for row in rows]

	async def execute(self, sql: str, params: tuple = ()) -> int:
		if not self._conn:
			raise RuntimeError("Database is not connected")
		# Note 10: commit() is called after every execute() to write the change
		# to disk immediately. For bulk inserts (many rows), use executemany()
		# which batches the commits for better performance.
		async with self._conn.execute(sql, params) as cur:
			await self._conn.commit()
			# Note 11: lastrowid returns the row ID of the last INSERT. For tables
			# using TEXT primary keys (UUID strings), this is not the UUID itself
			# but the SQLite internal row number. Callers should use the UUID they
			# generated rather than relying on this return value.
			return cur.lastrowid

	async def executemany(self, sql: str, params_list: list) -> None:
		if not self._conn:
			raise RuntimeError("Database is not connected")
		# Note 12: executemany() is much more efficient than calling execute() in
		# a loop. It sends all parameter sets to the DB engine at once, reducing
		# Python-to-SQLite round-trips. Used for batch embedding inserts in the
		# ingestion pipeline where thousands of chunks need to be recorded.
		await self._conn.executemany(sql, params_list)
		await self._conn.commit()

	@asynccontextmanager
	async def transaction(self):
		if not self._conn:
			raise RuntimeError("Database is not connected")
		# Note 13: The transaction() context manager provides explicit BEGIN/COMMIT/
		# ROLLBACK control. Use it when you need multiple SQL statements to succeed
		# or fail together atomically — e.g. inserting a session AND its first turn
		# where partial success would leave the DB in an inconsistent state.
		async with self._conn.cursor() as cur:
			try:
				yield cur
				await self._conn.commit()
			except Exception:
				await self._conn.rollback()
				raise
