# Agent Contributing Guide — PHINOX

> This file describes how AI agents pick up work, log it, and hand off to the
> next agent. It is referenced from `AGENTS.md §11`. Read it before your first
> task; revisit it if you're unsure how to log work.

---

## 1. The task lifecycle

```
┌──────────────────────────────────────────────────────────────┐
│  HUMAN creates a task spec:                                  │
│    .agents/tasks/TASK-NNN-<slug>.md                          │
│  (goal, scope, files, acceptance criteria, phase)            │
└──────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────────┐
│  AGENT picks up the task:                                    │
│    1. Read AGENTS.md + ARCHITECTURE_MAP.md                   │
│    2. Read .agents/CONTRIBUTING.md (this file)               │
│    3. Read .agents/worklog.md (all of it — append-only)      │
│    4. Read .agents/tasks/TASK-NNN-<slug>.md                  │
│    5. Read relevant app source                               │
└──────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────────┐
│  AGENT works:                                                │
│    - Append a "Started" entry to worklog.md                  │
│    - Make changes (surgical edits preferred)                 │
│    - Run ruff + pytest + makemigrations --check              │
│    - Append a "Finished" entry to worklog.md                 │
└──────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────────┐
│  AGENT opens PR:                                             │
│    - Branch: phase/<N>-<slug>                                │
│    - Title: feat(<app>): <summary>                           │
│    - Body references: Task: .agents/tasks/TASK-NNN-...md     │
│    - Squash-merge to main                                    │
└──────────────────────────────────────────────────────────────┘
```

---

## 2. Worklog convention

The worklog lives at `.agents/worklog.md`. It is **append-only**.

- Every entry starts with a `---` horizontal rule.
- Every entry has a header block (Task ID, Agent, Started, Finished).
- Every entry has the five body sections: Task, Work Log, Decisions, Open
  questions surfaced, Files added/changed, Next-task recommendation.
- Never edit a prior entry. If you made a mistake, append a correction
  entry that references the original by Task ID.

### Entry template

```markdown
---
Task ID: TASK-NNN
Agent: <agent name + model>
Started: <ISO 8601 with timezone>
Finished: <ISO 8601 with timezone>

Task:
<one-line summary of the assigned task>

Work Log:
- <step 1 — concrete and verifiable>
- <step 2>
- <step 3>
- ...

Decisions:
- <decision 1>: <why — reference AGENTS.md section if applicable>
- <decision 2>: <why>

Open questions surfaced:
- <if any — reference ARCHITECTURE_MAP.md §8 row, or propose a new row>

Files added/changed:
- <path 1> — <one-line description>
- <path 2> — <one-line description>

Next-task recommendation:
- <one-line suggestion for the next agent, with a proposed Task ID>
```

### When to log

- **At task start**: append a "Started" entry with the Task header and the
  Task summary. No body sections yet.
- **During work**: optional intermediate updates are encouraged for long
  tasks (> 1 hour), to avoid progress loss if the session dies. Append
  them as additional `---` sections with the same Task ID.
- **At task finish**: append the full entry (with all body sections). If
  you already appended a "Started" entry, the "Finished" entry is a new
  `---` section — do not edit the "Started" one.

---

## 3. How to pick up a task

1. **Check `.agents/tasks/`** for files matching `TASK-NNN-*.md`.
2. **Read `.agents/worklog.md`** to see which tasks are already in progress
   or done. A task with a "Finished" entry in the worklog is done — do not
   pick it up again unless the entry says "blocked" or "incomplete".
3. **Pick the lowest-numbered unclaimed task** that matches the current
   phase (per `AGENTS.md §1` phase roadmap). Do not jump ahead.
4. **Append a "Started" entry** to the worklog before reading source code.
   This claims the task — another agent seeing your entry should not pick
   up the same task.

If no task files exist, **do not invent one**. Escalate to the human: the
absence of tasks is a planning gap, not an invitation to freestyle.

---

## 4. How to finish a task

Before appending the "Finished" entry:

1. **`ruff check . && ruff format --check .`** — must pass.
2. **`pytest`** — must pass. If no tests exist for the touched app yet,
   document that in the worklog (it's a known gap, not a failure).
3. **`python manage.py makemigrations --check --dry-run`** — must report
   "no changes". If it reports drift, either fix the migration or fix the
   model (model is source of truth per `AGENTS.md §6`), then re-run.
4. **Open a PR** (or hand off to the human for PR review, depending on
   workflow). Branch name: `phase/<N>-<slug>`.

---

## 5. Handoff to the next agent

The "Next-task recommendation" field in your worklog entry is the handoff.
It should:

- Propose a specific Task ID (e.g. "TASK-002: cart service — add/remove/merge").
- Be one line — the human will write the full task spec, not you.
- Reference the phase (e.g. "Phase 3b") so the human knows where it fits.
- Note any blockers that should influence task ordering (e.g. "blocked on
  open question #5 — don't start TASK-004 until that's resolved").

If your task surfaced an open question, **add it to `ARCHITECTURE_MAP.md §8`**
as a new row (append, do not edit existing rows) before appending your
"Finished" worklog entry.

---

## 6. Conflict resolution

If two agents are working in parallel and their changes conflict:

1. The agent who appended their "Started" entry **first** has priority.
2. The second agent must either rebase onto the first's work or pick a
   different task.
3. If both started simultaneously (timestamps within 5 minutes), escalate
   to the human — do not race.

If an agent's work contradicts a decision in a prior worklog entry:

1. Do not silently override it.
2. Append a new entry referencing the prior one: "Contradicts TASK-NNN
   decision X because Y".
3. If the contradiction is with `AGENTS.md` itself, **stop** — escalate.

---

## 7. The worklog is the project's memory

Treat `.agents/worklog.md` as the single source of truth for "what's been
done and why". Code can be read from the diff, but **why** decisions were
made only lives here.

- If you find yourself about to make a decision and you don't see it
  addressed in the worklog, **check `AGENTS.md` and `ARCHITECTURE_MAP.md`
  first**. If it's not there either, it's a new decision — log it.
- If you find yourself about to reverse a prior decision, **find the prior
  worklog entry** that made it, reference it, and explain why the reversal
  is warranted. Do not silently reverse.

The worklog is the project's memory across agents and sessions. Protect it.
