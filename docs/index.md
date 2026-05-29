# DocGuard

**Your API spec is a lie. DocGuard fixes that.**

DocGuard is a CLI tool and CI/CD guardrail that detects **documentation drift** between your API source code and your OpenAPI specification. If the code changes but the spec doesn't, the build fails.

## Why DocGuard?

In high-velocity engineering teams, OpenAPI specs and production code slowly diverge until the documentation becomes fiction. Frontend and mobile teams waste hours building against endpoints that don't exist or have different response schemas than documented.

DocGuard turns your spec from a **passive artifact** into an **active guardrail** in the development lifecycle.

## Key Features

- **Static AST Analysis** -- Infers your API shape directly from decorators and type annotations. No runtime imports, no dependency on your project's environment.
- **Framework Support** -- Built-in support for FastAPI, with Express.js and Spring Boot on the roadmap.
- **CI/CD Ready** -- Runs as a GitHub Action, pre-commit hook, or standalone CLI. Non-zero exit code on drift.
- **Detailed Drift Reports** -- JSON reports with field-level diffs, severity classification, and drift scoring.
- **LLM Auto-Fix** -- Suggests the exact YAML changes needed to bring your spec in line with the code.

## Get Started

```bash
git clone https://github.com/Shishir99-code/DocGuard.git
cd DocGuard
pip install -e .
docguard init
docguard check
```

Read the [Getting Started guide](getting-started.md) for a full walkthrough.

## Documentation

| Guide | Description |
|-------|-------------|
| [Getting Started](getting-started.md) | Install and run your first drift check in 5 minutes |
| [CLI Reference](cli-reference.md) | Every command, flag, and exit code |
| [Configuration](configuration.md) | `.docguard.yaml` reference |
| [Drift Report Schema](drift-report-schema.md) | JSON report format specification |
| [GitHub Actions](integrations/github-actions.md) | CI/CD integration guide |
| [Pre-commit Hooks](integrations/pre-commit.md) | Local development integration |
| [Auto-Fix](auto-fix.md) | LLM-powered spec correction |
| [Architecture](architecture.md) | System design and internals |
| [Writing a Parser](extending/writing-a-parser.md) | Add support for a new framework |
