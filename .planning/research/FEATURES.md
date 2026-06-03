# Feature Landscape: DocGuard Correctness Improvements

**Domain:** API documentation drift detector (FastAPI + OpenAPI, static AST analysis)
**Researched:** 2026-06-02
**Scope:** What a reliable drift detector must handle correctly

---

## Must-Fix (causes incorrect output today)

These produce wrong results — false positives, silent endpoint loss, or zero output — on real apps.

---

### MF-1: Router variable name detection is too narrow

**Current behavior:** `_ROUTER_NAMES = {"app", "router"}` at line 30 of `fastapi_parser.py`. The check at line 204 uses `any(r in obj_name.lower() for r in _ROUTER_NAMES)`, so only decorators on objects whose name contains `"app"` or `"router"` are recognized. Any other name produces zero endpoints with no warning.

**What the ecosystem actually uses:**

The canonical FastAPI docs (`/tutorial/bigger-applications/`) always name the variable `router`, and most tutorials follow this. But in real production projects several other patterns are prevalent:

- `api_router = APIRouter()` — the "aggregate router" pattern, where one file collects sub-routers from feature modules and exposes a single `api_router` for `main.py` to include. Confirmed seen in FastAPITutorial.com examples.
- `users_router`, `auth_router`, `items_router` — feature-suffixed names, extremely common in domain-driven structures (zhanymkanov best-practices pattern).
- `v1_router = APIRouter(prefix="/v1")` — versioned routers.
- `internal_router`, `admin_router` — access-scoped names.
- Routers returned from factory functions: `def create_router() -> APIRouter: ...` — application factory pattern, discussed in fastapi/fastapi#5343 and #6302.
- APIRouter subclasses: `class AuthRouter(APIRouter): ...` then `auth = AuthRouter()`. Discussed in fastapi/fastapi#3079.
- `router` imported as module attribute: `from .routers import items, users` then `app.include_router(users.router)` — the `obj_name` resolves to `users.router` or `items.router` in the AST. The current `"router" in obj_name.lower()` substring check handles this by coincidence, but only because the attribute name is `router`.

**Root cause of the gap:** The check is substring-based on the variable name at the call site, not on what the variable is bound to. It cannot detect `api_router.get(...)` because `"api"` is not in `_ROUTER_NAMES` and `"api_router"` does not contain `"app"` or `"router"` as a substring... wait — actually `"router"` IS a substring of `"api_router"`. Re-examining line 204: `any(r in obj_name.lower() for r in _ROUTER_NAMES)` where `_ROUTER_NAMES = {"app", "router"}`. So `"router" in "api_router"` = True. The actual failure case the user hit was a variable name like `api` (bare), or `v1`, or a custom name containing neither `"app"` nor `"router"`.

**Concrete failing examples:**
```python
api = APIRouter()        # "api" contains neither "app" nor "router"
v1 = APIRouter()         # "v1" contains neither
endpoints = APIRouter()  # "endpoints" contains neither
```

**Fix approach:** Two complementary strategies:
1. First-pass AST scan: collect all names bound to `APIRouter()` or `FastAPI()` calls. Use those names as the dynamic router set for the second pass.
2. Config escape hatch: `router_names` list in `.docguard.yaml` for projects that need immediate relief without waiting for the AST improvement.

The config escape hatch is the right immediate fix (matches the "Key Decisions" in PROJECT.md). The AST-based approach is the correct long-term fix and eliminates the config requirement entirely.

**Warning needed:** When zero endpoints are found after parsing, emit a stderr warning: `"Warning: 0 endpoints detected in <N> source files. If your router uses a non-standard variable name (e.g. 'api', 'v1'), add it to router_names in .docguard.yaml."` This transforms a silent failure into an actionable message.

---

### MF-2: `$ref` parameters in OpenAPI spec silently dropped

**Current behavior:** `_extract_parameters` in `spec_loader.py` (lines 117-131) calls `param.get("name", "")` on each parameter dict. When a parameter is a Reference Object (`{"$ref": "#/components/parameters/UserId"}`), `.get("name")` returns `""` and `.get("in")` returns `""`. The field is appended as `InferredField(name="", type="string", required=False)` — a ghost field that matches nothing.

Actually re-reading line 119-130: since `name = param.get("name", "")` returns `""` and `location = param.get("in", "")` also returns `""`, the field ends up in neither `path_fields` nor `query_fields` (neither `"path"` nor `"query"` matches). So the parameter is silently discarded, not added as a ghost.

**How common is this pattern:** The OpenAPI 3.x spec explicitly allows parameters arrays to contain either Parameter Objects or Reference Objects. The pattern `$ref: '#/components/parameters/ParameterName'` is a standard DRY practice recommended by Speakeasy, Redocly, and in the official spec (confirmed: spec.openapis.org/oas/v3.1.0). It is used to share common parameters (pagination, API version header, correlation IDs) across many endpoints without repeating them inline.

**What breaks:** Shared parameters defined in `components/parameters` are invisible to DocGuard. The spec endpoint appears to have no parameters. The code endpoint has parameters. This produces false `PARAM_ADDED_IN_CODE` drift for every endpoint using the shared parameter pattern.

**Fix:** In `_extract_parameters`, when a `param` dict has a `"$ref"` key, resolve it against `spec["components"]["parameters"]` before extracting `name`/`in`. The resolution path is `#/components/parameters/<name>`, analogous to how `_resolve_ref` handles `#/components/schemas/<name>`.

**Note:** The current `_resolve_ref` in `spec_loader.py` only resolves against `components_schemas`, not `components_parameters`. A separate resolver or a generalized one is needed.

---

### MF-3: External `$ref` in schemas produces empty field lists

**Current behavior:** `_resolve_ref` (lines 226-243) returns the input schema unchanged for any `$ref` that doesn't start with `"#/components/schemas/"`. This means:
- `"$ref": "./schemas/user.yaml"` → returns the `{"$ref": "..."}` dict unchanged
- `"$ref": "https://example.com/schemas/user.json"` → same
- `"$ref": "#/components/responses/..."` → same (wrong prefix)
- `"$ref": "#/components/requestBodies/..."` → same

When the unchanged `{"$ref": "..."}` dict goes through `_schema_to_fields`, it has no `type`, no `properties`. Result: `None` is returned. Every field in that schema appears as drift.

**How common in the wild:** External `$ref` is a standard OpenAPI pattern for large API specs (confirmed in openapi-generator issues #1976, Stoplight blog). However, full external ref resolution (fetching remote URLs, reading other files) is complex and was correctly scoped out of this milestone. What IS missing is the **warning**: users get unexplained drift, not a message telling them why.

**Fix:** When `_resolve_ref` encounters an unresolvable `$ref` (non-schema local ref, external file, remote URL), instead of silently returning the raw schema, emit a warning string. Collect these warnings into a `source_warnings` list on the report (see MF-5). This converts a silent failure into an actionable diagnostic.

---

### MF-4: `Union[A, B]` type resolution collapses to left branch silently

**Current behavior:** `_resolve_annotation` in `fastapi_parser.py` (lines 109-116): for `X | Y` (PEP 604) where neither side is `None`, it returns `left, False`. No warning. `Union[str, int]` becomes `"str"` → JSON type `"string"`. The spec says `anyOf: [string, integer]`. The comparator sees `string` vs (whatever the spec says) and flags a mismatch.

**What FastAPI/Pydantic actually generates in OpenAPI:** `Union[A, B]` where neither is None → `anyOf: [{$ref: A}, {$ref: B}]` for model types, or `anyOf: [{type: string}, {type: integer}]` for primitives (confirmed: fastapi/fastapi#4959, fastapi/fastapi#8504). The spec says `anyOf`, the code parser says the first type. Comparator always sees a mismatch.

**Common patterns affected:**
- `Union[str, int]` — flexible ID fields accepting both formats
- `Union[ModelA, ModelB]` — polymorphic response bodies (discriminated unions)
- `Optional[X]` where X is not in `_PYTHON_TYPE_TO_JSON` — the inner type resolves to `"object"` but the spec says the actual type name

**Fix:** In `_resolve_annotation`, when encountering a non-nullable union, return a special sentinel type like `"anyOf"` or map to `"object"` (closest JSON Schema equivalent) with a flag indicating it was a union. In `_schema_to_fields`, when the spec side uses `anyOf`, the comparator needs to know both sides are "union-ish" to avoid false TYPE_MISMATCH. This requires coordination between the parser and comparator — the type normalization should happen in the comparator as per PROJECT.md's key decision.

**Simpler near-term fix:** For `Union[A, B]` where neither is None, return `"object"` instead of the left branch. The spec's `anyOf` resolves to `"object"` at the field level since `_schema_to_fields` sees object-type schemas. This eliminates the false mismatch without requiring a full anyOf-aware comparator.

---

### MF-5: `severity_threshold` config key is loaded but never applied

**Current behavior:** `DocGuardConfig.check.severity_threshold` defaults to `"error"` but is never read in `cli.py`. All diffs — `Severity.ERROR`, `Severity.WARNING`, `Severity.INFO` — are displayed and counted regardless of this setting. Users who set `severity_threshold: warning` to reduce noise see no change.

**Mental model from the ecosystem (Spectral as reference):** Spectral uses `--fail-severity` which sets the minimum severity that causes a non-zero exit code. Rules still run and produce output at all severity levels, but only violations at or above the threshold contribute to CI failure. This is the correct mental model: **threshold controls CI failure, not display**. Display can have a separate `--min-severity` or show all by default.

For DocGuard's current scope, the simpler interpretation is: `severity_threshold` determines which diffs are counted toward `fail_on` and toward the exit code. Diffs below the threshold are still shown but do not trigger failure.

**Fix:** In `cli.py`, after `compare()` returns the report, filter the set of "active" diffs by `severity >= cfg.check.severity_threshold` before computing the exit code. The full report (all diffs) is still output for visibility. This makes the existing documented behavior actually work.

---

### MF-6: Silent parse failures produce no user-visible output

**Current behavior:** `extract_endpoints` in `fastapi_parser.py` (lines 380-384):
```python
except (SyntaxError, OSError):
    continue
```
No log, no warning, no counter. In CI, an endpoint file with a syntax error simply disappears from DocGuard's view. The user sees "0 endpoints in code" with no explanation.

**Fix:** Surface failures in two places:
1. Immediately at parse time: `sys.stderr.write(f"Warning: skipped {filepath}: {type(e).__name__}: {e}\n")` — cheap, immediate, zero model changes.
2. In the report: add `source_warnings: list[str]` to `DriftReportMetadata` or `DriftReport`. Populate it during `extract_endpoints` by returning `(endpoints, warnings)` or by threading a warning accumulator through. This allows JSON/GitHub output formats to surface warnings in CI annotations.

The CONCERNS.md already identifies this as an opportunity (line 125). It is a must-fix because silent file skipping produces incorrect output (wrong endpoint count, false missing_in_code drift).

---

## Should-Fix (improves reliability for real-world apps)

These do not cause obviously wrong results in most cases but are reliability gaps that will surface on real teams.

---

### SF-1: `can_handle` does not check Python imports

**Current behavior:** `FastAPIParser.can_handle` only reads `requirements.txt`, `pyproject.toml`, `setup.py`, `setup.cfg`. If FastAPI is in `uv.lock`, `poetry.lock`, inline script metadata (`# /// script` PEP 723), or vendor-installed, detection returns `False` silently.

**Fix:** If no dependency manifest matches, fall back to scanning `*.py` files in `project_root` for `import fastapi` or `from fastapi import`. Cap the scan to top-level Python files and direct subdirectories to stay fast. This removes the need for `--framework fastapi` as a workaround.

---

### SF-2: `Annotated[X, Query(...)]` parameter type not recognized

**Current behavior:** `_parse_function_params` calls `_resolve_name(annotation)` which returns `"Annotated"` for `Annotated[str, Query(...)]`. This does not match any Pydantic model or any known DI type, so it falls through to `json_type = _PYTHON_TYPE_TO_JSON.get("Annotated", "string")` — producing `"string"` with the actual inner type discarded.

**How common:** The FastAPI docs explicitly recommend the `Annotated` pattern for all new code (as of FastAPI 0.100+). Real projects use `Annotated[str, Query(max_length=50)]`, `Annotated[int, Path(ge=1)]`, `Annotated[str | None, Query()] = None` pervasively. This is the modern FastAPI idiom.

**Fix:** In `_resolve_annotation` (or a new helper called from `_parse_function_params`), detect `Annotated` as the outer name and extract the first type argument as the actual type. Detect the second argument's type (`Query`, `Path`, `Header`, `Cookie`, `Body`) to determine the parameter location. This also unlocks correct detection of `Header` and `Cookie` parameters which are currently never extracted.

---

### SF-3: `include_in_schema=False` parameters not suppressed

**Current behavior:** FastAPI supports `@app.get("/path", include_in_schema=False)` at the route level and `Query(include_in_schema=False)` at the parameter level. These suppress the endpoint or parameter from the generated OpenAPI spec. DocGuard sees the code endpoint but it is absent from the spec, producing false `MISSING_IN_SPEC` drift.

**Fix:** In `_parse_route_decorator`, check for `include_in_schema=False` in the decorator keywords. If present, skip the endpoint entirely. Similarly in `_parse_function_params`, skip parameters with `Query(include_in_schema=False)`.

---

### SF-4: `#/components/requestBodies/$ref` not resolved

**Current behavior:** `_extract_request_body` (spec_loader.py lines 135-145) reads `operation.get("requestBody", {})`. If the operation has `requestBody: {$ref: '#/components/requestBodies/CreateUser'}`, this returns `{"$ref": "..."}` directly. `body.get("content")` returns `None`. Result: no request body fields extracted, producing false drift on all request body fields.

**How common:** Shared request bodies via `components/requestBodies` are a standard OpenAPI DRY pattern, though less common than `$ref` in parameters or schemas. Generated specs from tools like openapi-generator often use it.

**Fix:** Before extracting `content` from `body`, check if `body` contains `$ref` and resolve it from `spec["components"]["requestBodies"]`.

---

### SF-5: Determinism — dict iteration order in `_schema_to_fields`

**Current behavior:** `properties = schema.get("properties", {})` then `for name, prop in properties.items()`. In Python 3.7+ dicts are insertion-ordered, but YAML loading order depends on the YAML library (PyYAML `safe_load` preserves insertion order). The `_visited` set modifies behavior on circular refs — this is fine. The issue is that `sorted(all_keys)` in comparator ensures sorted output, but the `InferredField` lists themselves (nested fields) are not sorted. If two runs produce fields in different orders (e.g., from different YAML loaders or spec regeneration), the comparator sees different orderings for the same semantic content.

**Fix:** Sort `fields` by `name` before returning from `_schema_to_fields` and `_extract_fields`. This is a one-line change per function and makes field order deterministic regardless of spec or source formatting.

---

### SF-6: `pyproject.toml` URLs pointing to wrong repository

**Current behavior:** `pyproject.toml` `[project.urls]` section points to `github.com/docguard/docguard` — a non-existent org. The actual repo is `Shishir99-code/DocGuard`.

**Fix:** Update the three URL fields. No functional impact but affects PyPI page, `pip show`, and contributor trust.

---

### SF-7: `git` subprocess has no timeout

**Current behavior:** `subprocess.check_output(["git", ...])` in `cli.py` (lines 93, 97) has no `timeout`. A stalled `git` process hangs DocGuard indefinitely in CI.

**Fix:** Add `timeout=5` to both calls. One-line change, high CI safety value.

---

## Nice-to-Have (polish, not blocking correctness)

These improve DX and robustness but do not affect whether drift detection is correct today.

---

### NTH-1: Config string fields should use `Literal` types

**Current behavior:** `fail_on`, `severity_threshold`, `format`, `framework` are raw `str` fields. A typo like `severity_threshold: wraning` silently falls through.

**Fix:** Use `Literal["error", "warning", "info"]` etc. in the Pydantic model. Pydantic V2 validates `Literal` fields on construction and raises a clear `ValidationError`. Zero runtime cost.

---

### NTH-2: Extract `_run_pipeline` helper to deduplicate CLI logic

**Current behavior:** `check`, `fix`, and `report` commands each repeat `_resolve_config_and_spec → detect parser → collect files → extract_endpoints → load_spec → normalize_spec → compare`. About 15 lines duplicated 3 times.

**Fix:** Extract `_run_pipeline(cfg, spec_path, source_path) -> DriftReport`. Reduces inconsistency risk when future changes only touch one command.

---

### NTH-3: Call `openapi-spec-validator` before normalizing

**Current behavior:** `openapi-spec-validator` is a hard dependency but never called. Invalid user specs produce confusing downstream errors (KeyError, empty field lists) instead of a clear "your spec is invalid" message.

**Fix:** Call `openapi_spec_validator.validate(spec)` in `normalize_spec` and surface any `ValidationError` as a user-visible fatal error with the spec path and the validator's message.

---

### NTH-4: `report_path` config key is never used

**Current behavior:** `OutputConfig.report_path` is documented in the default YAML but ignored at runtime.

**Fix:** In the `check` and `report` commands, if `cfg.output.report_path` is set, write the JSON report to that path in addition to stdout. Small implementation, removes a docs/behavior mismatch.

---

### NTH-5: `InferredField.default` loses type information

**Current behavior:** `_const_to_str` coerces all default values to `str`. `default=0` and `default=""` are indistinguishable after parsing.

**Fix:** Change `InferredField.default` to `Any` and store the original constant value. The comparator currently does not compare defaults (no `DEFAULT_MISMATCH` diff type exists), so this change has no immediate correctness impact. It is preparatory for future default comparison.

---

### NTH-6: `__all__` router exposure not detected

**Pattern:** Some projects define `__all__ = ["router"]` and export a router from a package `__init__.py` without a direct `APIRouter()` call in the file. The caller does `from myapp.routes import router` and calls `app.include_router(router)`. The file where routes are decorated has a local `router = APIRouter()`, which the current parser handles fine as long as the variable name is `router`. No fix needed today; documented here so it is not mistaken for a gap.

---

## Feature Dependencies

```
MF-1 (router names) → requires: warning on zero endpoints (part of MF-1 fix)
MF-2 ($ref parameters) → requires: generalized ref resolver (shared with MF-3)
MF-3 (external $ref warnings) → requires: source_warnings field (MF-6 fix)
MF-5 (severity_threshold) → requires: no dependencies; pure comparator/CLI change
MF-6 (silent failures) → blocks: MF-3 (needs the warnings surface)
SF-1 (import-based can_handle) → independent
SF-2 (Annotated types) → blocks correct detection for modern FastAPI apps
SF-3 (include_in_schema) → independent
```

---

## MVP Prioritization

**Implement in this order (highest correctness value per effort):**

1. **MF-1 (router names)** — the user's immediate pain; config escape hatch is one-afternoon work
2. **MF-6 (silent failures)** — one-line stderr write unblocks all diagnosis; `source_warnings` field is one afternoon
3. **MF-2 ($ref parameters)** — very common OpenAPI pattern; false drift on shared parameters is high noise
4. **MF-5 (severity_threshold)** — documented feature that doesn't work; one-hour fix in cli.py
5. **MF-4 (Union types)** — return `"object"` instead of left branch to eliminate false TYPE_MISMATCH
6. **MF-3 (external $ref warning)** — warning only; one-line addition to `_resolve_ref`

**Defer to next pass:**
- SF-2 (Annotated types): Correct but requires more AST plumbing; modern FastAPI best practice means this will surface on more projects over time
- SF-3 (include_in_schema): Rare edge case; not blocking correctness for typical apps
- SF-4 (requestBodies $ref): Less common than parameters $ref; same fix pattern, lower priority
- All NTH items: Polish, no correctness impact

---

## Anti-Features

| Anti-Feature | Why Avoid | What to Do Instead |
|---|---|---|
| Executing source code to detect routers | Unsafe in CI environments (arbitrary code execution) | Stay AST-only; use two-pass name collection |
| Fetching remote `$ref` URLs at runtime | Adds network dependency to a fast static tool; breaks in offline CI | Warn and skip external refs; bundle spec before running DocGuard |
| Guessing router type from decorators (e.g. checking `@app.middleware`) | Overfit to specific FastAPI idioms; fragile | Collect all `APIRouter()` and `FastAPI()` call targets in first pass |
| Interactive prompts in check/report commands | Breaks non-TTY CI usage | Stderr warnings, never prompts in non-interactive commands |
| LLM in the core check pipeline | Violates determinism and speed requirements | LLM stays in `fix` command only |

---

## Sources

- FastAPI official docs: Bigger Applications tutorial — `https://fastapi.tiangolo.com/tutorial/bigger-applications/`
- FastAPI best practices (zhanymkanov): `https://github.com/zhanymkanov/fastapi-best-practices`
- FastAPI application factory discussion: `https://github.com/fastapi/fastapi/discussions/6302`
- FastAPI custom APIRouter subclass issue: `https://github.com/fastapi/fastapi/issues/3079`
- FastAPI Union → anyOf discussion: `https://github.com/fastapi/fastapi/discussions/8504`
- FastAPI Union → anyOf issue: `https://github.com/fastapi/fastapi/issues/4959`
- FastAPI extra models (Union response): `https://fastapi.tiangolo.com/tutorial/extra-models/`
- FastAPI Annotated + Query/Path patterns: `https://fastapi.tiangolo.com/tutorial/query-params-str-validations/`
- Speakeasy OpenAPI $ref best practices: `https://www.speakeasy.com/openapi/references`
- OpenAPI $ref in parameters (Redocly): `https://redocly.com/learn/openapi/ref-guide`
- Spectral severity model: `https://docs.stoplight.io/docs/spectral/d373afba57903-open-api-support`
- openapi-generator external $ref issue: `https://github.com/OpenAPITools/openapi-generator/issues/1976`
- CLI UX patterns: `https://lucasfcosta.com/2022/06/01/ux-patterns-cli-tools.html`
- Heroku CLI style guide: `https://devcenter.heroku.com/articles/cli-style-guide`
