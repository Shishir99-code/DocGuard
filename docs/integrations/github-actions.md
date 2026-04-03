# GitHub Actions Integration

DocGuard provides a GitHub Action that validates your code against your OpenAPI spec on every pull request. Drift issues appear as inline annotations on the "Files changed" tab.

## Quick Setup

Add this workflow to your repository:

```yaml
# .github/workflows/docguard.yml
name: DocGuard Drift Check
on: [pull_request]

jobs:
  drift-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: docguard/action@v1
        with:
          spec: openapi.yaml
          fail-on: any
```

That's it. The action installs DocGuard, runs the check, and posts inline annotations for any drift detected.

## Action Inputs

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `spec` | No | `openapi.yaml` | Path to the OpenAPI spec file |
| `source` | No | `.` | Source directory to scan |
| `framework` | No | `auto` | Force a specific framework parser |
| `fail-on` | No | `any` | Failure threshold: `any`, `drift-only`, `missing` |
| `python-version` | No | `3.11` | Python version to use |

## Action Outputs

| Output | Description |
|--------|-------------|
| `drift-score` | The drift score (0.0 to 1.0) |
| `report` | Path to the generated JSON drift report |

## Using Outputs

You can use the action outputs in subsequent steps:

```yaml
jobs:
  drift-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: docguard/action@v1
        id: docguard
        with:
          spec: openapi.yaml

      - name: Comment on PR
        if: failure()
        uses: actions/github-script@v7
        with:
          script: |
            github.rest.issues.createComment({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: context.issue.number,
              body: `DocGuard detected API drift (score: ${{ steps.docguard.outputs.drift-score }}). Please update the OpenAPI spec.`
            })
```

## Manual Setup (Without the Action)

If you prefer not to use the composite action, install DocGuard directly:

```yaml
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
      - run: pip install docguard
      - run: docguard check --spec openapi.yaml --format github --fail-on any
```

The `--format github` flag outputs `::error` and `::warning` workflow commands, which GitHub renders as inline annotations on the pull request.

## Caching

To speed up repeated runs, cache the pip installation:

```yaml
steps:
  - uses: actions/checkout@v4
  - uses: actions/setup-python@v5
    with:
      python-version: "3.11"
      cache: pip
  - run: pip install docguard
  - run: docguard check --format github
```

## Saving the Drift Report

To archive the drift report as a build artifact:

```yaml
steps:
  - uses: actions/checkout@v4
  - uses: actions/setup-python@v5
    with:
      python-version: "3.11"
  - run: pip install docguard
  - run: docguard report --output drift-report.json
  - uses: actions/upload-artifact@v4
    with:
      name: drift-report
      path: drift-report.json
  - run: docguard check --format github
```
