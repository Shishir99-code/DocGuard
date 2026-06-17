# DocGuard — Correctness & Consistency

## What This Is

DocGuard is a Python CLI tool that detects documentation drift between an OpenAPI spec and the actual FastAPI source code, running as a static analyzer (no live server needed). It is used primarily in CI pipelines (GitHub Actions, pre-commit) to catch spec divergence before it reaches production. This milestone focuses on eliminating false positives and incorrect drift detection that make the tool unreliable on real-world FastAPI apps.

## Core Value

A developer running `docguard check` on any real FastAPI app gets accurate, deterministic results — zero false positives, zero silently missed endpoints.

## Requirements

### Validated

- ✓ CLI with `check`, `fix`, `report`, `init` commands — existing
- ✓ FastAPI endpoint extraction via two-pass AST analysis — existing
- ✓ OpenAPI spec loading and normalization — existing
- ✓ Drift comparison producing `DriftReport` — existing
- ✓ Text, JSON, and GitHub Actions output formats — existing
- ✓ `.docguard.yaml` config file with Pydantic validation — existing
- ✓ GitHub Actions integration (`action.yml`) — existing
- ✓ Basic false positive elimination for standard app/router names — v0.1.0

### Active

- [ ] Custom router variable names are detected and respected (not just `app`/`router`)
- [ ] OpenAPI `$ref` parameters are resolved, not silently dropped
- [ ] External `$ref` and multi-file specs are partially resolved (at least warn when skipped)
- [ ] `Optional[X]` and `Union[A, B]` types compared correctly to OpenAPI equivalents
- [ ] `severity_threshold` config key actually filters drift output as documented
- [ ] Silent parse failures produce user-visible warnings (files skipped are reported)
- [ ] Running DocGuard twice on the same codebase always produces identical output

### Out of Scope

- LLM fixer improvements (`fixers/llm_fixer.py`) — separate feature, different risk profile
- New output formats — no user request
- New frameworks (non-FastAPI) — scope creep
- Full multi-file `$ref` resolution — complex; partial resolution + warning is sufficient for now
- Web UI or interactive mode — not the tool's purpose
- Performance optimization — not a current pain point

## Context

DocGuard v0.1.0 ships and the core pipeline works for simple FastAPI apps. Real-world testing (`28f11f6`) already fixed one round of false positives. The known correctness gaps come from:

1. **Router detection too narrow** — `_ROUTER_NAMES = {"app", "router"}` is hardcoded. Any project naming its router `api`, `v1`, `prefix_router`, etc. sees zero detected endpoints with no warning. The user's real app hits this case.

2. **`$ref` parameters silently dropped** — `_extract_parameters` calls `param.get("name")` on a raw dict. When a parameter is a `$ref` object, `.get("name")` returns `None` and the parameter is skipped. This makes spec parameters appear missing from the code, producing false drift.

3. **External `$ref` ignored in spec loader** — `_resolve_ref` skips any `$ref` that doesn't start with `"#/components/schemas/"`. Split-file specs or remote refs produce empty field lists, so every field looks like drift.

4. **Type mapping gaps** — `Union[A, B]` collapses to the left branch; `Optional` falls back to `"string"`. These produce type-mismatch drift on correctly-typed endpoints.

5. **`severity_threshold` is a no-op** — the config key is validated by Pydantic but never read at comparison or reporting time. Users who configure it to reduce noise see no effect.

6. **Silent failures** — `SyntaxError` and `OSError` during AST parsing are caught and `continue`d with no log output. In CI, this means real endpoints are invisible with no trace.

## Constraints

- **Tech stack**: Python 3.9+, no new runtime dependencies without strong justification — tool is installed in CI environments where dep count matters
- **Backwards compatibility**: `.docguard.yaml` config file format must remain backwards-compatible — existing CI configs must keep working
- **No LLM in core pipeline**: The `check`, `report` path must remain LLM-free — it runs on every CI push and must be fast and deterministic
- **AST-only parser**: FastAPI endpoint extraction stays AST-based (no import/exec) — safe to run in restricted CI environments

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Router names configurable via config file (not CLI flag) | Consistent with existing config-first design; CLI flags are for one-off overrides | — Pending |
| Warn on skipped `$ref` rather than error | External refs are valid OpenAPI; refusing to run would break existing users | — Pending |
| Type normalization happens in comparator, not parser | Parser should reflect source code faithfully; normalization is a comparison concern | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-06-02 after initialization*
