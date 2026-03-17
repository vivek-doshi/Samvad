samvad/
│
├── .env.example              ← copy to .env, fill in secrets
├── .gitignore                ← models/, runtime/, corpus PDFs excluded
├── docker-compose.yml        ← three services: model-server, backend, frontend
├── README.md                 ← quick start guide
│
├── config/
│   ├── samvad.yaml           ← all tunable parameters (token budgets, RAG settings, corpus registry)
│   ├── corpus_manifest.json  ← auto-updated by index_corpus.py — tracks what is indexed
│   └── logging.yaml          ← log format, rotation, level
│
├── frontend/                 ← Angular application
│   ├── Dockerfile            ← ng build → nginx serve
│   ├── nginx.conf            ← proxy /api/* to backend:8000
│   └── src/app/
│       ├── chat/             ← ChatComponent — streaming message list
│       ├── sidebar/          ← SidebarComponent — session history from SQLite
│       ├── upload/           ← FileUploadComponent — drag-drop, progress
│       ├── sources/          ← SourcesPanelComponent — RAG citations display
│       ├── auth/             ← LoginComponent — JWT auth
│       ├── shared/           ← MessageComponent, MarkdownPipe, DisclaimerComponent
│       ├── services/         ← ChatService (SSE), SessionService, UploadService, AuthService
│       └── models/           ← TypeScript interfaces — Session, Message, Document, User
│
├── backend/                  ← FastAPI application
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py               ← FastAPI app entry, CORS, middleware registration
│   ├── config.py             ← Pydantic settings, loads from .env + samvad.yaml
│   │
│   ├── api/
│   │   ├── routes/
│   │   │   ├── auth.py       ← POST /auth/login, POST /auth/logout
│   │   │   ├── chat.py       ← POST /chat — SSE streaming endpoint
│   │   │   ├── sessions.py   ← GET/POST/DELETE /sessions
│   │   │   ├── upload.py     ← POST /upload — file ingestion trigger
│   │   │   ├── corpus.py     ← GET /corpus — what is indexed, admin only
│   │   │   └── health.py     ← GET /health — model + DB + ChromaDB status
│   │   └── middleware/
│   │       ├── auth_middleware.py   ← JWT validation on every request
│   │       └── rate_limiter.py      ← prevents brute force on /auth/login
│   │
│   ├── core/
│   │   ├── llm_client.py         ← async HTTP client to llama-cpp-python server
│   │   ├── token_manager.py      ← 32K budget allocator
│   │   ├── session_manager.py    ← two-store: SQLite (persistent) + dict (active)
│   │   └── context_assembler.py  ← assembles [system + summary + history + chunks + query]
│   │
│   ├── rag/
│   │   ├── ingestion.py      ← parse → chunk → embed → store (for user uploads)
│   │   ├── chunkers.py       ← hierarchical chunker (IT Act) + semantic chunker (user docs)
│   │   ├── embedder.py       ← BGE-small wrapper, batch embedding
│   │   ├── retriever.py      ← vector + BM25 + RRF + rerank + parent promotion
│   │   ├── reranker.py       ← cross-encoder MiniLM wrapper
│   │   ├── bm25_index.py     ← BM25 build, serialise, load, query
│   │   ├── query_expander.py ← rule-based expansion ("80C" → "section 80C deduction limit")
│   │   └── web_search.py     ← DuckDuckGo fallback, sanitises results
│   │
│   ├── prompts/
│   │   ├── library.py        ← all prompt templates (BASE, TAX, EQUITY, RISK, DOC, GENERAL)
│   │   ├── router.py         ← keyword classifier → domain
│   │   └── assembler.py      ← combines base + domain + format + injection shield
│   │
│   ├── security/
│   │   ├── auth.py               ← bcrypt, JWT issue/verify
│   │   ├── input_sanitiser.py    ← Layer 1: user input cleaning
│   │   ├── document_sanitiser.py ← Layer 2: upload scanning
│   │   ├── output_validator.py   ← Layer 4: response validation
│   │   └── conversation_guard.py ← multi-turn injection detection
│   │
│   ├── db/
│   │   ├── schema.sql            ← full validated schema (8 tables, 5 views, 13 indexes)
│   │   ├── db_client.py          ← aiosqlite wrapper, PRAGMA setup
│   │   ├── models.py             ← Pydantic models matching DB tables
│   │   ├── migrations/
│   │   │   └── 001_initial_schema.sql
│   │   └── seeds/
│   │       └── seed_admin_user.py
│   │
│   ├── scripts/
│   │   ├── index_corpus.py       ← ONE-TIME: parse PDFs → chunk → embed → ChromaDB + BM25
│   │   ├── setup_first_user.py   ← create admin user, prompt for password
│   │   ├── benchmark_retrieval.py ← test RAG quality against curated questions
│   │   ├── verify_model.py       ← check GGUF file, test llama-server connection
│   │   └── export_session.py     ← export session to PDF/Markdown (F13)
│   │
│   └── tests/
│       ├── unit/                 ← sanitiser, router, token_manager, chunkers
│       └── integration/          ← full retrieval pipeline, chat pipeline, injection defence
│
├── data/
│   └── corpus/                   ← source PDFs — not in git, mounted read-only
│       ├── income_tax_act_2025/  ← IT Act 2025 full text PDF
│       ├── sebi_regulations/     ← LODR, ICDR, Takeover, PIT regulations
│       ├── fema/                 ← FEMA 1999 + key notifications
│       ├── dtaa/                 ← 94 DTAA PDFs
│       ├── companies_act/        ← Companies Act 2013 (finance chapters)
│       └── books/                ← MBA/CA textbooks (optional corpus)
│
├── runtime/                      ← generated data — Docker volume, never in git
│   ├── chromadb/                 ← ChromaDB persistent vector store
│   ├── bm25_index/               ← serialised BM25 pickle files
│   ├── sqlite/                   ← samvad.db — sessions, users, turns, summaries
│   ├── user_uploads/             ← uploaded files, scoped by user_id/session_id
│   └── session_exports/          ← exported PDFs/Markdown
│
├── models/                       ← GGUF + embedding + reranker — not in git
│   ├── arthvidya/                ← arthvidya-4b-q4_k_m.gguf
│   ├── embeddings/               ← bge-small-en-v1.5/
│   └── reranker/                 ← cross-encoder-ms-marco-MiniLM-L-6-v2/
│
├── infra/
│   ├── nginx/nginx.conf          ← proxy Angular → backend API
│   └── docker/
│       ├── backend.Dockerfile
│       ├── frontend.Dockerfile
│       └── model_server.Dockerfile
│
└── docs/
    ├── setup.md                  ← step-by-step setup guide
    ├── architecture.md           ← system design reference
    ├── rag_pipeline.md           ← RAG pipeline explained
    ├── api_reference.md          ← all FastAPI endpoints
    └── security.md               ← 4-layer defence documentation
