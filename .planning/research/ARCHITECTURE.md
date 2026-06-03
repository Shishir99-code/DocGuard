# Architecture Patterns — DocGuard Correctness Fixes

**Domain:** Python CLI / static API analysis tool
**Researched:** 2026-06-02
**Confidence:** HIGH — all findings derived from direct source code reading

---

## Fix 1: Router Name Resolution (`fastapi_parser.py:30`)

### Problem

`_ROUTER_NAMES = {"app", "router"}` is a module-level frozenset. `_parse_route_decorator` at line 204 checks `any(r in obj_name.lower() for r in _ROUTER_NAMES)`. Any `APIRouter()` assigned to a name outside this set (e.g. `api`, `v1`, `users_router`, `prefix_router`) is silently ignored — its decorated endpoints are never collected.

### Approaches

**Option A — First-pass assignment scan (recommended)**

Add a third pre-pass (`_RouterNameCollector`) that walks `ast.Assign` and `ast.AnnAssign` nodes and adds the left-hand-side name to a set whenever the right-hand-side is a `Call` whose function name resolves to `APIRouter` or `FastAPI`. Pass the resulting set into `_RouteVisitor` to augment `_ROUTER_NAMES`.

```python
class _RouterNameCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.names: set[str] = set(_ROUTER_NAMES)  # start with defaults

    def visit_Assign(self, node: ast.Assign) -> None:
        if self._is_router_call(node.value):
            for target in node.targets:
                name = _resolve_name(target)
                if name:
                    self.names.add(name.lower())
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value and self._is_router_call(node.value):
            name = _resolve_name(node.target)
            if name:
                self.names.add(name.lower())
        self.generic_visit(node)

    @staticmethod
    def _is_router_call(node: ast.expr | None) -> bool:
        if not isinstance(node, ast.Call):
            return False
        name = _resolve_name(node.func)
        return bool(name and name.split(".")[-1] in ("APIRouter", "FastAPI"))
```

`_RouteVisitor.__init__` accepts `router_names: set[str]` and stores it. `_parse_route_decorator` uses `self.router_names` instead of the global `_ROUTER_NAMES`. `FastAPIParser.extract_endpoints` runs `_RouterNameCollector` over all trees first (it can share the same first-pass loop as `_PydanticModelCollector`), then passes the collected names into each `_RouteVisitor`.

**Option B — Dataflow / assignment tracking**

Track which names are aliased from router variables (`v2 = router`) and follow those chains. More correct for reassigned routers but significantly more complex — needs use-def tracking across function scope boundaries.

**Option C — Skip the object-name check entirely**

Remove the `obj_name` guard and match any `@<anything>.<http_method>(...)` pattern. Fastest to implement but produces false positives on non-FastAPI decorators that happen to use HTTP method names as attributes.

### Recommendation

**Option A** handles 95%+ of real apps. Direct `= APIRouter()` and `= FastAPI()` assignments at module scope are the overwhelmingly common pattern. Aliased routers (B) and nameless decorators (C) are rare edge cases that can be deferred.

### Model Impact

None. The `router_names` set is an internal detail of `_RouteVisitor`. No changes to `models.py`, `InferredEndpoint`, or any downstream layer.

### Files Touched

- `src/docguard/parsers/fastapi_parser.py` only
  - Add `_RouterNameCollector` class (~20 lines)
  - Change `_RouteVisitor.__init__` to accept `router_names: set[str]`
  - Change `_parse_route_decorator` to use `self.router_names` instead of global `_ROUTER_NAMES`
  - Change `FastAPIParser.extract_endpoints` to run the collector and pass names to each visitor

---

## Fix 2: `$ref` Parameters in `_extract_parameters` (`spec_loader.py:117-131`)

### Problem

`_extract_parameters` iterates `all_params` and calls `param.get("name", "")`. A `$ref` parameter object looks like `{"$ref": "#/components/parameters/MyParam"}` — it has no `"name"` key. The name evaluates to `""`, the `InferredField` is created with `name=""`, and it is silently added to the list (rather than dropped). At compare time it creates spurious diffs because the spec side has a field named `""` and the code side has a real named field.

### Approaches

**Option A — Inline resolution at iteration time (recommended)**

Before reading `name` and `location`, call `_resolve_ref` on each param dict. The existing `_resolve_ref` handles `#/components/schemas/` refs; parameters live at `#/components/parameters/`. Two options within A:

- A1: Thread `components_parameters` into `_extract_parameters` and resolve there (cleanest, two-line change at call site).
- A2: Generalise `_resolve_ref` to resolve any `#/components/<section>/` ref. Then call it with the full `spec.get("components", {})` dict.

A1 is more surgical. `normalize_spec` already passes `components_schemas` as a separate argument to other helpers — the same pattern can be followed for `components_parameters`.

```python
def _extract_parameters(
    op_params: list[dict],
    path_params_shared: list[dict],
    components: dict,  # full spec["components"]
) -> tuple[list[InferredField], list[InferredField]]:
    components_params = components.get("parameters", {})
    components_schemas = components.get("schemas", {})
    visited: set[str] = set()
    all_params = list(path_params_shared) + list(op_params)
    ...
    for param in all_params:
        # Resolve $ref to #/components/parameters/Foo
        param = _resolve_component_ref(param, components_params, visited)
        if not param or not param.get("name"):
            continue
        ...
```

Add a small `_resolve_component_ref` that mirrors `_resolve_ref` but operates on the parameters map (same pattern, ~8 lines).

**Option B — Pre-resolve all `$ref`s before normalization**

Walk the entire spec dict recursively before calling `normalize_spec` and inline every `$ref` in place. This is how many OpenAPI toolkits work (`openapi-spec-validator` does this). It is more robust but turns a surgical fix into a foundational change, and it requires handling circular refs carefully. Overkill for the current codebase.

### Recommendation

**Option A1.** Thread `components` through to `_extract_parameters`. The change is 3–4 lines in `normalize_spec` (pass `spec.get("components", {})` instead of nothing) and ~15 lines inside `_extract_parameters`. The existing `_resolve_ref` pattern proves this works; this is the same pattern applied to parameters.

### Model Impact

None. `InferredField` does not change. The fix prevents the creation of a corrupt `InferredField(name="")` — it never reaches models.

### Files Touched

- `src/docguard/core/spec_loader.py` only
  - `_extract_parameters` signature gains a `components: dict` parameter
  - Add `_resolve_component_ref` helper (mirrors `_resolve_ref`)
  - `normalize_spec` passes `spec.get("components", {})` at the call site

---

## Fix 3: `_resolve_ref` for Non-`#/components/schemas/` Refs (`spec_loader.py:232-238`)

### Problem

`_resolve_ref` returns the original schema dict unchanged when the ref does not start with `#/components/schemas/`. This means `#/components/parameters/Foo`, `#/components/requestBodies/Bar`, and all external refs (`./other.yaml#/...`) are silently passed through as-is. For non-schemas refs the dict still has `$ref` in it, so `_schema_to_fields` eventually sees `"$ref" in resolved_prop` and recurses into `_resolve_ref` again — infinite loop broken by the `_visited` set returning `{}`, producing empty fields.

This is directly related to Fix 2 (parameters refs) but also affects inline `$ref`s inside request body / response schemas that point to locations other than `#/components/schemas/`.

### Approach

Extend `_resolve_ref` to accept the full `components` dict and resolve any `#/components/<section>/<name>` ref, not just schemas.

```python
_COMPONENTS_REF_PREFIX = "#/components/"

def _resolve_ref(schema: dict, components: dict, visited: set[str]) -> dict:
    ref = schema.get("$ref")
    if not ref:
        return schema
    if not ref.startswith(_COMPONENTS_REF_PREFIX):
        return {}  # external refs: return empty, do not silently pass through

    rest = ref[len(_COMPONENTS_REF_PREFIX):]
    parts = rest.split("/", 1)
    if len(parts) != 2:
        return {}
    section, name = parts
    if name in visited:
        return {}
    visited.add(name)
    return components.get(section, {}).get(name, {})
```

This is a compatible signature change. All call sites in `spec_loader.py` that currently pass `components_schemas` are updated to pass the full `components` dict instead. The `_schema_to_fields` function already passes `components_schemas` everywhere; swapping to `components` is mechanical.

### Recommendation

Fix this alongside Fix 2 — the two are coupled. Change `_resolve_ref` to the generalised form in the same PR. The total diff is mechanical: find-replace `components_schemas` → `components` in `spec_loader.py` + update `_resolve_ref` body. External refs deliberately return `{}` (same as the current unknown-ref behavior) rather than trying to fetch remote files.

### Model Impact

None.

### Files Touched

- `src/docguard/core/spec_loader.py` only (same file as Fix 2)
  - `_resolve_ref` generalised
  - All `components_schemas` locals in `normalize_spec`, `_schema_to_fields`, `_extract_request_body`, `_extract_response_fields`, `_unwrap_anyof_nullable` updated to use full `components` dict

---

## Fix 4: `Union[A, B]` Collapse in `_resolve_annotation` (`fastapi_parser.py:115-116`)

### Problem

At line 115–116, when the PEP 604 `A | B` form has two non-None branches (e.g. `int | str`), the code silently returns the left branch (`left, False`). This is the `_PydanticModelCollector._resolve_annotation` method. The exact same pattern exists in `_annotation_to_fields` in `_RouteVisitor`, which handles return type annotations.

The consequence: a field annotated `str | int` reports as `"string"` where the spec may say `"integer"`, or vice versa, generating spurious TYPE_MISMATCH diffs.

### Approaches

**Option A — Emit the left branch as-is (status quo, intentional fallback)**

The comment at line 25 already notes `"Optional": "string"` is a "fallback; inner type resolved separately." For `Union[A, B]` where neither is None, there is no single OpenAPI type — OpenAPI would use `anyOf`. Silently returning the left type is a reasonable heuristic and will not regress existing correct behavior.

**Option B — Return "object" as the fallback type for ambiguous unions (recommended)**

When neither branch is None and the two resolved types differ, return `"object"` (the OpenAPI catch-all). This avoids false TYPE_MISMATCH errors because the spec side for a union type is likely inferred as `"object"` too (via `_OPENAPI_TYPE_MAP` fallback).

```python
# X | Y where neither is None
left_type, _ = self._resolve_annotation(node.left)
right_type, _ = self._resolve_annotation(node.right)
if left_type == right_type:
    return left_type, False
return "object", False  # ambiguous union
```

**Option C — Introduce a sentinel "union" type and compare leniently in the comparator**

Add `"union"` to `InferredField.type` and teach `_compare_fields` to skip TYPE_MISMATCH when either side is `"union"`. This is the most correct approach but it touches the data model and comparator.

**Option D — Skip type comparison entirely for body fields that come from Pydantic models**

Add an `inferred: bool` flag to `InferredField` so the comparator knows when a type was inferred vs explicitly declared. This is a larger data model change.

### Recommendation

**Option B** for now — it is a 3-line change isolated to `_resolve_annotation`, removes false positives without adding false negatives, and requires no model changes. Option C is worth revisiting when the team wants to model union types in the output format.

Note: the same `return left, False` fallback also fires for `Annotated[X, ...]` and other subscript forms that don't match `Optional`/`List`/`Dict`. Option B should be applied to the general subscript fallback on line 105–106 as well, not just the BinOp branch.

### Model Impact

None for Option B. Option C would add a field to `InferredField` in `models.py` and logic to `comparator.py`.

### Files Touched (Option B)

- `src/docguard/parsers/fastapi_parser.py` only
  - `_PydanticModelCollector._resolve_annotation` lines 109–116: return `"object"` for ambiguous unions
  - Optionally the same treatment for the `ast.Subscript` fallback at line 105–106

---

## Fix 5: `severity_threshold` Not Wired in `cli.py`

### Problem

`CheckConfig.severity_threshold` is defined in `config.py:13` and documented in the default `.docguard.yaml`, but `cli.py` never reads it. The `check` command's output loop and exit-code logic at lines 180–195 use `cfg.check.fail_on` but not `cfg.check.severity_threshold`. All diffs with any severity are shown and all `Severity.ERROR` diffs trigger exit code 1, regardless of what the user configured.

### Where Filtering Should Happen

The pipeline has three candidate sites:

| Site | Filter semantics |
|------|-----------------|
| **Comparator** | Never emit diffs below threshold — they disappear from the `DriftReport` entirely |
| **Formatter** | Emit all diffs, but mark sub-threshold ones differently (dimmed, omitted from count) |
| **CLI** | Filter the already-built `DriftReport` before choosing exit code and before passing to formatter |

**Comparator filtering** is wrong for a tool whose primary output is a `DriftReport` consumed by CI, dashboards, and the LLM fixer. Permanently dropping diffs based on a display preference corrupts the data contract. The `DriftReport` is meant to be the complete picture.

**Formatter filtering** is half-right for display but does nothing for exit codes. The formatter and exit-code logic would need to agree on a shared threshold, leading to coupling.

**CLI filtering (recommended):** After `compare()` returns the full `DriftReport`, apply the threshold as a view filter in the CLI layer before both display and exit-code evaluation. This keeps `DriftReport` complete and keeps the filtering concern at the composition root where all config is already resolved.

### Implementation

The CLI already does a similar filter-then-act pattern for `fail_on`. The natural extension:

```python
# In cli.py check(), after report = compare(...)

threshold_order = {"info": 0, "warning": 1, "error": 2}
threshold_level = threshold_order.get(cfg.check.severity_threshold, 2)

def _passes_threshold(d: FieldDiff) -> bool:
    return threshold_order.get(d.severity.value, 0) >= threshold_level

# Filter diffs on each EndpointResult for display/exit purposes
# Do NOT mutate the report — create a filtered view
filtered_endpoints = [
    EndpointResult(
        path=ep.path, method=ep.method, status=ep.status,
        source_location=ep.source_location, spec_location=ep.spec_location,
        diffs=[d for d in ep.diffs if _passes_threshold(d)],
    )
    for ep in report.endpoints
]
```

Pass `filtered_endpoints` to the formatter and use it for exit code evaluation. The original `report` (unfiltered) is still available for `report_path` JSON output if needed.

Alternatively, if full-report JSON output should also respect the threshold (likely the right UX), mutate the report in place: `ep.diffs[:] = [d for d in ep.diffs if _passes_threshold(d)]`. This is simpler and is defensible since the report is a local ephemeral object.

### Model Impact

None. `Severity` enum and `FieldDiff.severity` already exist and have the right values.

### Files Touched

- `src/docguard/cli.py` only
  - ~15 lines added after `report = compare(...)` in the `check` command
  - No changes to `comparator.py`, `models.py`, or any formatter

---

## Cross-Cutting Summary

### Which Changes Touch `models.py`

None of the five fixes require changes to `models.py` under the recommended options. The data model is already correct — `InferredField.type` is a `str`, `FieldDiff.severity` is a `Severity` enum, and `InferredEndpoint` carries all needed fields. The bugs are all in the production of data (parsers, spec loader) and the consumption of config (CLI), not in the shared representation.

### Coupling and Isolation

| Fix | Files | Cross-layer? |
|-----|-------|-------------|
| 1 — Router name detection | `fastapi_parser.py` only | No |
| 2 — `$ref` parameter resolution | `spec_loader.py` only | No |
| 3 — Generalise `_resolve_ref` | `spec_loader.py` only (same file as Fix 2) | No |
| 4 — `Union` type collapse | `fastapi_parser.py` only | No |
| 5 — Wire `severity_threshold` | `cli.py` only | No |

All five fixes are single-file changes. Fix 2 and Fix 3 are in the same file and should be done together as one coherent spec-loading fix (they share the `_resolve_ref` / `components` threading change).

### Recommended Commit Order

1. Fix 2 + Fix 3 together (spec_loader.py) — they share the `components` parameter threading
2. Fix 1 (fastapi_parser.py) — router name collector
3. Fix 4 (fastapi_parser.py) — union type fallback (same file, separate commit for clarity)
4. Fix 5 (cli.py) — severity_threshold wiring

### Minimal Viable Scope

If prioritising by user-visible correctness impact:

- **Highest impact:** Fix 1 (silently drops entire endpoints), Fix 2 (corrupts param names)
- **Medium impact:** Fix 3 (empty fields on non-schema refs), Fix 5 (config setting does nothing)
- **Lower impact:** Fix 4 (spurious type mismatch, not a silent drop)

---

_Confidence: HIGH — all analysis derived from direct reading of the five source files. No external dependencies or ecosystem research required._
