"""Load and normalize an OpenAPI spec into InferredEndpoint format."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from docguard.core.models import InferredEndpoint, InferredField

_OPENAPI_TYPE_MAP: dict[str, str] = {
    "string": "string",
    "integer": "integer",
    "number": "number",
    "boolean": "boolean",
    "array": "array",
    "object": "object",
}


def load_spec(spec_path: Path) -> dict:
    """Read an OpenAPI spec from YAML or JSON and return the raw dict."""
    content = spec_path.read_text(encoding="utf-8")
    if spec_path.suffix in (".yaml", ".yml"):
        return yaml.safe_load(content)
    return json.loads(content)


def find_spec(project_root: Path) -> Path | None:
    """Auto-detect an OpenAPI spec file in *project_root*."""
    candidates = [
        "openapi.yaml",
        "openapi.yml",
        "openapi.json",
        "swagger.yaml",
        "swagger.yml",
        "swagger.json",
        "api.yaml",
        "api.yml",
        "api.json",
    ]
    for name in candidates:
        path = project_root / name
        if path.exists():
            return path
    return None


def normalize_spec(spec: dict) -> list[InferredEndpoint]:
    """Convert a raw OpenAPI spec dict into a list of ``InferredEndpoint``."""
    endpoints: list[InferredEndpoint] = []
    paths: dict = spec.get("paths", {})
    components_schemas: dict = spec.get("components", {}).get("schemas", {})

    for path, methods in paths.items():
        if not isinstance(methods, dict):
            continue
        for method, operation in methods.items():
            if method.startswith("x-") or method == "parameters":
                continue
            if not isinstance(operation, dict):
                continue

            summary = operation.get("summary")
            tags = operation.get("tags", [])
            status_code = _infer_success_status(operation)

            path_params, query_params = _extract_parameters(
                operation.get("parameters", []),
                methods.get("parameters", []),
            )

            request_body = _extract_request_body(operation, components_schemas)
            response_fields = _extract_response_fields(operation, status_code, components_schemas)

            endpoints.append(InferredEndpoint(
                path=path,
                method=method.upper(),
                summary=summary,
                request_body=request_body,
                response_fields=response_fields,
                response_status=status_code,
                query_params=query_params,
                path_params=path_params,
                tags=tags,
            ))

    return endpoints


def _infer_success_status(operation: dict) -> int:
    """Pick the primary success status code from the responses block."""
    responses = operation.get("responses", {})
    for code in ("200", "201", "202", "204"):
        if code in responses:
            return int(code)
    # Fall back to the first 2xx code present
    for code in responses:
        try:
            c = int(code)
            if 200 <= c < 300:
                return c
        except ValueError:
            continue
    return 200


def _extract_parameters(
    op_params: list[dict], path_params_shared: list[dict]
) -> tuple[list[InferredField], list[InferredField]]:
    """Extract path and query parameters from the combined parameter list."""
    all_params = list(path_params_shared) + list(op_params)
    path_fields: list[InferredField] = []
    query_fields: list[InferredField] = []

    for param in all_params:
        if not isinstance(param, dict):
            continue
        name = param.get("name", "")
        location = param.get("in", "")
        required = param.get("required", location == "path")
        schema = param.get("schema", {})
        field_type = _OPENAPI_TYPE_MAP.get(schema.get("type", "string"), "string")

        f = InferredField(name=name, type=field_type, required=required)
        if location == "path":
            path_fields.append(f)
        elif location == "query":
            query_fields.append(f)

    return path_fields, query_fields


def _extract_request_body(
    operation: dict, components_schemas: dict
) -> list[InferredField] | None:
    """Extract request body fields from the operation."""
    body = operation.get("requestBody", {})
    if not body:
        return None
    content = body.get("content", {})
    json_content = content.get("application/json", {})
    schema = json_content.get("schema", {})
    return _schema_to_fields(schema, components_schemas)


def _extract_response_fields(
    operation: dict, status_code: int, components_schemas: dict
) -> list[InferredField] | None:
    """Extract response body fields for the given status code."""
    responses = operation.get("responses", {})
    response = responses.get(str(status_code), {})
    content = response.get("content", {})
    json_content = content.get("application/json", {})
    schema = json_content.get("schema", {})
    if not schema:
        return None
    return _schema_to_fields(schema, components_schemas)


def _schema_to_fields(
    schema: dict, components_schemas: dict, _visited: set[str] | None = None
) -> list[InferredField] | None:
    """Recursively convert an OpenAPI schema into a list of ``InferredField``."""
    if _visited is None:
        _visited = set()

    schema = _resolve_ref(schema, components_schemas, _visited)
    if not schema:
        return None

    # Array of items
    if schema.get("type") == "array":
        items = schema.get("items", {})
        return _schema_to_fields(items, components_schemas, _visited)

    # Object with properties
    properties = schema.get("properties", {})
    if not properties:
        return None

    required_fields = set(schema.get("required", []))
    fields: list[InferredField] = []

    for name, prop in properties.items():
        prop = _resolve_ref(prop, components_schemas, _visited)
        # OAS 3.1: nullable fields use anyOf: [{type: X}, {type: null}] with no
        # top-level "type" key. Unwrap to the non-null variant before mapping.
        resolved_prop = _unwrap_anyof_nullable(prop, components_schemas, _visited)
        prop_type = _OPENAPI_TYPE_MAP.get(resolved_prop.get("type", "object"), "object")
        nested = None
        if resolved_prop.get("type") == "object" or "$ref" in resolved_prop or "properties" in resolved_prop:
            nested = _schema_to_fields(resolved_prop, components_schemas, _visited)
        elif resolved_prop.get("type") == "array":
            items = resolved_prop.get("items", {})
            nested = _schema_to_fields(items, components_schemas, _visited)

        fields.append(InferredField(
            name=name,
            type=prop_type,
            required=name in required_fields,
            description=prop.get("description"),
            nested=nested,
        ))

    return fields


def _unwrap_anyof_nullable(
    prop: dict, components_schemas: dict, visited: set[str]
) -> dict:
    """If *prop* is an OAS 3.1 anyOf nullable (e.g. anyOf: [{type: X}, {type: null}]),
    return the non-null variant so type resolution works correctly."""
    if "type" in prop or "$ref" in prop:
        return prop
    any_of = prop.get("anyOf") or prop.get("oneOf")
    if not any_of:
        return prop
    non_null = [v for v in any_of if v.get("type") != "null" and v != {"type": "null"}]
    if len(non_null) == 1:
        return _resolve_ref(non_null[0], components_schemas, visited)
    return prop


def _resolve_ref(schema: dict, components_schemas: dict, visited: set[str]) -> dict:
    """Follow a ``$ref`` pointer to the actual schema definition."""
    ref = schema.get("$ref")
    if not ref:
        return schema

    # Only support local #/components/schemas/... refs
    prefix = "#/components/schemas/"
    if not ref.startswith(prefix):
        return schema

    model_name = ref[len(prefix):]
    if model_name in visited:
        return {}
    visited.add(model_name)

    resolved = components_schemas.get(model_name, {})
    return resolved
