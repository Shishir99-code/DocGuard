# External Integrations
_Last updated: 2026-06-02_

## CLI Entry Points

DocGuard exposes four subcommands via the `docguard` script (entry point: `docguard.cli:app` in `src/docguard/cli.py`):

| Command | Purpose |
|---|---|
| `docguard init` | Write a `.docguard.yaml` config file to the current directory |
| `docguard check` | Run drift detection; exits non-zero on detected drift |
| `docguard report` | Generate full drift report as JSON (stdout or file) |
| `docguard fix` | Use an LLM to suggest spec updates that resolve drift |
| `docguard version` | Print installed version |

**Typical invocation:**
```bash
docguard check --spec openapi.yaml --source . --format github
docguard report --spec openapi.yaml --output /tmp/drift-report.json
docguard fix --spec openapi.yaml --apply
```

## Configuration File

**Format:** YAML
**Filename:** `.docguard.yaml` (searched from CWD up to 10 parent directories)
**Schema:** Validated by `DocGuardConfig` Pydantic model in `src/docguard/config.py`

```yaml
spec: openapi.yaml
source: "."
framework: auto          # auto | fastapi
ignore:
  - "*/tests/*"
  - "*/migrations/*"
check:
  fail_on: any           # any | drift-only | missing
  severity_threshold: error
fix:
  model: gpt-4o-mini
  api_key_env: OPENAI_API_KEY
output:
  format: text           # text | json | github
```

## OpenAPI / Swagger Spec Files

**Supported formats:** YAML (`.yaml`, `.yml`) and JSON (`.json`)

**Auto-detection candidates** (in priority order, searched in project root):
1. `openapi.yaml` / `openapi.yml` / `openapi.json`
2. `swagger.yaml` / `swagger.yml` / `swagger.json`
3. `api.yaml` / `api.yml` / `api.json`

Logic in `src/docguard/core/spec_loader.py` → `find_spec()`.

**Spec parsing:**
- `load_spec()` reads YAML via `pyyaml.safe_load` or JSON via `json.loads`
- `normalize_spec()` converts raw spec dict to `list[InferredEndpoint]`
- Supports OpenAPI 3.x `$ref` resolution for `#/components/schemas/` local references
- Handles OAS 3.1 `anyOf` nullable fields (unwraps `{type: null}` variants)
- Reads `paths`, `parameters`, `requestBody`, `responses`, and `components.schemas`

## Framework Parsers

**Parser registry:** `src/docguard/parsers/registry.py`
**Base class:** `src/docguard/parsers/base.py`

Currently one parser is implemented:

**FastAPI Parser** (`src/docguard/parsers/fastapi_parser.py`):
- Analyzes Python source files via `ast` (no import/execution of user code)
- Detects `@app.get(...)`, `@router.post(...)`, etc. decorators
- Extracts Pydantic `BaseModel` subclasses as request/response schemas
- Infers path params, query params, request body, response fields
- Auto-detection heuristic: scans for `fastapi` import in source files

**Framework selection:**
- `auto` (default): calls `detect_framework()` which scans source files
- Explicit: `--framework fastapi` or `framework: fastapi` in config

**Extension point:** New parsers can be added by subclassing `BaseParser` and registering in `src/docguard/parsers/registry.py`. The docs directory `docs/extending/` exists, suggesting a plugin/extension system is planned or documented.

## Output Formatters

Three output formatters in `src/docguard/formatters/`:

| Module | Format | Use case |
|---|---|---|
| `text.py` | Human-readable terminal output (Rich) | Default; local dev |
| `json_fmt.py` | Structured JSON | Machine consumption, reporting |
| `github.py` | GitHub Actions workflow commands | CI annotation in PR checks |

The `github` format uses raw `print()` (not Rich) to emit `::error` / `::warning` annotations consumed by GitHub Actions.

## GitHub Actions Integration

**Composite action defined in:** `action.yml`

**Inputs:**

| Input | Default | Description |
|---|---|---|
| `spec` | `openapi.yaml` | Path to OpenAPI spec |
| `source` | `.` | Source directory to scan |
| `framework` | `auto` | Force specific parser |
| `fail-on` | `any` | Failure threshold: `any`, `drift-only`, `missing` |
| `python-version` | `3.11` | Python version to install |

**Outputs:**

| Output | Description |
|---|---|
| `drift-score` | Float 0.0–1.0 (0 = synced, 1 = fully drifted) |
| `report` | Path to generated JSON drift report file |

**Action steps:**
1. `actions/setup-python@v5` — install Python
2. `pip install git+https://github.com/Shishir99-code/DocGuard.git` — install DocGuard
3. Run `docguard report` → write JSON to `$RUNNER_TEMP/docguard-report.json`
4. Extract `drift_score` from JSON via inline Python
5. Run `docguard check --format github` → emits GitHub annotations

**Usage in a workflow:**
```yaml
- uses: Shishir99-code/DocGuard@main
  with:
    spec: openapi.yaml
    fail-on: any
```

## Pre-commit Integration

A pre-commit hook configuration is documented in `docs/integrations/pre-commit.md`. The `pre-commit` package is included in dev dependencies (`>=3.7`), indicating hooks are configured for local development. No `.pre-commit-config.yaml` was found at repo root (may be user-side only).

## LLM / OpenAI Integration

**Module:** `src/docguard/fixers/llm_fixer.py`

**Provider:** OpenAI (via `openai>=1.0` — optional `[llm]` extra)

**Default model:** `gpt-4o-mini` (configurable via `fix.model` in `.docguard.yaml` or `--model` flag)

**API key:** Read from environment variable named in `fix.api_key_env` (default: `OPENAI_API_KEY`)

**How it works:**
1. Builds a prompt containing drift report JSON + current spec YAML
2. Calls `client.chat.completions.create` with `temperature=0.0`
3. Returns raw YAML string from model response
4. Caller either prints it (dry-run) or writes it back to the spec file (`--apply`)

**Error handling:**
- Missing `openai` package raises `RuntimeError` with install instructions
- Missing API key env var raises `RuntimeError` with guidance

## Git Integration

**Module:** `cli.py` → `_git_metadata()`

DocGuard reads git metadata (commit SHA and branch name) via subprocess calls to `git rev-parse` to annotate drift reports. Failures are silently ignored (returns empty strings). No git library dependency — uses stdlib `subprocess`.

## File System Patterns

- All file path operations use `pathlib.Path`
- Config search traverses up to 10 parent directories from CWD
- Source file collection uses `Path.rglob("*.py")` with `fnmatch` glob-based ignore patterns
- Report output can be written to a file path via `--output` flag on `docguard report`

## Environment Variables

| Variable | Purpose | Required |
|---|---|---|
| `OPENAI_API_KEY` | OpenAI API key for `docguard fix` | Only for `fix` command |
| Custom (via `fix.api_key_env`) | Override API key env var name | No |

No other environment variables are read by the core tool.

---

_Integration audit: 2026-06-02_
