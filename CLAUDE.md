<!-- GSD:project-start source:PROJECT.md -->

## Project

**DocGuard — Correctness & Consistency**

DocGuard is a Python CLI tool that detects documentation drift between an OpenAPI spec and the actual FastAPI source code, running as a static analyzer (no live server needed). It is used primarily in CI pipelines (GitHub Actions, pre-commit) to catch spec divergence before it reaches production. This milestone focuses on eliminating false positives and incorrect drift detection that make the tool unreliable on real-world FastAPI apps.

**Core Value:** A developer running `docguard check` on any real FastAPI app gets accurate, deterministic results — zero false positives, zero silently missed endpoints.

### Constraints

- **Tech stack**: Python 3.9+, no new runtime dependencies without strong justification — tool is installed in CI environments where dep count matters
- **Backwards compatibility**: `.docguard.yaml` config file format must remain backwards-compatible — existing CI configs must keep working
- **No LLM in core pipeline**: The `check`, `report` path must remain LLM-free — it runs on every CI push and must be fast and deterministic
- **AST-only parser**: FastAPI endpoint extraction stays AST-based (no import/exec) — safe to run in restricted CI environments

<!-- GSD:project-end -->

<!-- GSD:stack-start source:codebase/STACK.md -->

## Technology Stack

## Language

- Minimum required: `>=3.11` (enforced in `pyproject.toml`)
- Classifiers declare support for 3.11, 3.12, 3.13
- All source files use `from __future__ import annotations` for forward-reference compatibility
- Type annotations are used throughout; strict mypy is enforced

## Runtime Environment

- Invoked as `docguard <subcommand>` via the `docguard` entry point script
- Entry point: `docguard.cli:app` (defined in `pyproject.toml` under `[project.scripts]`)
- Primary CLI module: `src/docguard/cli.py`
- Also usable as a GitHub Actions composite action via `action.yml`

## Package Manager & Build

- Config in `pyproject.toml` under `[build-system]`
- Wheel target: `src/docguard` (`[tool.hatch.build.targets.wheel]`)
- Not yet on PyPI as of this analysis
- Development install: `pip install -e .`

## Core Frameworks & Libraries

| Package | Version Constraint | Purpose |
|---|---|---|
| `typer` | `>=0.12` | CLI argument parsing and command routing |
| `pyyaml` | `>=6.0` | YAML parsing (OpenAPI spec files, config) |
| `rich` | `>=13.0` | Terminal output formatting and styling |
| `pydantic` | `>=2.0` | Data models, config validation, structured output |
| `openapi-spec-validator` | `>=0.7` | OpenAPI spec validation (imported as dependency) |

## Optional Dependencies

| Package | Version Constraint | Purpose |
|---|---|---|
| `openai` | `>=1.0` | LLM-powered auto-fix suggestions (`docguard fix` command) |

## Dev Tooling

| Tool | Version Constraint | Purpose |
|---|---|---|
| `pytest` | `>=8.0` | Test runner |
| `pytest-cov` | `>=5.0` | Coverage reporting |
| `ruff` | `>=0.4` | Linting and import sorting (replaces flake8 + isort) |
| `mypy` | `>=1.10` | Static type checking |
| `pre-commit` | `>=3.7` | Git hook manager |

### Ruff Configuration (`pyproject.toml`)

- Rule sets: pycodestyle (E), pyflakes (F), isort (I), naming (N), pyupgrade (UP), bugbear (B), simplify (SIM), type-checking (TCH)

### mypy Configuration (`pyproject.toml`)

## Test Framework

- Config in `pyproject.toml` under `[tool.pytest.ini_options]`
- Test paths: `tests/`
- Default flags: `-v --tb=short`
- `tests/test_cli.py`
- `tests/test_fastapi_parser.py`
- `tests/test_comparator.py`
- `tests/conftest.py`
- `tests/fixtures/sample_fastapi_app.py`

## Documentation

- Config: `mkdocs.yml`
- Docs source: `docs/`
- Published at: `https://docs.docguard.dev` (per `mkdocs.yml`)

## AST Analysis

## Standard Library Usage

- `ast` — static Python source analysis
- `json` — JSON spec loading and report output
- `pathlib` — all file path operations use `Path`
- `subprocess` — git metadata extraction in `cli.py`
- `fnmatch` — glob-based ignore patterns

## CI / CD

- Installs Python via `actions/setup-python@v5`
- Installs DocGuard via git URL (not PyPI)
- Runs `docguard report` then `docguard check`
- No separate `.github/workflows/` directory exists in the repo itself (no self-CI pipeline detected)

<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->

## Conventions

## Tooling

- Line length: 100 characters
- Target: Python 3.11+
- Active rule sets: `E` (pycodestyle errors), `F` (pyflakes), `I` (isort), `N` (pep8 naming),
- Config in `pyproject.toml` under `[tool.mypy]`
- `strict = true`, `warn_return_any = true`, `warn_unused_configs = true`
- Python version target: 3.11

## Type Annotations

- All functions carry full type annotations — parameters and return types without exception.
- `from __future__ import annotations` is present in every source file, enabling PEP 563
- Union types use the `X | Y` syntax (Python 3.10+ style), not `Optional[X]` or `Union[X, Y]`.
- `typing.Protocol` with `@runtime_checkable` is used to define parser contracts
- Inline type annotations on local variables when not inferrable:

## Naming Conventions

- Public domain models: `InferredEndpoint`, `DriftReport`, `EndpointResult`
- Internal AST visitors: prefixed with `_` (e.g., `_PydanticModelCollector`)
- Private helpers: prefixed with `_` (e.g., `_collect_source_files`, `_resolve_name`)
- Examples: `_PYTHON_TYPE_TO_JSON`, `_HTTP_METHODS`, `_ROUTER_NAMES` (module-private with `_` prefix)
- All enums inherit from both `str` and `enum.Enum` for JSON serialization compatibility:

## Import Organization

## Docstrings

- Module-level docstrings on every file: single-line summary sentence.
- Class docstrings: multi-line when the class has a non-obvious purpose
- Method docstrings: present on public interface methods and non-obvious helpers.
- `dataclass` fields use inline comments rather than docstrings for brief notes:

## Data Models

- Domain data uses `@dataclass` (stdlib), not Pydantic, for internal representation.
- All dataclass models implement a `to_dict() -> dict` method for JSON serialization.
- `field(default_factory=list)` is used for mutable defaults.

## Error Handling

- No custom exception hierarchy observed in the codebase; errors propagate as stdlib exceptions.
- CLI layer uses Typer's built-in exit code mechanism (`raise typer.Exit(code=N)`).
- Exit codes are meaningful: `0` = no drift, `1` = drift detected (convention visible in `test_cli.py`).

## Section Separators

## Adding New Features

<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->

## Architecture

## System Overview

```text

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

### FastAPI Parser — Two-Pass AST Strategy

### `fix` Command Path

## Key Abstractions

### `InferredEndpoint` — shared currency

### `FrameworkParser` protocol

### `DriftReport` — single output contract

### `DocGuardConfig` — Pydantic settings

## Module Boundaries and Coupling

- `core/` has no imports from `parsers/`, `formatters/`, or `fixers/`. It is the lowest layer.
- `parsers/` imports only from `core/models`. No formatter or fixer imports.
- `formatters/` and `fixers/` import only from `core/models`. They do not import each other.
- `cli.py` is the only module that imports from all layers. It is the composition root.
- The `openai` package is a lazy import inside `fixers/llm_fixer.py` — guarded by `try/except ImportError` so it is not required unless the `fix` command is used.

## Configuration System Design

```yaml

```

## Error Handling Strategy

- Config/spec resolution errors print a user-facing message via `rich.Console` and call `raise typer.Exit(2)`. No exceptions propagate to the user.
- Parser errors per file (syntax errors, OS errors) are silently skipped via `except (SyntaxError, OSError): continue` in `FastAPIParser.extract_endpoints` (`src/docguard/parsers/fastapi_parser.py:379`).
- LLM fixer raises `RuntimeError` for missing API key or missing `openai` package; CLI catches and prints it before `raise typer.Exit(2)`.
- Exit codes: `0` = success/no violations, `1` = drift detected (respects `fail_on` policy), `2` = configuration/runtime error.
- No custom exception hierarchy. The tool uses `RuntimeError` for programmer-facing errors and Typer's exit mechanism for user-facing errors.

## Drift Score Calculation

```

```
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->

## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->

## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:

- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->

## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
