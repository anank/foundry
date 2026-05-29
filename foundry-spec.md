# The Foundry — Project Specification

**Version:** 0.2 (Draft)
**Owner:** Anang
**Date:** 2026-05-26
**Status:** Specification phase — Phase 0 ready to start

**Changes from v0.1:**
- Brain dump capture now happens in the web app (Obsidian path retained as fallback)
- Triage now routes by entry type: idea / feature / bug fix — each with its own killer
- AI endpoints are pluggable via `models.yaml` config (Anthropic / OpenRouter / local mlx-lm)
- Removed gut_score field from brain dump (creates emotional anchoring that interferes with killer)
- Added LiteLLM as the multi-provider adapter

---

## 1. Purpose

The Foundry is a personal idea-to-deployment system. Its job is to close the gap between an idea in Obsidian notes and a system running in the world.

It is explicitly **a triage killer system**, not a triage execution system. The default verdict for any new idea is rejection. Ideas must earn survival by passing structured checks. Only surviving ideas become tasks, and only completed tasks become deployments.

**Non-goals:**
- Perfect software quality
- Maximum throughput
- General-purpose project management
- A tool for other users (single-user, owner-operated)

**Core principle:** "You're not a musician if the song only lives in your notes." The Foundry exists to manifest ideas into reality, ruthlessly filtered.

---

## 2. System Architecture

### 2.1 Topology

```
┌─────────────────────────────────────────────────────────────────────┐
│                          VPS (cPanel)                                │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ FastAPI Dashboard      (port 8000, behind Tailscale)        │    │
│  │   - Web UI for review, triage, project mgmt                 │    │
│  │   - Mobile-first HTMX interface                             │    │
│  └─────────────────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ MCP Server              (port 8001, behind Tailscale)       │    │
│  │   - Exposes vault state to Claude.ai                        │    │
│  │   - Read-only by default, write tools require confirmation  │    │
│  └─────────────────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ Vault (Git repo)        /home/anang/foundry-vault           │    │
│  │   - Markdown files = source of truth                        │    │
│  │   - SQLite index = queryable cache                          │    │
│  │   - Git remote = sync to dev machines                       │    │
│  └─────────────────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ Triage Worker          (background process)                 │    │
│  │   - Runs killer/interviewer/critic/atomizer/classifier      │    │
│  │   - Calls Anthropic API directly                            │    │
│  └─────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
                                 ▲
                                 │ Tailscale
                                 │
        ┌────────────────────────┼────────────────────────┐
        │                                                  │
┌───────▼────────┐                                ┌───────▼────────┐
│   MacBook M1   │                                │ Windows Laptop │
│                │                                │                │
│ - Git pull     │                                │ - Git pull     │
│ - Claude Code  │                                │ - Claude Code  │
│ - mlx-lm local │                                │                │
│ - Git push     │                                │ - Git push     │
└────────────────┘                                └────────────────┘
        │                                                  │
        └──────────────────────────────────────────────────┘
                              │
                              ▼
                  ┌───────────────────────┐
                  │  Phone (Tailscale)    │
                  │  - Read dashboard     │
                  │  - Approve / Reject   │
                  │  - Brain dump entries │
                  └───────────────────────┘
```

### 2.2 Component Responsibilities

| Component | Runs On | Responsibility |
|-----------|---------|----------------|
| Dashboard | VPS | Web UI, review queue, project list, brain dump capture |
| MCP Server | VPS | Exposes vault to Claude.ai for context-aware conversations |
| Triage Worker | VPS | Runs the killer/interviewer/critic/atomizer/classifier skills |
| Vault | VPS (Git origin) | Source-of-truth markdown files |
| SQLite Index | VPS | Cached views over markdown for fast dashboard queries |
| Claude Code Executor | MacBook / Windows | Pulls tasks from Git, executes builds, pushes results |
| Tailscale | All devices | Private network, no public auth needed |

---

## 3. Vault Structure

The vault is a single Git repository. All state is in markdown files. SQLite is a derived cache, never the source of truth.

```
foundry-vault/
├── .git/
├── README.md
├── goals.md                          # What Anang is trying to manifest
├── principles.md                     # Triage criteria + hard rules
├── existing-systems.md               # Inventory of built systems
│
├── brain-dump/
│   └── YYYY-MM.md                    # One file per month, append-only
│
├── projects/
│   ├── _index.md                     # List of all projects + status
│   ├── pipnesiatest-ea/
│   │   ├── PROJECT.md                # Spec, MVP, priority, status
│   │   ├── CLAUDE.md                 # Tech stack, deploy, test instructions
│   │   ├── tasks/
│   │   │   ├── _next.md              # Ordered list of next tasks for this project
│   │   │   ├── 001-add-trailing-stop.md
│   │   │   └── 002-fix-spread-filter.md
│   │   └── archive/
│   │       └── 000-initial-setup.md  # Completed tasks
│   └── [other-project]/
│
├── pipeline/
│   ├── _next.md                      # GLOBAL next tasks across all projects
│   ├── operating.md                  # Live systems
│   ├── building.md                   # Currently in dev (max 2)
│   ├── queued.md                     # Approved, waiting
│   └── parked.md                     # Survived triage but not active
│
├── triage/
│   ├── _log.md                       # Audit log of all triage decisions
│   ├── pending/                      # Brain dump entries awaiting triage
│   └── reviewed/                     # Triaged entries with verdicts
│
├── graveyard/
│   ├── _index.md                     # Searchable index of killed ideas
│   └── YYYY-MM/
│       └── [killed-idea].md          # One file per killed idea
│
└── archive/
    └── completed-tasks/
        └── YYYY-MM/
            └── [task-id].md          # Completed and approved tasks
```

### 3.1 File Templates

**`brain-dump/YYYY-MM.md`** (append-only)
```markdown
## 2026-05-26 14:32
type: idea | feature | bug
project: [project-name if feature/bug, blank if idea]
content: telegram bot that posts EA equity curve daily
context: while watching MT5 charts, friction of opening laptop
state: energized
source: app | obsidian
triage_status: pending | classified | killed | advanced
```

Notes:
- `type` is required. Entries without a type fail validation and are returned to the user.
- `project` is required for `feature` and `bug` types.
- `gut_score` deliberately omitted — self-scoring anchors the killer's verdict.
- Entries can be written by the dashboard form OR by Obsidian directly. The triage worker doesn't care about origin.

**`projects/[name]/PROJECT.md`**
```markdown
# Project: [Name]
status: operating | building | queued | parked
priority: high | medium | low
created: YYYY-MM-DD
goal_anchor: [link to relevant goals.md entry]

## Description
[What this project is and why it exists]

## Tech Spec
[High-level architecture]

## MVP Definition
[What "minimum viable" means for this project — measurable]

## Current State
[Where it stands today]

## Links
- Repo: [URL]
- Deploy: [URL]
- Dashboard: [URL]
```

**`projects/[name]/CLAUDE.md`**
```markdown
# CLAUDE.md — [Project Name]

## Tech Stack
- Language:
- Framework:
- Dependencies:
- External services:

## Local Development
[Step-by-step to run locally]

## Testing
[How to test, what tests exist, acceptance criteria pattern]

## Deployment
[Target: VPS / cPanel / prop firm / local]
[Step-by-step deploy procedure]

## Important Constraints
[Project-specific rules Claude Code must respect]
```

**`projects/[name]/tasks/NNN-[slug].md`**
```markdown
# Task NNN: [Title]
status: queued | building | review | approved | rejected
project: [project-name]
review_tag: behavioral | output | code
estimated_diff: N lines
token_budget: N
created: YYYY-MM-DD
spec_locked: true | false

## Origin
[Link to brain dump entry or generation context]

## Spec
[Locked specification — what to build]

## Acceptance Criteria
[Numeric/binary "done" conditions]

## Demo Script
[For behavioral tasks: step-by-step user flow Chrome will execute]

## Out of Scope
[Explicit non-goals to prevent drift]

## Files Expected to Change
[List — used for scope drift detection]
```

**`pipeline/_next.md`**
```markdown
# Global Pipeline — Next Tasks

## Currently Building (max 2)
1. [project] / [task-id] — [title]

## Queued (ordered)
1. [project] / [task-id] — [title]
2. ...

Last updated: [timestamp by triage worker]
```

**`graveyard/YYYY-MM/[killed-idea].md`**
```markdown
# Killed: [Idea Title]
killed_date: YYYY-MM-DD
verdict: KILL | PARK
revival_condition: [for PARK only — what would make this worth revisiting]

## Original Idea
[Verbatim from brain dump]

## Triage Checks
- Goal anchor: [pass/fail + reasoning]
- Existing system overlap: [pass/fail + reasoning]
- Manual baseline: [pass/fail + reasoning]
- Killshot: [pass/fail + reasoning]
- Existence test: [pass/fail + reasoning]

## Verdict Reasoning
[2-3 sentences]

## Related Killed Ideas
[Links to similar deaths]
```

---

## 4. The Triage Pipeline

### 4.1 Flow

```
brain-dump entry
       │
       ▼
┌──────────────┐
│  Classifier  │  validates type, asks if ambiguous
└──────┬───────┘
       │
       ├─ idea ──────► ┌───────────────┐
       │               │  Idea Killer  │ ──► graveyard (most die here)
       │               └───────┬───────┘
       │                       │ survives
       │                       ▼
       │               ┌───────────────┐
       │               │  Interviewer  │ ──► clarifying Q&A → draft spec
       │               └───────┬───────┘
       │                       │
       │                       ▼
       │               ┌───────────────┐
       │               │    Critic     │ ──► spec adversarial review
       │               └───────┬───────┘
       │                       │ locked
       │                       ▼
       │               ┌───────────────┐
       │               │   Atomizer    │ ──► ≤200-line tasks
       │               └───────┬───────┘
       │                       │
       │                       ▼
       │               ┌───────────────┐
       │               │ Task Tagger   │ ──► behavioral|output|code
       │               └───────┬───────┘
       │                       │
       │                       ▼
       │               new project + tasks queued
       │
       ├─ feature ───► ┌──────────────────┐
       │               │ Feature Killer   │ ──► graveyard
       │               └──────┬───────────┘
       │                      │ survives
       │                      ▼
       │               feeds into target project's interviewer
       │               (skips classifier since project context known)
       │
       └─ bug ───────► ┌──────────────────┐
                       │  Bug Triage      │ ──► graveyard (won't fix / not reproducible)
                       └──────┬───────────┘
                              │ survives
                              ▼
                       severity tag (critical | high | low)
                              │
                              ▼
                       inserted into project's task queue
                       (critical bugs jump the queue)
```

### 4.2 The Classifier

**First step for every brain dump entry.** Validates the `type` field and ensures it makes sense.

Behavior:
- If `type` is missing → reject, return to user with prompt to add it
- If `type` is `feature` or `bug` but no `project` set → ask which project
- If the content reads like a different type than declared (e.g. type=feature but no existing project plausibly hosts it) → flag for user confirmation, do not silently reclassify
- Never guesses when ambiguous — always asks

Tech: cheapest model (Haiku or local Qwen). Pure routing, no judgment.

### 4.3 The Idea Killer

**For `type: idea` only.** This is the discipline-enforcing component. Default verdict: KILL.

Five checks, cheapest first:

1. **Goal anchor** — connects to `goals.md`? If no → KILL.
2. **Existing system overlap** — covered by something in `existing-systems.md`? If yes → KILL ("propose as feature instead") or PARK.
3. **Manual baseline** — has Anang done this manually ≥5 times? If no → KILL ("automate after manual pattern is proven").
4. **Killshot** — generate 3 strongest objections. If any decisive → KILL.
5. **Existence test** — "if this were built and running, what concretely changes?" If vague → KILL.

Bias: kill rate target 60-80%. Monthly audit retunes prompts.

### 4.4 The Feature Killer

**For `type: feature` only.** Lighter than idea killer because the host project's existence already justifies some scope.

Four checks:

1. **Project MVP exists?** — If host project hasn't shipped MVP yet → KILL ("ship MVP first, then add features").
2. **Roadmap conflict** — Does this conflict with anything currently in the project's `tasks/_next.md`? If yes → either resolve (drop the conflicting task) or KILL.
3. **Scope creep on finished project** — Is the host project in `operating` status and untouched for >30 days? If yes → high bar to add features. Default PARK with revival condition.
4. **Killshot** — 2 strongest objections specific to feature additions: "does this complicate the project beyond its current responsibility?" and "is this a new project in disguise?"

Bias: kill rate target 40-60%. Lower than idea killer because features are usually grounded in operational reality.

### 4.5 The Bug Triage

**For `type: bug` only.** Different shape — bugs aren't killed for being unworthy, they're triaged by severity and reproducibility.

Checks:

1. **Reproducibility** — can it be reproduced from the description? If no → flag for more info, do not queue yet.
2. **Impact** — data loss / wrong output / minor annoyance / cosmetic?
3. **Workaround exists?** — if yes, severity drops one level.
4. **Severity assignment**:
   - **Critical**: data loss, financial impact, security, operating system down → jumps to top of project's queue
   - **High**: wrong output but contained, system degraded → next in project queue
   - **Low**: annoyance, cosmetic, edge case → backlog (may never be fixed, that's fine)

Output: a task spec written directly (no interviewer/critic needed for bug fixes — the description IS the spec). Added to the host project's task queue with severity tag.

Bugs in `graveyard` only when: not reproducible AND user confirms they don't care about it AND no impact on operations.

### 4.6 The Interviewer (idea path only)

Q&A loop with the user. Asks clarifying questions until the spec is concrete enough to lock.

Required outputs:
- Concrete success criteria (numeric where possible)
- Demo script (for behavioral tasks)
- Files/modules expected to change
- Out-of-scope items

### 4.7 The Critic (idea path only)

Adversarial review of the draft spec. Returns:
- `LOCKED` — spec is buildable
- `RETURN` — gaps identified, sends back to interviewer with specific questions

### 4.8 The Atomizer (idea path only)

Splits the spec into tasks of ≤200 lines of expected diff each. Each task is independently reviewable and revertable.

### 4.9 The Task Tagger

Tags each task with one of:
- `[behavioral]` — Chrome demo for review
- `[output]` — sample data review
- `[code]` — full code review required (security, money, production data)

---

## 5. The Dashboard

### 5.1 Pages

**Home / Review Queue**
- Tasks awaiting review, oldest first
- Each card: title, project, review tag, diff size, tokens used
- Three buttons: Approve / Reject / Revise

**Projects**
- List of all projects with status badges
- Click → project detail view
- "New Project" button → AI-assisted PROJECT.md + CLAUDE.md generation

**Pipeline**
- Current state of `pipeline/_next.md`
- Operating / Building / Queued / Parked sections
- Drag-to-reorder for queued items

**Brain Dump**
- Mobile-first capture form
- Required: type selector (idea | feature | bug)
- Conditional: project dropdown (shown when type = feature or bug)
- Text fields: content, context
- State selector: energized | tired | frustrated | inspired | bored
- Two submit buttons:
  - **Submit & Triage Now** — appends to vault + immediately runs classifier and appropriate killer, returns verdict
  - **Submit for Weekly Batch** — appends to vault only, processed in Sunday's triage run
- Also accepts entries written directly to `brain-dump/YYYY-MM.md` from Obsidian (no functional difference)

**Triage**
- Pending brain dump entries
- "Run Triage" button to process pending
- Edit `principles.md` (the triage criteria)
- View kill log

**Graveyard**
- Searchable list of killed ideas
- Filter by verdict, date, project
- Patterns view: kill reasons over time

**Settings**
- Token budget (daily cap)
- Pause flag (halts the executor)
- Quiet hours
- API keys (stored in env, surfaced for testing)

**Models** (new page)
- Edit `models.yaml` — which AI endpoint runs each triage role
- Per-role selector: classifier, idea-killer, feature-killer, bug-triage, interviewer, critic, atomizer, task-tagger
- Provider options: anthropic | openrouter | mlx-local | ollama
- Test button per role — runs a canned input through the configured endpoint
- Audit log: which model produced each triage verdict (so killed ideas can be re-evaluated if model changes)

### 5.2 Tech Stack

- **Backend:** FastAPI + Jinja2 templates
- **Frontend:** HTMX + Tailwind (no SPA, server-rendered, mobile-first)
- **State:** SQLite (`foundry.db`) for indexed queries
- **Vault access:** Direct filesystem reads (FastAPI runs on same box)
- **Vault writes:** Through a write API that updates both markdown and SQLite, then commits to Git

### 5.3 Pluggable AI Endpoints

All triage roles call AI through a single abstraction:

```python
class TriageLLM:
    """Single interface for all AI calls in The Foundry."""
    def analyze(
        self,
        system: str,
        prompt: str,
        max_tokens: int = 2048,
    ) -> str: ...
```

Implementations:
- `AnthropicLLM` — direct Anthropic API
- `OpenRouterLLM` — any OpenRouter model
- `MLXLocalLLM` — local mlx-lm endpoint (Anang's MacBook M1 Max)
- `OllamaLLM` — local Ollama endpoint

Underlying transport: **LiteLLM** (already in Anang's stack from Multi-Agent Content System). LiteLLM provides one client interface across all providers. The `TriageLLM` is a thin wrapper around LiteLLM with logging and audit.

Configuration in `vault/models.yaml`:

```yaml
endpoints:
  classifier:
    provider: anthropic
    model: claude-haiku-4-5
    max_tokens: 256

  idea_killer:
    provider: anthropic
    model: claude-haiku-4-5
    max_tokens: 1024

  feature_killer:
    provider: anthropic
    model: claude-haiku-4-5
    max_tokens: 1024

  bug_triage:
    provider: anthropic
    model: claude-haiku-4-5
    max_tokens: 1024

  interviewer:
    provider: anthropic
    model: claude-sonnet-4-6
    max_tokens: 4096

  critic:
    provider: anthropic
    model: claude-sonnet-4-6
    max_tokens: 2048

  atomizer:
    provider: anthropic
    model: claude-sonnet-4-6
    max_tokens: 4096

  task_tagger:
    provider: anthropic
    model: claude-haiku-4-5
    max_tokens: 256

# Sensitive content (trading strategies, financial data) routed locally
sensitive_overrides:
  patterns:
    - "trading"
    - "EA"
    - "Pipnesia"
    - "bank statement"
    - "BCA"
    - "Mandiri"
  endpoint:
    provider: mlx-local
    model: qwen2.5-coder-14b
    base_url: http://localhost:11434/v1
```

The `sensitive_overrides` block is critical: any brain dump entry matching the patterns is routed to local-only models. Never leaves the MacBook. Implemented at the `TriageLLM` dispatcher level.

Audit: every triage decision is logged with `(role, provider, model, timestamp, prompt_hash, verdict)` in SQLite. This means killed ideas can be re-evaluated if the model changes — useful for spotting whether Haiku is being too harsh or Sonnet too lenient.

---

## 6. The MCP Server

### 6.1 Purpose

Exposes vault state to Claude.ai so conversations like this one can have full project context.

### 6.2 Tools Exposed

**Read tools (no confirmation):**
- `list_projects()` — returns project index
- `get_project(name)` — returns PROJECT.md + CLAUDE.md
- `get_pipeline()` — current next/queued/building/operating state
- `get_goals()` — contents of goals.md
- `get_principles()` — contents of principles.md
- `get_existing_systems()` — inventory
- `search_graveyard(query)` — find killed ideas
- `get_brain_dump(month?)` — recent brain dump entries

**Write tools (require explicit confirmation in chat):**
- `add_brain_dump(idea, context, state)` — append entry
- `trigger_triage()` — run triage on pending brain dump
- `update_principles(diff)` — edit triage criteria
- `create_project(name, draft_spec)` — scaffold new project files
- `set_pause(true|false)` — toggle executor pause flag

### 6.3 Transport

HTTP over Tailscale, no auth needed (network-level trust).

---

## 7. Sync Model

### 7.1 Source of Truth

**The Git repo on the VPS is canonical.** All other locations are caches.

### 7.2 Executor Flow

On MacBook / Windows:

```
1. cd ~/foundry-vault
2. git pull
3. Read pipeline/_next.md
4. Pick top task whose status is "building"
5. Read task spec from projects/X/tasks/NNN-*.md
6. Open Claude Code with task spec
7. Execute (Claude Code does the build)
8. Run tests
9. If behavioral: run Chrome demo, generate flow-review.md
10. Write result to projects/X/tasks/NNN-*.md (update status, add result)
11. git add -A && git commit -m "task NNN: complete" && git push
12. Dashboard detects new commit, updates review queue
```

### 7.3 Conflict Handling

Since you're the only user, conflicts are rare. Strategy:
- Executor always pulls before starting a task
- Dashboard writes via API that holds a per-file lock
- On conflict: dashboard wins (manual edits take precedence over executor)

---

## 8. Build Phases

**Phase 0: Foundation (Day 1-2)**
- [ ] Create Git repo `foundry-vault` on VPS
- [ ] Write `goals.md`, `principles.md`, `existing-systems.md` by hand
- [ ] Set up Tailscale on all devices
- [ ] Decide port allocation on VPS

**Phase 1: Killer + Vault Skeleton (Week 1-2)**
- [ ] Build vault directory structure
- [ ] Implement `TriageLLM` abstraction with LiteLLM under the hood
- [ ] Implement `models.yaml` loader + sensitive overrides
- [ ] Implement classifier (validates type, asks if ambiguous)
- [ ] Implement idea-killer as standalone Python script (no dashboard yet)
- [ ] Test idea-killer against 10 real brain dump entries
- [ ] Iterate until kill rate is honest (60-80%)
- [ ] Implement feature-killer
- [ ] Implement bug-triage
- [ ] Implement interviewer, critic, atomizer, task-tagger (idea path only for v1)
- [ ] Triage coordinator CLI (`foundry triage` runs the right killer per entry)

**Phase 2: Dashboard MVP (Week 3-4)**
- [ ] FastAPI scaffold
- [ ] SQLite indexer (reads vault, builds index)
- [ ] Brain dump capture page with type/project/state fields
- [ ] "Triage Now" endpoint — synchronous classifier + killer run
- [ ] Project list + detail pages
- [ ] Pipeline view
- [ ] Models settings page (edit `models.yaml`, test endpoints)
- [ ] Mobile CSS pass

**Phase 3: Project Generator (Week 4)**
- [ ] "New Project" flow: AI-assisted PROJECT.md + CLAUDE.md generation
- [ ] Tech stack detection from description
- [ ] Deploy/test template selection

**Phase 4: Executor Integration (Week 5)**
- [ ] Git sync model tested across all 3 machines
- [ ] Task pickup script on MacBook
- [ ] Result writeback
- [ ] Chrome demo runner for behavioral tasks

**Phase 5: Review Flow (Week 5-6)**
- [ ] Review queue page (mobile)
- [ ] Approve / Reject / Revise actions
- [ ] Telegram notification on new review item
- [ ] Result rendering (flow-review.md with inline screenshots)

**Phase 6: MCP Server (Week 7)**
- [ ] FastMCP server on VPS
- [ ] Read tools implemented
- [ ] Write tools with confirmation pattern
- [ ] Test against Claude.ai

**Phase 7: Polish + Hardening (Week 8)**
- [ ] Token budget enforcement
- [ ] Pause flag mechanism
- [ ] Quiet hours
- [ ] Backup strategy for vault
- [ ] Daily digest report

**Rule:** No phase begins until the previous phase has been used successfully against 3 real tasks/ideas.

---

## 9. Tech Stack Summary

| Layer | Choice | Reason |
|-------|--------|--------|
| Backend | FastAPI (Python 3.11+) | Familiar, async, good for AI integration |
| Templates | Jinja2 + HTMX | Server-rendered, mobile-friendly, no SPA complexity |
| Styles | Tailwind CSS | Fast mobile-first development |
| State | SQLite | Single file, no server, lives in vault |
| Source of truth | Markdown in Git | Human-editable, portable, no lock-in |
| AI adapter | LiteLLM | Multi-provider (Anthropic / OpenRouter / mlx-local / Ollama), already in Anang's stack |
| Default cloud model | Anthropic API | Sonnet for judgment, Haiku for bulk |
| Local fallback | mlx-lm on MacBook | Sensitive content routing (trading, financial) |
| MCP | FastMCP (Python) | Same ecosystem as backend |
| Sync | Git over SSH | Already understood, reliable |
| Network | Tailscale | No public auth needed |
| Executor | Claude Code | Builds the actual code |
| Browser automation | Chrome skill (Claude Code) | For behavioral demos |
| Notifications | Telegram bot | Already in Anang's workflow |
| Process management | systemd (VPS) | Standard, reliable |

---

## 10. Deployment

### 10.1 VPS Setup

```bash
# On cPanel SSH
cd ~
git init --bare foundry-vault.git
git clone foundry-vault.git foundry-vault

# Python environment
python3.11 -m venv ~/foundry-env
source ~/foundry-env/bin/activate
pip install fastapi uvicorn jinja2 sqlalchemy anthropic litellm fastmcp httpx pyyaml gitpython

# systemd services (one per: dashboard, mcp, triage-worker)
# Run via cPanel's Application Manager or as user-level systemd
```

### 10.2 Dev Machine Setup

```bash
# Clone vault
git clone ssh://anang@vps/home/anang/foundry-vault.git ~/foundry-vault

# Add executor script to PATH
ln -s ~/foundry-vault/bin/run-next-task.sh ~/bin/

# Claude Code config points to ~/foundry-vault for project context
```

### 10.3 Tailscale

```bash
# All devices: install Tailscale, log in to same account
# VPS gets a stable name like foundry.tail-net.ts.net
# Dashboard URL: http://foundry.tail-net.ts.net:8000
# MCP URL: http://foundry.tail-net.ts.net:8001
```

---

## 11. Testing Strategy

### 11.1 Per-Component Tests

- **Killer:** test against a curated set of 20 ideas with known verdicts. Track kill rate and reasoning quality.
- **Interviewer:** integration test — give it a partial idea, verify it asks specific questions.
- **Critic:** test against deliberately weak specs, verify it catches gaps.
- **Atomizer:** verify it splits a known large spec into the expected number of tasks.
- **Dashboard:** Playwright tests for critical flows (approve, reject, brain dump capture).
- **MCP:** test from a Claude.ai conversation against a known vault state.

### 11.2 End-to-End Test

Take a known idea through the full flow:
1. Add to brain dump via mobile
2. Run triage
3. Verify it survives killer + gets specced
4. Verify atomizer splits correctly
5. Pull on MacBook, run Claude Code
6. Verify Chrome demo runs
7. Approve via mobile dashboard
8. Verify Git state is clean

---

## 12. Open Questions / Decisions Deferred

1. **Backup strategy for vault** — Git remote alone isn't enough. Decision deferred to Phase 7.
2. **Multi-project token budget** — global or per-project caps? Deferred until usage data exists.
3. **Killed-idea revival** — automated pattern detection vs manual review? Deferred until graveyard has 30+ entries.
4. **VPS resource limits** — cPanel may restrict long-running Python processes. May need to move to a small dedicated VPS if cPanel limits bite.

---

## 13. Risk Register

| Risk | Impact | Mitigation |
|------|--------|------------|
| Killer too lenient → builder addiction returns | High | Monthly kill-rate audit, retune prompts |
| cPanel restricts long-running processes | Medium | Fallback to small dedicated VPS (Hetzner/DO) |
| Token budget overrun | Medium | Hard daily cap, executor halts on hit |
| Git conflicts between dashboard writes and executor pushes | Low | Per-file locking + dashboard-wins policy |
| Tailscale outage | Low | Local-only fallback (SSH tunnel as backup) |
| Spec quality drift → bad builds | High | Critic skill is mandatory, no skipping |
| Builder addiction transfers to building The Foundry itself | Highest | Phase rule: prove previous phase before starting next |

---

## 14. Definition of Done (for The Foundry itself)

The Foundry is "done" when:

1. An idea typed into mobile brain dump on Monday evening
2. Goes through triage automatically on Tuesday morning
3. If it survives, gets specced and atomized into tasks by Tuesday afternoon
4. Tasks get pulled and executed by MacBook overnight
5. Review queue is full on phone by Wednesday morning
6. Anang reviews 5-10 tasks during Wednesday work shift
7. Approved tasks deploy via manual approval Wednesday evening
8. By Thursday, the idea is running in the world

If this loop runs without manual intervention beyond review + deploy approval, The Foundry is done. Everything else is polish.

---

## 15. The Anti-Addiction Rule

This specification itself is a large building project. To prevent The Foundry from becoming the addiction it was designed to cure:

- **No phase begins until the previous phase is used against 3 real items.**
- **Phase 1 (the killer) must run against 10 real ideas before Phase 2 starts.**
- **If a phase takes more than 2x its estimated time, stop and triage The Foundry itself through the killer.**
- **The Foundry's own development tasks live in `projects/foundry/tasks/` and are subject to the same rules as everything else.**

If you find yourself wanting to add features to The Foundry that aren't in this spec, those ideas go into the brain dump. They get triaged like everything else. No exceptions.
