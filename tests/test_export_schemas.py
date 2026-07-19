"""Validate the --json / --compact exports against the published schemas."""

import json
import sys
from pathlib import Path

import jsonschema
import pytest

from build_graph import graph

SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schema"


@pytest.fixture()
def tiny_project(tmp_path: Path) -> Path:
    (tmp_path / "app").mkdir(parents=True)
    (tmp_path / "docs").mkdir()
    (tmp_path / "app" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "app" / "core.py").write_text(
        '"""Core logic, see docs/design.md."""\n\nVALUE = 1\n',
        encoding="utf-8",
    )
    (tmp_path / "app" / "cli.py").write_text(
        "from app.core import VALUE\n\nprint(VALUE)\n",
        encoding="utf-8",
    )
    (tmp_path / "docs" / "design.md").write_text(
        "# Design\n\nEntry point is `cli.py`, logic in [core](../app/core.py).\n",
        encoding="utf-8",
    )
    return tmp_path


def _load_schema(name: str) -> dict:
    return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))


def _run(tiny_project: Path, monkeypatch: pytest.MonkeyPatch, *extra: str) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["build-graph", "--root", str(tiny_project), "--json", "--compact", *extra],
    )
    graph.main()


def _validate(instance: dict, schema: dict) -> None:
    jsonschema.validate(
        instance=instance,
        schema=schema,
        format_checker=jsonschema.FormatChecker(),
    )


@pytest.mark.parametrize("extra", [(), ("--mock-git",)], ids=["plain", "mock-git"])
def test_exports_match_schemas(
    tiny_project: Path, monkeypatch: pytest.MonkeyPatch, extra: tuple[str, ...]
) -> None:
    _run(tiny_project, monkeypatch, *extra)

    verbose = json.loads(
        (tiny_project / "docs" / "graph.json").read_text(encoding="utf-8")
    )
    _validate(verbose, _load_schema("graph-v1.schema.json"))

    compact = json.loads(
        (tiny_project / "docs" / "graph-compact.json").read_text(encoding="utf-8")
    )
    _validate(compact, _load_schema("graph-compact-v2.schema.json"))


def test_schemas_are_valid_2020_12() -> None:
    for name in ("graph-v1.schema.json", "graph-compact-v2.schema.json"):
        jsonschema.Draft202012Validator.check_schema(_load_schema(name))
