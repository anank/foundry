# CLAUDE.md — The Foundry

**For:** Claude Code agents working on this repository
**Owner:** Anang (Bali)
**Companion docs:**
- `revision.md` — redesign plan (card system, SSH execution, multi-provider LLM)

---

## 1. What This Project Is

The Foundry is a personal idea-to-deployment system. It is a **task execution system** — the home page shows your next task per project, and you run it on any configured device with one click.

Triage (idea killer, feature killer, etc.) is still available as an optional standalone page, but it is no longer the main flow.

---

## 2. Architecture Overview

- **SQLite** at `~/.foundry/foundry.db` is the single source of truth. No vault markdown files.
- **FastAPI + HTMX + Tailwind** dashboard at `http://localhost:8000`.
- **Devices** are first-class: add SSH-connected machines, configure per-project paths, click Run to launch `claude` in a tmux session on that device.
- **LLM config** lives in the DB: Providers → Models → Roles (3-level). API keys stored as env var names only.
- **Triage** page accepts a textarea input, runs the coordinator pipeline, shows verdict inline.

---

## 3. Tech Stack

### 3.1 Languages and frameworks
- **Python 3.11+** — the entire backend
- **FastAPI** — dashboard backend
- **HTMX + Tailwind** — dashboard frontend (CDN, no build step)
- **Typer** — CLI
- **LiteLLM** — multi-provider AI calls (Anthropic, OpenAI-compatible, local Ollama)
- **Pydantic v2** — data models throughout
- **SQLite** (stdlib `sqlite3`) — primary database, no ORM
- **FastMCP** — MCP server (out of scope for this redesign, may be broken)

### 3.2 Forbidden choices
- ❌ No new database engines (SQLite is sufficient)
- ❌ No Docker for v1
- ❌ No frontend frameworks beyond HTMX
- ❌ No new languages (Python only)
- ❌ No async I/O complexity beyond what FastAPI provides natively
- ❌ No paramiko — SSH via subprocess calling the `ssh` CLI

---

## 4. Directory Layout

```
foundry/
├── CLAUDE.md                       # This file
├── revision.md                     # Redesign plan
├── pyproject.toml
├── .env.example
│
├── foundry/                        # Python package
│   ├── cli.py                      # Typer entry point
│   ├── config.py                   # Env var loading
│   │
│   ├── llm/
│   │   ├── base.py                 # TriageLLM interface + LLMResponse
│   │   ├── dispatcher.py           # LiteLLMDispatcher — reads config from DB
│   │   └── audit.py                # ~/.foundry/audit.jsonl writer
│   │
│   ├── triage/
│   │   ├── schema.py               # Pydantic verdict models (extracted from vault/schema.py)
│   │   ├── coordinator.py          # Orchestrates the full pipeline
│   │   ├── classifier.py
│   │   ├── idea_killer.py
│   │   ├── feature_killer.py
│   │   ├── bug_triage.py
│   │   ├── interviewer.py
│   │   ├── critic.py
│   │   ├── atomizer.py
│   │   └── task_tagger.py
│   │
│   ├── vault/
│   │   └── schema.py               # Kept for backward compat — imports from triage/schema.py
│   │
│   ├── devices/
│   │   └── manager.py              # DeviceManager: list, get, current_device_id, is_local
│   │
│   ├── executor/
│   │   ├── runner.py               # dispatch(task_id, device_id) — SSH + tmux launcher
│   │   └── ssh.py                  # SSHRunner: run, run_in_tmux, tmux_session_exists
│   │
│   ├── dashboard/
│   │   ├── app.py                  # FastAPI app, router registration, startup
│   │   ├── db.py                   # Schema init + repository helpers
│   │   ├── llm.py                  # get_dispatcher() — reads from DB
│   │   ├── routes/
│   │   │   ├── index.py            # Home: card grid + quick-add
│   │   │   ├── projects.py         # Project CRUD + task run endpoint
│   │   │   ├── devices.py          # Device CRUD + test endpoint
│   │   │   ├── triage.py           # Triage page (textarea input) + graveyard
│   │   │   ├── review.py           # Review queue
│   │   │   └── settings.py         # LLM providers/models/roles
│   │   ├── templates/
│   │   │   ├── base.html
│   │   │   ├── index.html
│   │   │   ├── projects.html
│   │   │   ├── project_detail.html
│   │   │   ├── project_new.html
│   │   │   ├── devices.html
│   │   │   ├── device_form.html
│   │   │   ├── triage.html
│   │   │   ├── graveyard.html
│   │   │   ├── review.html
│   │   │   ├── review_card_done.html
│   │   │   ├── settings_models.html
│   │   │   ├── 404.html
│   │   │   └── partials/
│   │   └── static/
│   │       └── app.css
│   │
│   ├── notifications/              # Untouched
│   └── mcp/                        # Out of scope — may be broken after vault removal
│       └── server.py
│
└── tests/
    └── test_*.py
```

---

## 5. Database Schema

Single SQLite file at `~/.foundry/foundry.db` (override with `FOUNDRY_DB_PATH` env var).

```sql
projects(id, name UNIQUE, description, spec, github_url, status, priority, created_at, updated_at)
devices(id, device_id UNIQUE, display_name, os, ssh_host, ssh_port, ssh_user, notes, created_at, updated_at)
project_device_paths(id, project_id FK, device_id FK, local_path, UNIQUE(project_id, device_id))
tasks(id, project_id FK, title, description, status, priority, created_at, updated_at)
  -- status: queued | running | review | approved | rejected | failed
task_runs(id, task_id FK, device_id FK, tmux_session, command, status, exit_code, log_path, started_at, finished_at)
llm_providers(id, name UNIQUE, type, base_url, api_key_env_var, created_at)
  -- type: 'anthropic' | 'openai_compatible'
llm_models(id, provider_id FK, model_id, display_name, context_window, UNIQUE(provider_id, model_id))
llm_roles(id, role_name UNIQUE, model_id FK)
graveyard_entries(id, source_text, verdict, reasoning_json, killed_at, revival_condition)
```

Migration strategy: hard reset on startup if schema version changes. No data preserved from old vault.

---

## 6. Key Env Vars

```
FOUNDRY_DB_PATH=~/.foundry/foundry.db   # override DB location
FOUNDRY_DEVICE_ID=my-macbook            # identifies this machine for Run buttons
FOUNDRY_LOG_LEVEL=INFO
```

API keys are stored in the DB as env var **names** (e.g. `ANTHROPIC_API_KEY`), not values. The dispatcher reads `os.environ[api_key_env_var]` at call time.

---

## 7. The TriageLLM Abstraction

Every AI call goes through `TriageLLM.analyze()`. The dispatcher reads provider/model config from the DB `llm_providers`, `llm_models`, `llm_roles` tables.

- `anthropic` provider type → bare model name to LiteLLM (e.g. `claude-sonnet-4-6`)
- `openai_compatible` provider type → `openai/<model_id>` with `api_base=provider.base_url`

Audit log at `~/.foundry/audit.jsonl` — one JSONL line per LLM call with prompt hash (not plaintext).

---

## 8. SSH + tmux Execution

Run button flow:
1. Resolve `project_device_paths` for (project, device) — error if missing
2. Build tmux session name `foundry-task-{task_id}`
3. If local device (`device_id == FOUNDRY_DEVICE_ID`): spawn `tmux new-session -d -s <session> -- bash -c 'cd <path> && claude --dangerously-skip-permissions "<task>" 2>&1 | tee <log>'`
4. If remote: same command via `ssh <ssh_host> -p <ssh_port> '...'`
5. Insert `task_runs` row, update `tasks.status = running`

User attaches via `tmux attach -t foundry-task-<id>` to watch. Status updated manually via Review page.

---

## 9. Testing

```bash
pytest tests/                    # fast, no API calls, no SSH
pytest tests/ -m real            # real API calls, costs money
```

Test files:
- `tests/test_db.py` — schema init, repo helpers
- `tests/test_devices.py` — DeviceManager
- `tests/test_executor.py` — dispatch logic (mocked SSH)
- `tests/test_coordinator.py` — triage pipeline (FakeLLM)
- `tests/test_dashboard_*.py` — route tests (TestClient)

FakeLLM in `tests/conftest.py` returns canned responses by role. Tests never make real API calls or SSH connections.

---

## 10. Working With Anang

- Direct feedback preferred over validation
- Push back when something seems off
- Concise > verbose, but show reasoning when it matters
- Anang post-resignation, transitioning to algo trading + AI projects, operates from Bali
- Existing systems: Pipnesiatest EA, AI Ticket Tool, Multi-Agent Content System, Skill Harness, bank statement pipeline

---

## 11. Done Definition

1. App starts: `foundry dashboard` → http://localhost:8000 loads
2. Can add a device, a project, a task
3. Run button dispatches to local device via tmux
4. Triage page accepts textarea, shows verdict
5. LLM settings: add provider + model + role, test button works
6. `pytest tests/` passes (all mocked)
