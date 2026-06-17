<!-- PRs labeled `ai-pipeline` are reviewed automatically by .github/workflows/ai-review.yml. -->

## What & why
<!-- Board item / feature this implements, and the change in one paragraph. -->

## Acceptance criteria
<!-- Checkboxes the planner defined; the reviewer verifies these. -->
- [ ]

## Guardrail check
- [ ] Python 3.11+, `from __future__ import annotations`, strict mypy clean
- [ ] No new runtime dependency (or justified below)
- [ ] `.docguard.yaml` remains backwards-compatible
- [ ] No LLM added to the `check`/`report` path
- [ ] Parser stays AST-only (no import/exec of analyzed code)
- [ ] Tests added, including a false-positive / missed-endpoint case where relevant

## Notes / neglected findings
<!-- Non-blocking review findings intentionally not addressed, with rationale. -->
