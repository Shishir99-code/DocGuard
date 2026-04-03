# Auto-Fix (LLM-Powered)

DocGuard's `fix` command uses a large language model to suggest the exact YAML changes needed to bring your OpenAPI spec in line with the source code.

## How It Works

1. DocGuard runs a normal drift check to produce a structured report
2. The drift report and the current spec YAML are combined into a prompt
3. The prompt is sent to an LLM (default: GPT-4o-mini via the OpenAI API)
4. The model returns the corrected YAML
5. In dry-run mode, the suggested YAML is printed to the terminal. With `--apply`, it overwrites the spec file.

```
Drift Report + Current Spec ──► LLM Prompt ──► OpenAI API ──► Fixed YAML
```

## Installation

The LLM feature requires the `openai` package:

```bash
pip install 'docguard[llm]'
```

## API Key Setup

Set your API key as an environment variable:

```bash
export OPENAI_API_KEY="sk-..."
```

The environment variable name is configurable in `.docguard.yaml`:

```yaml
fix:
  api_key_env: OPENAI_API_KEY
```

## Usage

### Dry-Run (Default)

Print the suggested spec without modifying any files:

```bash
docguard fix --spec openapi.yaml
```

Review the output carefully before applying.

### Apply Fixes

Write the corrected spec directly to disk:

```bash
docguard fix --spec openapi.yaml --apply
```

### Choosing a Model

```bash
docguard fix --model gpt-4o          # More capable, higher cost
docguard fix --model gpt-4o-mini     # Default -- fast and cheap
```

Or set it in the config:

```yaml
fix:
  model: gpt-4o-mini
```

## Cost Estimates

Typical token usage for a drift report with 5-10 drifted endpoints:

| Model | Input Tokens | Output Tokens | Approximate Cost |
|-------|-------------|---------------|-----------------|
| gpt-4o-mini | ~2,000 | ~1,500 | ~$0.002 |
| gpt-4o | ~2,000 | ~1,500 | ~$0.03 |

Costs vary with the size of your spec and the number of issues.

## Accuracy

The LLM does a good job for straightforward drift (adding fields, fixing types), but **always review the output before applying**. Known limitations:

- Complex nested schemas may require manual adjustment
- The model may alter formatting or field ordering
- Custom `x-` extensions may not be preserved

We recommend running `docguard check` after applying fixes to verify the spec is now in sync.

## Security

The prompt contains your OpenAPI spec and the drift report (endpoint paths, field names, types). No source code is sent to the LLM. If your spec contains sensitive information, review the prompt before running `fix` in environments where data sensitivity is a concern.
