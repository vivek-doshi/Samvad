import aiosqlite
from contextlib import asynccontextmanager
from pathlib import Path


class DBClient:
	def __init__(self, db_path: str):
		self.db_path = db_path
		self._conn: aiosqlite.Connection | None = None

	async def connect(self) -> None:
		Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
		self._conn = await aiosqlite.connect(self.db_path)
		self._conn.row_factory = aiosqlite.Row
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

		schema_path = Path(__file__).parent / "schema.sql"
		schema = schema_path.read_text(encoding="utf-8")
		await self._conn.executescript(schema)
		await self._conn.commit()

	async def fetchone(self, sql: str, params: tuple = ()) -> dict | None:
		if not self._conn:
			raise RuntimeError("Database is not connected")

		async with self._conn.execute(sql, params) as cur:
			row = await cur.fetchone()
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

		async with self._conn.execute(sql, params) as cur:
			await self._conn.commit()
			return cur.lastrowid

	async def executemany(self, sql: str, params_list: list) -> None:
		if not self._conn:
			raise RuntimeError("Database is not connected")

		await self._conn.executemany(sql, params_list)
		await self._conn.commit()

	@asynccontextmanager
	async def transaction(self):
		if not self._conn:
			raise RuntimeError("Database is not connected")

		async with self._conn.cursor() as cur:
			try:
				yield cur
				await self._conn.commit()
			except Exception:
				await self._conn.rollback()
				raise
