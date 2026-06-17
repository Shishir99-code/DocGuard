---
description: Drive the DocGuard autonomous feature pipeline (plan→implement→test→secure→PR)
argument-hint: [feature description | "next" to pull from the board]
---

Run the autonomous development pipeline for DocGuard.

Delegate to the `pipeline-orchestrator` subagent. Pass it this directive:

> Feature: $ARGUMENTS
>
> If the feature is "next" or empty, pull the next item from the GitHub Project
> board's **Ready** column (`scripts/pipeline/board.sh next-ready`). Otherwise treat
> $ARGUMENTS as the feature to build, ensuring it exists on the board.
>
> Take it through the full loop: plan → implement → test (green) → security pass →
> pre-push self-review → open a PR labeled `ai-pipeline`. Honor every DocGuard
> guardrail. Once the PR is open, the server-side AI Review → AI Fix → Auto Merge
> workflows take over. Then either stop (if the user asked for one feature) or pull
> the next Ready item and continue.

Notes:
- For a continuous local loop, the user can run `/loop /pipeline next` — each tick
  builds the next Ready feature and opens its PR.
- The orchestrator must never bypass a guardrail; if a feature requires it, it
  surfaces that on the board item and moves on rather than guessing.
