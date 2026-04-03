"""LLM-powered auto-fixer that suggests YAML patches to resolve spec drift."""

from __future__ import annotations

import json
import os

from docguard.core.models import DriftReport


def build_fix_prompt(report: DriftReport, spec_content: str) -> str:
    """Build the LLM prompt from a drift report and the current spec YAML."""
    drifted = [ep for ep in report.endpoints if ep.diffs or ep.status.value == "missing_in_spec"]
    issues = json.dumps([ep.to_dict() for ep in drifted], indent=2)

    return f"""\
You are an OpenAPI specification expert. The following drift issues were detected
between the source code and the OpenAPI spec below.

DRIFT ISSUES:
{issues}

CURRENT SPEC:
```yaml
{spec_content}
```

Produce the updated OpenAPI YAML that resolves every drift issue above.
Only output the YAML -- no explanations, no markdown fences."""


def suggest_fix(
    report: DriftReport,
    spec_content: str,
    model: str = "gpt-4o-mini",
    api_key_env: str = "OPENAI_API_KEY",
) -> str:
    """Call an LLM to generate the fixed spec YAML.

    Returns the raw YAML string from the model.  Raises ``RuntimeError``
    if the ``openai`` package is not installed or the key is missing.
    """
    api_key = os.environ.get(api_key_env)
    if not api_key:
        raise RuntimeError(
            f"Environment variable '{api_key_env}' is not set. "
            f"Set it to your OpenAI API key, or use --model to choose a different provider."
        )

    try:
        import openai  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError(
            "The 'openai' package is required for auto-fix. "
            "Install it with: pip install 'docguard[llm]'"
        ) from exc

    client = openai.OpenAI(api_key=api_key)
    prompt = build_fix_prompt(report, spec_content)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are an OpenAPI specification expert."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.0,
    )

    return response.choices[0].message.content or ""
