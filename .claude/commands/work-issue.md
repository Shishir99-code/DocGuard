---
description: Have the agent pipeline build one specific GitHub issue end-to-end
argument-hint: <issue-number>
---

Drive the local pipeline on a single GitHub issue. This runs in the current Claude Code
session (no GitHub App required) — use it to build issue **#$ARGUMENTS** right now.

Delegate to the `pipeline-orchestrator` subagent with this directive:

> Work on GitHub issue **#$ARGUMENTS** in this repository, end-to-end and unattended.
>
> 1. Read the authoritative spec: `gh issue view $ARGUMENTS --comments`. Treat its
>    acceptance criteria as the definition of done.
> 2. Move its board card to In Progress:
>    `bash scripts/pipeline/board.sh move-issue $ARGUMENTS "In Progress"` (ignore failure).
> 3. Branch from up-to-date `main` (`pipeline/<slug>`), then run the full loop:
>    plan → implement (atomic commits) → tests green (`pytest` + `ruff` + `mypy`) →
>    security pass → pre-push self-review (`pr-reviewer`).
> 4. Open the PR: body implements the issue's acceptance criteria as checkboxes, explains
>    the change, and **contains `Closes #$ARGUMENTS`**. Label it `ai-pipeline`. Move the
>    board card to In Review (`board.sh move-issue $ARGUMENTS "In Review"`).
>
> Honor every DocGuard guardrail (AST-only parser, no new runtime deps, `.docguard.yaml`
> back-compat, no LLM in check/report, strict mypy). Stop once the PR is open — the
> server-side AI Review → Fix → Auto-Merge loop takes it from there. Report the PR URL.

For a fully server-side (terminal-closed) build of an issue instead, run:
`scripts/pipeline/work-issue.sh $ARGUMENTS`.
