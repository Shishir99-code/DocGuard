# Coding Conventions
_Last updated: 2026-06-02_

## Tooling

**Formatter/Linter:** Ruff (`ruff>=0.4`), configured in `pyproject.toml`
- Line length: 100 characters
- Target: Python 3.11+
- Active rule sets: `E` (pycodestyle errors), `F` (pyflakes), `I` (isort), `N` (pep8 naming),
  `UP` (pyupgrade), `B` (bugbear), `SIM` (simplify), `TCH` (type-checking imports)

**Type Checker:** mypy (`mypy>=1.10`), strict mode
- Config in `pyproject.toml` under `[tool.mypy]`
- `strict = true`, `warn_return_any = true`, `warn_unused_configs = true`
- Python version target: 3.11

**Pre-commit:** `pre-commit>=3.7` listed as dev dependency (hooks file not inspected but tooling installed)

## Type Annotations

- All functions carry full type annotations — parameters and return types without exception.
- `from __future__ import annotations` is present in every source file, enabling PEP 563
  postponed evaluation. This is the first import in every module.
- Union types use the `X | Y` syntax (Python 3.10+ style), not `Optional[X]` or `Union[X, Y]`.
  Example from `src/docguard/core/models.py`:
  ```python
  description: str | None = None
  nested: list[InferredField] | None = None
  ```
- `typing.Protocol` with `@runtime_checkable` is used to define parser contracts
  (`src/docguard/parsers/base.py`).
- Inline type annotations on local variables when not inferrable:
  ```python
  fields: list[InferredField] = []
  result: dict = {...}
  ```

## Naming Conventions

**Modules/packages:** `snake_case` (e.g., `fastapi_parser.py`, `spec_loader.py`, `json_fmt.py`)

**Classes:** `PascalCase`
- Public domain models: `InferredEndpoint`, `DriftReport`, `EndpointResult`
- Internal AST visitors: prefixed with `_` (e.g., `_PydanticModelCollector`)

**Functions/methods:** `snake_case`
- Private helpers: prefixed with `_` (e.g., `_collect_source_files`, `_resolve_name`)

**Variables:** `snake_case`

**Constants / module-level dicts:** `UPPER_SNAKE_CASE`
- Examples: `_PYTHON_TYPE_TO_JSON`, `_HTTP_METHODS`, `_ROUTER_NAMES` (module-private with `_` prefix)

**Enums:** `PascalCase` class, `UPPER_SNAKE_CASE` members
- All enums inherit from both `str` and `enum.Enum` for JSON serialization compatibility:
  ```python
  class EndpointStatus(str, enum.Enum):
      SYNCED = "synced"
  ```

## Import Organization

Ruff `I` rules (isort) enforce import order. Observed pattern across all files:

1. `from __future__ import annotations` — always first
2. Standard library imports (e.g., `ast`, `enum`, `json`, `sys`, `time`)
3. Third-party imports (e.g., `typer`, `rich`, `pydantic`)
4. Internal `docguard` imports

No relative imports observed; all internal imports use the full `docguard.*` package path.

## Docstrings

- Module-level docstrings on every file: single-line summary sentence.
  Example: `"""FastAPI parser -- extracts API endpoints from FastAPI source code via AST analysis."""`
- Class docstrings: multi-line when the class has a non-obvious purpose
  (e.g., `FrameworkParser`, `_PydanticModelCollector`).
- Method docstrings: present on public interface methods and non-obvious helpers.
  Single-line preferred; multi-line when parameters or behavior need explanation.
- `dataclass` fields use inline comments rather than docstrings for brief notes:
  ```python
  type: str  # JSON Schema type: "string", "integer", "array", etc.
  ```

## Data Models

- Domain data uses `@dataclass` (stdlib), not Pydantic, for internal representation.
  Pydantic is a runtime dependency for *user* code analysis, not for DocGuard's own models.
- All dataclass models implement a `to_dict() -> dict` method for JSON serialization.
- `field(default_factory=list)` is used for mutable defaults.

## Error Handling

- No custom exception hierarchy observed in the codebase; errors propagate as stdlib exceptions.
- CLI layer uses Typer's built-in exit code mechanism (`raise typer.Exit(code=N)`).
- Exit codes are meaningful: `0` = no drift, `1` = drift detected (convention visible in `test_cli.py`).

## Section Separators

The CLI file uses ASCII banner comments to separate logical sections:
```python
# ── Helpers ──────────────────────────────────────────────────────────────────
```
This pattern may be used in larger files for readability.

## Adding New Features

**New parser:** Implement the `FrameworkParser` Protocol from `src/docguard/parsers/base.py`,
place in `src/docguard/parsers/`, register in `src/docguard/parsers/registry.py`.

**New formatter:** Add a module to `src/docguard/formatters/`, import in `src/docguard/cli.py`.

**New model field:** Add to the relevant `@dataclass` in `src/docguard/core/models.py` and update
the corresponding `to_dict()` method.

**New CLI command:** Add a `@app.command()` function to `src/docguard/cli.py`.
