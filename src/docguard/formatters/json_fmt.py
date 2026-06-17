"""JSON output formatter."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from docguard.core.models import DriftReport


def render(report: DriftReport) -> str:
    """Serialize the drift report to a JSON string."""
    return json.dumps(report.to_dict(), indent=2)
