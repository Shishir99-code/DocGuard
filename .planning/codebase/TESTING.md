# Testing Patterns
_Last updated: 2026-06-02_

## Test Framework

**Runner:** pytest (`pytest>=8.0`)
- Coverage plugin: `pytest-cov>=5.0`
- Config in `pyproject.toml`:
  ```toml
  [tool.pytest.ini_options]
  testpaths = ["tests"]
  addopts = "-v --tb=short"
  ```

**Assertion library:** pytest built-in (no third-party assertion helpers)

**Run Commands:**
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=docguard --cov-report=term-missing

# Run a single test file
pytest tests/test_fastapi_parser.py

# Run a single test class
pytest tests/test_comparator.py::TestComparatorDrifted

# Watch mode (not configured; no pytest-watch dependency)
```

## Test File Organization

**Location:** All tests live in `tests/` at the project root, separate from source in `src/`.

**Naming:** `test_<module_name>.py` mirroring the source module being tested:
- `tests/test_fastapi_parser.py` → `src/docguard/parsers/fastapi_parser.py`
- `tests/test_comparator.py` → `src/docguard/core/comparator.py`
- `tests/test_cli.py` → `src/docguard/cli.py`

**Fixtures directory:** `tests/fixtures/` contains static test assets:
- `tests/fixtures/sample_fastapi_app.py` — a real FastAPI app with 5 known endpoints
- `tests/fixtures/sample_openapi.yaml` — OpenAPI spec in sync with `sample_fastapi_app.py`
- `tests/fixtures/drifted_openapi.yaml` — OpenAPI spec with deliberate drift scenarios

**`__init__.py`:** Present in `tests/` (empty), making it a package.

## Test Structure

**Suite organization:** Tests are grouped into classes by scenario/behavior, not by method.

```python
class TestComparatorSynced:
    """When the spec perfectly matches the code, everything should be SYNCED."""

    def test_all_synced(self, sample_app_path: Path, sample_spec_path: Path) -> None:
        ...

class TestComparatorDrifted:
    """When the spec diverges from the code, drift should be detected."""

    def test_drift_score_nonzero(self, ...) -> None:
        ...
```

**Setup pattern:** `setup_method` (not `setUp`) is used where instance state is needed:
```python
class TestFastAPIParser:
    def setup_method(self) -> None:
        self.parser = FastAPIParser()
```

**Type annotations:** All test methods carry full return type `-> None`.

**Module-level:** `from __future__ import annotations` present in all test files.

## Fixtures (conftest.py)

`tests/conftest.py` defines four path-returning fixtures:

```python
@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR

@pytest.fixture
def sample_app_path() -> Path:
    return FIXTURES_DIR / "sample_fastapi_app.py"

@pytest.fixture
def sample_spec_path() -> Path:
    return FIXTURES_DIR / "sample_openapi.yaml"

@pytest.fixture
def drifted_spec_path() -> Path:
    return FIXTURES_DIR / "drifted_openapi.yaml"
```

All fixtures return `Path` objects. No session-scoped or autouse fixtures exist currently.

`tmp_path` (pytest built-in) is used in CLI tests to create isolated working directories:
```python
def test_synced_exits_zero(self, tmp_path: Path) -> None:
    shutil.copy(FIXTURES_DIR / "sample_fastapi_app.py", tmp_path / "main.py")
    ...
```

## Mocking

**No mocking framework in use.** No `unittest.mock`, `pytest-mock`, or `MagicMock` calls are
present in any test file. Tests exercise real implementations against fixture files.

This is intentional for the current scope: the parsers and comparator are pure functions over
file inputs, making mocking unnecessary for core logic tests.

**CLI tests** use `typer.testing.CliRunner` (not mocked) to invoke the full CLI stack:
```python
from typer.testing import CliRunner
runner = CliRunner()

result = runner.invoke(app, ["check", "--spec", ..., "--source", ...])
assert result.exit_code == 0
```

## Test Types

**Unit tests (`test_fastapi_parser.py`):**
- Test individual endpoint extraction behaviors (query params, path params, request body, response model)
- Each test re-parses the fixture app and selects one endpoint by path+method
- Pattern: parse → filter → assert one property

**Integration tests (`test_comparator.py`, `test_cli.py`):**
- `test_comparator.py`: exercises the full parse → load_spec → normalize_spec → compare pipeline
- `test_cli.py`: exercises the full CLI surface including file I/O and exit codes
- Both use the same fixture files as unit tests

**No E2E tests** (no network calls, no subprocess-level CLI testing beyond CliRunner).

## Assertions

- Simple equality: `assert ep.summary == "List all users"`
- Set membership (for unordered collections): `assert "skip" in param_names`
- Boolean checks: `assert p.required is False`
- Numeric comparisons: `assert report.drift_score > 0`
- Dict structure: `assert "$schema" in d`
- Exit code: `assert result.exit_code == 0` / `== 1`

Inline failure messages are used sparingly, only when ambiguity is likely:
```python
assert p.required is False, f"Query param '{p.name}' should not be required (has default)"
```

## Coverage

**No enforced coverage threshold** in `pyproject.toml` or CI config (none found).

`pytest-cov` is installed but coverage reporting is opt-in via CLI flag.

## Coverage Gaps (Observed)

- **`src/docguard/core/spec_loader.py`** — not directly tested; exercised only indirectly
  through comparator tests.
- **`src/docguard/config.py`** — no dedicated test file; exercised partially through CLI tests.
- **`src/docguard/fixers/llm_fixer.py`** — no tests at all; this is the LLM-powered fix path.
- **`src/docguard/formatters/text.py`** and **`src/docguard/formatters/github.py`** — no
  dedicated formatter unit tests; `github.py` is partially exercised via `test_github_format`
  in `test_cli.py`.
- **`src/docguard/parsers/registry.py`** — no direct test; auto-detection logic is untested
  in isolation.
- **Error paths** — no tests for malformed YAML specs, unparseable Python files, or missing
  required CLI arguments (beyond the `test_creates_config` smoke test).
- **Parser `can_handle` logic** — only two cases tested (`requirements.txt` with and without
  FastAPI); `pyproject.toml`-based detection not tested.
