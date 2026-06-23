"""Tests for deterministic, AST-only framework auto-detection in the registry."""

from __future__ import annotations

from typing import TYPE_CHECKING

from docguard.parsers.fastapi_parser import FastAPIParser
from docguard.parsers.flask_parser import FlaskParser
from docguard.parsers.registry import (
    FASTAPI,
    FLASK,
    REST_FRAMEWORK,
    STARLETTE,
    available_parsers,
    detect_framework,
    detect_framework_name,
    get_parser_by_name,
    register_parser,
)

if TYPE_CHECKING:
    from pathlib import Path


def _write(root: Path, name: str, source: str) -> None:
    (root / name).write_text(source, encoding="utf-8")


class TestDetectFrameworkName:
    """AST import detection for each supported framework."""

    def test_detects_fastapi(self, tmp_path: Path) -> None:
        _write(tmp_path, "app.py", "from fastapi import FastAPI\napp = FastAPI()\n")
        assert detect_framework_name(tmp_path) == FASTAPI

    def test_detects_flask(self, tmp_path: Path) -> None:
        _write(tmp_path, "app.py", "from flask import Flask\napp = Flask(__name__)\n")
        assert detect_framework_name(tmp_path) == FLASK

    def test_detects_starlette(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "app.py",
            "from starlette.applications import Starlette\napp = Starlette()\n",
        )
        assert detect_framework_name(tmp_path) == STARLETTE

    def test_detects_rest_framework(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "views.py",
            "from rest_framework.views import APIView\n\n\nclass V(APIView):\n    pass\n",
        )
        assert detect_framework_name(tmp_path) == REST_FRAMEWORK

    def test_plain_import_statement_is_detected(self, tmp_path: Path) -> None:
        _write(tmp_path, "app.py", "import fastapi\napp = fastapi.FastAPI()\n")
        assert detect_framework_name(tmp_path) == FASTAPI

    def test_dotted_import_root_is_used(self, tmp_path: Path) -> None:
        _write(tmp_path, "r.py", "from rest_framework.decorators import api_view\n")
        assert detect_framework_name(tmp_path) == REST_FRAMEWORK


class TestNeverRaisesOnUnknown:
    """Detection must return None -- never raise -- for unknown/empty input."""

    def test_empty_directory_returns_none(self, tmp_path: Path) -> None:
        assert detect_framework_name(tmp_path) is None
        assert detect_framework(tmp_path) is None

    def test_no_framework_imports_returns_none(self, tmp_path: Path) -> None:
        _write(tmp_path, "util.py", "import os\nimport json\n\n\nx = os.getcwd()\n")
        assert detect_framework_name(tmp_path) is None

    def test_syntax_error_file_is_skipped(self, tmp_path: Path) -> None:
        _write(tmp_path, "broken.py", "def f(:\n")
        _write(tmp_path, "app.py", "from flask import Flask\n")
        # The broken file is ignored; the valid Flask import still wins.
        assert detect_framework_name(tmp_path) == FLASK

    def test_relative_import_does_not_crash(self, tmp_path: Path) -> None:
        _write(tmp_path, "app.py", "from . import helpers\n")
        assert detect_framework_name(tmp_path) is None


class TestTieBreak:
    """Deterministic, documented tie-break order when signals are mixed."""

    def test_fastapi_beats_starlette_on_tie(self, tmp_path: Path) -> None:
        # FastAPI is built on Starlette; a tie resolves to FastAPI.
        _write(
            tmp_path,
            "app.py",
            "from fastapi import FastAPI\nfrom starlette.routing import Route\n",
        )
        assert detect_framework_name(tmp_path) == FASTAPI

    def test_higher_score_wins_over_tie_break_order(self, tmp_path: Path) -> None:
        # Flask appears twice, FastAPI once: score beats tie-break priority.
        _write(tmp_path, "a.py", "import flask\n")
        _write(tmp_path, "b.py", "from flask import Blueprint\n")
        _write(tmp_path, "c.py", "import fastapi\n")
        assert detect_framework_name(tmp_path) == FLASK

    def test_equal_scores_follow_tie_break_order(self, tmp_path: Path) -> None:
        # One signal each for Flask and REST Framework -> Flask wins (earlier).
        _write(tmp_path, "a.py", "import flask\n")
        _write(tmp_path, "b.py", "import rest_framework\n")
        assert detect_framework_name(tmp_path) == FLASK


class TestVendorDirsIgnored:
    def test_site_packages_does_not_skew_detection(self, tmp_path: Path) -> None:
        vendor = tmp_path / ".venv" / "lib" / "site-packages"
        vendor.mkdir(parents=True)
        _write(vendor, "django_stub.py", "import flask\n")
        _write(tmp_path, "app.py", "from fastapi import FastAPI\n")
        assert detect_framework_name(tmp_path) == FASTAPI


class TestDetectFrameworkParser:
    """`detect_framework` maps a detected name to a registered parser."""

    def test_returns_fastapi_parser(self, tmp_path: Path) -> None:
        _write(tmp_path, "app.py", "from fastapi import FastAPI\n")
        parser = detect_framework(tmp_path)
        assert isinstance(parser, FastAPIParser)

    def test_returns_flask_parser(self, tmp_path: Path) -> None:
        _write(tmp_path, "app.py", "from flask import Flask\n")
        parser = detect_framework(tmp_path)
        assert isinstance(parser, FlaskParser)

    def test_detected_but_unparsable_framework_returns_none(self, tmp_path: Path) -> None:
        # Starlette can be detected but ships no parser yet -> None, not a guess.
        _write(tmp_path, "app.py", "from starlette.applications import Starlette\n")
        assert detect_framework(tmp_path) is None

    def test_falls_back_to_dependency_file_heuristic(self, tmp_path: Path) -> None:
        # No framework imports in source, but requirements.txt names fastapi.
        _write(tmp_path, "main.py", "import os\n")
        _write(tmp_path, "requirements.txt", "fastapi>=0.110\nuvicorn\n")
        parser = detect_framework(tmp_path)
        assert isinstance(parser, FastAPIParser)


class TestOverridePath:
    """`--framework` / config override resolves a parser by name, bypassing detection."""

    def test_get_parser_by_name_is_case_insensitive(self) -> None:
        assert isinstance(get_parser_by_name("fastapi"), FastAPIParser)
        assert isinstance(get_parser_by_name("FASTAPI"), FastAPIParser)
        assert isinstance(get_parser_by_name("flask"), FlaskParser)

    def test_unknown_name_returns_none(self) -> None:
        assert get_parser_by_name("django") is None

    def test_override_wins_over_ast_signals(self, tmp_path: Path) -> None:
        # Source clearly looks like FastAPI, but the caller forces Flask by name.
        _write(tmp_path, "app.py", "from fastapi import FastAPI\n")
        assert detect_framework_name(tmp_path) == FASTAPI
        forced = get_parser_by_name("flask")
        assert isinstance(forced, FlaskParser)


class TestRegistryManagement:
    def test_available_parsers_lists_builtins(self) -> None:
        names = available_parsers()
        assert "FastAPI" in names
        assert "Flask" in names

    def test_register_custom_parser_is_discoverable(self, tmp_path: Path) -> None:
        class DummyParser:
            @property
            def name(self) -> str:
                return "Dummy"

            def can_handle(self, project_root: Path) -> bool:
                return False

            def extract_endpoints(self, source_files: list[Path]) -> list:  # type: ignore[type-arg]
                return []

        register_parser(DummyParser())
        assert get_parser_by_name("dummy") is not None
        assert "Dummy" in available_parsers()
