# DocGuard Autonomous AI Pipeline

A self-driving feature factory: give it **one direction**, and it plans → implements →
tests → secures → opens a PR → reviews it → fixes the review → merges — looping to the
next board item until you interrupt or the board's **Ready** column is empty.

It runs in two layers that hand off to each other:

| Layer | Where it runs | Responsibility |
|---|---|---|
| **Local subagents** (`.claude/agents/`) | Your machine, in a Claude Code session | Plan, implement, test, secure, self-review, open the PR |
| **GitHub Actions** (`.github/workflows/`) | GitHub servers, event-driven | Review every PR, fix the review, gate + auto-merge, dispatch the next feature |

```
            you: /pipeline "build X"   (or move a board card to Ready)
                         │
        ┌────────────────▼────────────────┐
        │  pipeline-orchestrator (local)   │
        │  planner→implementer→test-author │
        │  →security-auditor→pr-reviewer   │
        └────────────────┬────────────────┘
                         │ opens PR (label: ai-pipeline)
                         ▼
   ┌─────────────── GitHub Actions (server-side, no you) ───────────────┐
   │  ci.yml ── quality-gate ─────────────────────────────┐            │
   │  ai-review.yml ─ labels ai-approved / ai-changes-requested         │
   │        │ changes requested                  │ approved             │
   │        ▼                                     ▼                      │
   │  ai-fix.yml ─ fix blocking / neglect nits ─ push ─┐  auto-merge.yml │
   │        └────────── re-triggers review ◄───────────┘  (merges when  │
   │                                                      green+approved)│
   │  feature-dispatch.yml ─ on merge, start the next Ready feature ─────┘
   └────────────────────────────────────────────────────────────────────┘
```

## The loop, precisely

1. **Dispatch.** A feature enters from `/pipeline "<desc>"` locally, by moving a board
   card to **Ready**, or automatically: when a PR merges, `feature-dispatch.yml` pulls
   the next Ready card and runs the whole build in CI.
2. **Build (local agents or feature-dispatch).** Branch `pipeline/<slug>` off `main` →
   plan → implement (atomic commits) → tests green (`pytest`+`ruff`+`mypy`) → security
   pass → self-review → open PR labeled `ai-pipeline`, card → **In Review**.
3. **Review** (`ai-review.yml`, every push). Applies DocGuard's rubric, posts inline +
   summary comments, sets exactly one label: `ai-approved` or `ai-changes-requested`.
4. **Fix** (`ai-fix.yml`, on `ai-changes-requested`). Fixes blocking findings at the root,
   **neglects** non-blocking ones with a one-line rationale, runs the gate, pushes. The
   push re-triggers review. **Bounded to 3 attempts** → then labels `blocked` for a human.
5. **Merge** (`auto-merge.yml`). On `ai-approved`, enables GitHub native auto-merge, which
   completes **only when the `quality-gate` check is green**. Nothing red ever reaches main.
6. **Advance.** On merge: card → **Done**, branch deleted, `feature-dispatch.yml` starts the
   next Ready feature. The loop continues with no input from you.

## "Fix or neglect" — how findings are routed

- **Blocking** (correctness bug, reintroduced false-positive / missed endpoint, guardrail
  break, type-safety hole, missing test, security issue): **must** be fixed. Never neglected.
- **Non-blocking** (naming, docstrings, minor dup, perf nits): may be **neglected** with a
  posted one-line rationale, or fixed. The reviewer and `pr-reviewer` agent share this rubric.

## Files in this pipeline

```
.claude/agents/
  pipeline-orchestrator.md     drives the local build loop (opus, can spawn agents)
  feature-planner.md           file-level plan + acceptance criteria (read-only)
  feature-implementer.md       writes code in atomic commits
  test-author.md               pytest incl. false-positive / missed-endpoint cases
  pipeline-security-auditor.md AST-only/no-exec, safe YAML, ReDoS, secrets
  pr-reviewer.md               local mirror of the server reviewer (pre-push gate)
  (~/.claude/agents/agent-installer.md — browse/install community agents)
.claude/commands/pipeline.md   the /pipeline entry point
.claude/settings.json          permission allowlist so the local loop runs smoothly
.github/workflows/
  ci.yml                       tests+ruff+mypy → the `quality-gate` required check
  ai-review.yml                autonomous PR review + verdict labels
  ai-fix.yml                   addresses review findings, bounded to 3 attempts
  auto-merge.yml               arms native auto-merge when approved+green; card→Done
  feature-dispatch.yml         pulls next Ready feature and builds it in CI
.github/pull_request_template.md
.github/pipeline.env           generated IDs (board/project/status) — do not hand-edit
scripts/pipeline/
  bootstrap_github.sh          one-time: labels, board, repo settings, branch protection, seed
  board.sh                     add / next-ready / move / done-pr helpers
  seed_features.txt            starter backlog (edit freely)
```

---

## Arming checklist (one time)

The pipeline is fully written but **inert** until these are done. Steps 1–4 need you;
the rest I can run for you once auth works.

1. **Re-authenticate `gh`** (the keyring token is currently invalid) with the scopes the
   board automation needs:
   ```bash
   gh auth login -h github.com
   gh auth refresh -h github.com -s project,read:project,repo,workflow
   ```
2. **Add a Claude Code OAuth token** as a repo secret (server-side Claude runs bill against
   your Claude subscription — no separate API-billed account):
   ```bash
   claude setup-token                     # interactive: logs in, prints a long-lived token
   gh secret set CLAUDE_CODE_OAUTH_TOKEN  # paste the token from the previous step
   ```
   > Alternative: use an API key instead — `gh secret set ANTHROPIC_API_KEY` and swap the
   > `claude_code_oauth_token:` lines back to `anthropic_api_key:` in the three AI workflows.
2b. **Install the Claude GitHub App on the repo** — REQUIRED, and separate from the token.
   The OAuth token authenticates Claude to Anthropic; the GitHub App is what lets the
   `claude-code-action` authenticate to GitHub (post reviews, push fixes). Without it the
   AI workflows fail with `401 — Claude Code is not installed on this repository`.
   ```bash
   # In the Claude Code terminal:
   /install-github-app
   # …or visit https://github.com/apps/claude → Install → select this repo.
   ```
3. **(Optional) Projects v2 token.** Moving board cards from CI needs a PAT with `project`
   scope (the default `GITHUB_TOKEN` can't always edit user/org projects):
   ```bash
   gh secret set PIPELINE_PROJECT_TOKEN   # classic PAT with `project` scope
   ```
   Without it, everything works except automatic card moves from CI.
4. **Push these files** so the workflows exist on `main`:
   ```bash
   git switch -c chore/ai-pipeline && git add .claude .github scripts docs && \
   git commit -m "feat: autonomous AI subagent pipeline" && git push -u origin chore/ai-pipeline
   # open + merge that PR (this first one is your manual gate)
   ```
5. **Run the bootstrap** (creates labels, the board, repo merge settings, branch
   protection requiring `quality-gate`, and seeds the backlog):
   ```bash
   bash scripts/pipeline/bootstrap_github.sh
   ```
6. **Kick it off.** Either locally — `/pipeline "your first feature"` (or `/loop /pipeline next`)
   — or fully server-side: move a board card to **Ready** and run the **Feature Dispatch**
   workflow once (`gh workflow run feature-dispatch.yml`). From the first merge onward it
   self-continues.

## Cost & safety controls (built in)

- **Bounded fix loop:** max 3 AI-fix attempts per PR, then `blocked` for a human.
- **One feature at a time:** `feature-dispatch` serializes via concurrency + an "open
  pipeline PR" guard, so branches don't collide and spend doesn't fan out.
- **Turn budgets:** `--max-turns` on every server run (review 30, fix 50, dispatch 80).
- **Nothing red merges:** branch protection requires the `quality-gate` check; auto-merge
  only completes on green.
- **Guardrails enforced at every stage:** no new runtime deps, AST-only parser, no LLM in
  `check`/`report`, `.docguard.yaml` back-compat, strict mypy.
- **You can always interrupt:** stop the local session, remove `ai-approved`, label a PR
  `blocked`, or disable a workflow (`gh workflow disable feature-dispatch.yml`).

## Troubleshooting

- **Auto-merge never fires:** ensure repo setting *Allow auto-merge* is on and branch
  protection requires `quality-gate` (both set by `bootstrap_github.sh`; needs admin).
- **Branch protection step failed in bootstrap:** the REST call needs admin and a JSON
  body on some API versions. Set it in the UI: Settings → Branches → add rule for `main`
  → Require status checks → `quality-gate`. Leave "require approvals" at 0 (a bot review
  can't satisfy a required human approval).
- **Cards don't move from CI:** set `PIPELINE_PROJECT_TOKEN` (step 3).
- **Status options missing on the board:** open the board → Status field → add
  `Backlog, Ready, In Progress, In Review, Done`, then re-run bootstrap to refresh
  `.github/pipeline.env`.
- **Reviewer too strict/noisy:** tune the rubric in `ai-review.yml` and `pr-reviewer.md`
  (they intentionally share wording — keep them in sync).
