# DocGuard

**Your API spec is a lie. DocGuard fixes that.**

[![License: BUSL-1.1](https://img.shields.io/badge/license-BUSL--1.1-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

---

DocGuard is a CLI tool and CI/CD guardrail that detects **documentation drift** between your API source code and your OpenAPI specification. If the code changes but the spec doesn't, the build fails.

## The Problem

In high-velocity teams, OpenAPI specs and production code slowly diverge until the documentation becomes fiction. Frontend and mobile teams waste hours building against endpoints that don't exist or have different response schemas than documented.

DocGuard turns your spec into an **active test case** instead of a passive artifact.

<!-- TODO: Replace with actual terminal recording -->
<!-- ![DocGuard demo](docs/assets/terminal-demo.gif) -->

## Quick Start

Clone the repository and install locally:

```bash
git clone https://github.com/Shishir99-code/DocGuard.git
cd DocGuard
pip install -e .
```

Initialize a config in your project:

```bash
docguard init
```

Run a drift check:

```bash
docguard check --spec openapi.yaml --source src/
```

If the code and spec are in sync, you get a clean exit. If they've diverged, you get a detailed drift report and a non-zero exit code.

## What It Catches

| Issue | Example | Severity |
|-------|---------|----------|
| **Missing endpoint in spec** | New route added to code, not documented | Error |
| **Type mismatch** | Field is `string` in code but `integer` in spec | Error |
| **Missing field in spec** | New response field added to code | Error/Warning |
| **Dead documentation** | Endpoint in spec but removed from code | Warning |
| **Required/optional mismatch** | Field required in code but optional in spec | Warning |

## How It Works

DocGuard uses **static AST analysis** to infer your API's shape directly from decorators and type annotations -- no runtime imports, no dependency on your project's environment.

```
Source Code ──► AST Parser ──► Canonical Model ──► Comparator ──► Drift Report
                                                       ▲
OpenAPI Spec ──► Spec Loader ──► Canonical Model ──────┘
```

**Supported frameworks:**
- Python / FastAPI (v0.1)
- Express.js (planned)
- Spring Boot (planned)

## CI/CD Integration

### GitHub Actions

Install DocGuard from the repository and run it in your workflow:

```yaml
# .github/workflows/docguard.yml
name: DocGuard
on: [pull_request]
jobs:
  drift-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install git+https://github.com/Shishir99-code/DocGuard.git
      - run: docguard check --spec openapi.yaml --format github --fail-on any
```

### Pre-commit Hook

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/Shishir99-code/DocGuard
    rev: main
    hooks:
      - id: docguard-check
        args: [--spec, openapi.yaml]
```

## Auto-Fix (LLM-Powered)

When drift is detected, DocGuard can suggest the exact YAML changes needed:

```bash
docguard fix --spec openapi.yaml          # Dry-run: prints suggested changes
docguard fix --spec openapi.yaml --apply  # Writes fixes directly
```

Requires an OpenAI API key. Install the LLM extra with:

```bash
pip install -e '.[llm]'
```

## CLI Reference

| Command | Description |
|---------|-------------|
| `docguard init` | Create a `.docguard.yaml` config file |
| `docguard check` | Run drift detection (exit 0 = clean, exit 1 = drift) |
| `docguard fix` | Suggest or apply spec updates via LLM |
| `docguard report` | Generate a full JSON drift report |
| `docguard version` | Print version info |

See the [full CLI reference](https://docs.docguard.dev/cli-reference) for all options.

## Configuration

```yaml
# .docguard.yaml
spec: openapi.yaml
source: src/
framework: auto
ignore:
  - "*/tests/*"
check:
  fail_on: any
  severity_threshold: error
output:
  format: text
```

See the [configuration reference](https://docs.docguard.dev/configuration) for all options.

## Documentation

- [Getting Started](docs/getting-started.md)
- [CLI Reference](docs/cli-reference.md)
- [Configuration](docs/configuration.md)
- [GitHub Actions Integration](docs/integrations/github-actions.md)
- [Architecture](docs/architecture.md)
- [Writing a Custom Parser](docs/extending/writing-a-parser.md)

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and guidelines.

## License

DocGuard is licensed under the [Business Source License 1.1](LICENSE). Free for open-source and small team use. See the license file for details.
