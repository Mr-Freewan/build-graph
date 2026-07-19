"""Tests for the ref-diff overlay (--diff-base): statuses + edge diff."""

import subprocess
from pathlib import Path

import pytest

from build_graph._diff import (
    _build_snapshot,
    apply_edge_diff,
    collect_ref_diff,
    materialize_ref,
)
from build_graph._git import (
    add_ghost_nodes_and_edges,
    apply_git_status_to_live_nodes,
)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=T", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


@pytest.fixture()
def diff_repo(tmp_path: Path) -> Path:
    """One base commit, then staged head changes covering every diff case.

    Base:  a.py -> b.py, a.py -> gone.py, user.py -> old.py
    Head:  gone.py deleted (edge removed), c.py added with a.py -> c.py
           (edge added), old.py renamed to new.py with the import updated
           (edge must survive the rename as "same").
    """
    (tmp_path / "a.py").write_text("import b\nimport gone\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("B = 1\n", encoding="utf-8")
    (tmp_path / "gone.py").write_text("G = 1\n", encoding="utf-8")
    (tmp_path / "old.py").write_text("X = 1\n", encoding="utf-8")
    (tmp_path / "user.py").write_text("import old\n", encoding="utf-8")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "base")

    (tmp_path / "a.py").write_text("import b\nimport c\n", encoding="utf-8")
    (tmp_path / "c.py").write_text("C = 1\n", encoding="utf-8")
    _git(tmp_path, "rm", "-q", "gone.py")
    _git(tmp_path, "mv", "old.py", "new.py")
    (tmp_path / "user.py").write_text("import new\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    return tmp_path


class TestCollectRefDiff:
    def test_statuses(self, diff_repo: Path) -> None:
        status = collect_ref_diff(diff_repo, "HEAD")
        assert status is not None
        assert status["added"] == ["c.py"]
        assert status["deleted"] == ["gone.py"]
        assert status["renamed"] == {"old.py": "new.py"}
        assert set(status["modified"]) == {"a.py", "user.py"}

    def test_unknown_ref(self, diff_repo: Path) -> None:
        assert collect_ref_diff(diff_repo, "no-such-ref") is None

    def test_not_a_repo(self, tmp_path: Path) -> None:
        assert collect_ref_diff(tmp_path, "HEAD") is None


class TestMaterializeRef:
    def test_extracts_base_tree(self, diff_repo: Path, tmp_path_factory) -> None:
        dest = tmp_path_factory.mktemp("base")
        assert materialize_ref(diff_repo, "HEAD", dest)
        assert (dest / "gone.py").exists()  # still present at the base ref
        assert not (dest / "c.py").exists()  # head-only file absent

    def test_bad_ref(self, diff_repo: Path, tmp_path_factory) -> None:
        dest = tmp_path_factory.mktemp("base-bad")
        assert not materialize_ref(diff_repo, "no-such-ref", dest)


class TestCollectRefDiffTwoRefs:
    """Explicit --diff-base + --diff-head: both sides are real refs, so a
    decoy worktree edit made after the head commit must not show up.
    """

    @pytest.fixture()
    def two_ref_repo(self, tmp_path: Path) -> Path:
        (tmp_path / "a.py").write_text("import b\n", encoding="utf-8")
        (tmp_path / "b.py").write_text("B = 1\n", encoding="utf-8")
        _git(tmp_path, "init", "-q")
        _git(tmp_path, "add", "-A")
        _git(tmp_path, "commit", "-q", "-m", "base")

        (tmp_path / "a.py").write_text("import b\nimport c\n", encoding="utf-8")
        (tmp_path / "c.py").write_text("C = 1\n", encoding="utf-8")
        _git(tmp_path, "add", "-A")
        _git(tmp_path, "commit", "-q", "-m", "head")

        # Decoy: uncommitted worktree change after the head commit — must
        # be invisible to an explicit base..head ref diff.
        (tmp_path / "d.py").write_text("D = 1\n", encoding="utf-8")
        _git(tmp_path, "add", "-A")
        return tmp_path

    def test_statuses_ignore_worktree_after_head(self, two_ref_repo: Path) -> None:
        status = collect_ref_diff(two_ref_repo, "HEAD~1", "HEAD")
        assert status is not None
        assert status["added"] == ["c.py"]
        assert status["modified"] == ["a.py"]

    def test_worktree_diff_sees_the_decoy(self, two_ref_repo: Path) -> None:
        status = collect_ref_diff(two_ref_repo, "HEAD~1")
        assert status is not None
        assert set(status["added"]) == {"c.py", "d.py"}

    def test_unknown_head_ref(self, two_ref_repo: Path) -> None:
        assert collect_ref_diff(two_ref_repo, "HEAD~1", "no-such-ref") is None

    def test_edge_diff_across_two_materialized_refs(
        self, two_ref_repo: Path, tmp_path_factory
    ) -> None:
        head_dest = tmp_path_factory.mktemp("head")
        assert materialize_ref(two_ref_repo, "HEAD", head_dest)
        assert not (head_dest / "d.py").exists()  # decoy never entered a ref

        nodes, edges = _build_snapshot(head_dest, {}, "full", True, False)
        git_data = collect_ref_diff(two_ref_repo, "HEAD~1", "HEAD")
        assert git_data is not None
        add_ghost_nodes_and_edges(nodes, edges, git_data, [], head_dest)
        info = apply_edge_diff(
            nodes, edges, two_ref_repo, "HEAD~1", {}, {}, "full", True, False
        )
        assert info == {"edgesAdded": 1, "edgesRemoved": 0}
        by_key = {(e["source"], e["target"]): e for e in edges}
        assert by_key[("a.py", "c.py")]["diffStatus"] == "added"
        assert by_key[("a.py", "b.py")]["diffStatus"] == "same"


class TestApplyEdgeDiff:
    def _run(self, repo: Path) -> tuple[list[dict], list[dict], dict]:
        nodes, edges = _build_snapshot(repo, {}, "full", True, False)
        git_data = collect_ref_diff(repo, "HEAD")
        assert git_data is not None
        apply_git_status_to_live_nodes(nodes, git_data)
        md_nodes = [n for n in nodes if n["path"].endswith(".md")]
        add_ghost_nodes_and_edges(nodes, edges, git_data, md_nodes, repo)
        info = apply_edge_diff(
            nodes, edges, repo, "HEAD", git_data["renamed"], {}, "full", True, False
        )
        assert info is not None
        return nodes, edges, info

    def test_edge_statuses(self, diff_repo: Path) -> None:
        _nodes, edges, info = self._run(diff_repo)
        by_key = {(e["source"], e["target"]): e for e in edges}

        assert by_key[("a.py", "b.py")]["diffStatus"] == "same"
        assert by_key[("a.py", "c.py")]["diffStatus"] == "added"
        # The base edge followed the rename — not removed + added.
        assert by_key[("user.py", "new.py")]["diffStatus"] == "same"

        removed = by_key[("a.py", "ghost::gone.py")]
        assert removed["diffStatus"] == "removed"
        assert removed["ghost"] is True
        assert removed["type"] == "code->code"

        assert info == {"edgesAdded": 1, "edgesRemoved": 1}

    def test_ghost_edges_not_annotated(self, diff_repo: Path) -> None:
        _nodes, edges, _info = self._run(diff_repo)
        for e in edges:
            if e["type"] == "rename":
                assert "diffStatus" not in e

    def test_bad_base_returns_none(self, diff_repo: Path) -> None:
        nodes, edges = _build_snapshot(diff_repo, {}, "full", True, False)
        info = apply_edge_diff(
            nodes, edges, diff_repo, "no-such-ref", {}, {}, "full", True, False
        )
        assert info is None
