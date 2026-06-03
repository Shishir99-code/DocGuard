# Codebase Structure
_Last updated: 2026-06-02_

## Directory Layout

```
DocGuard/
├── src/
│   └── docguard/               # Main package (src-layout)
│       ├── __init__.py         # Package version (__version__ = "0.1.0")
│       ├── cli.py              # Typer CLI entry point — all commands
│       ├── config.py           # .docguard.yaml loader (Pydantic)
│       ├── core/               # Framework-agnostic engine
│       │   ├── __init__.py
│       │   ├── comparator.py   # Diff logic: code vs spec
│       │   ├── models.py       # All shared dataclasses and enums
│       │   └── spec_loader.py  # OpenAPI spec reader + normalizer
│       ├── parsers/            # Framework-specific code analyzers
│       │   ├── __init__.py
│       │   ├── base.py         # FrameworkParser Protocol definition
│       │   ├── fastapi_parser.py  # AST-based FastAPI extractor
│       │   └── registry.py     # Parser discovery and registration
│       ├── formatters/         # DriftReport renderers
│       │   ├── __init__.py
│       │   ├── github.py       # GitHub Actions annotation format
│       │   ├── json_fmt.py     # JSON output (canonical schema)
│       │   └── text.py         # Rich terminal output
│       └── fixers/             # Optional LLM-powered repair
│           ├── __init__.py
│           └── llm_fixer.py    # OpenAI prompt builder + API call
├── tests/
│   ├── __init__.py
│   ├── conftest.py             # Shared pytest fixtures (path helpers)
│   ├── fixtures/
│   │   ├── sample_fastapi_app.py    # Realistic FastAPI app for parsing tests
│   │   ├── sample_openapi.yaml      # Matching spec (no drift)
│   │   └── drifted_openapi.yaml     # Spec with intentional drift
│   ├── test_cli.py             # End-to-end CLI command tests
│   ├── test_comparator.py      # Unit tests for comparator logic
│   └── test_fastapi_parser.py  # Unit tests for AST parser
├── docs/                       # MkDocs documentation source
│   ├── index.md
│   ├── architecture.md
│   ├── auto-fix.md
│   ├── cli-reference.md
│   ├── configuration.md
│   ├── drift-report-schema.md
│   ├── getting-started.md
│   ├── extending/
│   │   └── writing-a-parser.md
│   └── integrations/
│       ├── github-actions.md
│       └── pre-commit.md
├── .docguard.yaml              # DocGuard config for this repo itself
├── action.yml                  # GitHub Actions composite action definition
├── mkdocs.yml                  # MkDocs site configuration
├── pyproject.toml              # Build metadata, deps, tool config
├── CHANGELOG.md
├── CONTRIBUTING.md
└── README.md
```

## Key Source Files

### Entry Points

- `src/docguard/cli.py` — The sole CLI entry point. Registered as `docguard = "docguard.cli:app"` in `pyproject.toml`. Contains four commands: `init`, `check`, `fix`, `report`. Also callable as `python -m docguard.cli`.

### Core Engine

- `src/docguard/core/models.py` — All shared data types. No external deps beyond stdlib. Import this to understand the data contract for the whole system. Key types: `InferredEndpoint`, `InferredField`, `FieldDiff`, `EndpointResult`, `DriftReport`, `DriftSummary`, `DriftReportMetadata`.

- `src/docguard/core/comparator.py` — Pure function `compare(code_endpoints, spec_endpoints, metadata) -> DriftReport`. No I/O. Matches endpoints by `"METHOD /path"` key, then recursively diffs fields and parameters.

- `src/docguard/core/spec_loader.py` — Two public functions: `load_spec(path)` reads YAML/JSON, `normalize_spec(raw_dict)` converts to `list[InferredEndpoint]`. Handles `$ref` resolution within `#/components/schemas/`, OAS 3.1 `anyOf` nullable variants, and array unwrapping.

### Parsers

- `src/docguard/parsers/base.py` — `FrameworkParser` Protocol. Required interface for all parsers: `name`, `can_handle(project_root)`, `extract_endpoints(source_files)`.

- `src/docguard/parsers/fastapi_parser.py` — Only currently implemented parser. Two internal AST visitor classes: `_PydanticModelCollector` (pass 1: collect Pydantic model schemas) and `_RouteVisitor` (pass 2: find route decorators and resolve types). Public class: `FastAPIParser`.

- `src/docguard/parsers/registry.py` — Module-level `_PARSERS` list. `detect_framework()` iterates and calls `can_handle()`. `register_parser()` allows third-party extension at runtime.

### Formatters

- `src/docguard/formatters/text.py` — `render(report, console)`. Uses `rich` Panel, Table. Only prints non-synced endpoints.
- `src/docguard/formatters/json_fmt.py` — `render(report) -> str`. Returns JSON string using `report.to_dict()`.
- `src/docguard/formatters/github.py` — `render(report) -> str`. Emits `::error` and `::warning` annotation lines for GitHub Actions.

### Config

- `src/docguard/config.py` — `DocGuardConfig` Pydantic model. `load_config(project_root)` walks up directory tree looking for `.docguard.yaml`. `default_config_yaml()` returns the template written by `docguard init`.

### Fixer

- `src/docguard/fixers/llm_fixer.py` — `suggest_fix(report, spec_content, model, api_key_env) -> str`. Lazily imports `openai`. `build_fix_prompt()` is separately testable.

## Entry Points (CLI)

| Command | Purpose |
|---------|---------|
| `docguard init` | Write default `.docguard.yaml` to cwd |
| `docguard check` | Run drift detection; exit 1 on violations |
| `docguard fix` | Suggest or apply LLM-generated spec patches |
| `docguard report` | Emit full JSON drift report to stdout or file |
| `docguard version` | Print version string |

## Test Organization

Tests live in `tests/` alongside a `fixtures/` subdirectory. There is no mirrored `src/` hierarchy — tests are organized by component, not by path.

| File | What it tests |
|------|---------------|
| `tests/test_cli.py` | CLI command integration (check, init, fix, report using fixture files) |
| `tests/test_comparator.py` | Comparator logic: synced, drifted, missing cases, drift score |
| `tests/test_fastapi_parser.py` | AST parser correctness against `fixtures/sample_fastapi_app.py` |
| `tests/conftest.py` | Shared fixtures: `fixtures_dir`, `sample_app_path`, `sample_spec_path`, `drifted_spec_path` |

Test fixtures:
- `tests/fixtures/sample_fastapi_app.py` — A realistic FastAPI app used as the canonical "real code" input.
- `tests/fixtures/sample_openapi.yaml` — OpenAPI spec that matches `sample_fastapi_app.py` (should produce zero drift).
- `tests/fixtures/drifted_openapi.yaml` — OpenAPI spec with deliberate mismatches for testing drift detection.

## Naming Conventions

**Files:**
- Source modules: `snake_case.py`
- Formatter files use `_fmt` suffix where the name would conflict with a stdlib module: `json_fmt.py`

**Directories:**
- Plural nouns for collections of similar components: `parsers/`, `formatters/`, `fixers/`
- `core/` for framework-agnostic engine code

**Classes:**
- Public classes: `PascalCase` (e.g. `FastAPIParser`, `DocGuardConfig`)
- Private AST visitor helpers: underscore-prefixed `PascalCase` (e.g. `_PydanticModelCollector`, `_RouteVisitor`)

## Where to Add New Code

**New framework parser (e.g., Django, Flask):**
1. Create `src/docguard/parsers/<framework>_parser.py` implementing `FrameworkParser` protocol
2. Add an instance to `_PARSERS` list in `src/docguard/parsers/registry.py`
3. Add tests in `tests/test_<framework>_parser.py` with fixture app in `tests/fixtures/`

**New output formatter:**
1. Create `src/docguard/formatters/<name>_fmt.py` with a `render(report) -> str` function
2. Register the format name in the `fmt` option handling inside `src/docguard/cli.py`

**New CLI command:**
1. Add a new `@app.command()` decorated function in `src/docguard/cli.py`

**New core models or data fields:**
1. Edit `src/docguard/core/models.py` only — do not duplicate type definitions elsewhere

**New configuration options:**
1. Add to the appropriate nested Pydantic class in `src/docguard/config.py`
2. Update `default_config_yaml()` to include the new option with a comment

## Documentation Structure

`docs/` contains MkDocs source. Key reference docs:
- `docs/architecture.md` — High-level design narrative
- `docs/configuration.md` — All `.docguard.yaml` options
- `docs/cli-reference.md` — All CLI commands and flags
- `docs/drift-report-schema.md` — JSON output schema
- `docs/extending/writing-a-parser.md` — Guide for adding new framework parsers
- `docs/integrations/github-actions.md` — CI setup with `action.yml`

---

_Structure analysis: 2026-06-02_
