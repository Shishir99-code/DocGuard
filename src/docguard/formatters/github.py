"""GitHub Actions annotation formatter.

Outputs ``::error`` and ``::warning`` workflow commands so that drift issues
appear as inline annotations on the pull request's "Files changed" tab.
"""

from __future__ import annotations

from docguard.core.models import DriftReport, EndpointStatus, Severity


def render(report: DriftReport) -> str:
    """Return newline-separated GitHub Actions workflow commands."""
    lines: list[str] = []

    for ep in report.endpoints:
        if ep.status == EndpointStatus.SYNCED:
            continue

        file = ep.source_location.get("file", "") if ep.source_location else ""
        line = ep.source_location.get("line", 1) if ep.source_location else 1

        if ep.status == EndpointStatus.MISSING_IN_SPEC:
            lines.append(
                f"::error file={file},line={line}::"
                f"Endpoint {ep.method} {ep.path} exists in code "
                "but is missing from the OpenAPI spec."
            )
            continue

        if ep.status == EndpointStatus.MISSING_IN_CODE:
            lines.append(
                f"::warning ::"
                f"Endpoint {ep.method} {ep.path} exists in spec but has no matching code."
            )
            continue

        for diff in ep.diffs:
            level = "error" if diff.severity == Severity.ERROR else "warning"
            lines.append(f"::{level} file={file},line={line}::{diff.message}")

    return "\n".join(lines)
