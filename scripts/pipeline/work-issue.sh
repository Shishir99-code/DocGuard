#!/usr/bin/env bash
# work-issue.sh — point the autonomous pipeline at ONE specific GitHub issue.
#
# Triggers the server-side Feature Dispatch workflow to implement → test → secure →
# open a PR that closes the issue, then hands it to the AI Review → Fix → Auto-Merge loop.
# The PR body gets `Closes #<issue>`, so merging closes the issue and moves its board
# card to Done.
#
# Usage:  scripts/pipeline/work-issue.sh <issue-number>
#
# Note: the actual build needs the Claude GitHub App installed on the repo
# (https://github.com/apps/claude). The dispatch itself works without it.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ISSUE="${1:?usage: work-issue.sh <issue-number>}"
REPO=$(gh repo view --json nameWithOwner --jq .nameWithOwner)

# 1. Validate the issue exists and is open.
info=$(gh issue view "$ISSUE" --repo "$REPO" --json state,title --jq '.state + "\t" + .title') || {
  echo "Issue #$ISSUE not found in $REPO" >&2; exit 1; }
state=${info%%$'\t'*}; title=${info#*$'\t'}
[[ "$state" == "OPEN" ]] || { echo "Issue #$ISSUE is $state, not OPEN." >&2; exit 1; }
echo "→ Dispatching the pipeline for issue #$ISSUE: $title"

# 2. Move its board card to In Progress for visibility (best-effort).
if bash "$ROOT/scripts/pipeline/board.sh" move-issue "$ISSUE" "In Progress" >/dev/null 2>&1; then
  echo "  board: #$ISSUE → In Progress"
else
  echo "  board: skipped (issue not on the board, or no project scope on this token)"
fi

# 3. Trigger the server-side build for this specific issue.
gh workflow run feature-dispatch.yml --repo "$REPO" -f issue="$ISSUE"
echo "  triggered Feature Dispatch for issue #$ISSUE."
echo
echo "Watch the run:"
echo "  gh run watch \"\$(gh run list --workflow=feature-dispatch.yml -L1 --json databaseId --jq '.[0].databaseId')\""
echo "Actions tab:  https://github.com/$REPO/actions/workflows/feature-dispatch.yml"
