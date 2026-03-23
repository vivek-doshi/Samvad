# POST /upload — file ingestion trigger
# Note 1: This module handles user document uploads. The full pipeline is:
# receive file -> validate type and size -> save to disk -> insert DB record
# -> run ingestion (parse + sanitise + chunk + embed + store) -> return result.
# The ingestion is synchronous within the request — for large files consider
# moving it to a background task (FastAPI BackgroundTasks) in a future version.

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, Form

from backend.api.middleware.auth_middleware import get_current_user_id
from backend.db.db_client import DBClient
from backend.rag.ingestion import DocumentIngester

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/upload", tags=["upload"])

# Note 2: ALLOWED_TYPES is a whitelist of permitted file extensions. A whitelist
# ("only allow these") is much safer than a blacklist ("block all others") because
# it is impossible to enumerate every malicious format. Any extension not in this
# set is rejected with HTTP 400 before reading the file content.
ALLOWED_TYPES = {"pdf", "docx", "csv", "xlsx", "txt"}
# Note 3: MAX_UPLOAD_BYTES = 50MB. This prevents denial-of-service attacks where
# an attacker uploads a huge file to exhaust server memory or disk. The limit is
# enforced AFTER reading the file into memory — see the len(content) check below.
MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB


@router.post("")
async def upload_document(
    request: Request,
    file: UploadFile,
    session_id: str = Form(...),
    user_id: str = Depends(get_current_user_id),
):
    """Upload and ingest a document into the session's ChromaDB collection."""
    db: DBClient = request.app.state.db
    ingester: DocumentIngester = request.app.state.ingester

    # 1. Validate file type
    # Note 4: We extract the extension from the filename using rsplit(".", 1)[-1].
    # rsplit with maxsplit=1 splits from the RIGHT so "report.2024.pdf" correctly
    # gives extension "pdf". The 'if "." in filename' guard handles files without
    # an extension, returning an empty string that will fail the ALLOWED_TYPES check.
    filename = file.filename or "upload"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{ext}' not allowed. Permitted: {', '.join(sorted(ALLOWED_TYPES))}",
        )

    # Read file content (enforce size limit)
    # Note 5: await file.read() reads the entire file into memory. For the 50MB
    # limit this is acceptable. For much larger files, consider streaming with
    # file.read(chunk_size) and writing chunks to disk to avoid memory exhaustion.
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds maximum size of 50 MB",
        )

    # 2. Generate doc_id
    doc_id = str(uuid.uuid4())

    # 3. Save file to disk
    # Note 6: Files are stored under runtime/user_uploads/<user_id>/ so each
    # user's files are in their own directory. The doc_id prefix on the filename
    # (e.g. "abc123_report.pdf") prevents filename collisions if two users upload
    # files with the same name. upload_dir.mkdir(parents=True, exist_ok=True) is
    # idempotent — it creates the directory tree if it doesn't exist yet.
    upload_dir = Path("runtime/user_uploads") / user_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_filename = f"{doc_id}_{filename}"
    file_path = upload_dir / safe_filename
    file_path.write_bytes(content)

    now = datetime.now(timezone.utc).isoformat()

    # 4. Insert into user_documents
    await db.execute(
        """INSERT INTO user_documents
           (doc_id, user_id, filename, file_type, file_size_bytes,
            sanitisation_status, indexed_at)
           VALUES (?, ?, ?, ?, ?, 'pending', ?)""",
        (doc_id, user_id, filename, ext, len(content), now),
    )

    # 5. Insert into session_documents
    await db.execute(
        """INSERT INTO session_documents (session_id, doc_id, attached_at)
           VALUES (?, ?, ?)""",
        (session_id, doc_id, now),
    )

    # 6. Ingest: chunk → embed → store
    # Note 7: ingester.ingest() is the main pipeline: parse file -> sanitise
    # content -> chunk into pieces -> embed with BGE -> store in ChromaDB + BM25.
    # It raises ValueError for quarantined documents (containing dangerous content)
    # and generic Exception for infrastructure failures (disk, embedding model).
    try:
        result = await ingester.ingest(
            file_path=str(file_path),
            filename=filename,
            file_type=ext,
            session_id=session_id,
            user_id=user_id,
            doc_id=doc_id,
            db=db,
        )
    except ValueError as exc:
        # Quarantined document
        logger.warning("Upload quarantined for user %s: %s", user_id, exc)
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.exception("Ingestion failed for doc %s: %s", doc_id, exc)
        raise HTTPException(status_code=500, detail="Ingestion failed")

    # 7. Return result
    return {
        "doc_id": doc_id,
        "filename": filename,
        "chunk_count": result["chunk_count"],
        "status": result["sanitisation_status"],
    }
