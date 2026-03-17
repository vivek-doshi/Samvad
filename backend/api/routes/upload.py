# POST /upload — file ingestion trigger

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

ALLOWED_TYPES = {"pdf", "docx", "csv", "xlsx", "txt"}
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
    filename = file.filename or "upload"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{ext}' not allowed. Permitted: {', '.join(sorted(ALLOWED_TYPES))}",
        )

    # Read file content (enforce size limit)
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds maximum size of 50 MB",
        )

    # 2. Generate doc_id
    doc_id = str(uuid.uuid4())

    # 3. Save file to disk
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
