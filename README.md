# Samvad
### Powered by Arthvidya

Local finance decision-support interface. Queries the Indian Income Tax Act 2025,
analyses uploaded financial documents, and provides equity and tax guidance —
all grounded in retrieved evidence. Nothing leaves the machine.

---

## Quick Start

```bash
# 1. Clone and configure
cp .env.example .env
nano .env          # fill in SECRET_KEY and model paths

# 2. Place model file
cp /path/to/arthvidya-4b-q4_k_m.gguf models/arthvidya/

# 3. Place corpus PDFs
cp income_tax_act_2025.pdf    data/corpus/income_tax_act_2025/
cp sebi_lodr_2015.pdf         data/corpus/sebi_regulations/
# ... add remaining regulatory PDFs

# 4. Index the corpus (one-time, takes ~10-15 minutes)
cd backend
python scripts/index_corpus.py

# 5. Create first user
python scripts/setup_first_user.py

# 6. Start everything
cd ..
docker-compose up -d

# Samvad is now at http://localhost:4200
```

---

## Project Layout

```
samvad/
│
├── frontend/              Angular UI — chat, sidebar, file upload
├── backend/               FastAPI — API, RAG pipeline, security
├── data/corpus/           Source PDFs — IT Act, SEBI, FEMA, DTAA (not in git)
├── runtime/               Generated at runtime — ChromaDB, SQLite, uploads
├── models/                GGUF model files (not in git)
├── config/                samvad.yaml, corpus_manifest.json
├── infra/                 Dockerfiles, nginx config
└── docs/                  Architecture, API reference, setup guides
```

Full structure documented in `docs/architecture.md`.

---

## Two Components

| Name | Role |
|------|------|
| **Arthvidya** | The fine-tuned 4B parameter finance LLM (the brain) |
| **Samvad** | This interface — Angular + FastAPI + RAG pipeline (the interface) |

Arthvidya is trained separately in the training WSL2 environment.
Samvad runs the trained model via llama-cpp-python server.

---

## Architecture

```
Angular UI ──SSE──▶ FastAPI ──▶ Session Manager ──▶ Context Assembler
                       │                                    │
                       ├──▶ Input Sanitiser                 │
                       ├──▶ Query Router                    ▼
                       └──▶ RAG Retriever ──────▶ llama-cpp-python
                                │                   (Arthvidya 4B)
                         ChromaDB + BM25
                         (IT Act + SEBI +
                          FEMA + DTAA +
                          user uploads)
```

---

## Environment Notes

- **Training**: Separate WSL2 instance. Do NOT mix with Samvad Docker.
- **GPU**: RTX 5070 12GB. VRAM budget ~5.6GB, headroom ~6.4GB.
- **Database**: SQLite for MVP. PostgreSQL migration path documented — zero schema changes required.
- **Context**: 32K tokens. Rolling summary keeps history compact.
