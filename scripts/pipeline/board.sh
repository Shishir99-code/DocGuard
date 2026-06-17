#!/usr/bin/env bash
# board.sh — thin wrapper over the GitHub Projects v2 board used by the autonomous
# pipeline. Reads IDs from .github/pipeline.env (written by bootstrap_github.sh).
#
# Usage:
#   board.sh add "<title>" [status]        Create a draft item (default status: Backlog)
#   board.sh next-ready [--title-only]      Print the first item whose Status == Ready
#   board.sh move <item-id> "<status>"      Set an item's Status
#   board.sh move-title "<title>" "<status>" Set Status by item title
#   board.sh done-pr <pr-number>            Set the item linked to a PR to Done
#   board.sh list [status]                  List items (optionally filtered by Status)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="$ROOT/.github/pipeline.env"

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$ENV_FILE"
else
  echo "board.sh: $ENV_FILE not found — run scripts/pipeline/bootstrap_github.sh first." >&2
  exit 3
fi

: "${PROJECT_NUMBER:?set in pipeline.env}"
: "${PROJECT_OWNER:?set in pipeline.env}"
: "${PROJECT_ID:?set in pipeline.env}"
: "${STATUS_FIELD_ID:?set in pipeline.env}"
STATUS_FIELD_NAME="${STATUS_FIELD_NAME:-Status}"

# Map a status name -> its single-select option id (exported as STATUS_OPT_<UPPER_SNAKE>).
status_opt_id() {
  local name="$1" var
  var="STATUS_OPT_$(echo "$name" | tr '[:lower:] ' '[:upper:]_')"
  echo "${!var:-}"
}

# Reads go through GraphQL: fieldValueByName is deterministic regardless of how the
# gh CLI flattens custom-field keys. Returns {"items":[{id,title,url,status}]}.
items_json() {
  gh api graphql -f query='
    query($id: ID!, $field: String!) {
      node(id: $id) {
        ... on ProjectV2 {
          items(first: 200) {
            nodes {
              id
              content { __typename
                ... on Issue        { url title }
                ... on PullRequest  { url title }
                ... on DraftIssue   { title }
              }
              fieldValueByName(name: $field) {
                ... on ProjectV2ItemFieldSingleSelectValue { name }
              }
            }
          }
        }
      }
    }' -f id="$PROJECT_ID" -f field="$STATUS_FIELD_NAME" --jq '
    { items: [ .data.node.items.nodes[] | {
        id: .id,
        title: (.content.title // ""),
        url: (.content.url // ""),
        status: (.fieldValueByName.name // "")
      } ] }'
}

cmd_add() {
  local title="$1" status="${2:-Backlog}"
  local out item_id
  out=$(gh project item-create "$PROJECT_NUMBER" --owner "$PROJECT_OWNER" \
        --title "$title" --format json)
  item_id=$(echo "$out" | jq -r '.id')
  cmd_move "$item_id" "$status"
  echo "$item_id"
}

cmd_move() {
  local item_id="$1" status="$2" opt
  opt=$(status_opt_id "$status")
  [[ -n "$opt" ]] || { echo "Unknown status '$status'" >&2; exit 4; }
  gh project item-edit --id "$item_id" --project-id "$PROJECT_ID" \
    --field-id "$STATUS_FIELD_ID" --single-select-option-id "$opt" >/dev/null
  echo "Moved $item_id -> $status"
}

cmd_move_title() {
  local title="$1" status="$2" id
  id=$(items_json | jq -r --arg t "$title" '.items[] | select(.title==$t) | .id' | head -1)
  [[ -n "$id" ]] || { echo "No board item titled '$title'" >&2; exit 5; }
  cmd_move "$id" "$status"
}

cmd_next_ready() {
  local title_only="" json first
  [[ "${1:-}" == "--title-only" ]] && title_only=1
  json=$(items_json)
  first=$(echo "$json" | jq -r '.items[] | select((.status // "") == "Ready") | .title' | head -1)
  [[ -n "$first" ]] || exit 0
  if [[ -n "$title_only" ]]; then
    echo "$first"
  else
    echo "$json" | jq -r --arg t "$first" '.items[] | select(.title==$t) | "\(.id)\t\(.title)"' | head -1
  fi
}

cmd_done_pr() {
  local pr="$1" url id
  url=$(gh pr view "$pr" --json url --jq .url)
  id=$(items_json | jq -r --arg u "$url" '.items[] | select(.url==$u) | .id' | head -1)
  if [[ -z "$id" ]]; then echo "No board item linked to PR #$pr"; exit 0; fi
  cmd_move "$id" "Done"
}

cmd_list() {
  local status="${1:-}"
  if [[ -n "$status" ]]; then
    items_json | jq -r --arg s "$status" '.items[] | select((.status // "")==$s) | "\(.title)"'
  else
    items_json | jq -r '.items[] | "[\(.status // "-")] \(.title)"'
  fi
}

case "${1:-}" in
  add)        shift; cmd_add "$@" ;;
  move)       shift; cmd_move "$@" ;;
  move-title) shift; cmd_move_title "$@" ;;
  next-ready) shift; cmd_next_ready "${1:-}" ;;
  done-pr)    shift; cmd_done_pr "$@" ;;
  list)       shift; cmd_list "${1:-}" ;;
  *) echo "Unknown command. See header of $0 for usage." >&2; exit 2 ;;
esac
