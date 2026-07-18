"""Tests for find-related-docs git modes, dir mode and the CLI report."""

import subprocess
import sys
from pathlib import Path

import pytest

from build_graph import related
from build_graph.related import (
    _check_git_files,
    find_related_docs_by_filename,
    find_related_docs_for_dir,
    get_git_modified_files,
    get_git_staged_files,
    load_md_files,
    resolve_path,
)


@pytest.fixture(autouse=True)
def _fresh_caches() -> None:
    """Process-wide memo caches are keyed by (possibly relative) path strings.

    Fine for the one-shot CLI, but tests chdir between tmp dirs — a cached
    resolve of "docs" from a previous test would leak into the next one.
    """
    related._RESOLVED_DIR_CACHE.clear()
    related._MD_META_CACHE.clear()


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=T", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    (tmp_path / "app").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / "app" / "core.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "app" / "orphan.py").write_text("X = 2\n", encoding="utf-8")
    (tmp_path / "docs" / "design.md").write_text(
        "# Design\n\nLogic lives in `core.py`.\n\n"
        "Legacy module `legacy.py` was removed.\n",
        encoding="utf-8",
    )
    return tmp_path


class TestFindRelatedDocsByFilename:
    def test_backtick_mention(self, project: Path) -> None:
        results, verbose = find_related_docs_by_filename(
            "legacy.py", str(project / "docs")
        )
        assert set(results) == {"design.md"}
        assert verbose["design.md"][0][0] == 5

    def test_table_row_mention(self, project: Path) -> None:
        (project / "docs" / "table.md").write_text(
            "| file | role |\n|---|---|\n| table_hit.py | helper |\n",
            encoding="utf-8",
        )
        results, _ = find_related_docs_by_filename(
            "table_hit.py", str(project / "docs")
        )
        assert results["table.md"] == 1

    def test_code_block_mention(self, project: Path) -> None:
        (project / "docs" / "block.md").write_text(
            "# Block\n\n```\npython block_hit.py --flag\n```\n",
            encoding="utf-8",
        )
        results, _ = find_related_docs_by_filename(
            "block_hit.py", str(project / "docs")
        )
        assert results["block.md"] == 1

    def test_test_class_pattern(self, project: Path) -> None:
        (project / "docs" / "tests.md").write_text(
            "# Tests\n\nSee TestAccessControl for the auth suite.\n",
            encoding="utf-8",
        )
        results, _ = find_related_docs_by_filename(
            "test_access_control.py", str(project / "docs")
        )
        assert results["tests.md"] == 1

    def test_missing_docs_dir(self, tmp_path: Path) -> None:
        results, verbose = find_related_docs_by_filename(
            "core.py", str(tmp_path / "nope")
        )
        assert results == {}
        assert verbose == {}


class TestFindRelatedDocsForDir:
    def test_only_mentioned_files_reported(self, project: Path) -> None:
        results = find_related_docs_for_dir(
            str(project / "app"), str(project / "docs")
        )
        assert set(results) == {"app/core.py"} or set(results) == {"app\\core.py"}
        (key,) = results
        assert results[key] == {"design.md": 1}

    def test_missing_dir(self, project: Path) -> None:
        assert find_related_docs_for_dir(
            str(project / "nope"), str(project / "docs")
        ) == {}


class TestGitFileLists:
    @pytest.fixture()
    def repo(self, project: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        _git(project, "init", "-q")
        _git(project, "add", "-A")
        _git(project, "commit", "-q", "-m", "init")
        monkeypatch.chdir(project)
        return project

    def test_staged_files(self, repo: Path) -> None:
        (repo / "app" / "new.py").write_text("N = 1\n", encoding="utf-8")
        _git(repo, "add", "app/new.py")
        _git(repo, "rm", "-q", "app/orphan.py")
        files_ar, files_d, all_files = get_git_staged_files()
        assert [str(p) for p in files_ar] == [str(Path("app/new.py"))]
        assert [str(p) for p in files_d] == [str(Path("app/orphan.py"))]
        assert len(all_files) == 2

    def test_modified_files_dedup(self, repo: Path) -> None:
        # Staged modification…
        (repo / "app" / "core.py").write_text("VALUE = 2\n", encoding="utf-8")
        _git(repo, "add", "app/core.py")
        # …then a further unstaged one on the same file: must come back once.
        (repo / "app" / "core.py").write_text("VALUE = 3\n", encoding="utf-8")
        (repo / "app" / "orphan.py").write_text("X = 9\n", encoding="utf-8")
        modified = get_git_modified_files()
        assert sorted(str(p) for p in modified) == [
            str(Path("app/core.py")),
            str(Path("app/orphan.py")),
        ]

    def test_no_repo_returns_empty(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        assert get_git_modified_files() == []
        files_ar, files_d, all_files = get_git_staged_files()
        assert (files_ar, files_d, all_files) == ([], [], [])


class TestResolvePath:
    def test_bare_filename_unique(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(project)
        assert resolve_path("core.py") == (project / "app" / "core.py").resolve()

    def test_explicit_path_kept(self, project: Path) -> None:
        p = str(project / "app" / "core.py")
        assert resolve_path(p) == Path(p).resolve()

    def test_multiple_matches_exit(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (project / "other").mkdir()
        (project / "other" / "core.py").write_text("Y = 1\n", encoding="utf-8")
        monkeypatch.chdir(project)
        with pytest.raises(SystemExit):
            resolve_path("core.py")

    def test_not_found_exit(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(project)
        with pytest.raises(SystemExit):
            resolve_path("ghost.py")


class TestCheckGitFiles:
    def test_triage(self, project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(project)
        docs_dir = str(project / "docs")
        md_cache = load_md_files(docs_dir)
        git_files = [
            Path("app/core.py"),  # exists, mentioned in design.md
            Path("app/orphan.py"),  # exists, no doc mentions
            Path("app/legacy.py"),  # deleted, mentioned in design.md
            Path("docs/design.md"),  # doc file — skipped
            Path("data.bin"),  # not code/config — skipped
        ]
        with_docs, without_docs, not_found = _check_git_files(
            git_files, docs_dir, md_cache, handle_deleted=True
        )
        assert [str(f) for f, _, _ in with_docs] == [str(Path("app/core.py"))]
        assert [str(f) for f in without_docs] == [str(Path("app/orphan.py"))]
        assert [str(f) for f, _, _ in not_found] == [str(Path("app/legacy.py"))]

    def test_deleted_skipped_without_flag(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(project)
        docs_dir = str(project / "docs")
        md_cache = load_md_files(docs_dir)
        _, _, not_found = _check_git_files(
            [Path("app/legacy.py")], docs_dir, md_cache, handle_deleted=False
        )
        assert not_found == []


class TestMainGitModes:
    @pytest.fixture()
    def repo(self, project: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        _git(project, "init", "-q")
        _git(project, "add", "-A")
        _git(project, "commit", "-q", "-m", "init")
        monkeypatch.chdir(project)
        return project

    def _run_main(self, monkeypatch: pytest.MonkeyPatch, *argv: str) -> None:
        monkeypatch.setattr(sys, "argv", ["find-related-docs", *argv])
        related.main()

    def test_git_added(
        self,
        repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        (repo / "app" / "new.py").write_text("N = 1\n", encoding="utf-8")
        _git(repo, "add", "app/new.py")
        self._run_main(monkeypatch, "--git-added")
        out = capsys.readouterr().out
        assert "1 staged file(s)" in out
        assert "No documentation mentions" in out  # new.py has no docs

    def test_git_added_empty(
        self,
        repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        self._run_main(monkeypatch, "--git-added")
        assert "No files staged" in capsys.readouterr().out

    def test_git_modified_all_ok(
        self,
        repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        (repo / "app" / "core.py").write_text("VALUE = 2\n", encoding="utf-8")
        self._run_main(monkeypatch, "--git-modified")
        out = capsys.readouterr().out
        assert "core.py mentioned in 1 doc(s)" in out
        assert "All modified files have documentation mentions" in out

    def test_git_modified_empty(
        self,
        repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        self._run_main(monkeypatch, "--git-modified")
        assert "No modified files found" in capsys.readouterr().out

    def test_single_file_verbose(
        self,
        repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        self._run_main(monkeypatch, "app/core.py", "-v")
        out = capsys.readouterr().out
        assert "design.md" in out
        assert ":3" in out  # verbose line number

    def test_directory_mode(
        self,
        repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        self._run_main(monkeypatch, str(repo / "app"))
        out = capsys.readouterr().out
        assert "core.py" in out
        assert "design.md" in out

    def test_no_mentions_single_file(
        self,
        repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        self._run_main(monkeypatch, "app/orphan.py")
        assert "No documentation files" in capsys.readouterr().out
