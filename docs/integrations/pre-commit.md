# Pre-commit Hook Integration

DocGuard can run as a [pre-commit](https://pre-commit.com/) hook to catch documentation drift before code is even pushed.

## Setup

### 1. Install pre-commit

```bash
pip install pre-commit
```

### 2. Add DocGuard to your config

Add the following to your `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/Shishir99-code/DocGuard
    rev: main
    hooks:
      - id: docguard-check
        args: [--spec, openapi.yaml]
```

### 3. Install the hooks

```bash
pre-commit install
```

Now DocGuard runs automatically on every `git commit`. If drift is detected, the commit is blocked.

## Configuration

Pass any `docguard check` flags via `args`:

```yaml
repos:
  - repo: https://github.com/Shishir99-code/DocGuard
    rev: main
    hooks:
      - id: docguard-check
        args:
          - --spec
          - api/openapi.yaml
          - --source
          - src/
          - --fail-on
          - drift-only
```

## Running Manually

To run the hook manually without committing:

```bash
pre-commit run docguard-check --all-files
```

## Performance

DocGuard uses static AST analysis and typically completes in under 2 seconds for projects with up to 50 endpoints. It does not import your project's code or dependencies, so there is no startup overhead from the target application.

## Skipping the Hook

If you need to commit without running DocGuard (e.g. for a documentation-only change):

```bash
git commit --no-verify -m "docs: update README"
```

Use this sparingly -- the whole point of DocGuard is to prevent undocumented API changes.
