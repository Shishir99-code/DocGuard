"""Tests for the Flask AST parser."""

from __future__ import annotations

from typing import TYPE_CHECKING

from docguard.parsers.flask_parser import FlaskParser

if TYPE_CHECKING:
    from pathlib import Path


class TestFlaskParser:
    def setup_method(self) -> None:
        self.parser = FlaskParser()

    def _by_key(self, endpoints: list, method: str, path: str):  # type: ignore[no-untyped-def]
        return next(
            e for e in endpoints if e.method == method and e.path == path
        )

    def test_app_route_default_method_is_get(self, sample_flask_app_path: Path) -> None:
        endpoints = self.parser.extract_endpoints([sample_flask_app_path])
        ep = self._by_key(endpoints, "GET", "/health")
        assert ep.method == "GET"

    def test_app_route_explicit_method(self, sample_flask_app_path: Path) -> None:
        endpoints = self.parser.extract_endpoints([sample_flask_app_path])
        ep = self._by_key(endpoints, "POST", "/login")
        assert ep.method == "POST"
        # No phantom GET should be created for a POST-only rule.
        assert not any(e.path == "/login" and e.method == "GET" for e in endpoints)

    def test_blueprint_declared_prefix(self, sample_flask_app_path: Path) -> None:
        endpoints = self.parser.extract_endpoints([sample_flask_app_path])
        # users_bp has url_prefix="/users"; "/" rule collapses to the prefix.
        ep = self._by_key(endpoints, "GET", "/users")
        assert ep.method == "GET"

    def test_blueprint_prefix_with_path_param(self, sample_flask_app_path: Path) -> None:
        endpoints = self.parser.extract_endpoints([sample_flask_app_path])
        ep = self._by_key(endpoints, "GET", "/users/{user_id}")
        assert len(ep.path_params) == 1
        assert ep.path_params[0].name == "user_id"
        assert ep.path_params[0].type == "integer"

    def test_multiple_methods_expand_to_endpoints(self, sample_flask_app_path: Path) -> None:
        endpoints = self.parser.extract_endpoints([sample_flask_app_path])
        methods = {
            e.method for e in endpoints if e.path == "/users/{user_id}"
        }
        assert methods == {"GET", "DELETE"}

    def test_register_blueprint_prefix_override(self, sample_flask_app_path: Path) -> None:
        endpoints = self.parser.extract_endpoints([sample_flask_app_path])
        # items_bp has no declared prefix; "/items" comes from register_blueprint.
        ep = self._by_key(endpoints, "GET", "/items/{item_id}")
        assert ep.path_params[0].name == "item_id"
        assert ep.path_params[0].type == "string"

    def test_add_url_rule(self, sample_flask_app_path: Path) -> None:
        endpoints = self.parser.extract_endpoints([sample_flask_app_path])
        ep = self._by_key(endpoints, "GET", "/reports/{report_id}")
        assert ep.path_params[0].name == "report_id"
        assert ep.path_params[0].type == "integer"

    def test_no_missed_endpoints(self, sample_flask_app_path: Path) -> None:
        endpoints = self.parser.extract_endpoints([sample_flask_app_path])
        keys = {(e.method, e.path) for e in endpoints}
        expected = {
            ("GET", "/health"),
            ("POST", "/login"),
            ("GET", "/users"),
            ("GET", "/users/{user_id}"),
            ("DELETE", "/users/{user_id}"),
            ("GET", "/items/{item_id}"),
            ("PUT", "/items/{item_id}"),
            ("GET", "/reports/{report_id}"),
        }
        assert keys == expected

    def test_source_tracking(self, sample_flask_app_path: Path) -> None:
        endpoints = self.parser.extract_endpoints([sample_flask_app_path])
        for ep in endpoints:
            assert ep.source_file == str(sample_flask_app_path)
            assert ep.source_line > 0

    def test_can_handle_with_requirements(self, tmp_path: Path) -> None:
        (tmp_path / "requirements.txt").write_text("flask>=3.0\ngunicorn\n")
        assert self.parser.can_handle(tmp_path) is True

    def test_can_handle_without_flask(self, tmp_path: Path) -> None:
        (tmp_path / "requirements.txt").write_text("fastapi\nuvicorn\n")
        assert self.parser.can_handle(tmp_path) is False

    def test_can_handle_ignores_flask_substring_package(self, tmp_path: Path) -> None:
        # A package that merely embeds "flask" as a substring (not a word) must
        # not trigger detection -- guards against false positives like "flaskish".
        (tmp_path / "requirements.txt").write_text("flaskish\nmyflask\n")
        assert self.parser.can_handle(tmp_path) is False

    def test_empty_file_list(self) -> None:
        assert self.parser.extract_endpoints([]) == []

    def test_name(self) -> None:
        assert self.parser.name == "Flask"
