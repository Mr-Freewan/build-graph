"""End-to-end smoke test: build a graph for a tiny synthetic project."""

import json
import sys
from pathlib import Path

import pytest

from build_graph import graph


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


def test_build_graph_end_to_end(
    tiny_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["build-graph", "--root", str(tiny_project), "--json", "--compact"],
    )
    graph.main()

    html = (tiny_project / "docs" / "graph.html").read_text(encoding="utf-8")
    assert "core.py" in html
    assert "design.md" in html

    snapshot = json.loads(
        (tiny_project / "docs" / "graph.json").read_text(encoding="utf-8")
    )
    paths = {n["path"] for n in snapshot["nodes"]}
    assert "app/core.py" in paths
    assert "docs/design.md" in paths
    edge_types = {e["type"] for e in snapshot["edges"]}
    assert "code->code" in edge_types  # cli.py imports app.core
    assert "code->doc" in edge_types  # core.py mentioned in design.md

    compact = json.loads(
        (tiny_project / "docs" / "graph-compact.json").read_text(encoding="utf-8")
    )
    assert compact["legend"]
    assert compact["n"]
    assert compact["e"]


def test_bench_reports_sizes_without_writing(
    tiny_project: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["build-graph", "--root", str(tiny_project), "--bench"],
    )
    graph.main()

    out = capsys.readouterr().out
    assert "Context cost on this repo" in out
    assert "raw corpus (4 files)" in out
    assert "--json export (schema v1)" in out
    assert "--compact export (schema v2)" in out

    docs = tiny_project / "docs"
    assert not (docs / "graph.html").exists()
    assert not (docs / "graph.json").exists()
    assert not (docs / "graph-compact.json").exists()
