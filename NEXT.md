# NEXT.md — Build Status as of 2026-05-27

## What's Done (committed to main)

### Layer 0 — Vault Files
| File | Status |
|------|--------|
| vault/goals.md | ✅ Filled by Anang |
| vault/principles.md | ✅ Filled by Anang |
| vault/existing-systems.md | ✅ Filled by Anang |
| Tailscale setup | ⬜ Still manual — not done |
| foundry-vault bare repo on VPS | ⬜ Still manual — not done |

### Layer 1 — Foundation ✅
| Task | Status | Tests |
|------|--------|-------|
| 1.1 Project scaffolding | ✅ Done | — |
| 1.2 TriageLLM + LiteLLMDispatcher + AuditLogger + FoundryConfig | ✅ Done | 17 passing |
| 1.3 Vault schema (9 Pydantic v2 models) + VaultReader + VaultWriter | ✅ Done | 38 passing |
| 1.4 CLI skeleton | ✅ Done | — |
| 1.5 Test fixtures | ✅ Done | — |

### Layer 2 — Triage Components ✅
| Task | Status | Tests |
|------|--------|-------|
| 2.1 Classifier + prompt | ✅ Done | 31 passing |
| 2.2 Idea Killer + 5-check prompt ⚠️ GATE A pending | ✅ Done | 36 passing |
| 2.3 Feature Killer + 4-check prompt | ✅ Done | 33 passing |
| 2.4 Bug Triage + severity/reproducibility | ✅ Done | 29 passing |
| 2.5 Interviewer Q&A loop | ✅ Done | 27 passing |
| 2.6 Critic adversarial spec review | ✅ Done | 29 passing |
| 2.7 Atomizer + Task Tagger | ✅ Done | 27 passing |

### Layer 3 — Triage Wiring ✅
| Task | Status | Tests |
|------|--------|-------|
| 3.1 Coordinator (full pipeline orchestrator) | ✅ Done | 14 passing |
| 3.2 CLI commands fully wired | ✅ Done | — |
| 3.2b `foundry triage` CLI wired to Coordinator | ✅ Done | — |
| 3.3 Phase 1 acceptance test | ❌ Not started — needs real vault + API keys |

### Layer 4 — Dashboard + MCP + Executor + Notifications ✅
| Task | Status | Tests |
|------|--------|-------|
| 4A.1 FastAPI scaffold + dark theme base layout | ✅ Done | — |
| 4A.2 SQLite indexer + file watcher | ✅ Done | 20 passing |
| 4A.3 Brain dump page | ✅ Done | 5 passing |
| 4A.4 Project list + detail pages | ✅ Done | 10 passing |
| 4A.5 Pipeline kanban view | ✅ Done | 8 passing |
| 4A.6 Review queue page | ✅ Done | 8 passing |
| 4A.7 Triage page + graveyard | ✅ Done | 17 passing |
| 4A.8 Models settings page | ✅ Done | 14 passing |
| 4B.1 FastMCP server (8 read tools) | ✅ Done | 28 passing |
| 4B.2 MCP write tools (5 tools, confirm pattern) | ✅ Done | 13 passing |
| 4C.1 Executor script + `foundry run-next` CLI | ✅ Done | 8 passing |
| 4D.1 Telegram bot + daily digest | ✅ Done | 7 passing |

---

## What Was NOT Done / Skipped

- **Task 3.3 Phase 1 acceptance test** — run `foundry triage --entry FILE` against real entries, verify audit log populates. Needs API keys + real vault content.
- **GATE A** — idea killer calibration against 10 real brain dump entries. Non-negotiable before relying on killer output in production.
- **4A.9 Project generator** — not built (depends on GATE A output).
- **4B.3 MCP integration test from Claude.ai** — manual test, not automated.
- **4C.2–4C.5** — Chrome demo runner, output review generator, pre/post-flight checks, watchdog — not started.
- **4D.2 Deploy scripts** — not started.
- **4D.3 Pause flag + token budget enforcer** — not started.
- **Tailscale + VPS bare repo** — manual setup, not done.

---

## What To Do Next (in order)

### 1. GATE A — Idea Killer Calibration (YOU, ~1-2 hours) ⚠️ NON-NEGOTIABLE
1. Set `ANTHROPIC_API_KEY` in `.env`
2. Set `FOUNDRY_VAULT_PATH` to your vault directory
3. Provide 10 real brain dump entries (5 expect KILL, 3 expect ADVANCE, 2 ambiguous)
4. Run `foundry triage --entry FILE` against each
5. Review verdicts — adjust `vault/principles.md` or `foundry/prompts/idea_killer.md` on disagreements
6. Re-run until kill rate is 60-80% AND you agree with all verdicts
7. Mark GATE A as passed here

### 2. Task 3.3 — Phase 1 acceptance test
Run `foundry triage` against real brain dump entries, verify CLI commands work, verify audit log at `vault/triage/_audit.jsonl` populates.

### 3. Start the dashboard
```bash
FOUNDRY_VAULT_PATH=./vault uvicorn foundry.dashboard.app:app --reload
```
Visit http://localhost:8000

### 4. Configure Telegram notifications
Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env`.

### 5. Layer 5 hardening (after GATE B)
- Backup strategy (rsync to S3)
- 4C.2–4C.5 executor hardening
- 4D.2 deploy scripts
- Killer prompt monthly retune

---

## Known Issues / Flags from Agents

1. **Sensitive pattern matching (Task 1.2)** — Short patterns like `"EA"` use whole-word matching to avoid false-positives on words like "idea". Multi-word patterns use substring. Review `foundry/llm/dispatcher.py` and confirm acceptable.

2. **`read_task` added to VaultReader (Task 1.3)** — Minor scope creep, useful for downstream. Flagged.

3. **GATE A is non-negotiable** — Do not rely on killer output in production until GATE A is signed off.

4. **4A.4 agent rewrote base.html** — The projects agent found base.html missing (only `.gitkeep` existed) and wrote it. The 4A.1 agent had already written it. Check `foundry/dashboard/templates/base.html` is the correct version (dark theme, Tailwind CDN, HTMX CDN, full nav).

---

## GitHub Repo
https://github.com/anank/foundry

## Test Count Summary
Total passing tests (mocked LLM, no API calls): **418**
Run with: `pytest tests/`
