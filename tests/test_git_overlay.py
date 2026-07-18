"""Tests for the git overlay: status collection, ghost nodes, mock data."""

import subprocess
from pathlib import Path

import pytest

from build_graph._git import (
    _classify_node_for_path,
    add_ghost_nodes_and_edges,
    apply_git_status_to_live_nodes,
    apply_mock_git_status,
    collect_git_status,
)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=T", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


@pytest.fixture()
def git_repo(tmp_path: Path) -> Path:
    """Repo with one commit, then a working tree covering every category."""
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "mod.py").write_text("A = 1\n", encoding="utf-8")
    (tmp_path / "app" / "del.py").write_text("B = 2\n", encoding="utf-8")
    (tmp_path / "app" / "old_name.py").write_text(
        "def func():\n    return 42\n", encoding="utf-8"
    )
    (tmp_path / "app" / "unstaged_del.py").write_text("C = 3\n", encoding="utf-8")
    (tmp_path / "keep.py").write_text("D = 4\n", encoding="utf-8")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "init")

    # added (staged)
    (tmp_path / "app" / "new.py").write_text("E = 5\n", encoding="utf-8")
    _git(tmp_path, "add", "app/new.py")
    # modified: one unstaged, one staged
    (tmp_path / "app" / "mod.py").write_text("A = 100\n", encoding="utf-8")
    (tmp_path / "keep.py").write_text("D = 400\n", encoding="utf-8")
    _git(tmp_path, "add", "keep.py")
    # deleted: one staged, one unstaged
    _git(tmp_path, "rm", "-q", "app/del.py")
    (tmp_path / "app" / "unstaged_del.py").unlink()
    # renamed (staged, identical content -> R100)
    _git(tmp_path, "mv", "app/old_name.py", "app/new_name.py")
    return tmp_path


class TestCollectGitStatus:
    def test_all_categories(self, git_repo: Path) -> None:
        status = collect_git_status(git_repo)
        assert status is not None
        assert status["added"] == ["app/new.py"]
        assert status["modified"] == ["app/mod.py", "keep.py"]
        assert status["deleted"] == ["app/del.py", "app/unstaged_del.py"]
        assert status["renamed"] == {"app/old_name.py": "app/new_name.py"}

    def test_clean_repo(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").write_text("A = 1\n", encoding="utf-8")
        _git(tmp_path, "init", "-q")
        _git(tmp_path, "add", "-A")
        _git(tmp_path, "commit", "-q", "-m", "init")
        status = collect_git_status(tmp_path)
        assert status == {"added": [], "modified": [], "deleted": [], "renamed": {}}

    def test_not_a_repo(self, tmp_path: Path) -> None:
        assert collect_git_status(tmp_path) is None


def test_classify_node_for_path() -> None:
    assert _classify_node_for_path("docs/design.md") == "doc/ghost"
    assert _classify_node_for_path("app/core.py") == "code/ghost"
    assert _classify_node_for_path("cfg/settings.toml") == "ghost/other"


class TestApplyGitStatusToLiveNodes:
    def test_statuses(self) -> None:
        nodes = [
            {"path": "app/new.py"},
            {"path": "app/mod.py"},
            {"path": "app/new_name.py"},
            {"path": "app/untouched.py"},
        ]
        git_data = {
            "added": ["app/new.py"],
            "modified": ["app/mod.py"],
            "deleted": [],
            "renamed": {"app/old_name.py": "app/new_name.py"},
        }
        apply_git_status_to_live_nodes(nodes, git_data)
        assert nodes[0]["gitStatus"] == "added"
        assert nodes[1]["gitStatus"] == "modified"
        assert nodes[2]["gitStatus"] == "renamed"
        assert nodes[3]["gitStatus"] == "clean"

    def test_renamed_wins_over_modified(self) -> None:
        nodes = [{"path": "app/new_name.py"}]
        git_data = {
            "added": [],
            "modified": ["app/new_name.py"],
            "deleted": [],
            "renamed": {"app/old_name.py": "app/new_name.py"},
        }
        apply_git_status_to_live_nodes(nodes, git_data)
        assert nodes[0]["gitStatus"] == "renamed"


class TestAddGhostNodesAndEdges:
    @pytest.fixture()
    def project(self, tmp_path: Path) -> Path:
        (tmp_path / "docs").mkdir()
        (tmp_path / "app").mkdir()
        (tmp_path / "docs" / "readme.md").write_text(
            "# Readme\n\nOld module lived in [del](../app/del.py).\n",
            encoding="utf-8",
        )
        return tmp_path

    def _fixture_graph(self) -> tuple[list[dict], list[dict], list[dict]]:
        md_node = {"id": "readme.md", "path": "docs/readme.md"}
        code_node = {"id": "app/new.py", "path": "app/new.py"}
        nodes = [md_node, code_node]
        return nodes, [], [md_node]

    def test_ghosts_rename_edge_and_doc_ref(self, project: Path) -> None:
        nodes, edges, md_nodes = self._fixture_graph()
        git_data = {
            "added": [],
            "modified": [],
            "deleted": ["app/del.py"],
            "renamed": {"app/old.py": "app/new.py"},
        }
        add_ghost_nodes_and_edges(nodes, edges, git_data, md_nodes, project)

        ghosts = {n["id"]: n for n in nodes if n.get("ghost")}
        assert set(ghosts) == {"ghost::app/del.py", "ghost::app/old.py"}
        assert ghosts["ghost::app/del.py"]["gitStatus"] == "deleted"
        assert ghosts["ghost::app/del.py"]["type"] == "code/ghost"
        assert ghosts["ghost::app/old.py"]["gitStatus"] == "renamed"

        rename_edges = [e for e in edges if e["type"] == "rename"]
        assert rename_edges == [
            {
                "source": "ghost::app/old.py",
                "target": "app/new.py",
                "type": "rename",
                "weight": 1,
                "lines": [],
                "ghost": True,
            }
        ]

        doc_edges = [e for e in edges if e["type"] == "doc->doc"]
        assert len(doc_edges) == 1
        assert doc_edges[0]["source"] == "readme.md"
        assert doc_edges[0]["target"] == "ghost::app/del.py"
        assert doc_edges[0]["lines"] == [3]

    def test_no_ghost_paths_is_noop(self, project: Path) -> None:
        nodes, edges, md_nodes = self._fixture_graph()
        git_data = {"added": [], "modified": [], "deleted": [], "renamed": {}}
        add_ghost_nodes_and_edges(nodes, edges, git_data, md_nodes, project)
        assert len(nodes) == 2
        assert edges == []

    def test_rename_without_live_target_skips_edge(self, project: Path) -> None:
        nodes, edges, md_nodes = self._fixture_graph()
        git_data = {
            "added": [],
            "modified": [],
            "deleted": [],
            "renamed": {"app/old.py": "app/gone.py"},
        }
        add_ghost_nodes_and_edges(nodes, edges, git_data, md_nodes, project)
        assert "ghost::app/old.py" in {n["id"] for n in nodes}
        assert edges == []


class TestApplyMockGitStatus:
    def _nodes(self) -> list[dict]:
        nodes = []
        for i in range(4):
            nodes.append({"id": f"doc{i}.md", "path": f"docs/doc{i}.md"})
        for i in range(2):
            nodes.append({"id": f"app/code{i}.py", "path": f"app/code{i}.py"})
        return nodes

    def test_all_categories_present(self) -> None:
        nodes = self._nodes()
        edges: list[dict] = []
        apply_mock_git_status(nodes, edges)

        by_path = {n["path"]: n for n in nodes}
        assert by_path["docs/doc0.md"]["gitStatus"] == "added"
        assert by_path["app/code1.py"]["gitStatus"] == "added"
        assert by_path["app/code0.py"]["gitStatus"] == "modified"
        assert by_path["docs/doc1.md"]["gitStatus"] == "modified"
        assert by_path["docs/doc2.md"]["gitStatus"] == "renamed"
        assert by_path["docs/doc3.md"]["gitStatus"] == "clean"

        ghost_paths = {n["path"] for n in nodes if n.get("ghost")}
        assert ghost_paths == {
            "__demo_renamed_from.md",
            "docs/__demo_deleted_with_refs.md",
            "__demo_deleted_orphan.md",
        }

        rename_edges = [e for e in edges if e["type"] == "rename"]
        assert len(rename_edges) == 1
        assert rename_edges[0]["source"] == "ghost::__demo_renamed_from.md"
        assert rename_edges[0]["target"] == "doc2.md"

        doc_edges = [e for e in edges if e["type"] == "doc->doc"]
        assert len(doc_edges) == 1
        assert doc_edges[0]["source"] == "doc3.md"
        assert doc_edges[0]["target"] == "ghost::docs/__demo_deleted_with_refs.md"
        assert doc_edges[0]["lines"] == [42]

    def test_noop_without_md_or_py(self) -> None:
        nodes = [{"id": "doc0.md", "path": "docs/doc0.md"}]
        edges: list[dict] = []
        apply_mock_git_status(nodes, edges)
        assert "gitStatus" not in nodes[0]
        assert edges == []
