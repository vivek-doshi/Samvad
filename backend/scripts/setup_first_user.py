import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.db.db_client import DBClient
from backend.security.auth import hash_password

load_dotenv()


async def main():
	db_path = os.getenv("SQLITE_PATH", "runtime/sqlite/samvad.db")
	db = DBClient(db_path)
	await db.connect()
	await db.init_schema()

	print("\n=== Samvad - Create First User ===\n")

	existing = await db.fetchone("SELECT COUNT(*) as cnt FROM users")
	if existing and existing["cnt"] > 0:
		print(f"Users already exist ({existing['cnt']} found).")
		confirm = input("Add another user? [y/N]: ").strip().lower()
		if confirm != "y":
			print("Exiting.")
			await db.close()
			return

	username = input("Username: ").strip().lower()
	display_name = input("Display name: ").strip()
	password = input("Password (min 8 chars): ").strip()
	role = input("Role [user/admin] (default: admin): ").strip() or "admin"

	if len(password) < 8:
		print("Password too short. Minimum 8 characters.")
		await db.close()
		return

	user_id = str(uuid.uuid4())
	password_hash = hash_password(password)
	now = datetime.now(timezone.utc).isoformat()

	await db.execute(
		"""
		INSERT INTO users
		(user_id, username, display_name, password_hash, role, is_active, created_at)
		VALUES (?,?,?,?,?,1,?)
		""",
		(user_id, username, display_name, password_hash, role, now),
	)

	print("\nUser created successfully.")
	print(f"  user_id : {user_id}")
	print(f"  username: {username}")
	print(f"  role    : {role}")
	print("\nYou can now log in to Samvad at http://localhost:4200\n")

	await db.close()


if __name__ == "__main__":
	asyncio.run(main())
