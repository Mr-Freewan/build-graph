"""Tests for the ultra-compact export (schema v3).

The load-bearing test is the round-trip: whatever v2 says the graph is, v3
has to say exactly the same, edge for edge and line for line. Everything v3
drops (degree, the index->path legend, per-edge type codes) must be
recomputable from what it keeps.
"""

import json
import sys
from pathlib import Path

import pytest

from build_graph import graph
from build_graph.graph import build_llm_export_ultra
from build_graph.query import load_snapshot


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
    (tmp_path / "setup.py").write_text("# root-level file\n", encoding="utf-8")
    (tmp_path / "docs" / "design.md").write_text(
        "# Design\n\nEntry point is `cli.py`, logic in [core](../app/core.py).\n"
        "See also [notes](notes.md).\n",
        encoding="utf-8",
    )
    (tmp_path / "docs" / "notes.md").write_text(
        "# Notes\n\nBack to [design](design.md).\n", encoding="utf-8"
    )
    # A third doc: --mock-git only synthesises its renamed pair when the
    # project has three of them.
    (tmp_path / "docs" / "guide.md").write_text(
        "# Guide\n\nStart at [notes](notes.md).\n", encoding="utf-8"
    )
    return tmp_path


def _build(project: Path, monkeypatch: pytest.MonkeyPatch, *extra: str) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build-graph",
            "--root",
            str(project),
            "--compact",
            "--ultra-compact",
            *extra,
        ],
    )
    graph.main()


def _read(project: Path, name: str) -> dict:
    return json.loads((project / "docs" / name).read_text(encoding="utf-8"))


def _edges_from_v2(data: dict) -> set[tuple[str, str, str, tuple[int, ...]]]:
    paths = [n["p"] for n in data["n"]]
    code_to_type = {v: k for k, v in data["legend"]["t"].items()}
    out = set()
    for row in data["e"] + data.get("ge", []):
        lines = tuple(row[3]) if len(row) > 3 else ()
        out.add((paths[row[0]], paths[row[1]], code_to_type[row[2]], lines))
    return out


def _paths_from_v3(data: dict) -> list[str]:
    cols = data["cols"]
    id_col, file_col = cols.index("id"), cols.index("file")
    by_id: dict[int, str] = {}
    for directory, rows in data["n"].items():
        prefix = "" if directory == "." else directory + "/"
        for row in rows:
            by_id[row[id_col]] = prefix + row[file_col]
    return [by_id[i] for i in range(len(by_id))]


def _edges_from_v3(data: dict) -> set[tuple[str, str, str, tuple[int, ...]]]:
    paths = _paths_from_v3(data)
    out = set()
    for section in ("e", "ge"):
        for name, groups in data.get(section, {}).items():
            edge_type, key_side = graph._ULTRA_SECTIONS[name]
            for key, items in groups:
                for item in items:
                    if isinstance(item, int):
                        other, lines = item, ()
                    elif isinstance(item[1], list):
                        other, lines = item[0], tuple(item[1])
                    else:
                        other, lines = item[0], (item[1],)
                    src, tgt = (other, key) if key_side else (key, other)
                    out.add((paths[src], paths[tgt], edge_type, lines))
    return out


@pytest.mark.parametrize("extra", [(), ("--mock-git",)], ids=["plain", "mock-git"])
def test_v3_carries_the_same_graph_as_v2(
    tiny_project: Path, monkeypatch: pytest.MonkeyPatch, extra: tuple[str, ...]
) -> None:
    _build(tiny_project, monkeypatch, *extra)
    v2 = _read(tiny_project, "graph-compact.json")
    v3 = _read(tiny_project, "graph-ultra.json")

    assert _paths_from_v3(v3) == [n["p"] for n in v2["n"]]
    assert _edges_from_v3(v3) == _edges_from_v2(v2)
    assert v3["stats"] == v2["stats"]


@pytest.mark.parametrize("extra", [(), ("--mock-git",)], ids=["plain", "mock-git"])
def test_degree_is_recomputable_from_v3(
    tiny_project: Path, monkeypatch: pytest.MonkeyPatch, extra: tuple[str, ...]
) -> None:
    """v3 drops `degree`; loading it back must reproduce v2's stored value."""
    _build(tiny_project, monkeypatch, *extra)
    v2 = _read(tiny_project, "graph-compact.json")
    snap = load_snapshot(tiny_project / "docs" / "graph-ultra.json")
    assert snap.degrees == [n["d"] for n in v2["n"]]


def test_v3_is_substantially_smaller_at_scale() -> None:
    """The compression claim, measured on a graph big enough to show it.

    On a handful of files v3 is *larger* than v2 — its legend spells out
    every section it uses, and that fixed cost dominates. The saving is
    proportional to the data, so the check needs a real-ish graph.
    """
    nodes = [
        {
            "id": f"m{i}.py",
            "path": f"pkg/sub{i % 12}/module_{i}.py",
            "type": "code/app",
            "degree": 0,
        }
        for i in range(300)
    ]
    edges = [
        {
            "source": f"m{i}.py",
            "target": f"m{(i * 7) % 300}.py",
            "type": "code->code",
            "lines": [i % 40 + 1],
        }
        for i in range(1200)
    ]
    cats = {"code/app": "app"}
    v2 = graph._compact_json(
        graph.build_llm_export_compact(nodes, edges, Path("/x"), False, cats)
    )
    v3 = graph._ultra_json(graph.build_llm_export_ultra(nodes, edges, cats))
    assert len(v3) < len(v2) * 0.6


def test_git_and_ghost_layers_survive(
    tiny_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _build(tiny_project, monkeypatch, "--mock-git")
    v3 = _read(tiny_project, "graph-ultra.json")
    v2 = _read(tiny_project, "graph-compact.json")

    assert v3["ghosts"] == [i for i, n in enumerate(v2["n"]) if n.get("G")]
    assert dict(v3["git"]) == {i: n["s"] for i, n in enumerate(v2["n"]) if n.get("s")}
    # A rename produces a ghost->live edge, which belongs to the ghost section.
    assert "renamed_to" in v3["ge"]
    assert "git" in v3["legend"] and "ghosts" in v3["legend"]


def test_root_level_files_sit_under_a_dot_heading(
    tiny_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _build(tiny_project, monkeypatch)
    v3 = _read(tiny_project, "graph-ultra.json")
    assert any(row[1] == "setup.py" for row in v3["n"]["."])


# --------------------------------------------------------------- metric layers

_NODES = [
    {"id": "a.py", "path": "app/a.py", "type": "code/app", "degree": 1},
    {"id": "b.py", "path": "app/b.py", "type": "code/app", "degree": 1},
]
_EDGES = [
    {"source": "a.py", "target": "b.py", "type": "code->code", "lines": [3]},
]
_CATS = {"code/app": "app"}


def test_metric_columns_absent_without_data() -> None:
    export = build_llm_export_ultra(_NODES, _EDGES, _CATS)
    assert export["cols"] == ["id", "file", "cat"]
    assert all(len(row) == 3 for row in export["n"]["app"])
    assert "git" not in export and "ghosts" not in export and "ge" not in export


def test_heat_and_coverage_become_columns() -> None:
    export = build_llm_export_ultra(
        _NODES,
        _EDGES,
        _CATS,
        heat_data={"app/a.py": 12},
        coverage_data={"app/a.py": 87.4},
    )
    assert export["cols"] == ["id", "file", "cat", "heat", "cov"]
    rows = {row[1]: row for row in export["n"]["app"]}
    assert rows["a.py"][3:] == [12, 87]
    # No history and no coverage entry: 0 commits, -1 = unmeasured.
    assert rows["b.py"][3:] == [0, -1]
    assert "heat" in export["legend"] and "cov" in export["legend"]


def test_single_line_is_scalar_and_many_stay_a_list() -> None:
    edges = [
        {"source": "a.py", "target": "b.py", "type": "code->code", "lines": [3]},
        {"source": "b.py", "target": "a.py", "type": "code->code", "lines": [4, 9]},
    ]
    export = build_llm_export_ultra(_NODES, edges, _CATS)
    items = dict(export["e"]["imported_by"])
    assert items[1] == [[0, 3]]
    assert items[0] == [[1, [4, 9]]]


def test_legend_describes_only_present_sections() -> None:
    export = build_llm_export_ultra(_NODES, _EDGES, _CATS)
    assert "imported_by" in export["legend"]
    assert "doc_mentions" not in export["legend"]
