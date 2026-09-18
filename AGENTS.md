# AGENTS.md — Global AI Agent Working Rules

## 1. Source of Truth & Context Hierarchy
The CURRENT native repository on `main` is authoritative. Do not infer current status from old plans.
When starting any task, agents MUST load context in this exact strict order:
1. `AGENTS.md` (this file — working rules and safety invariants)
2. `docs/CURRENT_STATE.md` (canonical current operational milestone and capability status)
3. `docs/CURRENT_BATCH.md` (active batch scope, objectives, and explicit boundaries)
4. Task-relevant module documentation only (see `docs/README.md` index)
5. Task-relevant source and test files only

**DO NOT** load historical audit/remediation logs or planning documents (`implementation_plan.md`, `docs/REMEDIATION_STATUS.md`, `docs/FEATURE_FREEZE.md`) by default.
**DO NOT** perform full-repository discovery scans (`find_by_name` across entire workspace) unless explicitly necessary.
**DO NOT** re-read unchanged large files repeatedly without a concrete reason.

## 2. Trading Safety Invariants (Absolute — Fail-Closed)
The following core invariants are non-negotiable across all branches and tasks:
- `TRADING_MODE=PAPER` must be preserved in all configurations and runtimes.
- `LIVE_AUTO_TRADING=false` must never be set to true.
- Authority Hierarchy: **Kill Switch > Risk Engine > Strategy Engine > AI Advisory > Human Operator**.
- AI agents are **ADVISORY ONLY**; they have ZERO execution authority, cannot place orders, cannot bypass Risk Engine decisions, and cannot fabricate market data.
- Broker Execution (`order_send`), OMS, and Live Position Management are **NOT IMPLEMENTED** and strictly prohibited from being stubbed or enabled.

## 3. Scope Discipline & Anti-Progression Rules
- Work ONLY on the active batch declared in `docs/CURRENT_BATCH.md`.
- **DO NOT** automatically begin the next batch (e.g., strictly **DO NOT** start Batch C).
- **DO NOT** investigate or attempt to fix out-of-scope defects unless they directly block the current task; report them in the final report instead.
- Do not redesign closed architectures (Batch A, B1, B2 are closed; B3.x is pending verification).

## 4. Loop Prevention & Retry Limits
- **DO NOT** retry the same failed command or approach more than 2 times without a distinct hypothesis.
- If the same blocker or test failure persists after 3 attempts: **STOP IMMEDIATELY**.
- When stopping on a blocker, report:
  1. Exact blocker description
  2. Concrete error evidence / logs
  3. Attempted approaches and why they failed
  4. Affected files
  5. Recommended next action

## 5. Model Routing & Escalation Guidelines
Do not default to High thinking or expensive models for routine tasks. Escalate only when justified:
- **Codex / Terra Medium**: Routine implementation, code edits, refactoring.
- **Luna Low / Medium**: Mechanical tasks, repetitive edits, formatting.
- **Gemini 3.8 Flash Low / Medium**: Documentation, repository scans, secondary review, probe verification.
- **Sol High**: Critical security architectures, concurrency/race closure, risk authority, final independent verification gates.

## 6. Git & Workspace Safety
- Do not create feature branches unless explicitly requested.
- Do not commit or push unless explicitly requested by the user prompt.
- Never run destructive git commands (`git reset --hard`, `git rebase`, `git commit --amend`, `git push --force`).
- Prior to ending, verify `git status` shows only expected files and that no application source files were modified during documentation tasks.

## 7. Task Handoff & Completion
At completion of each session:
- Update `docs/HANDOFF.md` (rolling 50–100 line summary; not an append-only archive).
- Return the required structured final report matching the prompt template exactly.
- State clearly whether the next step requires an independent verification gate.
