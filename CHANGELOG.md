# Changelog

All notable changes to DocGuard will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - Unreleased

### Added

- **FastAPI parser**: Static AST analysis to extract endpoints, request/response models, path params, query params, status codes, and tags from FastAPI source code.
- **OpenAPI spec loader**: Load and normalize OpenAPI 3.x specs from YAML or JSON into a canonical internal model.
- **Comparator engine**: Field-level diffing between code-inferred endpoints and spec-defined endpoints, with severity classification (error/warning/info).
- **Drift scoring**: Weighted drift score from 0.0 (synced) to 1.0 (fully drifted).
- **CLI commands**:
  - `docguard init` -- Create a `.docguard.yaml` config file.
  - `docguard check` -- Run drift detection with configurable failure thresholds.
  - `docguard fix` -- LLM-powered auto-fix suggestions (requires `openai` package).
  - `docguard report` -- Generate a full JSON drift report.
  - `docguard version` -- Print version info.
- **Output formatters**: Rich terminal text, JSON, and GitHub Actions annotation formats.
- **GitHub Action**: Composite action for GitHub Marketplace (`action.yml`).
- **Configuration**: `.docguard.yaml` config file with framework detection, ignore patterns, severity thresholds, and output format settings.
- **Documentation site**: MkDocs Material-based docs covering getting started, CLI reference, configuration, drift report schema, integrations, architecture, and extensibility.
