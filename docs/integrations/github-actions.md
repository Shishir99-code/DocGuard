# GitHub Actions Integration

DocGuard can run on every pull request to catch drift before it merges. Drift issues appear as inline annotations on the "Files changed" tab when using `--format github`.

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
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install git+https://github.com/Shishir99-code/DocGuard.git
      - run: docguard check --spec openapi.yaml --format github --fail-on any
```

The `--format github` flag outputs `::error` and `::warning` workflow commands, which GitHub renders as inline annotations on the pull request.

## Using the Composite Action

If your project clones or embeds this repository, you can reference the bundled `action.yml` directly:

```yaml
jobs:
  drift-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: Shishir99-code/DocGuard@main
        with:
          spec: openapi.yaml
          fail-on: any
```

### Action Inputs

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `spec` | No | `openapi.yaml` | Path to the OpenAPI spec file |
| `source` | No | `.` | Source directory to scan |
| `framework` | No | `auto` | Force a specific framework parser |
| `fail-on` | No | `any` | Failure threshold: `any`, `drift-only`, `missing` |
| `python-version` | No | `3.11` | Python version to use |

### Action Outputs

| Output | Description |
|--------|-------------|
| `drift-score` | The drift score (0.0 to 1.0) |
| `report` | Path to the generated JSON drift report |

## Using Outputs

```yaml
jobs:
  drift-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install git+https://github.com/Shishir99-code/DocGuard.git
      - id: check
        run: |
          docguard report --output "$RUNNER_TEMP/docguard-report.json"
          echo "report=$RUNNER_TEMP/docguard-report.json" >> "$GITHUB_OUTPUT"
          SCORE=$(python -c "import json; print(json.load(open('$RUNNER_TEMP/docguard-report.json'))['drift_score'])")
          echo "drift-score=$SCORE" >> "$GITHUB_OUTPUT"
          docguard check --format github --fail-on any

      - name: Comment on PR
        if: failure()
        uses: actions/github-script@v7
        with:
          script: |
            github.rest.issues.createComment({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: context.issue.number,
              body: `DocGuard detected API drift (score: ${{ steps.check.outputs.drift-score }}). Please update the OpenAPI spec.`
            })
```

## Caching

To speed up repeated runs, cache the pip installation:

```yaml
steps:
  - uses: actions/checkout@v4
  - uses: actions/setup-python@v5
    with:
      python-version: "3.11"
      cache: pip
  - run: pip install git+https://github.com/Shishir99-code/DocGuard.git
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
  - run: pip install git+https://github.com/Shishir99-code/DocGuard.git
  - run: docguard report --output drift-report.json
  - uses: actions/upload-artifact@v4
    with:
      name: drift-report
      path: drift-report.json
  - run: docguard check --format github
```
