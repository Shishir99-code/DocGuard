"""FastAPI parser -- extracts API endpoints from FastAPI source code via AST analysis."""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

from docguard.core.models import InferredEndpoint, InferredField

if TYPE_CHECKING:
    from pathlib import Path

_PYTHON_TYPE_TO_JSON: dict[str, str] = {
    "str": "string",
    "int": "integer",
    "float": "number",
    "bool": "boolean",
    "list": "array",
    "dict": "object",
    "List": "array",
    "Dict": "object",
    "Any": "object",
    "bytes": "string",
    "datetime": "string",
    "date": "string",
    "UUID": "string",
    "Decimal": "number",
    "Optional": "string",  # fallback; inner type resolved separately
}

_HTTP_METHODS = {"get", "post", "put", "delete", "patch", "options", "head"}

_ROUTER_NAMES = {"app", "router"}


class _PydanticModelCollector(ast.NodeVisitor):
    """First pass: collect all Pydantic BaseModel subclass definitions."""

    def __init__(self) -> None:
        self.models: dict[str, list[InferredField]] = {}

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        if self._inherits_base_model(node):
            fields = self._extract_fields(node)
            self.models[node.name] = fields
        self.generic_visit(node)

    @staticmethod
    def _inherits_base_model(node: ast.ClassDef) -> bool:
        for base in node.bases:
            name = _resolve_name(base)
            if name and ("BaseModel" in name or "Schema" in name):
                return True
        return False

    def _extract_fields(self, node: ast.ClassDef) -> list[InferredField]:
        fields: list[InferredField] = []
        for item in node.body:
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                field_name = item.target.id
                field_type, is_optional = self._resolve_annotation(item.annotation)
                required = not is_optional and item.value is None
                default = None
                if item.value is not None and not self._is_field_call(item.value):
                    default = _const_to_str(item.value)
                    required = False
                if item.value is not None and self._is_field_call(item.value):
                    required, default = self._parse_field_call(item.value, is_optional)

                nested = (
                    self.models.get(field_type)
                    if field_type not in _PYTHON_TYPE_TO_JSON
                    else None
                )
                # _resolve_annotation may return a JSON type directly (e.g.
                # "array" for list[X]) — pass those through as-is.
                json_types = ("array", "object", "string", "integer", "number", "boolean")
                json_type = _PYTHON_TYPE_TO_JSON.get(
                    field_type,
                    field_type if field_type in json_types else "object",
                )

                fields.append(InferredField(
                    name=field_name,
                    type=json_type,
                    required=required,
                    default=default,
                    nested=list(nested) if nested else None,
                ))
        return fields

    def _resolve_annotation(self, node: ast.expr) -> tuple[str, bool]:
        """Return (type_name, is_optional)."""
        if isinstance(node, ast.Name):
            return node.id, False

        if isinstance(node, ast.Attribute):
            return node.attr, False

        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value, False

        # Optional[X] or X | None
        if isinstance(node, ast.Subscript):
            outer = _resolve_name(node.value)
            if outer == "Optional":
                inner, _ = self._resolve_annotation(node.slice)
                return inner, True
            if outer in ("List", "list"):
                return "array", False
            if outer in ("Dict", "dict"):
                return "object", False
            inner, _ = self._resolve_annotation(node.slice)
            return inner, False

        # X | None  (PEP 604)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            left, _ = self._resolve_annotation(node.left)
            right, _ = self._resolve_annotation(node.right)
            if right == "None":
                return left, True
            if left == "None":
                return right, True
            return left, False

        return "object", False

    @staticmethod
    def _is_field_call(node: ast.expr | None) -> bool:
        if node is None:
            return False
        if isinstance(node, ast.Call):
            name = _resolve_name(node.func)
            return name in ("Field", "field")
        return False

    @staticmethod
    def _parse_field_call(node: ast.expr, is_optional: bool) -> tuple[bool, str | None]:
        """Parse Field(...) to extract required and default."""
        if not isinstance(node, ast.Call):
            return not is_optional, None
        default = None
        required = not is_optional
        for kw in node.keywords:
            if kw.arg == "default" and isinstance(kw.value, ast.Constant):
                default = str(kw.value.value)
                required = False
            elif kw.arg == "default_factory":
                # Any default_factory makes the field non-required
                required = False
        if (
            node.args
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value is not ...
        ):
            default = str(node.args[0].value)
            required = False
        return required, default


class _RouteVisitor(ast.NodeVisitor):
    """Second pass: find route decorator calls and extract endpoint metadata."""

    def __init__(self, models: dict[str, list[InferredField]], filepath: str) -> None:
        self.models = models
        self.filepath = filepath
        self.endpoints: list[InferredEndpoint] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._check_decorators(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._check_decorators(node)
        self.generic_visit(node)

    def _check_decorators(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        for decorator in node.decorator_list:
            route_info = self._parse_route_decorator(decorator)
            if route_info is None:
                continue
            method, path, status_code, tags, summary = route_info
            path_params, query_params, body_fields = self._parse_function_params(node, path)
            response_fields = (
                self._extract_response_model(decorator)
                if isinstance(decorator, ast.Call)
                else None
            )
            # Fall back to the function's return-type annotation (FastAPI 0.90+ feature)
            if response_fields is None:
                response_fields = self._extract_return_annotation_fields(node)

            self.endpoints.append(InferredEndpoint(
                path=path,
                method=method.upper(),
                summary=summary,
                request_body=body_fields if body_fields else None,
                response_fields=response_fields,
                response_status=status_code,
                query_params=query_params,
                path_params=path_params,
                tags=tags,
                source_file=self.filepath,
                source_line=node.lineno,
            ))

    def _parse_route_decorator(
        self, node: ast.expr
    ) -> tuple[str, str, int, list[str], str | None] | None:
        """Try to parse @app.get("/path", ...) or @router.post("/path", ...)."""
        if not isinstance(node, ast.Call):
            return None
        if not isinstance(node.func, ast.Attribute):
            return None

        method = node.func.attr
        if method not in _HTTP_METHODS:
            return None

        obj_name = _resolve_name(node.func.value)
        if obj_name and not any(r in obj_name.lower() for r in _ROUTER_NAMES):
            return None

        path = ""
        if node.args and isinstance(node.args[0], ast.Constant):
            path = str(node.args[0].value)

        status_code = 200
        tags: list[str] = []
        summary: str | None = None

        for kw in node.keywords:
            if (
                kw.arg == "status_code"
                and isinstance(kw.value, ast.Constant)
                and isinstance(kw.value.value, (int, str))
            ):
                status_code = int(kw.value.value)
            elif kw.arg == "tags" and isinstance(kw.value, (ast.List, ast.Tuple)):
                tags = [str(e.value) for e in kw.value.elts if isinstance(e, ast.Constant)]
            elif kw.arg == "summary" and isinstance(kw.value, ast.Constant):
                summary = str(kw.value.value)

        return method, path, status_code, tags, summary

    def _parse_function_params(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef, path: str
    ) -> tuple[list[InferredField], list[InferredField], list[InferredField]]:
        path_param_names = _extract_path_param_names(path)
        path_params: list[InferredField] = []
        query_params: list[InferredField] = []
        body_fields: list[InferredField] = []

        for arg in node.args.args:
            name = arg.arg
            if name in ("self", "cls", "request", "response", "db", "session"):
                continue

            annotation = arg.annotation
            if annotation is None:
                continue

            type_name = _resolve_name(annotation)
            if type_name is None:
                type_name = "string"

            # If the type is a known Pydantic model, treat as request body
            if type_name in self.models:
                body_fields = list(self.models[type_name])
                continue

            # Depends(...) and similar DI markers are skipped
            if type_name in ("Depends", "Security", "BackgroundTasks", "Request", "Response"):
                continue

            json_type = _PYTHON_TYPE_TO_JSON.get(type_name, "string")

            if name in path_param_names:
                path_params.append(InferredField(name=name, type=json_type, required=True))
            else:
                has_default = _arg_has_default(node, arg)
                query_params.append(
                    InferredField(name=name, type=json_type, required=not has_default)
                )

        return path_params, query_params, body_fields

    def _extract_response_model(self, decorator: ast.Call) -> list[InferredField] | None:
        for kw in decorator.keywords:
            if kw.arg == "response_model":
                model_name = _resolve_name(kw.value)
                if model_name and model_name in self.models:
                    return list(self.models[model_name])
                # List[Model] case
                if isinstance(kw.value, ast.Subscript):
                    inner_name = _resolve_name(kw.value.slice)
                    if inner_name and inner_name in self.models:
                        return list(self.models[inner_name])
        return None

    def _extract_return_annotation_fields(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> list[InferredField] | None:
        """Resolve `-> Model` / `-> list[Model]` return annotations to response fields."""
        if node.returns is None:
            return None
        return self._annotation_to_fields(node.returns)

    def _annotation_to_fields(self, annotation: ast.expr) -> list[InferredField] | None:
        if isinstance(annotation, ast.Subscript):
            outer = _resolve_name(annotation.value)
            # list[Model] / List[Model] — unwrap to inner type
            if outer in ("list", "List"):
                return self._annotation_to_fields(annotation.slice)
            # Optional[Model] / Union[Model, None] — unwrap to inner type
            if outer in ("Optional",):
                return self._annotation_to_fields(annotation.slice)
        # X | Y  (PEP 604) — take the non-None side
        if isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
            left_name = _resolve_name(annotation.left)
            right_name = _resolve_name(annotation.right)
            if right_name == "None":
                return self._annotation_to_fields(annotation.left)
            if left_name == "None":
                return self._annotation_to_fields(annotation.right)
        name = _resolve_name(annotation)
        if name and name in self.models:
            return list(self.models[name])
        return None


# ── Helpers ──────────────────────────────────────────────────────────────────


def _resolve_name(node: ast.expr | None) -> str | None:
    """Resolve an AST node to a dotted name string."""
    if node is None:
        return None
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _resolve_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _const_to_str(node: ast.expr) -> str | None:
    if isinstance(node, ast.Constant):
        return str(node.value)
    return None


def _extract_path_param_names(path: str) -> set[str]:
    """Extract parameter names from a path template like '/users/{user_id}'."""
    import re
    return set(re.findall(r"\{(\w+)\}", path))


def _arg_has_default(func: ast.FunctionDef | ast.AsyncFunctionDef, arg: ast.arg) -> bool:
    """Check whether *arg* has a default value in the function signature."""
    all_args = func.args.args
    num_defaults = len(func.args.defaults)
    num_args = len(all_args)
    idx = all_args.index(arg)
    default_start = num_args - num_defaults
    return idx >= default_start


# ── Public API ───────────────────────────────────────────────────────────────


class FastAPIParser:
    """Parses FastAPI source files via AST to extract API endpoints."""

    @property
    def name(self) -> str:
        return "FastAPI"

    def can_handle(self, project_root: Path) -> bool:
        """Detect FastAPI by checking imports in Python files or requirements."""
        # Quick check: look for fastapi in requirements or pyproject
        for req_file in ("requirements.txt", "pyproject.toml", "setup.py", "setup.cfg"):
            req_path = project_root / req_file
            if req_path.exists():
                try:
                    content = req_path.read_text()
                    if "fastapi" in content.lower():
                        return True
                except OSError:
                    continue
        return False

    def extract_endpoints(self, source_files: list[Path]) -> list[InferredEndpoint]:
        """Parse all *source_files* and return discovered endpoints."""
        # First pass: collect Pydantic models across all files
        model_collector = _PydanticModelCollector()
        trees: list[tuple[Path, ast.Module]] = []

        for filepath in source_files:
            try:
                source = filepath.read_text(encoding="utf-8")
                tree = ast.parse(source, filename=str(filepath))
            except (SyntaxError, OSError):
                continue
            model_collector.visit(tree)
            trees.append((filepath, tree))

        # Second pass: extract routes using the collected model definitions
        all_endpoints: list[InferredEndpoint] = []
        for filepath, tree in trees:
            visitor = _RouteVisitor(model_collector.models, str(filepath))
            visitor.visit(tree)
            all_endpoints.extend(visitor.endpoints)

        return all_endpoints
