"""Canonical data models for DocGuard drift detection."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


class EndpointStatus(str, enum.Enum):
    SYNCED = "synced"
    DRIFT = "drift"
    MISSING_IN_SPEC = "missing_in_spec"
    MISSING_IN_CODE = "missing_in_code"


class DiffType(str, enum.Enum):
    FIELD_ADDED_IN_CODE = "field_added_in_code"
    FIELD_REMOVED_IN_CODE = "field_removed_in_code"
    TYPE_MISMATCH = "type_mismatch"
    REQUIRED_MISMATCH = "required_mismatch"
    STATUS_CODE_MISMATCH = "status_code_mismatch"
    PARAM_ADDED_IN_CODE = "param_added_in_code"
    PARAM_REMOVED_IN_CODE = "param_removed_in_code"
    PARAM_TYPE_MISMATCH = "param_type_mismatch"


class Severity(str, enum.Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class HttpMethod(str, enum.Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"
    OPTIONS = "OPTIONS"
    HEAD = "HEAD"


@dataclass
class InferredField:
    """A single field in a request/response body or parameter."""

    name: str
    type: str  # JSON Schema type: "string", "integer", "array", etc.
    required: bool = True
    description: str | None = None
    nested: list[InferredField] | None = None
    default: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "name": self.name,
            "type": self.type,
            "required": self.required,
        }
        if self.description:
            result["description"] = self.description
        if self.default is not None:
            result["default"] = self.default
        if self.nested:
            result["nested"] = [f.to_dict() for f in self.nested]
        return result


@dataclass
class InferredEndpoint:
    """A single API endpoint inferred from source code or an OpenAPI spec."""

    path: str
    method: str
    summary: str | None = None
    request_body: list[InferredField] | None = None
    response_fields: list[InferredField] | None = None
    response_status: int = 200
    query_params: list[InferredField] = field(default_factory=list)
    path_params: list[InferredField] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    source_file: str = ""
    source_line: int = 0

    @property
    def key(self) -> str:
        """Unique identifier for matching endpoints: 'METHOD /path'."""
        return f"{self.method.upper()} {self.path}"


@dataclass
class FieldDiff:
    """A single difference between the code and spec for one endpoint."""

    type: DiffType
    location: str  # e.g. "response.body.email_verified"
    code_value: dict[str, Any] | None = None
    spec_value: dict[str, Any] | None = None
    severity: Severity = Severity.ERROR
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            "location": self.location,
            "code_value": self.code_value,
            "spec_value": self.spec_value,
            "severity": self.severity.value,
            "message": self.message,
        }


@dataclass
class EndpointResult:
    """Comparison result for a single endpoint."""

    path: str
    method: str
    status: EndpointStatus
    source_location: dict[str, Any] | None = None  # {"file": ..., "line": ...}
    spec_location: dict[str, Any] | None = None  # {"json_path": ...}
    diffs: list[FieldDiff] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "method": self.method,
            "status": self.status.value,
            "source_location": self.source_location,
            "spec_location": self.spec_location,
            "diffs": [d.to_dict() for d in self.diffs],
        }


@dataclass
class DriftSummary:
    total_endpoints_in_code: int = 0
    total_endpoints_in_spec: int = 0
    synced: int = 0
    drifted: int = 0
    missing_in_spec: int = 0
    missing_in_code: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_endpoints_in_code": self.total_endpoints_in_code,
            "total_endpoints_in_spec": self.total_endpoints_in_spec,
            "synced": self.synced,
            "drifted": self.drifted,
            "missing_in_spec": self.missing_in_spec,
            "missing_in_code": self.missing_in_code,
        }


@dataclass
class DriftReportMetadata:
    repository: str = ""
    commit_sha: str = ""
    branch: str = ""
    timestamp: str = ""
    spec_path: str = ""
    framework_detected: str = ""
    scan_duration_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "repository": self.repository,
            "commit_sha": self.commit_sha,
            "branch": self.branch,
            "timestamp": self.timestamp or datetime.now(UTC).isoformat(),
            "spec_path": self.spec_path,
            "framework_detected": self.framework_detected,
            "scan_duration_ms": self.scan_duration_ms,
        }


@dataclass
class DriftReport:
    """The complete drift report -- single data contract for CLI, CI, and dashboard."""

    version: str = "1.0.0"
    metadata: DriftReportMetadata = field(default_factory=DriftReportMetadata)
    drift_score: float = 0.0
    summary: DriftSummary = field(default_factory=DriftSummary)
    endpoints: list[EndpointResult] = field(default_factory=list)

    def calculate_drift_score(self) -> float:
        total = (
            self.summary.synced
            + self.summary.drifted
            + self.summary.missing_in_spec
            + self.summary.missing_in_code
        )
        if total == 0:
            return 0.0
        # Drifted and missing_in_spec carry full weight (active integration risk).
        # Missing_in_code carries half weight (stale docs, less urgent).
        weighted = (
            self.summary.drifted * 1.0
            + self.summary.missing_in_spec * 1.0
            + self.summary.missing_in_code * 0.5
        )
        return round(weighted / total, 4)

    def to_dict(self) -> dict[str, Any]:
        return {
            "$schema": "https://docguard.dev/schemas/drift-report-v1.json",
            "version": self.version,
            "metadata": self.metadata.to_dict(),
            "drift_score": self.drift_score,
            "summary": self.summary.to_dict(),
            "endpoints": [e.to_dict() for e in self.endpoints],
        }
