# The Foundry — Full Build Plan (Parallel-Agent Edition)

**Companion doc:** `foundry-spec.md`, `CLAUDE.md`

This document replaces the linear "phases" view with a **dependency graph** designed for parallel agent execution.

---

## How to Read This

- Tasks are grouped into **layers**. Tasks in the same layer can run in parallel.
- Each task lists:
  - **Inputs** — files/components it reads
  - **Outputs** — files/components it produces
  - **Blocks** — tasks that can't start until this one is done
  - **Estimated effort** — for budgeting agent time/tokens
- A task can begin as soon as all its **Inputs** exist. It doesn't matter which agent built them.

---

## The One Synchronization Point (Read This First)

There is exactly **one** mandatory synchronization gate in the entire build:

> **GATE A: Idea killer tuning against 10 real brain dump entries (you participate).**

This gate exists because the idea killer is the only component making genuine judgment calls. Every downstream component (interviewer, atomizer, dashboard, executor, deploy) inherits the killer's verdicts. If the killer is miscalibrated, the entire system amplifies the miscalibration faster than you can review.

Everything else can be swarmed. This gate cannot be skipped, and it requires you, not just an agent.

After GATE A, everything else runs in parallel until **GATE B: end-to-end smoke test before VPS deploy.**

---

## Layer 0: Constitution (You, by hand, before any agent starts)

These are not agent tasks. You write them.

| Task | Output | Why it must be you |
|------|--------|---------------------|
| Write `goals.md` | 5-10 sentences on what you're manifesting in 6 months | An agent can't know your goals. Guessing them poisons the killer. |
| Write `existing-systems.md` | Inventory of built/half-built/abandoned systems | You know what you've built. Memory entries help but aren't complete. |
| Write `principles.md` | Hard rules: token budgets, max BUILDING, tags, quiet hours, etc. | These are *your* policies. Defaults from agents are wrong. |
| Decide vault location | Path on MacBook (dev) + VPS path (prod) | Locks in deployment topology |
| Set up Tailscale | All devices on same tailnet | Network foundation |
| Create empty Git repo `foundry-vault` on VPS | bare repo + working clone | Source-of-truth location |

**Estimated time:** 2-3 hours total. Most is `existing-systems.md` because the inventory is detailed.

**Do not start Layer 1 until these exist.** Agents in Layer 1 will read these files.

---

## Layer 1: Foundation (parallelizable, ~3 agents)

All of Layer 1 can run in parallel. No agent needs another's output.

### Task 1.1 — Project scaffolding
- **Agent:** Code Agent A
- **Inputs:** None (greenfield)
- **Outputs:**
  - `pyproject.toml` with Phase 1 deps (LiteLLM, Pydantic, Typer, pyyaml, GitPython, pytest, anthropic)
  - Directory structure per CLAUDE.md section 5
  - `.env.example`, `.gitignore`
  - Empty prompt files in `foundry/prompts/`
  - `foundry/__init__.py`, `foundry/cli.py` skeleton
  - `foundry --help` runs and shows command list (commands themselves stubbed)
- **Blocks:** Nothing depends on this *file structure* — but having it makes everything cleaner.
- **Effort:** 2 hours

### Task 1.2 — TriageLLM + dispatcher
- **Agent:** Code Agent B
- **Inputs:** None
- **Outputs:**
  - `foundry/llm/base.py` — `TriageLLM` ABC, `LLMResponse` dataclass
  - `foundry/llm/dispatcher.py` — `LiteLLMDispatcher` with sensitive override routing
  - `foundry/llm/audit.py` — writes to `vault/triage/_audit.jsonl`
  - `foundry/config.py` — loads `.env` and `models.yaml`
  - Tests with mocked LiteLLM
  - Real-API smoke test (manual run, hits Anthropic with trivial prompt)
- **Blocks:** Tasks 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7
- **Effort:** 4 hours

### Task 1.3 — Vault reader/writer + Pydantic schemas
- **Agent:** Code Agent C
- **Inputs:** Layer 0 files (to validate parser against real content)
- **Outputs:**
  - `foundry/vault/schema.py` — Pydantic models for every vault file type:
    - `BrainDumpEntry`, `IdeaKillerVerdict`, `FeatureKillerVerdict`, `BugTriageResult`
    - `Spec`, `Task`, `Project`, `Goal`, `Principle`, `ExistingSystem`
  - `foundry/vault/reader.py` — parse markdown + YAML frontmatter, return typed objects
  - `foundry/vault/writer.py` — atomic write + git commit
  - Tests against fixture files
- **Blocks:** All triage components (2.1-2.7), CLI (1.4)
- **Effort:** 4 hours

### Task 1.4 — CLI skeleton
- **Agent:** Code Agent A (continues from 1.1)
- **Inputs:** 1.1
- **Outputs:**
  - Typer-based CLI with all commands stubbed (`triage`, `vault validate`, `vault status`, `kill-log`, `audit`)
  - Each command parses args and prints "not yet implemented"
- **Blocks:** Wiring up real commands (Layer 3)
- **Effort:** 1 hour

### Task 1.5 — Test fixtures
- **Agent:** Content Agent (or you)
- **Inputs:** Layer 0 files
- **Outputs:** `tests/fixtures/brain_dumps/` with 9 entries representing each verdict class (see CLAUDE.md section 11.1)
- **Blocks:** All triage tests (2.1-2.7)
- **Effort:** 1 hour

---

## Layer 2: Triage Components (parallelizable, ~7 agents)

Once 1.2 and 1.3 are done, ALL of Layer 2 can swarm in parallel.

### Task 2.1 — Classifier
- **Agent:** Code Agent
- **Inputs:** 1.2, 1.3, 1.5
- **Outputs:**
  - `foundry/prompts/classifier.md`
  - `foundry/triage/classifier.py` — validates type, asks if ambiguous
  - Tests using fixture entries
- **Blocks:** Coordinator (3.1)
- **Effort:** 2 hours

### Task 2.2 — Idea Killer (CRITICAL — extra care)
- **Agent:** Code Agent (most experienced, or you supervise closely)
- **Inputs:** 1.2, 1.3, 1.5, `goals.md`, `existing-systems.md`, `principles.md`
- **Outputs:**
  - `foundry/prompts/idea_killer.md` — five-check prompt biased toward KILL
  - `foundry/triage/idea_killer.py`
  - Tests against all "obvious_kill_*" and "obvious_advance_*" fixtures
  - Graveyard file writer
- **Blocks:** Interviewer (2.5), end-to-end (Layer 3), GATE A
- **Effort:** 6 hours (most of it on prompt iteration)
- **⚠️ Goes through GATE A before downstream tasks can rely on it**

### Task 2.3 — Feature Killer
- **Agent:** Code Agent
- **Inputs:** 1.2, 1.3, 1.5
- **Outputs:**
  - `foundry/prompts/feature_killer.md`
  - `foundry/triage/feature_killer.py`
  - Tests against feature fixtures
- **Blocks:** Coordinator (3.1)
- **Effort:** 3 hours

### Task 2.4 — Bug Triage
- **Agent:** Code Agent
- **Inputs:** 1.2, 1.3, 1.5
- **Outputs:**
  - `foundry/prompts/bug_triage.md`
  - `foundry/triage/bug_triage.py` — reproducibility + severity, writes task spec directly
  - Tests against bug fixtures
- **Blocks:** Coordinator (3.1)
- **Effort:** 3 hours

### Task 2.5 — Interviewer
- **Agent:** Code Agent
- **Inputs:** 1.2, 1.3
- **Outputs:**
  - `foundry/prompts/interviewer.md`
  - `foundry/triage/interviewer.py` — iterative Q&A loop, returns SPEC_DRAFT or NEEDS_USER_INPUT
  - Tests with canned responses
- **Blocks:** Critic (2.6), Coordinator (3.1)
- **Effort:** 4 hours

### Task 2.6 — Critic
- **Agent:** Code Agent
- **Inputs:** 1.2, 1.3
- **Outputs:**
  - `foundry/prompts/critic.md`
  - `foundry/triage/critic.py` — adversarial spec review, LOCKED or RETURN_WITH_QUESTIONS
  - Tests against deliberately weak specs
- **Blocks:** Atomizer (2.7), Coordinator (3.1)
- **Effort:** 3 hours

### Task 2.7 — Atomizer + Task Tagger
- **Agent:** Code Agent
- **Inputs:** 1.2, 1.3
- **Outputs:**
  - `foundry/prompts/atomizer.md`, `foundry/prompts/task_tagger.md`
  - `foundry/triage/atomizer.py` — splits spec into ≤200-line tasks
  - `foundry/triage/task_tagger.py` — behavioral/output/code
  - Tests
- **Blocks:** Coordinator (3.1)
- **Effort:** 4 hours

---

## ⚠️ GATE A — Idea Killer Calibration (YOU + idea killer agent)

**This is the one synchronization point.**

After Task 2.2 produces the idea killer v1, **before** anything downstream uses it:

1. You provide 10 real brain dump entries from your existing notes (5 you expect to KILL, 3 you expect to ADVANCE, 2 ambiguous).
2. Run idea killer against all 10.
3. You review every verdict + reasoning.
4. For disagreements, you edit the prompt or adjust `principles.md`/`goals.md`.
5. Re-run until you agree with verdicts AND kill rate is 60-80%.

**Estimated time:** 1-2 hours of your time, mostly reading 10 verdicts.

**Why this can't be parallelized away:** the killer is comparing ideas against *your* goals using *your* principles. Only you can judge whether its calibration matches your intent. No agent can do this.

**What's allowed during GATE A:** Layer 3+ tasks that don't depend on idea killer output can proceed (dashboard scaffolding, MCP server scaffolding, Telegram setup, etc.). Anything that processes killer output (review queue, executor) must wait.

---

## Layer 3: Triage Wiring + Phase 1 Completion (parallelizable, ~3 agents)

### Task 3.1 — Coordinator (orchestrates the full triage pipeline)
- **Agent:** Code Agent
- **Inputs:** 2.1-2.7
- **Outputs:**
  - `foundry/triage/coordinator.py` — orchestrates classifier → appropriate killer → (idea path: interviewer → critic → atomizer → tagger)
  - Wires up CLI commands `foundry triage`, `foundry triage --type X`, `foundry triage --entry FILE`
  - End-to-end test: fixture entry → final task list
- **Blocks:** Phase 1 complete signal
- **Effort:** 3 hours

### Task 3.2 — CLI commands fully wired
- **Agent:** Code Agent
- **Inputs:** 1.4, 3.1
- **Outputs:**
  - `foundry vault validate` — checks vault structure
  - `foundry vault status` — pending/killed/queued/operating counts
  - `foundry kill-log --since N` — recent kills
  - `foundry kill-log --pattern X` — search graveyard
  - `foundry audit --since N` — LLM usage report
- **Blocks:** Phase 1 complete signal
- **Effort:** 2 hours

### Task 3.3 — Phase 1 acceptance test
- **Agent:** Test Agent (or you)
- **Inputs:** 3.1, 3.2
- **Outputs:**
  - Run `foundry triage` against your real Phase 1 brain dump (≥10 entries)
  - Verify CLI commands work
  - Verify audit log is populated
- **Blocks:** Layer 4 (dashboard work depends on Phase 1 being usable)
- **Effort:** 1 hour

**End of Phase 1 equivalent.** Everything below this is Phase 2+ work, and it can almost entirely be parallelized.

---

## Layer 4: Dashboard + MCP + Executor (parallel megaswarm, ~6-10 agents)

This is where you get to swarm hardest. None of these tasks block each other.

### Track A: Dashboard

#### Task 4A.1 — FastAPI scaffold
- **Inputs:** None (greenfield FastAPI app)
- **Outputs:** FastAPI app, base templates, Tailwind+HTMX setup, mobile-first base layout
- **Effort:** 3 hours

#### Task 4A.2 — SQLite indexer
- **Inputs:** 1.3 (vault reader)
- **Outputs:** SQLite schema + indexer that reads vault and builds queryable views; file watcher to re-index on changes
- **Effort:** 4 hours

#### Task 4A.3 — Brain dump page
- **Inputs:** 4A.1
- **Outputs:** Mobile form with type/project/state/content fields, "Triage Now" + "Submit for Batch" buttons, calls coordinator API
- **Effort:** 3 hours

#### Task 4A.4 — Project list + detail pages
- **Inputs:** 4A.1, 4A.2
- **Outputs:** `/projects` index, `/projects/{name}` detail showing PROJECT.md + CLAUDE.md + task list
- **Effort:** 3 hours

#### Task 4A.5 — Pipeline view
- **Inputs:** 4A.1, 4A.2
- **Outputs:** `/pipeline` showing operating/building/queued/parked, drag-to-reorder for queued
- **Effort:** 3 hours

#### Task 4A.6 — Review queue page
- **Inputs:** 4A.1, 4A.2
- **Outputs:** `/review` mobile-first page, lists tasks awaiting review, renders flow-review.md inline, Approve/Reject/Revise buttons
- **Effort:** 4 hours

#### Task 4A.7 — Triage page + graveyard
- **Inputs:** 4A.1, 4A.2
- **Outputs:** `/triage` pending entries, run-triage button; `/graveyard` searchable killed ideas
- **Effort:** 3 hours

#### Task 4A.8 — Models settings page
- **Inputs:** 4A.1, models.yaml schema
- **Outputs:** `/settings/models` to edit per-role endpoint config + test buttons
- **Effort:** 3 hours

#### Task 4A.9 — Project generator
- **Inputs:** 4A.1, 4A.4, idea killer output (post-GATE A)
- **Outputs:** "New Project" flow that uses AI to scaffold PROJECT.md and CLAUDE.md from a description
- **Effort:** 4 hours

### Track B: MCP Server

#### Task 4B.1 — FastMCP server scaffold
- **Inputs:** 1.3
- **Outputs:** FastMCP server, read tools (list_projects, get_project, get_pipeline, get_goals, get_principles, get_existing_systems, search_graveyard, get_brain_dump)
- **Effort:** 4 hours

#### Task 4B.2 — Write tools with confirmation pattern
- **Inputs:** 4B.1
- **Outputs:** add_brain_dump, trigger_triage, update_principles, create_project, set_pause — each requires confirmation pattern
- **Effort:** 3 hours

#### Task 4B.3 — MCP integration test from Claude.ai
- **Inputs:** 4B.1, 4B.2
- **Outputs:** Test conversation from claude.ai validating all tools work; documentation of MCP server URL
- **Effort:** 1 hour

### Track C: Executor (MacBook/Windows)

#### Task 4C.1 — Executor script
- **Inputs:** Vault structure
- **Outputs:** `run-next-task.sh` that pulls vault, picks top task, opens Claude Code with spec, watches for completion, writes result, commits, pushes
- **Effort:** 4 hours

#### Task 4C.2 — Chrome demo runner
- **Inputs:** 4C.1, task with demo_script field
- **Outputs:** Wrapper around Chrome skill that executes demo script, captures screenshots, generates flow-review.md
- **Effort:** 4 hours

#### Task 4C.3 — Output review generator
- **Inputs:** 4C.1
- **Outputs:** For `[output]` tasks, runs the produced code and generates sample-data review file
- **Effort:** 2 hours

#### Task 4C.4 — Pre-flight + post-flight checks
- **Inputs:** 4C.1
- **Outputs:** Pre-flight (clean git, budget, pause flag), post-flight (tests, scope drift, result.md generation)
- **Effort:** 3 hours

#### Task 4C.5 — Watchdog process
- **Inputs:** 4C.1
- **Outputs:** Separate process that kills runaway sessions on token/time overrun
- **Effort:** 2 hours

### Track D: Notifications + Deploy

#### Task 4D.1 — Telegram bot
- **Inputs:** None
- **Outputs:** Bot setup, push notification on review-queue item, daily digest sender
- **Effort:** 3 hours

#### Task 4D.2 — Deploy scripts per project type
- **Inputs:** Project type registry
- **Outputs:** Deploy template for VPS, cPanel, prop firm EA; one-tap approval endpoint
- **Effort:** 4 hours per project type (do as needed)

#### Task 4D.3 — Pause flag mechanism + token budget enforcer
- **Inputs:** 4C.4
- **Outputs:** File-based pause flag, daily budget tracker, halt-on-cap behavior
- **Effort:** 2 hours

---

## ⚠️ GATE B — End-to-End Smoke Test (YOU)

After Layer 4 completes:

1. You enter a brain dump from your phone.
2. System classifies, kills/specs, atomizes, queues.
3. MacBook executor pulls the task, runs Claude Code, produces output + demo.
4. Review queue notification on your phone.
5. You approve.
6. Deploy approval triggers VPS deploy.
7. Idea is running in the world.

**If this loop works for ONE real idea end-to-end, The Foundry is functional.**

If it doesn't work, agents debug whatever broke. No new features until the loop works.

---

## Layer 5: Hardening (parallel, on-demand)

After Gate B passes. These are quality improvements, not features.

- Backup strategy for vault (rsync to S3, secondary git remote)
- Multi-project token budget granularity
- Killed-idea revival pattern detection (after graveyard has 30+ entries)
- VPS resource monitoring + alerting
- Killer prompt audit (monthly retune based on kill log)

---

## Agent Coordination

### How to actually swarm this

**For each Layer:**

1. Identify all tasks in the layer with their inputs satisfied
2. Spawn one Claude Code agent per task
3. Each agent reads:
   - `CLAUDE.md` (the operational guide)
   - `foundry-spec.md` (architecture)
   - `BUILD_PLAN.md` (this file)
   - Their specific task definition
4. Agents work in feature branches: `feature/task-X.Y-description`
5. When done, agent opens PR with diff + tests passing
6. You review PRs in batch during work shifts

**Conflict prevention:**

- Each task has a defined output file set (above). Agents don't write outside their set.
- Shared files (e.g. `foundry/cli.py` if multiple tasks add commands) → one task owns the file, others write to their own module and the owner imports them.
- For Layer 4 tracks, each track works in its own subdirectory (`dashboard/`, `mcp/`, `executor/`) so cross-track conflicts are rare.

### Token budget per task

Rough budgets so swarming doesn't burn $500/day:

| Layer | Total tasks | Estimated tokens per task | Layer total |
|-------|-------------|---------------------------|-------------|
| 1 | 5 | 20-40k | ~150k |
| 2 | 7 | 30-60k | ~300k |
| 3 | 3 | 20-30k | ~75k |
| 4 (all tracks) | 17 | 30-60k | ~700k |
| 5 | varies | varies | varies |

**Roughly 1.2M tokens total for the full build.** At Sonnet rates, ballpark $30-50. At Haiku for simpler tasks, less. Track in `foundry audit` after each layer.

---

## What's Different From the Original Phased Plan

**Removed:**
- The "3 real items between phases" rule for everything except GATE A and GATE B
- Sequential phase gating
- "Don't build X yet" restrictions on things that don't depend on the killer

**Kept:**
- GATE A (idea killer calibration) — non-negotiable
- GATE B (end-to-end smoke test) — non-negotiable
- Anti-Addiction Rule applied to The Foundry itself (no out-of-spec features)
- The killer-first philosophy in component design

**Why this is safe to swarm:**
- The killer's calibration is the only thing the rest of the system *can't* recover from. Everything else is fixable in review.
- All Layer 4 components have clear interfaces and can be developed against mock data while the killer is being tuned.
- You're the integration point. Swarming code doesn't reduce your review burden — but you've said work-shift review is fine, and the architecture supports it.

---

## Your Next Action

1. Write Layer 0 files by hand (2-3 hours)
2. Spawn Layer 1 agents (3 in parallel)
3. While Layer 1 runs, draft your 10 real brain dump entries for GATE A
4. Spawn Layer 2 agents when 1.2 and 1.3 are done (up to 7 in parallel)
5. GATE A with the idea killer agent — this is hands-on, ~1-2 hours of your time
6. Layer 3 (3 agents)
7. Layer 4 megaswarm (up to ~17 agents in parallel across tracks)
8. GATE B — first real idea through the full system
9. Layer 5 as needed

If you parallelize aggressively and your dev machines can run multiple Claude Code instances, **the full build is realistically 1-2 weeks of calendar time**, with maybe 20-30 hours of your actual involvement (mostly review + Gate A + Gate B).
