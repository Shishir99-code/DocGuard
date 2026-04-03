# CLI Reference

DocGuard provides four main commands: `init`, `check`, `fix`, and `report`.

## Global Behavior

All commands automatically look for a `.docguard.yaml` config file in the current directory or its parents. CLI flags override config file values.

## Commands

### `docguard init`

Create a `.docguard.yaml` configuration file in the current directory.

```bash
docguard init [--force]
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--force`, `-f` | bool | `false` | Overwrite an existing config file |

---

### `docguard check`

Run drift detection. This is the primary command for CI/CD pipelines.

```bash
docguard check [OPTIONS]
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--spec`, `-s` | string | auto-detect | Path to the OpenAPI spec file |
| `--source`, `-d` | string | `.` | Source directory to scan |
| `--framework`, `-f` | string | `auto` | Force a specific framework parser |
| `--format` | string | `text` | Output format: `text`, `json`, `github` |
| `--fail-on` | string | `any` | Failure threshold: `any`, `drift-only`, `missing` |
| `--ignore` | list | `[]` | Glob patterns for files to ignore |

**Output formats:**

- `text` -- Human-readable Rich terminal output with colors and tables
- `json` -- Machine-readable JSON drift report (see [Drift Report Schema](drift-report-schema.md))
- `github` -- GitHub Actions workflow commands (`::error` / `::warning`) for inline PR annotations

**Failure thresholds:**

- `any` -- Fail on any drift, missing endpoints, or type mismatches
- `drift-only` -- Only fail when existing endpoints have field/type differences
- `missing` -- Only fail when endpoints are missing from the spec

**Examples:**

```bash
# Basic check with auto-detection
docguard check

# Specify spec and source explicitly
docguard check --spec api/openapi.yaml --source src/

# JSON output for scripting
docguard check --format json

# GitHub Actions mode
docguard check --format github --fail-on any

# Ignore test files
docguard check --ignore "*/tests/*" --ignore "*/conftest.py"
```

---

### `docguard fix`

Suggest or apply spec updates using an LLM to resolve detected drift.

```bash
docguard fix [OPTIONS]
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--spec`, `-s` | string | auto-detect | Path to the OpenAPI spec file |
| `--source`, `-d` | string | `.` | Source directory to scan |
| `--framework`, `-f` | string | `auto` | Force a specific framework parser |
| `--apply` | bool | `false` | Write fixes directly to the spec file |
| `--model` | string | `gpt-4o-mini` | LLM model to use |

Requires the `openai` package: `pip install 'docguard[llm]'`

Set your API key via the environment variable configured in `.docguard.yaml` (default: `OPENAI_API_KEY`).

**Examples:**

```bash
# Dry-run: print suggested changes
docguard fix

# Apply fixes directly to the spec file
docguard fix --apply

# Use a different model
docguard fix --model gpt-4o
```

---

### `docguard report`

Generate a full drift report in JSON format.

```bash
docguard report [OPTIONS]
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--spec`, `-s` | string | auto-detect | Path to the OpenAPI spec file |
| `--source`, `-d` | string | `.` | Source directory to scan |
| `--framework`, `-f` | string | `auto` | Force a specific framework parser |
| `--output`, `-o` | string | stdout | Output file path |

**Examples:**

```bash
# Print report to stdout
docguard report

# Write report to a file
docguard report --output drift-report.json
```

---

### `docguard version`

Print the installed DocGuard version.

```bash
docguard version
```

---

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | No drift detected -- spec and code are in sync |
| `1` | Drift detected -- spec and code have diverged |
| `2` | Configuration or runtime error (missing spec file, unsupported framework, etc.) |

## Environment Variables

| Variable | Description | Used by |
|----------|-------------|---------|
| `OPENAI_API_KEY` | API key for LLM-powered auto-fix (default) | `docguard fix` |
| `DOCGUARD_SPEC_PATH` | Override spec path (alternative to `--spec`) | All commands |

The API key environment variable name is configurable via `.docguard.yaml` under `fix.api_key_env`.
