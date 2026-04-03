"""JSON output formatter."""

from __future__ import annotations

import json

from docguard.core.models import DriftReport


def render(report: DriftReport) -> str:
    """Serialize the drift report to a JSON string."""
    return json.dumps(report.to_dict(), indent=2)
