# Technology Stack — Correctness Fixes
_Researched: 2026-06-02_
_Scope: DocGuard correctness milestone (router detection, $ref resolution, type normalization, determinism)_

---

## Finding 1: $ref Resolution — No New Dependencies Required

### Available transitive dependencies

`openapi-spec-validator>=0.7` is already a hard dependency in `pyproject.toml`. It pulls in:

| Package | Version (installed) | What it gives us |
|---------|---------------------|------------------|
| `jsonschema` | 4.24.1 | JSON Schema validation, `RefResolver` (deprecated), `referencing` |
| `jsonschema-path` | 0.4.5 | `SchemaPath` — transparent $ref traversal across all OAS component types |
| `referencing` | 0.37.0 | `referencing.exceptions.Unresolvable` — catchable exception for unresolvable refs |

These are already installed in every DocGuard environment. They do not need to be added to `pyproject.toml`. Do NOT add `jsonref` or `prance` — they are unnecessary and would add weight.

### What `jsonschema.RefResolver` provides vs why NOT to use it

`RefResolver.from_schema(spec)` + `resolver.resolving(ref)` context manager resolves any `$ref` string to the pointed-at dict. It works correctly for `#/components/parameters/`, `#/components/schemas/`, and `#/components/responses/`. However, `RefResolver` is deprecated since `jsonschema` 4.18.0. Using it would introduce a `DeprecationWarning` on every import. Do not use it.

### What `jsonschema-path.SchemaPath` provides — recommended for future use, not for the immediate fix

`SchemaPath.from_dict(spec)` wraps the raw spec dict and resolves `$ref` entries transparently during traversal. Accessing `(sp / 'paths' / '/users/{id}' / 'get' / 'parameters')[0]` returns the fully-resolved parameter dict even when the original spec contains `{"$ref": "#/components/parameters/Id"}`. This was confirmed to work for `components/parameters`, `components/requestBodies`, `components/responses`, and `components/schemas` — all OAS 3.x component categories.

External file refs (e.g. `./schemas/user.yaml`) raise `referencing.exceptions.Unresolvable` when accessed. That exception is catchable and provides the warning surface.

However, migrating `spec_loader.normalize_spec` to use `SchemaPath` throughout is a larger refactor that touches every field access. The correctness milestone does not require it. The minimal fix below achieves the same result with zero new imports.

### Recommended minimal fix for `_extract_parameters` in `spec_loader.py`

Add a `_resolve_component_ref(obj, components, visited)` helper that generalizes the existing `_resolve_ref` pattern to cover any `#/components/X/name` path, not just `#/components/schemas/`:

```python
def _resolve_component_ref(
    obj: dict,
    components: dict,
    visited: set[str],
) -> tuple[dict, str | None]:
    """Follow a $ref within #/components/X/name. Returns (resolved, warning_or_None)."""
    ref = obj.get("$ref")
    if not ref:
        return obj, None
    if not ref.startswith("#/"):
        return {}, f"External $ref not supported (skipped): {ref}"
    parts = ref.lstrip("#/").split("/")
    if len(parts) < 3 or parts[0] != "components":
        return {}, f"Unrecognized $ref format: {ref}"
    category, name = parts[1], parts[2]
    if name in visited:
        return {}, f"Circular $ref detected: {ref}"
    visited.add(name)
    resolved = components.get(category, {}).get(name)
    if resolved is None:
        return {}, f"Unresolvable $ref: {ref}"
    return resolved, None
```

Call it at the top of the `for param in all_params` loop in `_extract_parameters`, passing `spec.get("components", {})`. Collect warnings and return them alongside the field lists so `normalize_spec` can surface them to the caller. This function handles `#/components/parameters/`, `#/components/requestBodies/`, and `#/components/schemas/` uniformly — it replaces the existing `_resolve_ref` as well.

The same helper resolves the `_resolve_ref`-only-handles-schemas limitation. Replace `_resolve_ref` with `_resolve_component_ref` in `_schema_to_fields` (pass `spec.get("components", {})` as the `components` dict instead of the narrower `components_schemas` dict). This enables response bodies referenced via `#/components/schemas/` to work as before, while also allowing `#/components/responses/` refs in the response block.

**No new imports are needed in `spec_loader.py`.** The function is pure Python dict traversal.

---

## Finding 2: FastAPI AST Router Name Detection

### The problem

`_parse_route_decorator` in `fastapi_parser.py` line 204 does:

```python
if obj_name and not any(r in obj_name.lower() for r in _ROUTER_NAMES):
    return None
```

`_ROUTER_NAMES = {"app", "router"}` (line 30). Any variable named `api`, `v1`, `prefix_router`, or anything else is rejected. No warning is emitted.

### The fix: a pre-pass AST collector

Add a `_RouterNameCollector(ast.NodeVisitor)` class that runs before `_RouteVisitor`. It inspects `ast.Assign` and `ast.AnnAssign` nodes for RHS calls to `FastAPI()`, `APIRouter()`, and `Router()`. It collects the LHS variable names into a set.

```python
_ROUTER_CONSTRUCTORS = {"FastAPI", "APIRouter", "Router"}

class _RouterNameCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.router_names: set[str] = set()

    def visit_Assign(self, node: ast.Assign) -> None:
        if isinstance(node.value, ast.Call):
            func_name = _resolve_name(node.value.func)
            # _resolve_name returns the last attribute component for dotted names
            # e.g. fastapi.APIRouter() -> "fastapi.APIRouter" -- take the final part
            if func_name and func_name.split(".")[-1] in _ROUTER_CONSTRUCTORS:
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        self.router_names.add(target.id)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if isinstance(node.value, ast.Call):
            func_name = _resolve_name(node.value.func)
            if func_name and func_name.split(".")[-1] in _ROUTER_CONSTRUCTORS:
                if isinstance(node.target, ast.Name):
                    self.router_names.add(node.target.id)
        self.generic_visit(node)
```

**Integration into `FastAPIParser.extract_endpoints`:** Run this collector in pass 1 (alongside `_PydanticModelCollector`) to build a `detected_router_names` set across all files. Merge it with the configurable baseline (see below). Pass the merged set into `_RouteVisitor.__init__` so it replaces `_ROUTER_NAMES`.

**Configurable baseline via `.docguard.yaml`:** Expose `router_names: list[str]` in `CheckConfig` (defaulting to `["app", "router"]`). The effective set = `set(cfg.check.router_names) | detected_router_names`. This lets users declare names that don't follow the constructor-assignment pattern (e.g. routers imported from other modules).

**The `_parse_route_decorator` check** (line 204) becomes:

```python
# self._router_names is the merged set passed in at construction
if obj_name and obj_name not in self._router_names:
    # Use exact match instead of substring match to avoid "router_v1" matching "router"
    return None
```

Note: the current `any(r in obj_name.lower() for r in _ROUTER_NAMES)` is a substring check — `"prefix_router"` would match `"router"`, which is correct behaviour but coincidental. An exact-match check against the full set of detected names is more precise. However, for backwards compatibility, keep the fallback `{"app", "router"}` in the baseline so simple apps keep working without configuration.

**Cross-file router names:** `_RouterNameCollector` must run over all files in pass 1 (not just the current file) so that routers defined in one file and decorated in another are correctly linked. The `FastAPIParser.extract_endpoints` two-pass loop already visits all files in pass 1 — add the router collector there.

---

## Finding 3: Type Annotation Normalization

### Current state

`_PydanticModelCollector._resolve_annotation` handles:
- `ast.Name` — plain name → returns `(node.id, False)`
- `ast.Subscript` with outer `Optional` → `(inner, True)`
- `ast.Subscript` with outer `List`/`list` → `("array", False)`
- `ast.Subscript` with outer `Dict`/`dict` → `("object", False)`
- `ast.Subscript` with any other outer → `_resolve_annotation(node.slice)` — this is wrong for `Union`
- `ast.BinOp(BitOr)` with right `None` → `(left, True)`
- `ast.BinOp(BitOr)` with left `None` → `(right, True)`
- `ast.BinOp(BitOr)` — neither side is None → `(left, False)` silently drops the right type

### Missing cases and fixes

**`Union[A, B]` (non-nullable):** The AST is `Subscript(Union, Tuple([A, B]))`. The current `Subscript(other)` branch calls `_resolve_annotation(Tuple([A, B]))` which falls through to `("object", False)` — always wrong. Fix:

```python
if outer == "Union":
    # Subscript slice is a Tuple of types
    if isinstance(node.slice, ast.Tuple):
        elts = node.slice.elts
        non_none = [e for e in elts if not (isinstance(e, ast.Constant) and e.value is None)]
        if len(non_none) == len(elts):
            # No None variant — true Union. Return first type (JSON Schema has no union type).
            inner, _ = self._resolve_annotation(non_none[0])
            return inner, False
        else:
            # Has None variant — it's Optional
            non_none_types = [e for e in elts if not (isinstance(e, ast.Constant) and e.value is None)]
            inner, _ = self._resolve_annotation(non_none_types[0])
            return inner, True
    # Single-arg Union[X] — degenerate but valid
    inner, _ = self._resolve_annotation(node.slice)
    return inner, True
```

**`Union[str, None]` (equivalent to `Optional[str]`):** The same `Union` branch above handles this — it detects the `None` element and returns `(str_type, True)`.

**`Literal["a", "b"]`:** The AST is `Subscript(Literal, Tuple([Constant("a"), Constant("b")]))`. JSON Schema represents `Literal` as `{"type": "string", "enum": [...]}` but `InferredField.type` is a flat string. The practical fix is to map `Literal` to `"string"` (the values are strings) or `"integer"` if all values are ints. For the correctness milestone, map to `"string"` with a note that enum value comparison is out of scope. Add `outer == "Literal"` to the `Subscript` handler:

```python
if outer == "Literal":
    # All Literal values are scalars. Infer the JSON type from the first constant.
    if isinstance(node.slice, ast.Tuple) and node.slice.elts:
        first = node.slice.elts[0]
        if isinstance(first, ast.Constant):
            if isinstance(first.value, bool):
                return "boolean", False
            if isinstance(first.value, int):
                return "integer", False
            if isinstance(first.value, float):
                return "number", False
    return "string", False
```

**`str | int | None` (3-way PEP 604 union):** `ast.BinOp` is left-associative, so `str | int | None` parses as `BinOp(BinOp(str, |, int), |, None)`. The current code checks only the direct left and right sides of the outer `BinOp`. Fix: recurse left and right then merge the optionality:

```python
if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
    left_type, left_opt = self._resolve_annotation(node.left)
    right_type, right_opt = self._resolve_annotation(node.right)
    is_none_right = (right_type == "None" or right_type is None)
    is_none_left = (left_type == "None" or left_type is None)
    if is_none_right:
        return left_type, True
    if is_none_left:
        return right_type, True
    # Non-nullable union: prefer left type, mark as non-optional
    return left_type, left_opt or right_opt
```

This handles `str | int | None` correctly: `BinOp(str|int, |, None)` → left resolves to `("string", False)`, right is `None` → returns `("string", True)`.

**`get_origin` / `get_args` are NOT applicable here.** These are runtime type inspection utilities for resolved `typing` objects. DocGuard's parser only ever sees `ast.expr` nodes (source text parsed to AST), not live Python type objects. Using `get_origin` would require importing and executing the source, which the AST-only constraint forbids.

---

## Finding 4: Deterministic Output

### The problem

`_collect_source_files` in `cli.py` (line 40) uses `source_dir.rglob("*.py")` without sorting. On macOS (APFS) and Linux (ext4), `rglob` returns files in inode order, which varies by filesystem state. Two runs on the same codebase may produce files in different order.

### Consequences

1. Pydantic model names are stored in a `dict` by `_PydanticModelCollector`. If two files define a class with the same name, the last file processed wins. File order = inode order = non-deterministic.
2. `all_endpoints.extend(visitor.endpoints)` appends in file-processing order. This means `FieldDiff` messages within a drifted endpoint may appear in different order across runs.

### The fix

One line in `_collect_source_files`:

```python
return sorted(files)
```

`sorted(list[Path])` compares `Path` objects lexicographically, which equals alphabetical sort by full absolute path string. This is stable across runs on any OS.

**Why this is sufficient:** The `compare()` function in `comparator.py` already uses `for key in sorted(all_keys)` (line 36), so endpoint-level output order is deterministic. The field-level diff ordering within a single endpoint is currently insertion-order (Python 3.7+ dict guarantee), which becomes deterministic once file processing order is deterministic.

**No changes needed in `comparator.py`.** The `compare()` function is already correctly order-independent for the purpose of detecting drift. The dict-keyed lookups (`code_map`, `spec_map`, `code_map` in `_compare_fields`) are all by name, not position.

---

## Finding 5: `severity_threshold` — Where to Apply the Filter

### The problem

`DocGuardConfig.check.severity_threshold` is parsed and stored but never read. `cli.py` uses `Severity.ERROR` directly (line 181) for the `has_errors` check, ignoring the config.

### The fix

Add `filter_by_severity(report: DriftReport, threshold: str) -> DriftReport` to `comparator.py`. Call it in `cli.py` between `compare()` and the output step in the `check` command:

```python
# After: report = compare(code_endpoints, spec_endpoints, metadata)
if cfg.check.severity_threshold != "info":  # "info" = no filtering
    from docguard.core.comparator import filter_by_severity
    report = filter_by_severity(report, cfg.check.severity_threshold)
```

The filter function: iterate `report.endpoints`, filter `EndpointResult.diffs` to only those where `SEVERITY_ORDER[diff.severity.value] <= SEVERITY_ORDER[threshold]`. Re-evaluate each `EndpointResult.status` (DRIFT if any diffs remain, SYNCED if zero). Update `DriftSummary.drifted` and `DriftSummary.synced` counts. Return a new `DriftReport`.

Severity ordering (lower index = higher severity):

```python
_SEVERITY_ORDER: dict[str, int] = {"error": 0, "warning": 1, "info": 2}
```

A diff passes the threshold if `_SEVERITY_ORDER[diff.severity.value] <= _SEVERITY_ORDER[threshold]`. Default config is `severity_threshold: error`, which filters out `WARNING` and `INFO` diffs. Setting `severity_threshold: info` keeps everything.

---

## Finding 6: Silent Parse Failure Warnings

### The problem

`FastAPIParser.extract_endpoints` lines 382–384:

```python
except (SyntaxError, OSError):
    continue
```

No logging, no counter, no warning. In CI, endpoints in a file with a syntax error become invisible.

### The fix

Add `source_warnings: list[str]` to `DriftReportMetadata` (or directly to `DriftReport`). Return parse warnings alongside endpoints from `extract_endpoints`. Update the `FrameworkParser` protocol to optionally expose parse warnings (or use a wrapper dataclass). In `cli.py`, merge warnings into the report metadata before formatting.

Minimal approach without changing the `FrameworkParser` protocol: make `FastAPIParser` accumulate warnings in an instance attribute (`self.parse_warnings: list[str]`) and let cli.py read it after calling `extract_endpoints`. This avoids a protocol change.

---

## Dependency Summary

| Fix | New dependency? | Uses existing transitive dep? |
|-----|----------------|-------------------------------|
| Router name detection | No | No (stdlib `ast`) |
| `$ref` parameter resolution | No | No (stdlib dict traversal) |
| `$ref` external ref warning | No | Yes (`referencing.exceptions.Unresolvable` if using SchemaPath) |
| Type normalization | No | No (stdlib `ast`) |
| Deterministic ordering | No | No (stdlib `sorted()`) |
| `severity_threshold` | No | No (pure comparison) |
| Silent failure warnings | No | No |

All correctness fixes are implementable with zero additions to `pyproject.toml` dependencies.

If a future milestone migrates `spec_loader.py` to use `SchemaPath` for full OAS traversal (external file refs, recursive `$ref` chains in request/response bodies), the correct import is `from jsonschema_path import SchemaPath` — this package is already installed as a transitive dep of `openapi-spec-validator`. It would need to be added to `pyproject.toml` as an explicit runtime dependency at that point (to lock the version), but not for the current milestone.

---

## Implementation Order (Recommended)

1. **`_collect_source_files` sort** — one line, eliminates all ordering non-determinism. Do this first so subsequent test runs are stable.
2. **`_resolve_component_ref` helper in `spec_loader.py`** — replaces `_resolve_ref`, fixes `$ref` parameters and extends schema ref resolution to all component categories. Collect warnings list alongside the result.
3. **`_RouterNameCollector` pre-pass in `fastapi_parser.py`** — add as a third pass in `extract_endpoints`, before `_RouteVisitor`. Feed detected names into `_RouteVisitor`. Add `router_names` to `CheckConfig` with default `["app", "router"]`.
4. **Union/Literal type resolution in `_PydanticModelCollector._resolve_annotation`** — targeted additions to the existing `Subscript` and `BinOp` branches. No structural changes.
5. **`filter_by_severity` in `comparator.py` + wiring in `cli.py`** — new function, new call site. Low blast radius.
6. **Silent failure warnings** — add `parse_warnings` accumulation to `FastAPIParser`, surface in output.

---

_Analysis based on direct source inspection of `fastapi_parser.py`, `spec_loader.py`, `comparator.py`, `config.py`, `cli.py`, and runtime verification of `jsonschema-path` 0.4.5 and `referencing` 0.37.0 behavior._
