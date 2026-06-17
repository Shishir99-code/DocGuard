"""Tests for the FastAPI AST parser."""

from __future__ import annotations

from typing import TYPE_CHECKING

from docguard.parsers.fastapi_parser import FastAPIParser

if TYPE_CHECKING:
    from pathlib import Path


class TestFastAPIParser:
    def setup_method(self) -> None:
        self.parser = FastAPIParser()

    def test_extract_endpoints_count(self, sample_app_path: Path) -> None:
        endpoints = self.parser.extract_endpoints([sample_app_path])
        assert len(endpoints) == 5

    def test_get_users_endpoint(self, sample_app_path: Path) -> None:
        endpoints = self.parser.extract_endpoints([sample_app_path])
        ep = next(e for e in endpoints if e.path == "/users" and e.method == "GET")
        assert ep.summary == "List all users"
        assert ep.tags == ["users"]
        assert ep.response_status == 200

    def test_get_users_query_params(self, sample_app_path: Path) -> None:
        endpoints = self.parser.extract_endpoints([sample_app_path])
        ep = next(e for e in endpoints if e.path == "/users" and e.method == "GET")
        param_names = {p.name for p in ep.query_params}
        assert "skip" in param_names
        assert "limit" in param_names

    def test_get_users_query_params_not_required(self, sample_app_path: Path) -> None:
        endpoints = self.parser.extract_endpoints([sample_app_path])
        ep = next(e for e in endpoints if e.path == "/users" and e.method == "GET")
        for p in ep.query_params:
            assert p.required is False, (
                f"Query param '{p.name}' should not be required (has default)"
            )

    def test_post_users_status_code(self, sample_app_path: Path) -> None:
        endpoints = self.parser.extract_endpoints([sample_app_path])
        ep = next(e for e in endpoints if e.path == "/users" and e.method == "POST")
        assert ep.response_status == 201

    def test_post_users_request_body(self, sample_app_path: Path) -> None:
        endpoints = self.parser.extract_endpoints([sample_app_path])
        ep = next(e for e in endpoints if e.path == "/users" and e.method == "POST")
        assert ep.request_body is not None
        field_names = {f.name for f in ep.request_body}
        assert "name" in field_names
        assert "email" in field_names

    def test_get_user_path_param(self, sample_app_path: Path) -> None:
        endpoints = self.parser.extract_endpoints([sample_app_path])
        ep = next(e for e in endpoints if e.path == "/users/{user_id}" and e.method == "GET")
        assert len(ep.path_params) == 1
        assert ep.path_params[0].name == "user_id"
        assert ep.path_params[0].type == "integer"

    def test_delete_users_status_code(self, sample_app_path: Path) -> None:
        endpoints = self.parser.extract_endpoints([sample_app_path])
        ep = next(e for e in endpoints if e.path == "/users/{user_id}" and e.method == "DELETE")
        assert ep.response_status == 204

    def test_response_model_fields(self, sample_app_path: Path) -> None:
        endpoints = self.parser.extract_endpoints([sample_app_path])
        ep = next(e for e in endpoints if e.path == "/users/{user_id}" and e.method == "GET")
        assert ep.response_fields is not None
        field_names = {f.name for f in ep.response_fields}
        assert "id" in field_names
        assert "name" in field_names
        assert "email" in field_names

    def test_items_endpoint_has_optional_query(self, sample_app_path: Path) -> None:
        endpoints = self.parser.extract_endpoints([sample_app_path])
        ep = next(e for e in endpoints if e.path == "/items/{item_id}" and e.method == "GET")
        q_params = {p.name: p for p in ep.query_params}
        assert "q" in q_params
        assert q_params["q"].required is False

    def test_source_file_tracking(self, sample_app_path: Path) -> None:
        endpoints = self.parser.extract_endpoints([sample_app_path])
        for ep in endpoints:
            assert ep.source_file == str(sample_app_path)
            assert ep.source_line > 0

    def test_can_handle_with_requirements(self, tmp_path: Path) -> None:
        (tmp_path / "requirements.txt").write_text("fastapi>=0.100\nuvicorn\n")
        assert self.parser.can_handle(tmp_path) is True

    def test_can_handle_without_fastapi(self, tmp_path: Path) -> None:
        (tmp_path / "requirements.txt").write_text("flask\nuvicorn\n")
        assert self.parser.can_handle(tmp_path) is False

    def test_empty_file_list(self) -> None:
        endpoints = self.parser.extract_endpoints([])
        assert endpoints == []
