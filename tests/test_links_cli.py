"""CLI-level tests for verify-doc-links exit codes."""

import sys
from pathlib import Path

import pytest

from build_graph import links


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    (tmp_path / "app").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / "app" / "core.py").write_text("VALUE = 1\n", encoding="utf-8")
    return tmp_path


def _run(argv: list[str], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["verify-doc-links", *argv])
    links.main()


def test_clean_docs_exit_zero(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (project / "docs" / "good.md").write_text(
        "See [core](../app/core.py).\n", encoding="utf-8"
    )
    _run(["docs", "--root", str(project)], monkeypatch)  # no SystemExit


def test_broken_ref_exit_one(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (project / "docs" / "bad.md").write_text(
        "See [gone](../app/missing_file.py).\n", encoding="utf-8"
    )
    with pytest.raises(SystemExit) as exc:
        _run(["docs", "--root", str(project)], monkeypatch)
    assert exc.value.code == 1


def test_known_brokens_whitelist_suppresses(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (project / "docs" / "bad.md").write_text(
        "See [gone](../app/missing_file.py).\n", encoding="utf-8"
    )
    (project / "known-brokens.txt").write_text(
        "../app/missing_file.py\n", encoding="utf-8"
    )
    _run(["docs", "--root", str(project)], monkeypatch)  # no SystemExit


def test_missing_path_exit_two(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(SystemExit) as exc:
        _run(["nope", "--root", str(project)], monkeypatch)
    assert exc.value.code == 2
