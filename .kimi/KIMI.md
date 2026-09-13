# KIMI.md — Kimi Overlay

> **This file is an overlay, not a constitution.**
> The canonical source of truth is [`../AGENTS.md`](../AGENTS.md). Read it first.
> This file adds Kimi-specific ergonomic notes only. **It must not
> contradict `AGENTS.md`.** If it ever appears to, `AGENTS.md` wins.

---

## Why this file exists

PHINOX is agent-agnostic by policy (see `AGENTS.md §11` — Anti-lock-in rule).
This file exists so that Kimi, when invoked in this repo, knows where to find
the constitution and how to format its work — **not** to give Kimi special
authority over Claude, Z.AI, Codex, Cursor, or any other agent.

If you are Kimi and you're reading this: your job is the same as every other
agent's. Read the constitution. Do the task. Log the work. Don't lock the
project into yourself.

---

## Reading order (Kimi-specific)

When Kimi is assigned a task in this repo, read in this exact order:

1. `AGENTS.md` — the constitution (non-negotiable).
2. `ARCHITECTURE_MAP.md` — the as-is system map.
3. `.agents/CONTRIBUTING.md` — worklog convention + how to pick up tasks.
4. `.agents/worklog.md` — every prior agent's log (append-only — read all of it).
5. `.agents/tasks/TASK-NNN-*.md` — the specific task assigned.
6. The relevant app's `models.py`, then `views.py` / `serializers.py` / `urls.py` if they exist.

Kimi's long-context strength is an asset here — prefer to read `worklog.md`
and large source files in full rather than chunking, when feasible. Decisions
from 20 entries ago may still be in force.

---

## Kimi-specific ergonomic notes

These do not change the rules in `AGENTS.md`. They just describe how Kimi
in particular should apply them.

### Long-context usage
- Kimi's context window is among the largest available. Use it: read the
  full `worklog.md` before starting, not just the most recent entries.
- When a task touches multiple apps, read all their `models.py` files in
  one pass before writing any code. Cross-app constraint relationships
  (e.g. `Order.coupon` → `Coupon.valid_until`, `OrderItem.variant` →
  `ProductVariant.sku`) are easy to miss in isolation.
- When reviewing a PR, read the full diff in one pass, then form a judgment.
  Do not comment file-by-file if the cross-file consistency is the real issue.

### Search strategy
- Prefer `Grep` with `-A`/`-B`/`-C` context flags over multiple single-line
  searches. Kimi handles large result sets well — pull the context, then
  reason about it.
- For "where is X used" questions, use `Grep` output mode `files_with_matches`
  first, then `Read` each file. Do not rely on memory from training data —
  the codebase may have diverged.

### Response language
- The human-facing conversational language may be Arabic (Egyptian), English,
  or a mix. Mirror the user's language in conversation.
- **Code, comments, docstrings, commit messages, worklog entries, and
  governance files are always in English.** This is a hard rule from
  `AGENTS.md §4` — do not localize code artifacts.

### When to ask vs. when to proceed
- `AGENTS.md §0` rule 10 says: "When unsure, write a short design note in the
  worklog and ask." For Kimi specifically:
  - **Ask** if: a constraint seems to contradict another, an open question
    applies, a phase boundary would be crossed, or a new dependency would
    be introduced.
  - **Proceed** if: the task spec is unambiguous, the constitution clearly
    permits the action, and no open question applies.
  - When in doubt between the two, **ask**. Kimi's long-context strength is
    in synthesizing the full picture, not in guessing faster.

### Worklog format
Kimi should append worklog entries in this exact shape (matches
`.agents/CONTRIBUTING.md`):

```markdown
---
Task ID: TASK-NNN
Agent: Kimi (model: <kimi-version>)
Started: 2025-01-01T12:00:00+02:00
Finished: 2025-01-01T13:30:00+02:00

Task:
<one-line summary of the assigned task>

Work Log:
- <step 1>
- <step 2>
- <step 3>

Decisions:
- <decision 1>: <why>
- <decision 2>: <why>

Open questions surfaced:
- <if any, with reference to ARCHITECTURE_MAP.md §8>

Files added/changed:
- <path 1>
- <path 2>

Next-task recommendation:
- <one-line suggestion for the next agent>
```

---

## What Kimi must NOT do in this repo

- Must not edit `AGENTS.md` or `ARCHITECTURE_MAP.md` without explicit human
  sign-off in the task spec.
- Must not add `# kimi-generated` or `# kimi-ignore` markers to committed code.
  Comments are for humans.
- Must not create a `.kimi/config.json` that overrides project policy.
- Must not assume Kimi is the only agent. Every worklog entry must be
  readable and actionable by a different agent in the next session.
- Must not rename or move governance files. The paths in `AGENTS.md §3` are
  stable contracts.

---

## Kimi-specific strengths to lean into

These are areas where Kimi's design makes it well-suited for PHINOX work.
Lean into them; they're a net positive for the project.

- **Long-context synthesis**: when a task spans many files (e.g. "audit all
  constraints across all apps", "trace the full checkout flow from cart to
  payment webhook"), Kimi can hold the full picture in one pass. Use this
  for cross-cutting tasks that would fragment a shorter-context agent.
- **Mathematical reasoning**: when a task involves money math (coupon
  redemption, order total reconciliation, Paymob amount validation), Kimi
  can reason through the precision/rounding edge cases carefully. Double-
  check every `Decimal` operation against `AGENTS.md §10` (Money rules).
- **Documentation**: Kimi tends to write thorough docstrings. This aligns
  with `AGENTS.md §4` (every module + every model has a docstring). Lean
  into it.

---

## Sign-off

This overlay was written by Z.ai on 2025-01-01 as part of the initial
constitution delivery. It exists to make Kimi a well-behaved citizen of
an agent-agnostic project — not to elevate Kimi above other agents.

If you are Kimi and you disagree with anything in `AGENTS.md`, the
correct response is to surface the disagreement in the worklog and ask the
human — not to work around it here.
