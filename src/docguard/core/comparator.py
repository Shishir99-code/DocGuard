"""Comparator engine -- diffs inferred code endpoints against spec endpoints."""

from __future__ import annotations

from docguard.core.models import (
    DiffType,
    DriftReport,
    DriftReportMetadata,
    DriftSummary,
    EndpointResult,
    EndpointStatus,
    FieldDiff,
    InferredEndpoint,
    InferredField,
    Severity,
)


def compare(
    code_endpoints: list[InferredEndpoint],
    spec_endpoints: list[InferredEndpoint],
    metadata: DriftReportMetadata | None = None,
) -> DriftReport:
    """Compare code-inferred endpoints against spec endpoints and produce a DriftReport."""
    code_map: dict[str, InferredEndpoint] = {ep.key: ep for ep in code_endpoints}
    spec_map: dict[str, InferredEndpoint] = {ep.key: ep for ep in spec_endpoints}

    all_keys = set(code_map.keys()) | set(spec_map.keys())
    results: list[EndpointResult] = []

    summary = DriftSummary(
        total_endpoints_in_code=len(code_endpoints),
        total_endpoints_in_spec=len(spec_endpoints),
    )

    for key in sorted(all_keys):
        code_ep = code_map.get(key)
        spec_ep = spec_map.get(key)

        if code_ep and not spec_ep:
            results.append(_missing_in_spec(code_ep))
            summary.missing_in_spec += 1
        elif spec_ep and not code_ep:
            results.append(_missing_in_code(spec_ep))
            summary.missing_in_code += 1
        elif code_ep and spec_ep:
            result = _compare_endpoints(code_ep, spec_ep)
            results.append(result)
            if result.status == EndpointStatus.SYNCED:
                summary.synced += 1
            else:
                summary.drifted += 1

    report = DriftReport(
        metadata=metadata or DriftReportMetadata(),
        summary=summary,
        endpoints=results,
    )
    report.drift_score = report.calculate_drift_score()
    return report


def _missing_in_spec(code_ep: InferredEndpoint) -> EndpointResult:
    return EndpointResult(
        path=code_ep.path,
        method=code_ep.method,
        status=EndpointStatus.MISSING_IN_SPEC,
        source_location={"file": code_ep.source_file, "line": code_ep.source_line},
        spec_location=None,
    )


def _missing_in_code(spec_ep: InferredEndpoint) -> EndpointResult:
    json_path = f"#/paths/{spec_ep.path.replace('/', '~1')}/{spec_ep.method.lower()}"
    return EndpointResult(
        path=spec_ep.path,
        method=spec_ep.method,
        status=EndpointStatus.MISSING_IN_CODE,
        source_location=None,
        spec_location={"json_path": json_path},
    )


def _compare_endpoints(code_ep: InferredEndpoint, spec_ep: InferredEndpoint) -> EndpointResult:
    """Deep-compare two matching endpoints and collect all diffs."""
    diffs: list[FieldDiff] = []

    if code_ep.response_status != spec_ep.response_status:
        diffs.append(FieldDiff(
            type=DiffType.STATUS_CODE_MISMATCH,
            location="response.status_code",
            code_value={"status_code": code_ep.response_status},
            spec_value={"status_code": spec_ep.response_status},
            severity=Severity.ERROR,
            message=(
                f"Status code is {code_ep.response_status} in code "
                f"but {spec_ep.response_status} in spec."
            ),
        ))

    # Compare response body fields
    diffs.extend(_compare_fields(
        code_ep.response_fields or [],
        spec_ep.response_fields or [],
        "response.body",
    ))

    # Compare request body fields
    diffs.extend(_compare_fields(
        code_ep.request_body or [],
        spec_ep.request_body or [],
        "request.body",
    ))

    # Compare path params
    diffs.extend(_compare_params(
        code_ep.path_params,
        spec_ep.path_params,
        "path_param",
    ))

    # Compare query params
    diffs.extend(_compare_params(
        code_ep.query_params,
        spec_ep.query_params,
        "query_param",
    ))

    json_path = f"#/paths/{spec_ep.path.replace('/', '~1')}/{spec_ep.method.lower()}"
    status = EndpointStatus.DRIFT if diffs else EndpointStatus.SYNCED

    return EndpointResult(
        path=code_ep.path,
        method=code_ep.method,
        status=status,
        source_location={"file": code_ep.source_file, "line": code_ep.source_line},
        spec_location={"json_path": json_path},
        diffs=diffs,
    )


def _compare_fields(
    code_fields: list[InferredField],
    spec_fields: list[InferredField],
    prefix: str,
) -> list[FieldDiff]:
    """Recursively compare two lists of fields."""
    diffs: list[FieldDiff] = []
    code_map = {f.name: f for f in code_fields}
    spec_map = {f.name: f for f in spec_fields}

    for name, code_f in code_map.items():
        location = f"{prefix}.{name}"
        if name not in spec_map:
            severity = Severity.ERROR if code_f.required else Severity.WARNING
            diffs.append(FieldDiff(
                type=DiffType.FIELD_ADDED_IN_CODE,
                location=location,
                code_value={"type": code_f.type, "required": code_f.required},
                spec_value=None,
                severity=severity,
                message=f"Field '{name}' ({code_f.type}) exists in code but is missing from the spec.",
            ))
            continue

        spec_f = spec_map[name]

        if code_f.type != spec_f.type:
            diffs.append(FieldDiff(
                type=DiffType.TYPE_MISMATCH,
                location=location,
                code_value={"type": code_f.type},
                spec_value={"type": spec_f.type},
                severity=Severity.ERROR,
                message=f"Field '{name}' is '{code_f.type}' in code but '{spec_f.type}' in spec.",
            ))

        if code_f.required != spec_f.required:
            diffs.append(FieldDiff(
                type=DiffType.REQUIRED_MISMATCH,
                location=location,
                code_value={"required": code_f.required},
                spec_value={"required": spec_f.required},
                severity=Severity.WARNING,
                message=f"Field '{name}' required={code_f.required} in code but required={spec_f.required} in spec.",
            ))

        # Recurse into nested fields
        if code_f.nested or spec_f.nested:
            diffs.extend(_compare_fields(
                code_f.nested or [],
                spec_f.nested or [],
                location,
            ))

    for name in spec_map:
        if name not in code_map:
            location = f"{prefix}.{name}"
            diffs.append(FieldDiff(
                type=DiffType.FIELD_REMOVED_IN_CODE,
                location=location,
                code_value=None,
                spec_value={"type": spec_map[name].type, "required": spec_map[name].required},
                severity=Severity.WARNING,
                message=f"Field '{name}' exists in spec but is missing from the code.",
            ))

    return diffs


def _compare_params(
    code_params: list[InferredField],
    spec_params: list[InferredField],
    prefix: str,
) -> list[FieldDiff]:
    """Compare parameter lists (path or query)."""
    diffs: list[FieldDiff] = []
    code_map = {p.name: p for p in code_params}
    spec_map = {p.name: p for p in spec_params}

    for name, code_p in code_map.items():
        location = f"{prefix}.{name}"
        if name not in spec_map:
            diffs.append(FieldDiff(
                type=DiffType.PARAM_ADDED_IN_CODE,
                location=location,
                code_value={"type": code_p.type, "required": code_p.required},
                spec_value=None,
                severity=Severity.ERROR,
                message=f"Parameter '{name}' ({code_p.type}) exists in code but not in spec.",
            ))
            continue

        spec_p = spec_map[name]
        if code_p.type != spec_p.type:
            diffs.append(FieldDiff(
                type=DiffType.PARAM_TYPE_MISMATCH,
                location=location,
                code_value={"type": code_p.type},
                spec_value={"type": spec_p.type},
                severity=Severity.ERROR,
                message=f"Parameter '{name}' is '{code_p.type}' in code but '{spec_p.type}' in spec.",
            ))

    for name in spec_map:
        if name not in code_map:
            location = f"{prefix}.{name}"
            diffs.append(FieldDiff(
                type=DiffType.PARAM_REMOVED_IN_CODE,
                location=location,
                code_value=None,
                spec_value={"type": spec_map[name].type, "required": spec_map[name].required},
                severity=Severity.WARNING,
                message=f"Parameter '{name}' exists in spec but not in code.",
            ))

    return diffs
