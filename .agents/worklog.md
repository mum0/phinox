# PHINOX Agent Worklog

> **Append-only.** Every agent reads this file in full before starting work,
> and appends a new `---` section when finishing. Never edit a prior entry.
> See `.agents/CONTRIBUTING.md` for the format.

---

Task ID: META-000
Agent: Z.ai (initial constitution delivery)
Started: 2025-01-01T22:00:00+02:00
Finished: 2025-01-01T22:30:00+02:00

Task:
Initial Project Audit + Architecture Map + AGENTS.md constitution + agent
overlays + first task spec (TASK-001). Set up the governance scaffold so
that subsequent agents (Kimi, Claude, Z.AI, or any other) can pick up
real PHINOX work in a consistent, agent-agnostic way.

Work Log:
- Extracted `phinox.rar` (uploaded by user) into `phinox-audit/phinox/`.
- Read all 14 apps' `models.py`, `apps/pages` views+urls, `apps/core` views,
  `config/settings/{base,dev,prod}.py`, `config/urls.py`, `requirements/*`,
  `package.json`, `tailwind.config.js`, `static/css/tokens.css`,
  `templates/base.html` + `base_standard.html` + `pages/home.html`,
  `docker/{Dockerfile,docker-compose.yml}`.
- Synthesized audit into `ARCHITECTURE_MAP.md` (10 sections: system context,
  app inventory, data model map, request flow, template inheritance, token
  system, infrastructure, open questions, tech debt, revision log).
- Wrote `AGENTS.md` constitution with 11 sections + a "Golden Rules" prelude
  (Architecture, Tech Stack, Folder Structure, Coding, Security, Database,
  Git, Testing, UI/UX, Business, AI Agent Rules).
- Wrote `.claude/CLAUDE.md` as an anti-lock-in overlay (points back to
  AGENTS.md, adds Claude-specific ergonomics only).
- Wrote `.kimi/KIMI.md` as a Kimi overlay (long-context strengths,
  ergonomic notes, same anti-lock-in posture).
- Wrote `.agents/CONTRIBUTING.md` (task lifecycle, worklog convention,
  pick-up rules, conflict resolution).
- Wrote `.agents/tasks/TASK-001-catalog-read-api.md` (Phase 3a first task:
  read-only DRF endpoints for Category/Product/ProductVariant, with full
  API contract, acceptance criteria, factories, test cases, and explicit
  out-of-scope list).

Decisions:
- Constitution written in English, not Arabic: the existing README, code
  comments, and all model docstrings are in English. Mixing languages in
  governance files would create a precedent for mixed-language code
  artifacts, which AGENTS.md §4 explicitly forbids. (Conversation with the
  human stays in Arabic/Egyptian.)
- AGENTS.md is agent-agnostic by design; `.claude/` and `.kimi/` are
  overlays that must not contradict it. This is the "anti-lock-in" rule
  (§11) — PHINOX must never depend on a single AI agent.
- First task chosen as Catalog Read API (not Auth, not Cart) because:
  (a) read-only → low risk, (b) exercises full DRF stack on real schema,
  (c) unblocks TASK-002 (cart) and TASK-003 (PDP), (d) contained enough
  for one agent-session.
- TASK-001 is scoped to **read-only** with explicit out-of-scope list.
  Phase discipline (AGENTS.md §0 rule 3) forbids skipping ahead to writes,
  search, or auth in this task.
- `ModelSerializer` with explicit `id` chosen over `HyperlinkedModelSerializer`
  for TASK-001 because the future frontend is server-rendered Django
  templates + vanilla JS, not a hyperlink-following SPA. (Decision is
  pre-seeded in the task spec for the picking-up agent to confirm.)

Open questions surfaced:
- None new. The 7 pre-existing open questions from the README are
  transcribed into ARCHITECTURE_MAP.md §8 with their blocking relationships.
  TASK-001 is scoped to not require any of them to be resolved first.

Files added/changed:
- ARCHITECTURE_MAP.md — as-is system map, 10 sections.
- AGENTS.md — constitution, 11 sections + Golden Rules.
- .claude/CLAUDE.md — Claude overlay (anti-lock-in).
- .kimi/KIMI.md — Kimi overlay (long-context strengths).
- .agents/CONTRIBUTING.md — task lifecycle + worklog convention.
- .agents/tasks/TASK-001-catalog-read-api.md — Phase 3a first task spec.
- .agents/worklog.md — this file (initial entry).

Next-task recommendation:
- TASK-001 (Catalog Read API) is ready to be picked up by the first agent.
  After TASK-001: TASK-002 (cart service — add/remove/merge, guest +
  auth), which is the real Phase 3b work and unblocks checkout.

---

Task ID: META-001 (handoff note)
Agent: Z.ai
Finished: 2025-01-01T22:30:00+02:00

Task:
Handoff note for the next agent (or the human, if no agent is queued).

Work Log:
- The governance scaffold is complete and self-consistent. The next agent
  should NOT edit AGENTS.md, ARCHITECTURE_MAP.md, or any overlay without
  human sign-off.
- The next agent's job is to execute TASK-001 (or whatever task the human
  assigns next) following the pick-up procedure in
  `.agents/CONTRIBUTING.md §3`.

Decisions:
- If the next agent is Kimi: lean into long-context per `.kimi/KIMI.md`.
- If the next agent is Claude: follow the reading order in
  `.claude/CLAUDE.md`.
- If the next agent is Z.AI or any other: read AGENTS.md in full, then
  ARCHITECTURE_MAP.md, then CONTRIBUTING.md, then this worklog, then the
  task file. Create a `<agent-name>/<AGENT_NAME>.md` overlay if one
  doesn't exist yet (follow the .kimi/.claude pattern).

Open questions surfaced:
- None.

Files added/changed:
- None (this is a handoff note, not a code change).

Next-task recommendation:
- Pick up TASK-001. Branch: `phase/3-catalog-read-api`.
