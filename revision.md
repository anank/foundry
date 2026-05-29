# Foundry Redesign — Card System, SSH Execution, Multi-Provider LLM

## What changed and why

The original Foundry treated triage as the main flow: brain dump → classifier → killer → tasks. Data lived in markdown files under `vault/`, indexed into SQLite as a cache. The executor ran `claude -p` as a local subprocess only.

This redesign pivots to **task execution as the main flow**:

- Home is a card grid of next tasks per project, with a quick-add widget.
- Each card has Run buttons per device. Run = SSH to that device, cd to the project's path on that device, launch `claude` inside a named tmux session. Resumable.
- Devices are first-class (CRUD). Per-project per-device paths replace the single `local_path` field.
- SQLite at `~/.foundry/foundry.db` is the source of truth. No vault markdown files.
- Triage becomes an optional standalone page (paste idea → verdict). Brain dump removed.
- LLM settings rebuilt as Providers → Models → Roles (3-level). API keys stored as env var names only.

---

## Files added

| File | Purpose |
|------|---------|
| `foundry/devices/__init__.py` | Package init |
| `foundry/devices/manager.py` | DeviceManager: list, get, current_device_id, is_local |
| `foundry/executor/ssh.py` | SSHRunner: run, run_in_tmux, run_local_in_tmux |
| `foundry/triage/schema.py` | Pydantic verdict models (extracted from vault/schema.py) |
| `foundry/dashboard/routes/devices.py` | Device CRUD + SSH test endpoint |
| `foundry/dashboard/templates/devices.html` | Device list |
| `foundry/dashboard/templates/device_form.html` | Device add/edit form |
| `foundry/dashboard/templates/partials/project_card.html` | Home card |
| `foundry/dashboard/templates/partials/task_list.html` | Task list partial |
| `foundry/dashboard/templates/partials/device_paths.html` | Per-project device paths |
| `foundry/dashboard/templates/partials/providers_list.html` | LLM providers partial |
| `foundry/dashboard/templates/partials/models_list.html` | LLM models partial |
| `foundry/dashboard/templates/partials/roles_list.html` | LLM roles partial |
| `foundry/dashboard/templates/partials/triage_result.html` | Triage verdict partial |
| `tests/test_db.py` | DB schema + repo helper tests |
| `tests/test_devices.py` | DeviceManager tests |
| `tests/test_dashboard.py` | Dashboard route tests (TestClient) |

## Files rewritten

| File | What changed |
|------|-------------|
| `foundry/dashboard/db.py` | Full new schema + all repo helpers |
| `foundry/dashboard/app.py` | Removed brain_dump/pipeline routers, added devices, startup init_db |
| `foundry/dashboard/llm.py` | get_dispatcher() reads from DB instead of YAML |
| `foundry/llm/dispatcher.py` | Reads provider/model config from DB; supports openai_compatible type |
| `foundry/llm/audit.py` | Audit path now `~/.foundry/audit.jsonl` |
| `foundry/executor/runner.py` | dispatch(task_id, device_pk) — SSH + tmux launcher |
| `foundry/dashboard/routes/__init__.py` | Removed brain_dump/pipeline, added devices |
| `foundry/dashboard/routes/index.py` | Card grid home + quick-add |
| `foundry/dashboard/routes/projects.py` | DB-backed CRUD, task management, run dispatch, GitHub commits |
| `foundry/dashboard/routes/devices.py` | New: device CRUD + test |
| `foundry/dashboard/routes/review.py` | DB-backed review queue |
| `foundry/dashboard/routes/triage.py` | Textarea input instead of brain dump files; graveyard from DB |
| `foundry/dashboard/routes/settings.py` | 3-section LLM settings (Providers, Models, Roles) |
| `foundry/dashboard/templates/base.html` | Nav: Home, Projects, Devices, Triage, Review, Graveyard, Settings |
| `foundry/dashboard/templates/index.html` | Card grid + quick-add |
| `foundry/dashboard/templates/project_detail.html` | Tabbed: Tasks, Spec, Commits, Run logs, Devices |
| `foundry/dashboard/templates/project_new.html` | Added github_url, removed local_path |
| `foundry/dashboard/templates/projects.html` | DB-backed list |
| `foundry/dashboard/templates/triage.html` | Textarea input, inline result |
| `foundry/dashboard/templates/graveyard.html` | DB-backed |
| `foundry/dashboard/templates/review.html` | DB-backed, task IDs are integers |
| `foundry/dashboard/templates/review_card_done.html` | Updated for integer task IDs |
| `foundry/dashboard/templates/settings_models.html` | 3-section providers/models/roles |
| `foundry/vault/schema.py` | Now re-exports from foundry/triage/schema.py |
| `foundry/cli.py` | Removed vault commands; added `device current`, `device test`; triage takes text arg |
| `CLAUDE.md` | Updated to reflect new architecture |
| `tests/test_executor.py` | Rewritten for new dispatch() API |

## Files deleted

- `foundry/dashboard/routes/brain_dump.py`
- `foundry/dashboard/routes/pipeline.py`
- `foundry/dashboard/templates/brain_dump.html`
- `foundry/dashboard/templates/pipeline.html`
- `foundry/dashboard/indexer.py`

## Files intentionally kept as-is

- `foundry/triage/*` (coordinator, classifier, idea_killer, etc.) — triage logic unchanged
- `foundry/llm/base.py` — TriageLLM interface unchanged
- `foundry/notifications/` — untouched
- `foundry/mcp/server.py` — out of scope; may break after vault removal, follow-up needed

---

## Smoke test checklist

1. **DB init**: delete `~/.foundry/foundry.db`. Run `foundry dashboard`. Confirm schema created, app loads at http://localhost:8000.
2. **Devices**: add a local device with `device_id` matching `FOUNDRY_DEVICE_ID`. Add a remote device. Click Test on each.
3. **LLM settings**: add Anthropic provider (env var `ANTHROPIC_API_KEY`), add model `claude-sonnet-4-6`, assign to `default` role. Click Test.
4. **Project**: create a project with a real `github_url`. Add device paths for both devices. Confirm commit list renders on project detail.
5. **Quick-add**: from home, add a task. Confirm card appears with the task as "next".
6. **Run (local)**: click Run → local device. Confirm `tmux attach -t foundry-task-<id>` shows Claude running.
7. **Run (remote)**: same flow against VPS device.
8. **Review**: mark task approved. Confirm status moves to `approved`.
9. **Triage**: paste an idea, click Run. KILL → graveyard entry persisted.
10. **Tests**: `pytest tests/` — all pass.

---

## Known follow-ups

- `foundry/mcp/server.py` imports from vault layer — will break; needs a separate fix.
- Triage coordinator still writes task files to a dummy vault path on ADVANCE — should write to DB tasks table instead (follow-up).
- Run status auto-detection (poll tmux exit) not implemented; user marks tasks manually via Review page.
- GitHub commit fetch requires `GITHUB_TOKEN` env var for private repos or to avoid rate limits.
