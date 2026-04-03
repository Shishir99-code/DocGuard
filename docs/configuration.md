# Configuration Reference

DocGuard is configured via a `.docguard.yaml` file in your project root. Create one with `docguard init` or write it manually.

## Full Schema

```yaml
# .docguard.yaml -- DocGuard configuration
# https://docs.docguard.dev/configuration

# Path to the OpenAPI spec file (YAML or JSON).
spec: openapi.yaml

# Root directory containing API source code.
source: "."

# Framework parser to use. "auto" detects based on project dependencies.
# Options: auto, fastapi
framework: auto

# Glob patterns for files/directories to exclude from scanning.
ignore:
  - "*/tests/*"
  - "*/migrations/*"
  - "*/conftest.py"

# Settings for the `docguard check` command.
check:
  # When to fail the build.
  #   any         -- fail on any drift, missing endpoints, or type mismatches
  #   drift-only  -- only fail when existing endpoints have field/type diffs
  #   missing     -- only fail when endpoints are missing from the spec
  fail_on: any

  # Minimum severity that triggers a failure.
  #   error   -- only errors fail the build
  #   warning -- errors and warnings fail the build
  #   info    -- everything fails the build
  severity_threshold: error

# Settings for the `docguard fix` command (LLM-powered).
fix:
  # LLM model identifier. Must be supported by the OpenAI API.
  model: gpt-4o-mini

  # Name of the environment variable containing the API key.
  api_key_env: OPENAI_API_KEY

# Output settings.
output:
  # Default output format for `docguard check`.
  #   text   -- human-readable Rich terminal output
  #   json   -- machine-readable JSON drift report
  #   github -- GitHub Actions workflow commands (::error / ::warning)
  format: text

  # If set, `docguard check` writes the JSON report to this path in addition
  # to the primary output format.
  # report_path: drift-report.json
```

## Option Details

### `spec`

Path to the OpenAPI spec file, relative to the project root. DocGuard supports both YAML (`.yaml`, `.yml`) and JSON (`.json`) formats.

If not specified, DocGuard auto-detects by searching for common filenames in this order:

1. `openapi.yaml` / `openapi.yml` / `openapi.json`
2. `swagger.yaml` / `swagger.yml` / `swagger.json`
3. `api.yaml` / `api.yml` / `api.json`

### `source`

Root directory to scan for API source files. DocGuard recursively finds all `.py` files under this directory (for the FastAPI parser).

### `framework`

Which framework parser to use. Set to `auto` (the default) to let DocGuard detect the framework from your project's dependency files (`requirements.txt`, `pyproject.toml`, etc.).

Available parsers:

| Value | Framework | Status |
|-------|-----------|--------|
| `auto` | Auto-detect | Stable |
| `fastapi` | Python / FastAPI | Stable |

### `ignore`

A list of glob patterns. Any source file whose path (relative to `source`) matches a pattern is excluded from scanning. Useful for skipping test files, migrations, and generated code.

### `check.fail_on`

Controls when `docguard check` exits with code `1`:

| Value | Fails when |
|-------|-----------|
| `any` | Any drift, missing endpoint, or type mismatch |
| `drift-only` | Only when existing endpoints have field/type differences |
| `missing` | Only when endpoints exist in code but not in the spec |

### `check.severity_threshold`

The minimum severity level that triggers a build failure. Diffs below this threshold are reported but don't cause a non-zero exit.

| Level | Includes |
|-------|----------|
| `error` | Type mismatches, missing required fields, missing endpoints |
| `warning` | Above + optional field differences, required/optional mismatches |
| `info` | Above + tag changes, summary differences |

### `fix.model`

The LLM model to call via the OpenAI-compatible API. Default is `gpt-4o-mini` for cost efficiency.

### `fix.api_key_env`

The name of the environment variable containing the LLM API key. This avoids hardcoding secrets in config files.

### `output.format`

The default output format when running `docguard check`. Can be overridden with `--format` on the command line.

### `output.report_path`

If set, `docguard check` writes a JSON drift report to this file path in addition to the primary output. Useful for archiving reports or feeding them into dashboards.

## Config Resolution

DocGuard searches for `.docguard.yaml` starting from the current working directory, then walking up to parent directories (up to 10 levels). The first file found is used. CLI flags always override config file values.
