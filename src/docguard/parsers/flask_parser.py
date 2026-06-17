"""Flask parser -- extracts API endpoints from Flask source code via AST analysis."""

from __future__ import annotations

import ast
import re
from typing import TYPE_CHECKING

from docguard.core.models import InferredEndpoint, InferredField

if TYPE_CHECKING:
    from pathlib import Path

_HTTP_METHODS = {"GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"}

# HEAD/OPTIONS are added automatically by Flask and rarely documented; skip them
# unless they are the only method declared on a rule.
_IMPLICIT_METHODS = {"HEAD", "OPTIONS"}

# Flask URL converters mapped to JSON Schema types.
_CONVERTER_TO_JSON: dict[str, str] = {
    "int": "integer",
    "float": "number",
    "string": "string",
    "path": "string",
    "uuid": "string",
    "any": "string",
}

# Matches Flask rule variables: <name>, <int:name>, <path:name>, etc.
_RULE_PARAM_RE = re.compile(r"<(?:(?P<conv>[a-zA-Z_][\w]*)(?:\([^)]*\))?:)?(?P<name>[a-zA-Z_]\w*)>")


def _normalize_path(rule: str) -> str:
    """Convert a Flask rule (``/users/<int:id>``) to OpenAPI style (``/users/{id}``)."""

    def repl(match: re.Match[str]) -> str:
        return "{" + match.group("name") + "}"

    return _RULE_PARAM_RE.sub(repl, rule)


def _extract_path_params(rule: str) -> list[InferredField]:
    """Extract path parameters and their JSON types from a Flask rule string."""
    params: list[InferredField] = []
    for match in _RULE_PARAM_RE.finditer(rule):
        conv = match.group("conv")
        json_type = _CONVERTER_TO_JSON.get(conv, "string") if conv else "string"
        params.append(InferredField(name=match.group("name"), type=json_type, required=True))
    return params


def _join_paths(prefix: str, rule: str) -> str:
    """Join a blueprint ``url_prefix`` with a route rule, collapsing slashes."""
    joined = rule if not prefix else f"{prefix.rstrip('/')}/{rule.lstrip('/')}"
    if len(joined) > 1:
        joined = joined.rstrip("/")
    return joined or "/"


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


def _string_const(node: ast.expr) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _methods_from_keyword(node: ast.expr) -> list[str]:
    """Extract uppercased HTTP methods from a ``methods=[...]`` keyword value."""
    methods: list[str] = []
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        for elt in node.elts:
            value = _string_const(elt)
            if value:
                upper = value.upper()
                if upper in _HTTP_METHODS:
                    methods.append(upper)
    return methods


def _select_documented_methods(methods: list[str]) -> list[str]:
    """Drop implicit HEAD/OPTIONS unless they are the only declared methods."""
    explicit = [m for m in methods if m not in _IMPLICIT_METHODS]
    selected = explicit or methods
    # De-duplicate while preserving order.
    seen: set[str] = set()
    result: list[str] = []
    for method in selected:
        if method not in seen:
            seen.add(method)
            result.append(method)
    return result


class _BlueprintCollector(ast.NodeVisitor):
    """First pass: map blueprint variable names to their resolved ``url_prefix``."""

    def __init__(self) -> None:
        # variable name -> url_prefix declared on Blueprint(...)
        self.declared_prefix: dict[str, str] = {}
        # variable name -> url_prefix override from app.register_blueprint(...)
        self.registered_prefix: dict[str, str] = {}

    def visit_Assign(self, node: ast.Assign) -> None:
        if isinstance(node.value, ast.Call) and _is_blueprint_call(node.value):
            prefix = _keyword_string(node.value, "url_prefix") or ""
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.declared_prefix[target.id] = prefix
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Attribute) and node.func.attr == "register_blueprint":
            bp_name = _resolve_name(node.args[0]) if node.args else None
            prefix = _keyword_string(node, "url_prefix")
            if bp_name and prefix is not None:
                self.registered_prefix[bp_name] = prefix
        self.generic_visit(node)

    def prefix_for(self, var_name: str | None) -> str:
        """Return the effective prefix for a blueprint variable (register overrides declared)."""
        if var_name is None:
            return ""
        if var_name in self.registered_prefix:
            return self.registered_prefix[var_name]
        return self.declared_prefix.get(var_name, "")


def _is_blueprint_call(node: ast.Call) -> bool:
    name = _resolve_name(node.func)
    return name is not None and name.split(".")[-1] == "Blueprint"


def _keyword_string(node: ast.Call, name: str) -> str | None:
    for kw in node.keywords:
        if kw.arg == name:
            return _string_const(kw.value)
    return None


class _RouteVisitor(ast.NodeVisitor):
    """Second pass: collect ``@x.route`` decorators and ``add_url_rule`` calls."""

    def __init__(self, prefixes: _BlueprintCollector, filepath: str) -> None:
        self.prefixes = prefixes
        self.filepath = filepath
        self.endpoints: list[InferredEndpoint] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._check_decorators(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._check_decorators(node)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        self._check_add_url_rule(node)
        self.generic_visit(node)

    def _check_decorators(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            if not isinstance(decorator.func, ast.Attribute):
                continue
            if decorator.func.attr != "route":
                continue
            if not decorator.args:
                continue
            rule = _string_const(decorator.args[0])
            if rule is None:
                continue

            owner = _resolve_name(decorator.func.value)
            prefix = self.prefixes.prefix_for(owner)

            methods_kw = next(
                (kw.value for kw in decorator.keywords if kw.arg == "methods"), None
            )
            methods = _methods_from_keyword(methods_kw) if methods_kw is not None else ["GET"]
            if not methods:
                methods = ["GET"]

            self._emit(rule, prefix, methods, node.lineno)

    def _check_add_url_rule(self, node: ast.Call) -> None:
        if not isinstance(node.func, ast.Attribute):
            return
        if node.func.attr != "add_url_rule":
            return
        if not node.args:
            return
        rule = _string_const(node.args[0])
        if rule is None:
            return

        owner = _resolve_name(node.func.value)
        prefix = self.prefixes.prefix_for(owner)

        methods_kw = next((kw.value for kw in node.keywords if kw.arg == "methods"), None)
        methods = _methods_from_keyword(methods_kw) if methods_kw is not None else ["GET"]
        if not methods:
            methods = ["GET"]

        self._emit(rule, prefix, methods, node.lineno)

    def _emit(self, rule: str, prefix: str, methods: list[str], lineno: int) -> None:
        full_rule = _join_paths(prefix, rule)
        path = _normalize_path(full_rule)
        path_params = _extract_path_params(full_rule)
        for method in _select_documented_methods(methods):
            self.endpoints.append(
                InferredEndpoint(
                    path=path,
                    method=method,
                    path_params=list(path_params),
                    source_file=self.filepath,
                    source_line=lineno,
                )
            )


class FlaskParser:
    """Parses Flask source files via AST to extract API endpoints."""

    @property
    def name(self) -> str:
        return "Flask"

    def can_handle(self, project_root: Path) -> bool:
        """Detect Flask by checking dependency declarations for ``flask``."""
        for req_file in ("requirements.txt", "pyproject.toml", "setup.py", "setup.cfg"):
            req_path = project_root / req_file
            if req_path.exists():
                try:
                    content = req_path.read_text()
                except OSError:
                    continue
                if re.search(r"(?<![\w-])flask\b", content, re.IGNORECASE):
                    return True
        return False

    def extract_endpoints(self, source_files: list[Path]) -> list[InferredEndpoint]:
        """Parse all *source_files* and return discovered endpoints."""
        # First pass: collect blueprint prefixes across all files.
        collector = _BlueprintCollector()
        trees: list[tuple[Path, ast.Module]] = []
        for filepath in source_files:
            try:
                source = filepath.read_text(encoding="utf-8")
                tree = ast.parse(source, filename=str(filepath))
            except (SyntaxError, OSError):
                continue
            collector.visit(tree)
            trees.append((filepath, tree))

        # Second pass: extract routes using the resolved prefixes.
        all_endpoints: list[InferredEndpoint] = []
        for filepath, tree in trees:
            visitor = _RouteVisitor(collector, str(filepath))
            visitor.visit(tree)
            all_endpoints.extend(visitor.endpoints)

        return all_endpoints
