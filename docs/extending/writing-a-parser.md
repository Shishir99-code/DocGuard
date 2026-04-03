# Writing a Custom Parser

DocGuard uses the Strategy Pattern to support multiple API frameworks. Each framework has its own parser module. This guide walks through adding a new one.

## Overview

To add support for a new framework, you need to:

1. Create a new parser module in `src/docguard/parsers/`
2. Implement the `FrameworkParser` protocol
3. Register it in the parser registry
4. Write tests with a fixture project

## Step 1: Create the Parser Module

Create a new file in the parsers directory. For this example, we'll sketch an Express.js parser:

```
src/docguard/parsers/express_parser.py
```

## Step 2: Implement the Protocol

Every parser must implement three things:

```python
from pathlib import Path
from docguard.core.models import InferredEndpoint, InferredField
from docguard.parsers.base import FrameworkParser


class ExpressParser:
    """Parses Express.js source files to extract API endpoints."""

    @property
    def name(self) -> str:
        return "Express"

    def can_handle(self, project_root: Path) -> bool:
        """Detect Express by checking package.json for the 'express' dependency."""
        package_json = project_root / "package.json"
        if not package_json.exists():
            return False
        import json
        try:
            pkg = json.loads(package_json.read_text())
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
            return "express" in deps
        except (json.JSONDecodeError, OSError):
            return False

    def extract_endpoints(self, source_files: list[Path]) -> list[InferredEndpoint]:
        """Parse source files and return all discovered API endpoints."""
        endpoints: list[InferredEndpoint] = []
        for filepath in source_files:
            endpoints.extend(self._parse_file(filepath))
        return endpoints

    def _parse_file(self, filepath: Path) -> list[InferredEndpoint]:
        # Framework-specific parsing logic goes here.
        # For JavaScript/TypeScript, you might use a JS AST parser
        # or regex-based extraction as a starting point.
        ...
```

### `name` Property

Return a human-readable framework name. This is used in CLI output and the drift report's `framework_detected` field.

### `can_handle(project_root)`

This method is called during auto-detection. It should return `True` if the project at `project_root` uses this framework. Common detection strategies:

- Check dependency files (`requirements.txt`, `package.json`, `pom.xml`)
- Look for framework-specific config files
- Scan import statements in source files

Keep this method fast -- it runs for every registered parser during auto-detection.

### `extract_endpoints(source_files)`

This is where the real work happens. Given a list of source file paths, parse them and return `InferredEndpoint` objects. Each endpoint should include:

- `path` -- the URL path template (e.g. `/users/:id` normalized to `/users/{id}`)
- `method` -- HTTP method (uppercase: GET, POST, etc.)
- `request_body` -- list of `InferredField` for the request body (if any)
- `response_fields` -- list of `InferredField` for the response body (if known)
- `query_params` / `path_params` -- parameter lists
- `source_file` / `source_line` -- for traceability in the drift report

## Step 3: Register the Parser

Add your parser to the registry in `src/docguard/parsers/registry.py`:

```python
from docguard.parsers.express_parser import ExpressParser

_PARSERS: list[FrameworkParser] = [
    FastAPIParser(),
    ExpressParser(),  # Add your parser here
]
```

The order matters for auto-detection: the first parser whose `can_handle()` returns `True` is used.

## Step 4: Write Tests

Create a test fixture -- a minimal project that uses the target framework:

```
tests/fixtures/sample_express_app/
  ├── package.json
  └── routes/
      └── users.js
```

Then write tests:

```python
# tests/test_express_parser.py
from pathlib import Path
from docguard.parsers.express_parser import ExpressParser

class TestExpressParser:
    def setup_method(self):
        self.parser = ExpressParser()

    def test_can_handle(self, tmp_path):
        (tmp_path / "package.json").write_text('{"dependencies": {"express": "^4.0"}}')
        assert self.parser.can_handle(tmp_path) is True

    def test_extract_endpoints(self):
        fixtures = Path(__file__).parent / "fixtures" / "sample_express_app"
        js_files = list(fixtures.rglob("*.js"))
        endpoints = self.parser.extract_endpoints(js_files)
        assert len(endpoints) > 0
```

## Tips

- **Normalize path parameters**: Express uses `:param`, FastAPI uses `{param}`, Spring uses `{param}`. Convert to OpenAPI style (`{param}`) in your parser.
- **Handle both sync and async**: Some frameworks support both patterns.
- **Two-pass parsing works well**: First pass collects type definitions (DTOs, schemas), second pass extracts routes and resolves types.
- **Source file tracking**: Always set `source_file` and `source_line` so drift reports can point to the exact location.

## Submitting Your Parser

If you'd like to contribute your parser upstream:

1. Fork the repository
2. Create a feature branch: `git checkout -b feat/express-parser`
3. Implement the parser following this guide
4. Ensure all tests pass: `pytest tests/ -v`
5. Run the linter: `ruff check src/ tests/`
6. Open a pull request

See [CONTRIBUTING.md](../contributing) for the full contribution guidelines.
