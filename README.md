# DevSync

AI-powered developer identity automation: a GitHub push tagged with a
`DevSync-Publish: true` commit trailer (or `[devsync:publish]` anywhere in
the message) triggers a LangGraph workflow that analyzes the repository with
Groq, scores it against your existing portfolio projects, and — after your
approval in Discord — updates your portfolio (Supabase), regenerates your
LaTeX résumé (compiled remotely, only in designated slots), and/or posts to
LinkedIn with a generated image.

See [ARCHITECTURE_REFERENCE.md](ARCHITECTURE_REFERENCE.md) for a deep
technical audit of the codebase.

## Processes

Three long-running processes, one queue:

```
GitHub → POST /github/webhook (api) → Redis queue → worker (LangGraph) → Discord (bot process) → worker resumes → publish
```

- **api** (`uvicorn app.main:app`) — webhook receiver + status/OAuth routes. Never runs the AI workflow itself.
- **worker** (`python -m app.workers.worker`) — runs/resumes LangGraph workflows, checkpointed to Postgres after every node.
- **discord-bot** (`python -m app.services.discord_bot_runner`) — the persistent gateway bot that receives Approve/Request-Changes/Reject clicks.

## Setup

1. `cp .env.example .env` and fill in every value (see comments inline). You already have GitHub App, Groq, Redis Cloud, and Discord credentials configured; still missing:
   - `SUPABASE_SERVICE_ROLE_KEY` — Supabase dashboard → Project Settings → API → `service_role` secret (the key currently on file is a publishable/anon key, not this).
   - `SUPABASE_DB_URL` — Project Settings → Database → Connection string → URI (Transaction pooler). Required for migrations and LangGraph checkpointing.
   - `LATEX_COMPILER_URL`/YtoTech — already defaults to the public endpoint and works with no token (verified live).
   - `LINKEDIN_ACCESS_TOKEN` / `LINKEDIN_PERSON_URN` — run the app, visit `GET /linkedin/authorize`, complete the OAuth flow, copy the values `GET /linkedin/callback` returns into `.env`.
   - `POLLINATIONS_API_TOKEN` — optional, works anonymously (verified live).
2. In Supabase: create a **Storage bucket is created automatically** on first write (`resumes`, `devsync-media`) as long as the service-role key has permission; no manual step needed.
3. `pip install -r requirements.txt`
4. `python -m app.db.migrate` — applies `app/db/migrations/*.sql` (pgvector extension, tables, RPC function).
5. Run the three processes (separate terminals, or `docker compose up --build`):
   ```bash
   uvicorn app.main:app --reload
   python -m app.workers.worker
   python -m app.services.discord_bot_runner
   ```
6. Point your GitHub App's webhook at `POST /github/webhook` with `GITHUB_WEBHOOK_SECRET` configured on the App, and install it on the repos you want DevSync watching.

## Tests

```bash
pytest -q
```

Covers webhook signature verification, final-commit detection, protected
LaTeX slot enforcement, scoring/replacement logic, graph routing decisions,
retry behavior, and stale-approval rejection — all offline, no external
credentials required.

## What's been verified live in this environment

A full real GitHub push → webhook → LangGraph pipeline run, all the way
through `score_project` (repository fetched via the GitHub App, analyzed by
Groq, embedded into pgvector, scored against existing portfolio projects),
checkpointed after every node in Supabase Postgres. Also verified
individually: Redis Cloud connectivity, local fastembed embeddings (384-d,
matches the pgvector schema), Pollinations image generation, LinkedIn OAuth
token validity, and a full slot-based résumé render + remote YtoTech compile
producing a real PDF.

**Default Groq model is `qwen/qwen3.6-27b`**, not `llama-3.3-70b-versatile`
(unavailable on this API key's account) and not `openai/gpt-oss-*` (Groq's
gpt-oss models have a tool-name mismatch bug with LangChain's structured
tool-calling — the model generates a correct result but Groq's API rejects
its own tool-name echo; reproducible, not transient — Qwen has no such
issue across all four of this app's structured-output schemas).

**Known Windows-specific fixes applied while testing on this machine:**
RQ's default `Worker` and its `UnixSignalDeathPenalty` job-timeout mechanism
both require POSIX (`os.fork()` / `SIGALRM`), so the worker uses
`SimpleWorker` with a `TimerDeathPenalty` override (see
[app/workers/worker.py](app/workers/worker.py)). The shared Redis client
must NOT set `decode_responses=True` — RQ stores pickled binary job payloads
in Redis, and force-decoding as UTF-8 corrupts them
([app/core/redis_client.py](app/core/redis_client.py)). The logger
reconfigures stdout to UTF-8 on startup, since Windows consoles default to
cp1252 and silently drop any log line with a non-ASCII character
([app/core/logging.py](app/core/logging.py)).

_Live end-to-end DevSync pipeline test — triggered 2026-08-23T23:14:07Z._

_Re-test after clearing the duplicate portfolio entry._
