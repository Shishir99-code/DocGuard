# Technology Stack
_Last updated: 2026-06-02_

## Language

**Primary:** Python 3.11+
- Minimum required: `>=3.11` (enforced in `pyproject.toml`)
- Classifiers declare support for 3.11, 3.12, 3.13
- All source files use `from __future__ import annotations` for forward-reference compatibility
- Type annotations are used throughout; strict mypy is enforced

## Runtime Environment

DocGuard is a **CLI tool and GitHub Action composite action**. It has no server component.

- Invoked as `docguard <subcommand>` via the `docguard` entry point script
- Entry point: `docguard.cli:app` (defined in `pyproject.toml` under `[project.scripts]`)
- Primary CLI module: `src/docguard/cli.py`
- Also usable as a GitHub Actions composite action via `action.yml`

## Package Manager & Build

**Build backend:** Hatchling (`hatchling`)
- Config in `pyproject.toml` under `[build-system]`
- Wheel target: `src/docguard` (`[tool.hatch.build.targets.wheel]`)

**Install method (current):** `pip install git+https://github.com/Shishir99-code/DocGuard.git`
- Not yet on PyPI as of this analysis
- Development install: `pip install -e .`

**Source layout:** `src/` layout (`src/docguard/`)

## Core Frameworks & Libraries

| Package | Version Constraint | Purpose |
|---|---|---|
| `typer` | `>=0.12` | CLI argument parsing and command routing |
| `pyyaml` | `>=6.0` | YAML parsing (OpenAPI spec files, config) |
| `rich` | `>=13.0` | Terminal output formatting and styling |
| `pydantic` | `>=2.0` | Data models, config validation, structured output |
| `openapi-spec-validator` | `>=0.7` | OpenAPI spec validation (imported as dependency) |

## Optional Dependencies

**`[llm]` extra:**
| Package | Version Constraint | Purpose |
|---|---|---|
| `openai` | `>=1.0` | LLM-powered auto-fix suggestions (`docguard fix` command) |

The `openai` package is a lazy import inside `src/docguard/fixers/llm_fixer.py` — it is only required when `docguard fix` is invoked. Install with: `pip install 'docguard[llm]'`

## Dev Tooling

Installed via `pip install -e '.[dev]'` (the `[dev]` extra in `pyproject.toml`).

| Tool | Version Constraint | Purpose |
|---|---|---|
| `pytest` | `>=8.0` | Test runner |
| `pytest-cov` | `>=5.0` | Coverage reporting |
| `ruff` | `>=0.4` | Linting and import sorting (replaces flake8 + isort) |
| `mypy` | `>=1.10` | Static type checking |
| `pre-commit` | `>=3.7` | Git hook manager |

### Ruff Configuration (`pyproject.toml`)
```toml
[tool.ruff]
target-version = "py311"
line-length = 100
src = ["src", "tests"]

[tool.ruff.lint]
select = ["E", "F", "I", "N", "UP", "B", "SIM", "TCH"]
```
- Rule sets: pycodestyle (E), pyflakes (F), isort (I), naming (N), pyupgrade (UP), bugbear (B), simplify (SIM), type-checking (TCH)

### mypy Configuration (`pyproject.toml`)
```toml
[tool.mypy]
python_version = "3.11"
strict = true
warn_return_any = true
warn_unused_configs = true
```
Strict mode is enabled — all functions must be fully annotated.

## Test Framework

**Runner:** pytest `>=8.0`
- Config in `pyproject.toml` under `[tool.pytest.ini_options]`
- Test paths: `tests/`
- Default flags: `-v --tb=short`

**Coverage:** pytest-cov `>=5.0`

**Test files:**
- `tests/test_cli.py`
- `tests/test_fastapi_parser.py`
- `tests/test_comparator.py`
- `tests/conftest.py`
- `tests/fixtures/sample_fastapi_app.py`

## Documentation

**Framework:** MkDocs with Material theme (`mkdocs-material>=9.5`)
- Config: `mkdocs.yml`
- Docs source: `docs/`
- Published at: `https://docs.docguard.dev` (per `mkdocs.yml`)

Optional `[docs]` extra installs `mkdocs-material` and `mkdocs-social`.

## AST Analysis

The FastAPI parser (`src/docguard/parsers/fastapi_parser.py`) uses Python's built-in `ast` module (stdlib) to statically analyze source code without importing it. No third-party AST library is used.

## Standard Library Usage

Key stdlib modules used across the codebase:
- `ast` — static Python source analysis
- `json` — JSON spec loading and report output
- `pathlib` — all file path operations use `Path`
- `subprocess` — git metadata extraction in `cli.py`
- `fnmatch` — glob-based ignore patterns

## CI / CD

**GitHub Actions composite action** (`action.yml`):
- Installs Python via `actions/setup-python@v5`
- Installs DocGuard via git URL (not PyPI)
- Runs `docguard report` then `docguard check`
- No separate `.github/workflows/` directory exists in the repo itself (no self-CI pipeline detected)

---

_Stack analysis: 2026-06-02_
