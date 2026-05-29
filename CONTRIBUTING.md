# Contributing to DocGuard

Thank you for your interest in contributing to DocGuard! This document covers everything you need to get started.

## Development Setup

### Prerequisites

- Python 3.11 or later
- Git

### Clone and Install

```bash
git clone https://github.com/Shishir99-code/DocGuard.git
cd docguard
pip install -e ".[dev]"
```

This installs DocGuard in editable mode with all development dependencies (pytest, ruff, mypy, pre-commit).

### Install Pre-commit Hooks

```bash
pre-commit install
```

This ensures linting and formatting run automatically before each commit.

## Code Style

- **Formatter/Linter**: [Ruff](https://docs.astral.sh/ruff/) -- run `ruff check src/ tests/` and `ruff format src/ tests/`
- **Type Checking**: [Mypy](https://mypy-lang.org/) in strict mode -- run `mypy src/`
- **Line Length**: 100 characters
- **Target Python**: 3.11+ (use modern syntax: `X | Y` unions, `list[T]` generics)
- **Docstrings**: Required for all public functions and classes
- **Imports**: Sorted by Ruff (isort-compatible)

## Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=docguard --cov-report=term-missing

# Run a specific test file
pytest tests/test_fastapi_parser.py -v
```

All tests must pass before a PR will be reviewed.

## Project Structure

```
src/docguard/
  cli.py              # Typer CLI commands
  config.py           # .docguard.yaml loader
  core/
    models.py         # Canonical data models (InferredEndpoint, DriftReport, etc.)
    comparator.py     # Drift detection logic
    spec_loader.py    # OpenAPI spec parser and normalizer
  parsers/
    base.py           # FrameworkParser protocol
    registry.py       # Parser auto-detection
    fastapi_parser.py # FastAPI AST visitor
  formatters/
    text.py           # Rich terminal output
    json_fmt.py       # JSON report
    github.py         # GitHub Actions annotations
  fixers/
    llm_fixer.py      # LLM-powered auto-fix
```

## Making Changes

### Branch Naming

- `feat/short-description` -- New features
- `fix/short-description` -- Bug fixes
- `docs/short-description` -- Documentation changes
- `refactor/short-description` -- Code refactoring

### Commit Messages

Use conventional commit format:

```
feat: add Express.js parser support
fix: handle Optional[List[Model]] annotations in FastAPI parser
docs: add pre-commit integration guide
test: add edge case tests for empty response models
```

### Pull Request Process

1. Create a feature branch from `main`
2. Make your changes with tests
3. Ensure `pytest`, `ruff check`, and `mypy` all pass
4. Open a pull request with a clear description of what and why
5. Link any related issues
6. Wait for review -- we aim to respond within 48 hours

### Adding a New Framework Parser

See the [Writing a Parser](https://docs.docguard.dev/extending/writing-a-parser) guide for step-by-step instructions.

## Issue Templates

When opening an issue, please include:

**Bug reports:**
- DocGuard version (`docguard version`)
- Python version
- Framework and version being scanned
- Steps to reproduce
- Expected vs. actual behavior

**Feature requests:**
- Use case description
- Proposed solution (if any)
- Alternatives considered

## Code of Conduct

All contributors are expected to follow our [Code of Conduct](CODE_OF_CONDUCT.md). Be respectful, constructive, and inclusive.

## Contributor License Agreement

By submitting a pull request, you agree that your contributions may be used under the terms of the project's license. For significant contributions, we may ask you to sign a Contributor License Agreement (CLA) to ensure the project can be commercially distributed.
