# Architecture
_Last updated: 2026-06-02_

## System Overview

DocGuard is a Python CLI tool that detects "documentation drift" — divergence between an OpenAPI spec file and the actual API endpoints implemented in source code. It operates as a static analysis tool: no running server is required. The primary use case is CI enforcement (GitHub Actions, pre-commit hooks).

```text
┌─────────────────────────────────────────────────────────────────┐
│                         CLI Layer                               │
│  `src/docguard/cli.py`  (Typer app: init, check, fix, report)  │
└──────────┬──────────────────┬──────────────────────────────────┘
           │                  │
           ▼                  ▼
┌─────────────────┐  ┌──────────────────────┐
│  Source Parser  │  │    Spec Loader        │
│  (per-framework)│  │  `core/spec_loader.py`│
│  `parsers/`     │  └──────────┬────────────┘
└────────┬────────┘             │
         │                      │
         ▼                      ▼
         └──────────┬───────────┘
                    │  Both produce list[InferredEndpoint]
                    ▼
         ┌──────────────────────┐
         │  Comparator Engine   │
         │  `core/comparator.py`│
         └──────────┬───────────┘
                    │  Produces DriftReport
                    ▼
    ┌───────────────┴────────────────┐
    │         Formatter Layer        │
    │  text / json / github          │
    │  `formatters/`                 │
    └────────────────────────────────┘
                    │
                    ▼  (optional)
         ┌──────────────────────┐
         │   LLM Fixer          │
         │  `fixers/llm_fixer.py`│
         └──────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | Key File |
|-----------|----------------|----------|
| CLI | Command dispatch, flag parsing, config resolution, exit codes | `src/docguard/cli.py` |
| Config | Load/merge `.docguard.yaml` with Pydantic validation | `src/docguard/config.py` |
| FrameworkParser protocol | Abstract interface for code-side endpoint extraction | `src/docguard/parsers/base.py` |
| FastAPIParser | Two-pass AST analysis: Pydantic models then routes | `src/docguard/parsers/fastapi_parser.py` |
| Parser Registry | Auto-detect framework; lookup by name; allow custom registration | `src/docguard/parsers/registry.py` |
| Spec Loader | Read YAML/JSON OpenAPI spec; normalize to `list[InferredEndpoint]` | `src/docguard/core/spec_loader.py` |
| Comparator | Diff code endpoints vs spec endpoints; produce `DriftReport` | `src/docguard/core/comparator.py` |
| Models | All shared dataclasses and enums — single data contract | `src/docguard/core/models.py` |
| Formatters | Render `DriftReport` as text (Rich), JSON, or GitHub Actions annotations | `src/docguard/formatters/` |
| LLM Fixer | Build prompt from drift report; call OpenAI API; return patched YAML | `src/docguard/fixers/llm_fixer.py` |

## Data Flow

### Primary `check` Command Path

1. CLI parses flags and merges with `.docguard.yaml` via `load_config()` (`src/docguard/config.py:53`)
2. `detect_framework()` or `get_parser_by_name()` selects a `FrameworkParser` (`src/docguard/parsers/registry.py:20`)
3. `_collect_source_files()` recursively gathers `.py` files, applying `ignore` globs (`src/docguard/cli.py:35`)
4. `parser.extract_endpoints(source_files)` runs AST analysis → `list[InferredEndpoint]` (`src/docguard/parsers/fastapi_parser.py:372`)
5. `load_spec(spec_path)` reads YAML/JSON → raw dict (`src/docguard/core/spec_loader.py:22`)
6. `normalize_spec(raw_spec)` converts spec dict → `list[InferredEndpoint]` (`src/docguard/core/spec_loader.py:50`)
7. `compare(code_endpoints, spec_endpoints, metadata)` produces `DriftReport` (`src/docguard/core/comparator.py:19`)
8. A formatter renders the `DriftReport` to stdout (`src/docguard/formatters/`)
9. CLI sets exit code based on `cfg.check.fail_on` and report contents (`src/docguard/cli.py:180`)

### FastAPI Parser — Two-Pass AST Strategy

The FastAPI parser uses a two-pass design to handle forward references between Pydantic models and route handler functions:

1. **Pass 1** — `_PydanticModelCollector` visits all AST trees and builds a `dict[str, list[InferredField]]` of Pydantic model definitions (`src/docguard/parsers/fastapi_parser.py:33`)
2. **Pass 2** — `_RouteVisitor` walks each file's AST, looks for `@app.get(...)` / `@router.post(...)` decorators, and resolves request/response body types by looking up the collected model dict (`src/docguard/parsers/fastapi_parser.py:150`)

### `fix` Command Path

1. Same steps 1–7 as `check`
2. If drift score > 0, `suggest_fix(report, spec_content, model, api_key_env)` builds an LLM prompt and calls the OpenAI chat completions API (`src/docguard/fixers/llm_fixer.py:32`)
3. Returned YAML is printed (dry-run) or written back to the spec file if `--apply` is passed

## Key Abstractions

### `InferredEndpoint` — shared currency

Both the code parser and the spec loader produce `list[InferredEndpoint]`. This is the common representation that feeds into the comparator. Defined at `src/docguard/core/models.py:71`. Key fields: `path`, `method`, `request_body`, `response_fields`, `query_params`, `path_params`, `response_status`. The `.key` property (`"METHOD /path"`) is used as the match key in comparator maps.

### `FrameworkParser` protocol

Defined at `src/docguard/parsers/base.py:12`. Any class implementing `name`, `can_handle(project_root)`, and `extract_endpoints(source_files)` can be registered via `register_parser()`. The protocol is `@runtime_checkable`, enabling `isinstance` checks.

### `DriftReport` — single output contract

`src/docguard/core/models.py:179`. Contains `DriftReportMetadata`, `DriftSummary`, `drift_score` (float 0–1), and `list[EndpointResult]`. All formatters and the LLM fixer consume this type. `to_dict()` produces the canonical JSON schema output.

### `DocGuardConfig` — Pydantic settings

`src/docguard/config.py:26`. Nested Pydantic models: `CheckConfig`, `FixConfig`, `OutputConfig`. CLI flags override config file values post-load. Config file is discovered by walking up the directory tree from `project_root` (max 10 levels).

## Module Boundaries and Coupling

- `core/` has no imports from `parsers/`, `formatters/`, or `fixers/`. It is the lowest layer.
- `parsers/` imports only from `core/models`. No formatter or fixer imports.
- `formatters/` and `fixers/` import only from `core/models`. They do not import each other.
- `cli.py` is the only module that imports from all layers. It is the composition root.
- The `openai` package is a lazy import inside `fixers/llm_fixer.py` — guarded by `try/except ImportError` so it is not required unless the `fix` command is used.

## Configuration System Design

Config resolution order (later overrides earlier):
1. Built-in defaults in `DocGuardConfig` Pydantic model
2. `.docguard.yaml` discovered by walking up from cwd
3. CLI flags passed at invocation time

Config file schema (`src/docguard/config.py`):
```yaml
spec: openapi.yaml          # path to OpenAPI spec
source: "."                 # directory to scan for source files
framework: auto             # auto | fastapi (or any registered parser name)
ignore: []                  # glob patterns to exclude from source scan
check:
  fail_on: any              # any | drift-only | missing
  severity_threshold: error
fix:
  model: gpt-4o-mini
  api_key_env: OPENAI_API_KEY
output:
  format: text              # text | json | github
  report_path: null
```

## Error Handling Strategy

- Config/spec resolution errors print a user-facing message via `rich.Console` and call `raise typer.Exit(2)`. No exceptions propagate to the user.
- Parser errors per file (syntax errors, OS errors) are silently skipped via `except (SyntaxError, OSError): continue` in `FastAPIParser.extract_endpoints` (`src/docguard/parsers/fastapi_parser.py:379`).
- LLM fixer raises `RuntimeError` for missing API key or missing `openai` package; CLI catches and prints it before `raise typer.Exit(2)`.
- Exit codes: `0` = success/no violations, `1` = drift detected (respects `fail_on` policy), `2` = configuration/runtime error.
- No custom exception hierarchy. The tool uses `RuntimeError` for programmer-facing errors and Typer's exit mechanism for user-facing errors.

## Drift Score Calculation

Computed in `DriftReport.calculate_drift_score()` (`src/docguard/core/models.py:188`):

```
drift_score = (drifted * 1.0 + missing_in_spec * 1.0 + missing_in_code * 0.5) / total_endpoints
```

Drifted and missing-in-spec endpoints have full weight (active integration risk); missing-in-code (stale spec entries) carry half weight.

---

_Architecture analysis: 2026-06-02_
