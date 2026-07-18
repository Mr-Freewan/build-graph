"""Tests for dead-code exemptions: names, globs, pyproject entry points."""

from pathlib import Path

from build_graph._render import apply_dead_exemptions, collect_entry_point_modules


def _write(root: Path, rel: str, content: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class TestCollectEntryPointModules:
    def test_flat_and_src_layout(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "pyproject.toml",
            '[project]\nname = "x"\n\n'
            "[project.scripts]\n"
            'run-flat = "tool.cli:main"\n'
            'run-src = "pkg.graph:main"\n'
            'run-missing = "pkg.nothere:main"\n',
        )
        _write(tmp_path, "tool/cli.py", "")
        _write(tmp_path, "src/pkg/graph.py", "")
        assert collect_entry_point_modules(tmp_path) == {
            "tool/cli.py",
            "src/pkg/graph.py",
        }

    def test_gui_scripts_table(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "pyproject.toml",
            '[project]\nname = "x"\n\n[project.gui-scripts]\napp = "gui.win:run"\n',
        )
        _write(tmp_path, "gui/win.py", "")
        assert collect_entry_point_modules(tmp_path) == {"gui/win.py"}

    def test_missing_pyproject(self, tmp_path: Path) -> None:
        assert collect_entry_point_modules(tmp_path) == set()

    def test_malformed_pyproject(self, tmp_path: Path) -> None:
        _write(tmp_path, "pyproject.toml", "not [ valid toml\n")
        assert collect_entry_point_modules(tmp_path) == set()

    def test_no_scripts_table(self, tmp_path: Path) -> None:
        _write(tmp_path, "pyproject.toml", '[project]\nname = "x"\n')
        assert collect_entry_point_modules(tmp_path) == set()

    def test_own_repo_entry_points(self) -> None:
        # The build-graph repo itself declares three console scripts.
        repo = Path(__file__).parent.parent
        assert collect_entry_point_modules(repo) == {
            "src/build_graph/graph.py",
            "src/build_graph/related.py",
            "src/build_graph/links.py",
        }


class TestApplyDeadExemptions:
    def _node(self, path: str) -> dict:
        return {"label": Path(path).name, "path": path}

    def test_entry_point_paths_exempt(self) -> None:
        nodes = [self._node("src/pkg/graph.py"), self._node("src/pkg/other.py")]
        apply_dead_exemptions(nodes, [], {"src/pkg/graph.py"})
        assert nodes[0].get("deadExempt") is True
        assert "deadExempt" not in nodes[1]

    def test_builtin_names_and_globs_still_work(self) -> None:
        nodes = [
            self._node("app/main.py"),
            self._node("tests/test_app.py"),
            self._node("scripts/oneoff.py"),
        ]
        apply_dead_exemptions(nodes, ["scripts/*"], set())
        assert all(n.get("deadExempt") for n in nodes)

    def test_ghost_nodes_untouched(self) -> None:
        node = {"label": "gone.py", "path": "app/gone.py", "ghost": True}
        apply_dead_exemptions([node], ["app/*"], set())
        assert "deadExempt" not in node
