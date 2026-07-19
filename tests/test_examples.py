"""Keep examples/tiny-project and its expected exports in sync with the code."""

import json
import shutil
import sys
from pathlib import Path

import pytest

from build_graph import graph

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def test_tiny_project_matches_expected_exports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Copy out of the repo so the parent .git can't add a git overlay —
    # the reference files are generated git-free.
    project = tmp_path / "tiny-project"
    shutil.copytree(EXAMPLES / "tiny-project", project)

    monkeypatch.setattr(
        sys,
        "argv",
        ["build-graph", "--root", str(project), "--json", "--compact"],
    )
    graph.main()

    produced = json.loads((project / "docs" / "graph.json").read_text(encoding="utf-8"))
    produced["project_root"] = "/path/to/tiny-project"
    expected = json.loads(
        (EXAMPLES / "expected" / "graph.json").read_text(encoding="utf-8")
    )
    assert produced == expected

    produced_compact = json.loads(
        (project / "docs" / "graph-compact.json").read_text(encoding="utf-8")
    )
    expected_compact = json.loads(
        (EXAMPLES / "expected" / "graph-compact.json").read_text(encoding="utf-8")
    )
    assert produced_compact == expected_compact
