# Domain Pitfalls: DocGuard Correctness

**Domain:** FastAPI AST analysis + OpenAPI spec comparison tool
**Researched:** 2026-06-02
**Scope:** Pitfalls relevant to fixing correctness issues after the first false-positive fix round (commit 28f11f6)

---

## Critical Pitfalls

Mistakes that cause rewrites or major issues in practice.

---

### Pitfall 1: `_ROUTER_NAMES` Hardcoded to `{"app", "router"}`

**Component:** `fastapi_parser.py` line 30, `_parse_route_decorator`

**What goes wrong:** The decorator check at line 204 does `any(r in obj_name.lower() for r in _ROUTER_NAMES)`. Any project using `api`, `v1`, `users_router`, `api_router`, `prefix_router`, `bp`, or any custom name produces **zero detected endpoints** with no warning. DocGuard silently reports 0 code endpoints, finds everything as MISSING_IN_CODE, and exits 0 if `fail_on` is not "missing" — appearing successful while being completely wrong.

**Why it happens:** The set was defined narrowly to avoid false positives from non-FastAPI `app` objects, but the substring check (`r in obj_name.lower()`) is the only guard. It works for the sample app; it fails for nearly any real project.

**Consequences:**
- 100% false negatives: all real endpoints are invisible
- If `fail_on = "any"` the tool still exits 0 because there are no code-side diffs — only spec-side `MISSING_IN_CODE` results
- Users see a perfect drift score when the tool did not scan anything useful

**Warning signs:**
- `total_endpoints_in_code: 0` in the drift report summary with a non-empty source directory
- All endpoints reported as `MISSING_IN_CODE`

**Prevention:**
- In the near term: extend `_ROUTER_NAMES` to `{"app", "router", "api", "bp", "blueprint"}` and add common suffixes
- Better fix: Make `router_names` a config option (noted as an opportunity in CONCERNS.md). Default `["app", "router"]` but let projects override.
- Best fix: Scan `include_router` calls to discover which variables are APIRouter instances, then accept any variable used in an `include_router` call as a recognized router.

**Phase:** FastAPI parser correctness phase — very high priority.

---

### Pitfall 2: `include_router` Prefix Concatenation Is Entirely Unimplemented

**Component:** `fastapi_parser.py` — no code handles `include_router`

**What goes wrong:** Real FastAPI applications almost universally use `app.include_router(users_router, prefix="/users")`. The parser currently ignores all `include_router` calls. Routes defined on a sub-router have paths like `/` or `/{user_id}` in the router file — these will appear as bare paths without the prefix, so `GET /users/{user_id}` in the spec will never match `GET /{user_id}` inferred from the router file.

**Why it happens:** AST analysis requires a two-pass: first collect `include_router` calls to build a prefix map, then apply those prefixes when extracting routes. This was not implemented.

**Consequences:**
- Every endpoint in a prefix-mounted router produces a path mismatch or MISSING_IN_SPEC
- A project with `prefix="/api/v1"` on the main router will have all endpoints wrong
- The sample app uses `app` directly, so this was never exercised

**Warning signs:**
- All endpoints are `MISSING_IN_SPEC` or `MISSING_IN_CODE` despite identical logic
- Router file paths look like `/`, `/{id}`, `/create` — suspiciously bare

**Prevention:**
- Pass 0 (new): walk the main app file for `include_router(obj, prefix=...)` calls, building `{router_var_name: prefix_string}` map
- Pass 1: still collects Pydantic models
- Pass 2: when extracting routes, look up the variable's prefix in the map and prepend it

**Complexity note:** Prefixes can be defined at multiple levels (router included into another router). Only single-level prefix is required for the common case. Multi-level can be deferred with a depth limit.

**Phase:** FastAPI parser correctness phase — very high priority, blocks any real-world usage.

---

### Pitfall 3: Router Variable Aliasing (`import users_router as ur`)

**Component:** `fastapi_parser.py` `_parse_route_decorator` line 203–204

**What goes wrong:** `_resolve_name` returns the full attribute path of the decorator's object. If code writes `from .routers.users import router as users_router`, the variable `users_router` does not contain "app" or "router" as a substring — the lowercase check `"router" in "users_router"` is True by coincidence here, but `from .routers import api as v1_api` resolves to `v1_api`, which contains neither "app" nor "router" and will be silently skipped.

More subtly: when routers are defined in separate files, the AST in that file sees only the local name (e.g., `router`), which passes. But if the alias is used in the main file to call routes, those routes are in the router file anyway. The aliasing problem surfaces when someone writes:

```python
from .admin import router as admin_router

@admin_router.get("/users")
def ...
```

Here `admin_router` fails the substring check.

**Warning signs:**
- Endpoints decorated with `@<alias>.get(...)` where the alias contains neither "app" nor "router"
- Import lines like `import ... as api_v2`, `import ... as bp`

**Prevention:**
- The `include_router` pass (Pitfall 2) naturally solves aliasing: any variable passed to `include_router()` is a confirmed router, regardless of its name
- Separately, when scanning for decorators, check whether the variable name is in the discovered-router set rather than checking against a hardcoded name list

**Phase:** Solved as a byproduct of implementing `include_router` tracking.

---

### Pitfall 4: Silent Swallowing of Parse Failures

**Component:** `fastapi_parser.py` lines 382–384

**What goes wrong:**
```python
except (SyntaxError, OSError):
    continue
```
When a file fails to parse (syntax error, encoding error, permission denied), it is skipped with no log message, no counter increment, and no indication in the report. In CI, this means a file containing the only instance of a route can disappear silently. The tool reports "0 endpoints in code" for that file, and it looks like a configuration problem, not a parser error.

**Why it happens:** Defensive coding to avoid crashing on bad files, but the silent skip was chosen over a warning.

**Consequences:**
- Real endpoints become invisible with no actionable error
- The user has no way to know the file was skipped without adding debug logging manually
- CI passes with false confidence

**Warning signs:**
- Endpoint count suddenly drops between runs
- Source files with Windows line endings or unusual encoding (cp1252) silently vanish

**Prevention:**
- Accumulate skipped files in a `list[str]` and either print them to stderr or add them to `DriftReportMetadata` as `source_warnings`
- At minimum: `console.print_err(f"[yellow]Warning: skipped {filepath}: {e}[/yellow]")`
- Ideal: add `source_warnings: list[str]` to `DriftReportMetadata` (noted in CONCERNS.md as an opportunity)

**Phase:** Parser robustness phase — low effort, high CI value.

---

### Pitfall 5: `$ref` Parameters Silently Dropped

**Component:** `spec_loader.py` lines 117–131

**What goes wrong:**
```python
name = param.get("name", "")
```
If a parameter uses `$ref: '#/components/parameters/UserIdParam'` instead of an inline definition, `param.get("name")` returns `""` (because the dict only has `{"$ref": "..."}` as a key). The parameter is then added with name `""` or silently skipped depending on the `location` check. In practice, a spec with all shared parameters defined in `#/components/parameters` will produce zero detected parameters, causing every path param to appear as `PARAM_ADDED_IN_CODE` drift.

**Why it happens:** `_extract_parameters` does not call `_resolve_ref` before reading the name. This is consistent with CONCERNS.md's "No support for `$ref` parameters" item.

**Consequences:**
- Every path parameter appears as a false positive drift
- Specs that DRY up shared parameters (which is encouraged by the OAS spec) all fail

**Warning signs:**
- All `path_param.*` diffs appear as `PARAM_ADDED_IN_CODE` despite the param being in the spec
- Spec file has a `components.parameters` section

**Prevention:**
- Before reading `name` and `in`, call `_resolve_ref(param, components_schemas, set())` but extended to also cover `components.parameters`
- The `_resolve_ref` function currently only handles `#/components/schemas/` — extend it or add a parallel `_resolve_param_ref` for `#/components/parameters/`

**Phase:** Spec loader correctness phase — medium effort.

---

### Pitfall 6: External and Non-Schema `$ref` Silently Ignored

**Component:** `spec_loader.py` lines 232–238

**What goes wrong:**
```python
if not ref.startswith(prefix):  # prefix = "#/components/schemas/"
    return schema  # returns the unresolved {"$ref": "..."} dict
```
External refs (`"./schemas/user.yaml"`, `"https://..."`) and refs to other component types (`#/components/responses/NotFound`) return the raw `$ref` dict. When `_schema_to_fields` receives this, it finds no `"properties"` key and returns `None`. Every field that lives in an external schema appears absent, producing complete `FIELD_ADDED_IN_CODE` drift for that endpoint.

**Consequences:**
- Specs that split schemas across files (common in large API specs) produce 100% false positive drift
- Specs using `$ref` responses (also common) show all response fields as missing

**Warning signs:**
- All response or request body fields report as `FIELD_ADDED_IN_CODE`
- Spec file has `$ref` values not starting with `#/components/schemas/`

**Prevention (short-term):** When a non-local `$ref` is encountered, emit a warning and treat the schema as opaque (skip field comparison for that schema) rather than treating it as empty
**Prevention (full fix):** Resolve `#/components/responses/` refs; support multi-file specs by loading referenced files relative to the spec path

**Phase:** Spec loader correctness phase — the no-comparison-on-unresolvable behavior is the minimum bar.

---

## Moderate Pitfalls

---

### Pitfall 7: `nullable: true` (OAS 3.0) vs `anyOf null` (OAS 3.1) — Partially Fixed

**Component:** `spec_loader.py` `_unwrap_anyof_nullable`

**What goes wrong:** The fix in commit 28f11f6 handles `anyOf: [{type: X}, {type: null}]`. However the following OAS 3.1 patterns are not yet handled:

1. `anyOf: [$ref: SomeModel, {type: null}]` — the non-null branch is a `$ref`, not a type dict. `_unwrap_anyof_nullable` calls `_resolve_ref` on it, so this is actually handled.
2. `oneOf: [{type: X}, {type: Y}]` — two non-null variants. The function returns the original `prop`, which has no `type` key, so `_OPENAPI_TYPE_MAP.get(None, "object")` resolves to `"object"`. This is the `Union[A, B]` case.
3. OAS 3.0 `nullable: true` on a property (e.g., `{type: string, nullable: true}`) — the `nullable` key is ignored by the current loader, so the type is correctly resolved as `string`. No problem here. But if the Python code uses `Optional[str]` and the spec uses `{type: string, nullable: true}`, they should both produce `is_optional=True`. The comparator does not check optionality at the field level via the `nullable` key — it only checks `required`, which comes from the parent `required` array. So `nullable` is effectively ignored, which is correct behavior for the comparison but means nullability is not compared.
4. A `$ref` at the top level of a property that points to a schema with `anyOf` inside it — the outer `_unwrap_anyof_nullable` check returns early because `"$ref" in prop`, so the inner anyOf is never processed. This is resolved later when `_schema_to_fields` recurses.

**Warning signs:** Fields typed as `"object"` in the spec output when the spec has `oneOf` with multiple non-null variants.

**Prevention:** Document that `oneOf` with multiple non-null variants is treated as `"object"`. For correctness, pick the first non-null variant (matching what FastAPI code-gen does).

**Phase:** Spec loader — low priority after the main fix is already in place.

---

### Pitfall 8: `allOf` Schemas Not Merged

**Component:** `spec_loader.py` `_schema_to_fields`

**What goes wrong:** `allOf: [Base, Extension]` is a standard OAS composition pattern (used heavily by FastAPI for inherited Pydantic models). The loader does not handle `allOf`. When `_schema_to_fields` receives a schema with no `properties` key (because all properties are inside `allOf` sub-schemas), it returns `None`. The endpoint appears to have no response/request fields, so every field from the code side becomes `FIELD_ADDED_IN_CODE`.

FastAPI's auto-generated spec uses `allOf` when a route returns a Pydantic model that inherits from another Pydantic model.

**Warning signs:**
- All response fields are `FIELD_ADDED_IN_CODE` for endpoints with inherited Pydantic models
- Spec has `allOf` in its schema definitions

**Prevention:**
- In `_schema_to_fields`: if `schema.get("allOf")` is present, merge all sub-schema `properties` dicts (recursively resolved) before processing
- This is a medium-complexity but common-enough pattern to be worth fixing

**Phase:** Spec loader correctness phase.

---

### Pitfall 9: Decorated Wrappers Around Route Handlers Break Detection

**Component:** `fastapi_parser.py` `_check_decorators`

**What goes wrong:**
```python
@cache(ttl=60)
@router.get("/users")
async def list_users(): ...
```
The `_check_decorators` loop iterates all decorators in order. `@cache(ttl=60)` is encountered first. `_parse_route_decorator` checks if the outer function (`cache`) is an attribute call with an HTTP method name as the attribute — it is not, so it returns None. Then `@router.get("/users")` is processed correctly. This case is **actually fine**: the loop continues and finds the route decorator.

The real problem is:
```python
@router.get("/users")
@cache(ttl=60)  # second decorator
async def list_users(): ...
```
This is also fine — both are processed, cache returns None, router.get is found.

The genuinely problematic case:
```python
@router.get("/users", response_model=User)
@require_permissions("admin")  # decorator factory returns a new function
async def list_users(): ...
```
If `@require_permissions` wraps the function and the outermost decorator in the *call stack* at AST parse time is different, there is no issue — AST-level decorators are always the ones listed, regardless of runtime order.

The real edge case is decorators that take the path as their own first argument and then call the route:
```python
@versioned_route("/users", version=1)  # custom decorator that internally calls router.get
async def list_users(): ...
```
Here no `router.get` is visible in the decorator list and the endpoint is completely invisible.

**Warning signs:**
- Custom decorator factories that wrap `router.get/post/...` internally
- Zero endpoints detected in files that clearly define routes

**Prevention:** No static AST fix is possible for runtime-wrapping decorators. The correct approach is to document the limitation and emit a warning if a file has functions with non-route decorators that return zero routes when the file imports fastapi.

**Phase:** Parser — document as known limitation, low priority fix.

---

### Pitfall 10: Class-Based Views and `APIRouter` in Classes

**Component:** `fastapi_parser.py` `_RouteVisitor`

**What goes wrong:** `_RouteVisitor.visit_FunctionDef` calls `generic_visit`, which recurses into nested class definitions. However, if route decorators inside a class use `self.router.get(...)`, the object name resolves to `self.router` — a dotted path — and `any(r in "self.router".lower() for r in {"app", "router"})` is True only because `"router"` is a substring of `"self.router"`. This actually works by accident.

However, `fastapi-utils` CBV pattern (`@cbv(router)` decorator on a class) does not use the method decorator approach at all — the decorator is on the class, not individual methods. All CBV-style endpoints are invisible.

**Warning signs:**
- Project uses `fastapi-utils` or `fastapi-class-views`
- Zero endpoints from files that contain class definitions with route logic

**Prevention:** Out of scope for static AST analysis without importing fastapi-utils. Document as not supported.

**Phase:** Documentation — not worth implementing in correctness phases.

---

### Pitfall 11: `Union[A, B]` (Non-Nullable) Collapses to Left Branch Without Warning

**Component:** `fastapi_parser.py` `_resolve_annotation` lines 115–116

**What goes wrong:**
```python
return left, False  # Union[str, int] → "str"
```
A field typed `Union[str, int]` silently becomes `"string"`. The spec may have `type: integer` for a field that was originally `int` but was later widened to `Union[str, int]`, producing a false negative (the drift is real but `left` happens to match the original type). Or in the opposite direction, it produces a false positive when `left` does not match.

This is documented in CONCERNS.md.

**Warning signs:**
- `Union[X, Y]` annotations in Pydantic models where neither `X` nor `Y` is `None`

**Prevention:**
- Emit a warning when this fallback is hit: `"Union[{left}, {right}] — using left branch only; inner type may be inaccurate"`
- For comparison purposes, treat the field type as `"object"` (unknown/complex) and skip type comparison rather than comparing the wrong type

**Phase:** Parser — low effort to add warning; moderate effort to change comparison behavior.

---

### Pitfall 12: `Depends(...)` Type Annotations Resolved as Parameters

**Component:** `fastapi_parser.py` `_parse_function_params` lines 252–254

**What goes wrong:** The skip list `{"Depends", "Security", "BackgroundTasks", "Request", "Response"}` catches the common cases. But:

1. `Depends` is often imported as an alias: `from fastapi import Depends as Di` — `Di` is not in the skip list and will be treated as a parameter name
2. Arguments annotated with a dependency class (not `Depends` itself) won't be skipped: `async def get_user(current_user: CurrentUser)` — `CurrentUser` is not in the models dict (it comes from a DI function return type), so it falls through to `json_type = _PYTHON_TYPE_TO_JSON.get(type_name, "string")` = `"string"` and becomes a false-positive query parameter named `current_user`

**Warning signs:**
- Spurious query parameters with names like `current_user`, `db`, `session`, `auth`, `settings` appearing as `PARAM_ADDED_IN_CODE`

**Prevention:**
- Extend the skip name list to also include common DI parameter names (`"db"`, `"session"`, `"current_user"` are already skipped via their variable names, but only `db` and `session` are in the hardcoded skip list)
- Actually, looking at the code again: `if name in ("self", "cls", "request", "response", "db", "session")` — this is a name-based skip, not type-based. Parameters named `current_user`, `auth_user`, `settings`, `background_tasks` are not skipped by name
- Better approach: when a type is not in `self.models` and not in `_PYTHON_TYPE_TO_JSON`, check if it could be a DI-injected class by looking for it in imported names or Pydantic model names. If unknown, skip it rather than defaulting to `"string"`

**Phase:** Parser correctness — medium priority, common false positive source.

---

## Minor Pitfalls

---

### Pitfall 13: File System Ordering Is Non-Deterministic

**Component:** `cli.py` `_collect_source_files`, `fastapi_parser.py` `extract_endpoints`

**What goes wrong:** `source_dir.rglob("*.py")` returns files in filesystem-dependent order (inode order on Linux ext4, alphabetical on some macOS configurations, random on NFS). When two files define the same Pydantic model name (e.g., both have `class UserResponse(BaseModel)`), the last file processed wins in `model_collector.models`. Which file wins depends on filesystem ordering, so results can differ between runs on different systems.

**Warning signs:**
- Intermittent drift results in CI (passes on developer machine, fails in CI, or vice versa)
- Two files with identical model names

**Prevention:**
- Sort `source_files` before processing: `sorted(source_dir.rglob("*.py"))` in `_collect_source_files`
- This is a one-line fix that costs nothing

**Phase:** Trivial fix — do it in any phase that touches the CLI or parser.

---

### Pitfall 14: Zero Endpoints Looks Like Success, Not an Error

**Component:** `cli.py` check command, output formatters

**What goes wrong:** When DocGuard detects 0 code endpoints (due to wrong router names, wrong source path, all files skipped), the drift report shows:
- `total_endpoints_in_code: 0`
- `total_endpoints_in_spec: N` (all as `MISSING_IN_CODE`)
- `drift_score: 0.25` (half-weight for missing_in_code)

If `fail_on = "any"`, the tool exits 1. If `fail_on = "drift-only"` (the default in most configs), no endpoints are drifted — only missing in code — so the tool exits 0. This looks like "no drift detected."

**Warning signs:**
- `total_endpoints_in_code: 0` in the JSON output
- All endpoints are `MISSING_IN_CODE`

**Prevention:**
- Add an explicit check: if `code_endpoints == []` and `source_files` was non-empty, print a prominent warning to stderr: "DocGuard found 0 endpoints in source code. Check that your router variable names match the configured `router_names`."
- Consider treating `total_endpoints_in_code == 0` as an error exit (exit code 2) when source files were found but no endpoints were detected

**Phase:** UX / error surfacing phase — easy, high value.

---

### Pitfall 15: `required` Mismatch Between `Optional` and OpenAPI `required` Array

**Component:** `fastapi_parser.py` `_PydanticModelCollector._extract_fields`, `spec_loader.py` `_schema_to_fields`

**What goes wrong:** In FastAPI/Pydantic, `Optional[str]` means the field may be omitted from the request body (not required). In OpenAPI, the `required` array at the schema level determines whether a field must be present. The two representations are:

- Python: `field: Optional[str] = None` → `is_optional=True`, `required=False`
- OAS: field absent from `required` array → `required=False`

These are aligned. However:

- Python: `field: str = "default"` → `is_optional=False`, `required=False` (has a default)
- OAS: field absent from `required` array → `required=False`

This is also aligned. The problematic case:

- Python: `field: str` (no default) → `required=True`
- OAS: field in `required` array → `required=True`

But the spec may be written with Pydantic v1 behavior in mind: Pydantic v1 allowed `Optional[str]` to mean "can be None" while still being required. In that case the Python side has `required=True, is_optional=True` but the spec has the field absent from `required`. This produces a `REQUIRED_MISMATCH` false positive.

**Warning signs:**
- `REQUIRED_MISMATCH` diffs for fields that are `Optional[str]` in code

**Prevention:**
- When `is_optional=True`, always set `required=False` (the current code already does this correctly)
- The issue only arises when mixing Pydantic v1 and v2 semantics, which is outside DocGuard's control

**Phase:** Low priority — mostly a documentation note.

---

### Pitfall 16: `InferredField.default` Always Coerced to `str`

**Component:** `fastapi_parser.py` lines 62, 327–329

**What goes wrong:** `_const_to_str` converts `0` to `"0"`, `False` to `"False"`, `None` to `"None"`. This means `default=0` and `default=""` are both stored as strings. If a future comparison ever uses defaults (e.g., to detect "default changed from 0 to null"), it will be comparing string representations instead of typed values.

Currently, defaults are not compared at all, so this is latent.

**Prevention:** Change `default` to `Any` and store the raw Python value. Low priority until default comparison is implemented.

---

### Pitfall 17: `_compare_params` Does Not Check Parameter Location

**Component:** `comparator.py` `_compare_params`

**What goes wrong:** The comparator has two separate calls for path params and query params. This is correct at the structural level. However, the spec loader's `_extract_parameters` classifies parameters by the `in` field (`path` vs `query`). If a spec incorrectly has a parameter marked `in: query` that the code treats as a path parameter (because it appears in `{}` in the path string), the name-match will fail across buckets: the spec's query param bucket has `user_id`, the code's path param bucket has `user_id`. Result: `PARAM_ADDED_IN_CODE` for the path param and `PARAM_REMOVED_IN_CODE` for the query param — both false positives representing one actual spec location error.

This is a spec authoring error, not a DocGuard bug, but the error message is confusing ("added in code" / "removed in code" instead of "wrong location in spec").

**Warning signs:**
- Paired `PARAM_ADDED_IN_CODE` and `PARAM_REMOVED_IN_CODE` for the same parameter name

**Prevention:**
- After all comparisons, scan for matching names across path/query buckets and emit a more specific `PARAM_LOCATION_MISMATCH` diff type
- Low priority.

---

### Pitfall 18: `_resolve_ref` Visits Are Per-Call, Not Global

**Component:** `spec_loader.py` `_resolve_ref`

**What goes wrong:** The `_visited` set is created fresh for each top-level `_schema_to_fields` call (once per property resolution). This means if schema A and schema B both reference schema C, schema C will be resolved twice. If the schema graph has cross-references (A references B, B references A), a fresh `_visited` per call would still catch the cycle. But the visited set is threaded through the recursive call chain, not across sibling calls. This is safe; no bug here.

However: when `_schema_to_fields` is called for a property that is a nested object, a new `_visited` is NOT created — the existing one is threaded through. This is also correct. No bug here, but the code is subtle enough to invite future bugs.

**Prevention:** Add a comment explaining that `_visited` is passed through to prevent infinite recursion on circular schemas. The current comment is absent.

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|---|---|---|
| `include_router` prefix support | Pitfall 2 — prefix concatenation missing | Two-pass approach: collect include_router calls first, then apply prefixes |
| Expand router name detection | Pitfall 1 — hardcoded `_ROUTER_NAMES` | Config option + include_router discovery |
| `$ref` parameter resolution | Pitfall 5 — silent drop | Extend `_resolve_ref` to cover `#/components/parameters/` |
| `allOf` schema merging | Pitfall 8 — empty fields for inherited models | Merge allOf sub-schema properties before extracting fields |
| Source file collection | Pitfall 13 — non-deterministic ordering | Sort files before processing |
| Zero endpoints UX | Pitfall 14 — looks like success | Check for 0 endpoints and warn loudly |
| DI parameter skip | Pitfall 12 — DI classes become false parameters | Skip unknown types not in models dict |
| Parse error surfacing | Pitfall 4 — silent swallow | Accumulate warnings, surface in report |
| `Union[A, B]` collapse | Pitfall 11 — wrong type silently | Warn + treat as "object" for comparison |
| External `$ref` | Pitfall 6 — fields appear absent | Warn and skip comparison rather than comparing against empty |

---

## What Was Already Fixed (commit 28f11f6)

These pitfalls are **resolved** and documented here for completeness:

| Fixed Pitfall | Fix Applied |
|---|---|
| Return-type annotation (`-> Model`) not used as response model | Added `_extract_return_annotation_fields` fallback |
| `list[X]` fields typed as `"object"` instead of `"array"` | Pass-through of JSON type strings in `_PYTHON_TYPE_TO_JSON` lookup |
| `Field(default_factory=...)` not recognized as non-required | Added `default_factory` keyword handling in `_parse_field_call` |
| OAS 3.1 `anyOf: [{type: X}, {type: null}]` nullable fields typed as `"object"` | Added `_unwrap_anyof_nullable` in spec_loader |

---

## Sources

- Direct code analysis: `/Users/shishirraj/DocGuard/src/docguard/parsers/fastapi_parser.py`
- Direct code analysis: `/Users/shishirraj/DocGuard/src/docguard/core/comparator.py`
- Direct code analysis: `/Users/shishirraj/DocGuard/src/docguard/core/spec_loader.py`
- Direct code analysis: `/Users/shishirraj/DocGuard/src/docguard/cli.py`
- Existing audit: `/Users/shishirraj/DocGuard/.planning/codebase/CONCERNS.md`
- Prior fix history: `git show 28f11f6` — false positive elimination commit
- Test coverage gap analysis: `tests/test_fastapi_parser.py`, `tests/test_comparator.py`
- FastAPI router patterns: HIGH confidence from code analysis; no external lookup required for structural patterns
- OpenAPI 3.1 `anyOf` nullable behavior: HIGH confidence (already fixed once in codebase)
- OpenAPI `$ref` parameter behavior: HIGH confidence (OAS 3.x spec is unambiguous)
