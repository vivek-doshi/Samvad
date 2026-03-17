You are working on Samvad FastAPI backend.
Phase 3: wire RAG retrieval and session turn saving into the
/chat endpoint. Update existing files — do not recreate them.

=============================================================
UPDATE 1: backend/main.py — startup initialisation
=============================================================

In the lifespan startup section, after db initialisation,
add RAG component initialisation:

  import chromadb
  from backend.rag.embedder import Embedder
  from backend.rag.bm25_index import BM25Index
  from backend.rag.reranker import Reranker
  from backend.rag.query_expander import QueryExpander
  from backend.rag.retriever import Retriever
  from backend.core.context_assembler import ContextAssembler
  from backend.prompts.router import QueryRouter
  from backend.prompts.assembler import PromptAssembler
  from backend.api.routes import upload as upload_router

  # ChromaDB
  chroma_path = os.getenv("CHROMADB_PATH", "runtime/chromadb")
  chroma_client = chromadb.PersistentClient(path=chroma_path)
  app.state.chroma = chroma_client

  # Embedder (on GPU)
  embedder = Embedder(
    model_name_or_path=os.getenv(
      "EMBEDDING_MODEL_PATH", "BAAI/bge-small-en-v1.5"),
    device=os.getenv("EMBEDDING_DEVICE", "cpu"),
  )
  app.state.embedder = embedder

  # BM25 — load all pre-built indices
  bm25 = BM25Index(index_dir=os.getenv(
    "BM25_INDEX_PATH", "runtime/bm25_index"))
  bm25.load_all()
  app.state.bm25 = bm25

  # Reranker (on CPU)
  reranker = Reranker()
  app.state.reranker = reranker

  # Query expander
  expander = QueryExpander()
  app.state.expander = expander

  # Retriever
  retriever = Retriever(
    chroma_client = chroma_client,
    embedder      = embedder,
    bm25          = bm25,
    reranker      = reranker,
    expander      = expander,
    top_k_retrieval = config.get("rag", {}).get("top_k_retrieval", 10),
    top_k_rerank    = config.get("rag", {}).get("top_k_rerank", 5),
    rrf_k           = config.get("rag", {}).get("rrf_k", 60),
  )
  app.state.retriever = retriever

  # Prompt assembler + router
  app.state.prompt_assembler = PromptAssembler()
  app.state.query_router     = QueryRouter()

  # Context assembler
  app.state.context_assembler = ContextAssembler(
    token_manager    = app.state.token_manager,
    prompt_assembler = app.state.prompt_assembler,
  )

  # Add upload router
  app.include_router(upload_router.router)

  # Log RAG readiness
  logger.info("RAG pipeline initialised — ChromaDB: %s", chroma_path)

=============================================================
UPDATE 2: backend/api/routes/chat.py — full RAG integration
=============================================================

Replace the current generate_response function entirely.
Keep the same function signature — just fill in the TODOs.

  async def generate_response(
    request:      ChatRequest,
    llm_client:   LLMClient,
    token_manager: TokenManager,
    config:       dict,
    # New parameters to add:
    retriever:          Retriever,
    context_assembler:  ContextAssembler,
    query_router:       QueryRouter,
    db:                 DBClient,
    user_id:            str | None,
  ) -> AsyncGenerator[str, None]:

  FULL IMPLEMENTATION:

  1. Validate query (existing)

  2. Route the query:
     domain = query_router.route(
       request.query,
       has_uploaded_docs=bool(request.session_id)
     )

  3. Get user doc collections for this session:
     user_doc_collections = []
     if request.session_id and db:
       rows = await db.fetchall(
         """SELECT ud.chroma_collection
            FROM session_documents sd
            JOIN user_documents ud ON sd.doc_id = ud.doc_id
            WHERE sd.session_id = ?
            AND ud.sanitisation_status != 'quarantined'""",
         (request.session_id,)
       )
       user_doc_collections = [r["chroma_collection"] for r in rows]

  4. Get session summary and history:
     session_summary = None
     history_turns   = []
     if request.session_id and db:
       summary_row = await db.fetchone(
         """SELECT summary_text FROM session_summaries
            WHERE session_id = ? AND is_current = 1""",
         (request.session_id,)
       )
       if summary_row:
         session_summary = summary_row["summary_text"]

       turn_rows = await db.fetchall(
         """SELECT role, content FROM turns
            WHERE session_id = ?
            ORDER BY turn_number DESC LIMIT 4""",
         (request.session_id,)
       )
       history_turns = list(reversed(turn_rows))

  5. RAG retrieval:
     retrieved_chunks = []
     if retriever:
       try:
         retrieved_chunks = await retriever.retrieve(
           query      = request.query,
           domain     = domain,
           session_id = request.session_id,
           user_doc_collections = user_doc_collections,
         )
       except Exception as e:
         logger.warning("RAG retrieval failed: %s", e)
         # Continue without RAG — degraded but functional

  6. Assemble context:
     messages, budget = context_assembler.assemble(
       query            = request.query,
       domain           = domain,
       retrieved_chunks = retrieved_chunks,
       session_summary  = session_summary,
       history_turns    = history_turns,
       session_id       = request.session_id,
     )

  7. Save user turn to DB (before streaming):
     turn_id_user = None
     if request.session_id and db and user_id:
       import uuid
       from datetime import datetime, timezone
       turn_id_user = str(uuid.uuid4())
       turn_number  = await _get_next_turn_number(
         db, request.session_id)
       await db.execute(
         """INSERT INTO turns
            (turn_id, session_id, user_id, turn_number, role,
             content, domain, tokens_input, retrieval_used, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
         (turn_id_user, request.session_id, user_id,
          turn_number, "user", request.query, domain,
          budget.get("query_tokens", 0),
          1 if retrieved_chunks else 0,
          datetime.now(timezone.utc).isoformat())
       )

  8. Stream response + accumulate full text:
     full_response = ""
     try:
       model_cfg = config.get("model", {})
       async for token in llm_client.stream_chat(
         messages,
         max_tokens    = model_cfg.get("max_tokens_generation", 1024),
         temperature   = model_cfg.get("temperature", 0.3),
         top_p         = model_cfg.get("top_p", 0.95),
         repeat_penalty = model_cfg.get("repeat_penalty", 1.1),
       ):
         full_response += token
         yield f"data: {json.dumps({'token': token, 'done': False})}\n\n"

  9. Build sources for response:
     sources = [
       {
         "document": c.source_name,
         "section":  c.metadata.get("section_number"),
         "page":     c.metadata.get("page_number"),
       }
       for c in retrieved_chunks[:5]
     ]

  10. Send done event with sources:
      yield f"data: {json.dumps({'token': '', 'done': True, 'sources': sources})}\n\n"

  11. Save assistant turn to DB (after streaming):
      if request.session_id and db and user_id:
        turn_id_asst = str(uuid.uuid4())
        await db.execute(
          """INSERT INTO turns
             (turn_id, session_id, user_id, turn_number, role,
              content, domain, tokens_output, sources_cited,
              retrieval_used, created_at)
             VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
          (turn_id_asst, request.session_id, user_id,
           turn_number + 1, "assistant", full_response,
           domain, budget.get("generation_budget", 0),
           json.dumps(sources), 1 if retrieved_chunks else 0,
           datetime.now(timezone.utc).isoformat())
        )
        # Update session last_active_at and total_turns
        await db.execute(
          """UPDATE sessions SET
             last_active_at = ?, total_turns = total_turns + 2,
             domain_last = ?
             WHERE session_id = ?""",
          (datetime.now(timezone.utc).isoformat(),
           domain, request.session_id)
        )

  Add helper function in chat.py:
  async def _get_next_turn_number(db: DBClient,
                                  session_id: str) -> int:
    row = await db.fetchone(
      "SELECT MAX(turn_number) as max_turn FROM turns WHERE session_id=?",
      (session_id,)
    )
    return (row["max_turn"] or 0) + 1

  Update the chat() endpoint to pull new dependencies from app.state:
    retriever         = request.app.state.retriever
    context_assembler = request.app.state.context_assembler
    query_router      = request.app.state.query_router
    db                = request.app.state.db

  Also extract user_id from JWT if auth header present:
    from backend.security.auth import decode_token
    user_id = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
      try:
        payload  = decode_token(auth_header[7:])
        user_id  = payload.get("sub")
      except Exception:
        pass   # Phase 1 compat — no auth required yet

  Pass all new args to generate_response.

=============================================================
UPDATE 3: backend/api/routes/upload.py — file upload endpoint
=============================================================

  ROUTER: APIRouter(prefix="/api/upload", tags=["upload"])

  POST /api/upload
    Requires: Depends(get_current_user_id)
    Accepts: multipart/form-data with file + session_id field
    Max file size: 50MB (from config)

    1. Validate file type — allowed: pdf, docx, csv, xlsx, txt
       Return 400 if not allowed

    2. Generate doc_id = str(uuid4())

    3. Save file to runtime/user_uploads/{user_id}/{doc_id}_{filename}

    4. Insert into user_documents table:
       INSERT user_documents (doc_id, user_id, filename, file_type,
       file_size_bytes, sanitisation_status, indexed_at)
       VALUES (?,?,?,?,?,'pending',now())

    5. Insert into session_documents (session_id, doc_id, attached_at)

    6. Call await ingester.ingest(file_path, filename, file_type,
                                  session_id, user_id, doc_id, db)

    7. Return:
       { "doc_id": str, "filename": str,
         "chunk_count": int, "status": str }

  Inject ingester from app.state.ingester
  (add to main.py startup):
    from backend.rag.ingestion import DocumentIngester
    app.state.ingester = DocumentIngester(
      embedder      = app.state.embedder,
      chroma_client = app.state.chroma,
      bm25          = app.state.bm25,
    )