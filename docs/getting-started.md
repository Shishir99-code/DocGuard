# Getting Started

This guide takes you from zero to a passing `docguard check` in under five minutes.

## Prerequisites

- Python 3.11 or later
- pip
- A FastAPI project with an OpenAPI spec file (`openapi.yaml` or `swagger.json`)

## Installation

Clone the repository and install it in editable mode:

```bash
git clone https://github.com/Shishir99-code/DocGuard.git
cd DocGuard
pip install -e .
```

To also enable LLM-powered auto-fix:

```bash
pip install -e '.[llm]'
```

## Step 1: Initialize

Navigate to your project root and run:

```bash
docguard init
```

This creates a `.docguard.yaml` configuration file with sensible defaults:

```yaml
spec: openapi.yaml
source: "."
framework: auto
ignore:
  - "*/tests/*"
  - "*/migrations/*"
check:
  fail_on: any
  severity_threshold: error
output:
  format: text
```

## Step 2: Run Your First Check

```bash
docguard check
```

If your code and spec are in sync, you'll see:

```
╭──────────── DocGuard Drift Report ────────────╮
│ Drift Score: 0.0%                             │
╰───────────────────────────────────────────────╯
        Summary
  Endpoints in code    5
  Endpoints in spec    5
  Synced               5
  Drifted              0
  Missing in spec      0
  Missing in code      0

All endpoints are in sync.
```

## Step 3: Introduce Drift

To see DocGuard in action, add a new field to a Pydantic response model in your FastAPI code **without** updating the OpenAPI spec.

For example, add `email_verified: bool` to your `UserResponse` model:

```python
class UserResponse(BaseModel):
    id: int
    name: str
    email: str
    email_verified: bool  # New field -- not yet in the spec
```

Now run the check again:

```bash
docguard check
```

DocGuard catches it:

```
╭──────────── DocGuard Drift Report ────────────╮
│ Drift Score: 20.0%                            │
╰───────────────────────────────────────────────╯

  GET /users/{user_id}  DRIFT  src/routes/users.py:23
    ERROR  Field 'email_verified' (boolean) exists in code but is missing from the spec.

1 issue(s) found.
```

The CLI exits with code `1`, which means it will fail your CI build.

## Step 4: Auto-Fix (Optional)

If you have an OpenAI API key, DocGuard can suggest the exact spec changes:

```bash
export OPENAI_API_KEY="sk-..."
docguard fix --spec openapi.yaml
```

This prints the corrected YAML. To apply it directly:

```bash
docguard fix --spec openapi.yaml --apply
```

## Next Steps

- [Set up GitHub Actions](integrations/github-actions.md) to catch drift on every pull request
- [Configure a pre-commit hook](integrations/pre-commit.md) for local development
- Read the [CLI Reference](cli-reference.md) for all available options
- See the [Configuration Reference](configuration.md) for advanced settings
