"""Tests for find-related-docs helpers."""

from pathlib import Path

import pytest

from build_graph.related import find_related_docs, load_md_files


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    (tmp_path / "app").mkdir()
    (tmp_path / "docs" / "internal").mkdir(parents=True)
    (tmp_path / "app" / "core.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "docs" / "design.md").write_text(
        "# Design\n\nLogic lives in `core.py`.\n", encoding="utf-8"
    )
    (tmp_path / "docs" / "internal" / "notes.md").write_text(
        "Private notes about `core.py`.\n", encoding="utf-8"
    )
    return tmp_path


def test_load_md_files_no_exclusion_by_default(project: Path) -> None:
    loaded = load_md_files(str(project / "docs"))
    names = {p.name for p, _, _ in loaded}
    assert names == {"design.md", "notes.md"}


def test_load_md_files_exclude_dirs(project: Path) -> None:
    loaded = load_md_files(str(project / "docs"), ("internal",))
    names = {p.name for p, _, _ in loaded}
    assert names == {"design.md"}


def test_find_related_docs_backtick_mention(project: Path) -> None:
    results, verbose = find_related_docs(
        str(project / "app" / "core.py"),
        str(project / "docs"),
        verbose=True,
        md_cache=load_md_files(str(project / "docs"), ("internal",)),
    )
    assert set(results) == {"design.md"}
    assert results["design.md"] == 1
    (line_num, line) = verbose["design.md"][0]
    assert line_num == 3
    assert "core.py" in line
