# Project Research Summary

**Project:** DocGuard — Correctness Improvement Milestone
**Domain:** Python CLI / static AST analysis / OpenAPI drift detection
**Researched:** 2026-06-02
**Confidence:** HIGH

## Executive Summary

DocGuard is a static analysis tool that compares FastAPI source code (via AST) against OpenAPI specs to detect drift. The v0.1.0 release made progress on false positives, but six correctness issues remain that produce wrong output on real-world applications. All six are fixable with stdlib AST manipulation and dict traversal — zero new dependencies are required. The recommended approach is to work in two tight phases: first fix the issues that silently drop entire endpoints or produce zero output (router names, parse failures, determinism), then fix the issues that corrupt field-level data ($ref resolution, type normalization, severity threshold).

The single biggest risk is that `include_router` prefix concatenation is entirely unimplemented. Any app that mounts sub-routers with a prefix (the standard FastAPI pattern for anything beyond a toy app) will show all endpoints as path-mismatched or missing. This is not one of the six MF-series fixes — it requires a new two-pass architecture — but it will surface immediately on any non-trivial real-world app and must be scoped explicitly, not deferred indefinitely.

The second structural risk is silent failure: when DocGuard detects 0 endpoints, it currently looks like success rather than a configuration error. Every correctness fix is undermined if the tool can fail silently without surfacing why.

---

## Recommended Stack

All fixes are pure Python. No new entries in `pyproject.toml` are needed.

- `ast.NodeVisitor` subclasses — router name collection (`_RouterNameCollector`), type annotation resolution
- stdlib dict traversal — generalized `_resolve_component_ref` covering all `#/components/X/name` refs
- `sorted(Path.rglob(...))` — one-line determinism fix in `_collect_source_files`
- Severity filter in `cli.py` — pure comparison, no library needed

---

## Table Stakes (Must Fix)

Ordered by impact:

1. **MF-1 — Router variable names** — apps using `api`, `v1`, `users_router` produce zero endpoints silently. Fix: `_RouterNameCollector` pre-pass + `router_names` config key.
2. **MF-6 — Silent parse failures** — `SyntaxError`/`OSError` swallowed with no output. One `sys.stderr.write` unblocks all diagnosis; add `source_warnings` to `DriftReportMetadata` for JSON output.
3. **MF-2 — `$ref` parameters silently dropped** — spec params using `$ref: '#/components/parameters/Foo'` are ignored, producing false `PARAM_ADDED_IN_CODE` drift. Fix: generalize `_resolve_ref` to cover `components/parameters`.
4. **MF-5 — `severity_threshold` never applied** — documented config key does nothing. ~15-line fix in `cli.py` after `compare()`.
5. **MF-4 — `Union[A, B]` collapse** — non-nullable unions silently return left branch → false TYPE_MISMATCH. Fix: return `"object"` for ambiguous unions.
6. **MF-3 — External/non-schema `$ref` warnings** — unresolvable refs produce empty field lists with no diagnostic.

Should-fix (real-world reliability, not blocking correctness today): `Annotated[X, Query(...)]` type extraction, import-based `can_handle`, `requestBodies/$ref`, `include_in_schema=False`, git subprocess timeout, pyproject.toml URLs.

---

## Watch Out For

1. **`include_router` prefix not implemented (CRITICAL)** — sub-routers mounted with `prefix=` have all paths wrong. Blocks real-world usage for non-trivial apps.
2. **Zero endpoints looks like success** — `total_endpoints_in_code: 0` with `fail_on: drift-only` exits 0. Add explicit guard: warn loudly when source files found but zero endpoints detected.
3. **`allOf` schemas not merged** — inherited Pydantic models produce `allOf` in the spec; loader returns empty fields, so all response fields appear as drift.
4. **`_RouterNameCollector` must run across all files in pass 1** — routers defined in one file and decorated in another require the collector to have seen all files before `_RouteVisitor` runs.
5. **`Depends` alias imports** — `from fastapi import Depends as Di` breaks the skip list; document as known limitation.

---

## Implementation Order

**Phase 1 — Foundation (silence, determinism)**
- `sorted()` in `_collect_source_files`
- Parse failure warnings + `source_warnings` in `DriftReportMetadata`
- Zero-endpoints guard in CLI
- `timeout=5` on git subprocess calls

**Phase 2 — Spec Loader $ref & allOf**
- Generalize `_resolve_ref` → `_resolve_component_ref` (all `#/components/X/name`)
- Thread full `components` dict through `normalize_spec`, `_schema_to_fields`, `_extract_parameters`
- Add `allOf` merging in `_schema_to_fields`

**Phase 3 — Parser Correctness**
- `_RouterNameCollector` pre-pass; `router_names` in `CheckConfig`
- Union → `"object"` fallback in `_resolve_annotation`
- `Annotated` outer-type unwrapping

**Phase 4 — include_router Prefix Support**
- Pass 0: collect `include_router(var, prefix=...)` calls; build prefix map
- Apply prefixes in `_RouteVisitor`
- Design decision: depth limit for nested routers

**Phase 5 — Config & CLI Polish**
- Wire `severity_threshold` in CLI
- `include_in_schema=False` suppression
- Fix pyproject.toml URLs

---

## Open Questions

1. **`include_router` depth limit:** Single-level only (covers ~80% of apps), or nested?
2. **`severity_threshold` semantics:** Controls exit code only, or also filters display?
3. **`allOf` + `$ref` interaction:** Does `_resolve_component_ref` run before or inside the `allOf` merge?
4. **`source_warnings` placement:** Add to `DriftReportMetadata` (clean model change) or accumulate on `FastAPIParser` instance (no model change)?

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Verified against installed transitive deps; zero new deps confirmed |
| Features | HIGH | All MF-series bugs confirmed by direct source code reading |
| Architecture | HIGH | All findings from direct file inspection of 5 source files |
| Pitfalls | HIGH | Derived from code analysis + prior fix history (commit 28f11f6) |
