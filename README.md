# Private Audio Intelligence

Self-hosted pipeline for turning recorded meetings into searchable, summarized transcripts. Drop in an audio file, get back a cleaned-up transcript, a structured summary, key points, decisions, and action items. Designed to run entirely on your own infrastructure — no third-party API calls required unless you opt in.

Primary use case: Greek-language meeting recordings (configurable). Pipeline is language-agnostic and works with any language Whisper supports.

---

## What it does

- **Upload** audio (m4a, mp3, wav, flac, ogg, aac, webm, mp4) up to 2 GB by default
- **In-browser recorder** for quick captures (no upload needed)
- **Transcribe** with [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (default model: `large-v3-turbo`, CPU `int8` quantization)
- **Chunk** long audio into overlapping windows so memory stays bounded
- **Diarize** (optional) — identify *who said what* with [pyannote-audio](https://github.com/pyannote/pyannote-audio)
- **Clean** the raw transcript (whitespace, repetition, sentence boundaries)
- **Summarize** with a local Ollama model by default, or OpenAI / Anthropic if configured
- **Organize**: tag each recording with title, project, description, meeting date, and participants
- **Export** as `.txt`, `.clean.txt`, `.summary.md`, `.srt`, or `.json`
- **Per-stage timing logs** with real-time-factor (RTF) so you can see where time goes

---

## Architecture

```
                ┌──────────┐
                │  Browser │
                └────┬─────┘
                     │ :8080
                ┌────▼─────┐
                │  nginx   │  reverse proxy
                └────┬─────┘
        ┌────────────┼────────────┐
        │            │            │
   /api/*       /  (SSR)    /_nuxt/*
        │            │            │
┌───────▼────┐  ┌────▼─────┐      │
│  backend   │  │ frontend │◄─────┘
│ (FastAPI)  │  │ (Nuxt 3) │
└─┬──────┬───┘  └──────────┘
  │      │
  │   ┌──▼────────┐
  │   │   redis   │◄──────┐
  │   └───────────┘       │
  │                       │ RQ queue 'audio'
  │   ┌──────────┐        │
  └──►│ postgres │◄───┬───┘
      └──────────┘    │
                  ┌───▼─────┐
                  │ worker  │  ffmpeg, faster-whisper,
                  │  (RQ)   │  pyannote, summarizer
                  └────┬────┘
                       │
                  ┌────▼─────────┐
                  │ /data volumes │  uploads, outputs, models
                  └───────────────┘
```

### Services

| Service | Image / Build | Purpose |
|---|---|---|
| `nginx` | `./nginx/Dockerfile` | TLS termination point, reverse proxy. Routes `/api/*` to backend, everything else to frontend. Exposes port `${HTTP_PORT}` (default 8080). |
| `frontend` | `./frontend/Dockerfile` | Nuxt 3 (SSR + Vite), Tailwind, Pinia. UI for upload, recording, job list, transcript viewer. |
| `backend` | `./backend/Dockerfile` | FastAPI app. Authentication, upload, job CRUD, transcript downloads. Runs `alembic upgrade head` at startup. |
| `worker` | `./worker/Dockerfile` | Python RQ worker subscribed to the `audio` queue. Contains ffmpeg, faster-whisper, pyannote-audio, torch. Heavy image (~3 GB). |
| `postgres` | `postgres:16-alpine` | Users, audio jobs, chunks, transcripts. |
| `redis` | `redis:7-alpine` | RQ broker and result backend. |
| `ollama` | `ollama/ollama:latest` | Optional. Behind the `ollama` profile. Local LLM host for summarization. |

### Persistent volumes

- `audio_uploads` — original uploaded files
- `audio_outputs` — generated artifacts
- `whisper_models` — downloaded faster-whisper / pyannote weights (so rebuilds don't re-download)
- `postgres_data`, `redis_data`, `ollama_data`

---

## The audio processing pipeline

Each upload triggers an RQ job that runs through these stages. Per-stage time is logged at completion with overall **real-time factor (RTF)** = `processing_time / audio_duration`.

| # | Stage | What it does | Typical share of total time |
|---|---|---|---|
| 1 | `validate` | Read file header, extract duration via ffprobe | <1% |
| 2 | `convert` | ffmpeg → 16 kHz mono WAV | <1% |
| 3 | `chunk` | Split WAV into `CHUNK_SECONDS`-long pieces with `OVERLAP_SECONDS` overlap | <1% |
| 4 | `transcribe` | faster-whisper inference, per chunk, sequentially | **~95%+** on CPU |
| 5 | `diarize` (optional) | pyannote pipeline on full audio, then align speakers to whisper segments | varies, often ~realtime |
| 6 | `merge_clean` | Stitch chunk transcripts (resolving overlap), basic text cleanup | <1% |
| 7 | `summarize` | LLM call (Ollama / OpenAI / Anthropic) — produces summary, key_points, decisions, action_items | 1–5% |

Sample log line on completion:

```
timings job=<uuid> audio=305.3s total=583.4s rtf=1.91x | validate=7.94s(1%) convert=1.96s(0%) chunk=0.04s(0%) transcribe=569.96s(98%) merge_clean=0.00s(0%) summarize=3.55s(1%)
```

---

## Quick start

Prerequisites: Docker + Docker Compose. ~10 GB disk for images + models. ~4 GB RAM minimum, 8 GB recommended.

```bash
git clone git@github.com:BillyTziv/audio-intel.git
cd audio-intel

# 1. Configure
cp .env.example .env   # then edit — at minimum set passwords + JWT_SECRET
#    or create .env from scratch (see Configuration below)

# 2. Boot the stack
docker compose up -d --build

# 3. Open the app
#    http://localhost:8080 — log in with ADMIN_USERNAME / ADMIN_PASSWORD
```

To enable the local Ollama LLM (free, fully local summarization):

```bash
docker compose --profile ollama up -d ollama
docker compose exec ollama ollama pull llama3.1:8b
```

---

## Configuration

Everything is driven by environment variables. See the table below for the important ones. Reasonable defaults exist for everything except secrets.

### Required

| Var | Purpose |
|---|---|
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | Database credentials |
| `JWT_SECRET` | JWT signing secret. Generate with `openssl rand -hex 32` |
| `ADMIN_USERNAME`, `ADMIN_PASSWORD` | Seeded on first start. Subsequent changes need a DB update. |

### Whisper transcription

| Var | Default | Notes |
|---|---|---|
| `WHISPER_MODEL` | `large-v3-turbo` | Multilingual. ~6× faster than `large-v3` on CPU. Alternatives: `large-v3`, `medium`, `small`. |
| `WHISPER_DEVICE` | `cpu` | `cuda` for GPU (typically 10–30× faster). |
| `WHISPER_COMPUTE_TYPE` | `int8` | Use `float16` on GPU. |
| `WHISPER_LANGUAGE` | `el` (Greek) | ISO-639-1 code; `auto` lets Whisper detect. |
| `CHUNK_SECONDS` | `900` | 15-minute chunks. |
| `OVERLAP_SECONDS` | `10` | Overlap between adjacent chunks (used for stitching). |

### Diarization (optional)

| Var | Default | Notes |
|---|---|---|
| `DIARIZATION_ENABLED` | `false` | Global kill switch. Even with this true, each job opts in via the `diarize` flag. |
| `DIARIZATION_MODEL` | `pyannote/speaker-diarization-3.1` | Gated on HuggingFace — accept the user agreement first. |
| `HF_TOKEN` | (empty) | HuggingFace access token (https://huggingface.co/settings/tokens). |
| `DIARIZATION_DEVICE` | `cpu` | `cuda` if available. |

### Summarization LLM

| Var | Default | Notes |
|---|---|---|
| `LLM_PROVIDER` | `ollama` | One of `ollama`, `openai`, `anthropic`, `none`. |
| `LLM_MODEL` | `llama3.1:8b` | Provider-specific. |
| `OLLAMA_URL` | `http://ollama:11434` | Only used when provider=ollama. |
| `OPENAI_API_KEY` | (empty) | Required if provider=openai. |
| `ANTHROPIC_API_KEY` | (empty) | Required if provider=anthropic. |

### Demo login (development convenience)

| Var | Notes |
|---|---|
| `DEMO_USERNAME`, `DEMO_PASSWORD` | When both are set, the login page shows a "Use demo credentials" button + copy-pasteable hint. Leave blank in production. |

### Other

| Var | Default | Notes |
|---|---|---|
| `HTTP_PORT` | `8080` | Host port that nginx listens on. |
| `MAX_UPLOAD_MB` | `2048` | Per-file upload limit. |
| `WORKER_MEMORY_LIMIT` | `8g` | Docker memory cap on the worker container. |
| `LOG_LEVEL` | `INFO` | Standard Python log level. |

---

## API surface

All endpoints under `/api/*`. Authentication: `Authorization: Bearer <jwt>`.

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/auth/login` | Returns JWT |
| `GET` | `/api/auth/me` | Current user |
| `POST` | `/api/audio/upload` | Multipart form. Fields: `file`, `diarize`, `title`, `project`, `description`, `meeting_date`, `participants` |
| `GET` | `/api/audio/jobs` | Paginated list |
| `GET` | `/api/audio/jobs/{id}` | Single job |
| `PATCH` | `/api/audio/jobs/{id}` | Update metadata (title, project, description, meeting_date, participants) |
| `GET` | `/api/audio/jobs/{id}/transcript` | Full transcript JSON |
| `GET` | `/api/audio/jobs/{id}/download/{fmt}` | `fmt` ∈ `txt`, `clean`, `summary`, `srt`, `json` |

---

## Performance notes

Numbers from a Greek 5-minute m4a meeting recording, CPU `int8`:

| Config | Total time | Transcribe RTF |
|---|---|---|
| `large-v3` + `beam_size=5` | 884.5 s | 2.90× (slower than realtime) |
| `large-v3-turbo` + `beam_size=1` (default) | 583.4 s | 1.91× |
| Both + first-run model download | (above includes ~60 s download) | — |

**What to do for more speed:**
- **GPU.** Single biggest jump. Set `WHISPER_DEVICE=cuda`, `WHISPER_COMPUTE_TYPE=float16`. Expect 10–30× speedup. Requires nvidia-docker.
- **Smaller model.** `medium` or `small` give another ~2–4× at noticeable quality cost.
- **Parallel chunks.** Long recordings benefit from running multiple RQ workers — each picks up a different job, but currently chunks within one job are sequential. Refactoring transcribe to dispatch chunks to a worker pool is a future improvement.
- **Diarization on CPU is slow.** Pyannote runs on the whole audio file and is not chunk-parallelizable. For meetings, plan on diarization adding roughly 0.5–1× realtime on top of transcription.

---

## Recording metadata

Each upload optionally carries:

| Field | Type | Purpose |
|---|---|---|
| `title` | string | Human label. Falls back to filename if empty. |
| `project` | string (indexed) | Grouping field. Future RAG / Q&A boundary. |
| `description` | text | Free-form context, fed into the summarizer. |
| `meeting_date` | timestamptz | Actual meeting time (separate from upload time). |
| `participants` | text[] | Names of people in the recording. Pairs with diarization for speaker→name mapping. |

Editable after the fact via `PATCH /api/audio/jobs/{id}` (and the **Edit details** button on the job detail page).

---

## Project structure

```
.
├── backend/                  FastAPI app
│   ├── alembic/versions/     DB migrations
│   ├── app/
│   │   ├── api/              Routers: auth, audio
│   │   ├── core/             Security primitives (JWT, password hashing)
│   │   ├── models/           SQLAlchemy ORM models
│   │   ├── schemas/          Pydantic request/response models
│   │   └── services/         Auth, queue, storage
│   └── Dockerfile
├── worker/                   RQ worker
│   ├── app/
│   │   ├── pipeline/         validate, convert, chunk, transcribe, diarize,
│   │   │                     merge, clean, summarize, llm
│   │   └── tasks.py          Orchestrates one job end to end
│   └── Dockerfile
├── frontend/                 Nuxt 3 SPA/SSR
│   ├── components/           UploadForm, Recorder, JobList, TranscriptViewer, …
│   ├── composables/          useApi
│   ├── pages/                index, login, jobs/[id]
│   └── nuxt.config.ts
├── nginx/                    Reverse proxy config
├── docker-compose.yml
└── .env                      gitignored — your secrets live here
```

---

## Known limitations

- **Single-user.** One admin account; no signup flow, no multi-tenant. Adequate for personal / single-team use.
- **First-job overhead.** Whisper model loads on first transcribe call (~30–60 s). After that the model stays in memory.
- **Worker chunk parallelism.** Within a single job, chunks are transcribed sequentially.
- **No real-time streaming.** Audio must be uploaded as a complete file. No partial transcripts during recording.
- **Diarization quality** is limited by pyannote — fine for 2–4 distinct speakers, degrades on noisy / overlapping speech.
- **Postgres-only.** The migrations assume PostgreSQL (uses `JSONB`, `ARRAY`, enum types).

---

## License

Private project. No license granted.
