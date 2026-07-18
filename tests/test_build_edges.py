"""Tests for edge building: code->code, type-only, dynamic imports, docstrings."""

from pathlib import Path

import pytest

from build_graph._build import (
    _parse_code_trees,
    add_code_code_edges,
    add_docstring_edges,
    build_doc_edges,
)


def _write(root: Path, rel: str, content: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _code_nodes(*ids: str) -> list[dict]:
    return [{"id": i, "path": i} for i in ids]


def _edges_by_type(edges: list[dict], edge_type: str) -> list[dict]:
    return [e for e in edges if e["type"] == edge_type]


class TestCodeCodeEdges:
    def test_regular_import(self, tmp_path: Path) -> None:
        _write(tmp_path, "pkg/a.py", "from pkg.b import X\n")
        _write(tmp_path, "pkg/b.py", "X = 1\n")
        nodes = _code_nodes("pkg/a.py", "pkg/b.py")
        trees = _parse_code_trees(nodes, tmp_path)
        edges = add_code_code_edges(nodes, tmp_path, trees)
        assert edges == [
            {
                "source": "pkg/a.py",
                "target": "pkg/b.py",
                "type": "code->code",
                "weight": 1,
                "lines": [1],
            }
        ]

    def test_type_checking_import_is_type_only(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "pkg/a.py",
            "from typing import TYPE_CHECKING\n"
            "if TYPE_CHECKING:\n"
            "    from pkg.b import X\n",
        )
        _write(tmp_path, "pkg/b.py", "X = 1\n")
        nodes = _code_nodes("pkg/a.py", "pkg/b.py")
        edges = add_code_code_edges(nodes, tmp_path, _parse_code_trees(nodes, tmp_path))
        assert _edges_by_type(edges, "code->code") == []
        (edge,) = _edges_by_type(edges, "type-only")
        assert edge["source"] == "pkg/a.py"
        assert edge["target"] == "pkg/b.py"
        assert edge["lines"] == [3]

    def test_runtime_and_type_only_are_parallel_edges(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "pkg/a.py",
            "from typing import TYPE_CHECKING\n"
            "from pkg.b import X\n"
            "if TYPE_CHECKING:\n"
            "    from pkg.b import Y\n",
        )
        _write(tmp_path, "pkg/b.py", "X = 1\nY = 2\n")
        nodes = _code_nodes("pkg/a.py", "pkg/b.py")
        edges = add_code_code_edges(nodes, tmp_path, _parse_code_trees(nodes, tmp_path))
        assert len(_edges_by_type(edges, "code->code")) == 1
        assert len(_edges_by_type(edges, "type-only")) == 1

    def test_repeat_imports_merge_lines_and_weight(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "pkg/a.py",
            "from pkg.b import X\nfrom pkg.b import Y\n",
        )
        _write(tmp_path, "pkg/b.py", "X = 1\nY = 2\n")
        nodes = _code_nodes("pkg/a.py", "pkg/b.py")
        (edge,) = add_code_code_edges(
            nodes, tmp_path, _parse_code_trees(nodes, tmp_path)
        )
        assert edge["weight"] == 2
        assert edge["lines"] == [1, 2]

    def test_relative_import(self, tmp_path: Path) -> None:
        _write(tmp_path, "pkg/a.py", "from . import b\n")
        _write(tmp_path, "pkg/b.py", "X = 1\n")
        nodes = _code_nodes("pkg/a.py", "pkg/b.py")
        (edge,) = add_code_code_edges(
            nodes, tmp_path, _parse_code_trees(nodes, tmp_path)
        )
        assert edge["target"] == "pkg/b.py"

    def test_external_import_skipped(self, tmp_path: Path) -> None:
        _write(tmp_path, "pkg/a.py", "import json\nfrom os import path\n")
        nodes = _code_nodes("pkg/a.py")
        edges = add_code_code_edges(nodes, tmp_path, _parse_code_trees(nodes, tmp_path))
        assert edges == []

    def test_syntax_error_file_skipped(self, tmp_path: Path) -> None:
        _write(tmp_path, "pkg/bad.py", "def broken(:\n")
        _write(tmp_path, "pkg/b.py", "X = 1\n")
        nodes = _code_nodes("pkg/bad.py", "pkg/b.py")
        trees = _parse_code_trees(nodes, tmp_path)
        assert "pkg/bad.py" not in trees
        assert add_code_code_edges(nodes, tmp_path, trees) == []


class TestDynamicImports:
    def test_import_module_literal(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "pkg/a.py",
            "import importlib\n\nmod = importlib.import_module(\"pkg.b\")\n",
        )
        _write(tmp_path, "pkg/b.py", "X = 1\n")
        nodes = _code_nodes("pkg/a.py", "pkg/b.py")
        edges = add_code_code_edges(nodes, tmp_path, _parse_code_trees(nodes, tmp_path))
        dynamic = [e for e in edges if e["target"] == "pkg/b.py"]
        assert len(dynamic) == 1
        assert dynamic[0]["type"] == "code->code"
        assert dynamic[0]["lines"] == [3]

    def test_dunder_import_literal(self, tmp_path: Path) -> None:
        _write(tmp_path, "pkg/a.py", "mod = __import__(\"pkg.b\")\n")
        _write(tmp_path, "pkg/b.py", "X = 1\n")
        nodes = _code_nodes("pkg/a.py", "pkg/b.py")
        (edge,) = add_code_code_edges(
            nodes, tmp_path, _parse_code_trees(nodes, tmp_path)
        )
        assert edge["target"] == "pkg/b.py"

    def test_const_folded_name(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "pkg/a.py",
            "import importlib\n\nMOD = \"pkg.b\"\n\n"
            "def load():\n    return importlib.import_module(MOD)\n",
        )
        _write(tmp_path, "pkg/b.py", "X = 1\n")
        nodes = _code_nodes("pkg/a.py", "pkg/b.py")
        edges = add_code_code_edges(nodes, tmp_path, _parse_code_trees(nodes, tmp_path))
        assert [e["target"] for e in edges] == ["pkg/b.py"]

    def test_annotated_const_folded_name(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "pkg/a.py",
            "import importlib\n\nMOD: str = \"pkg.b\"\n\n"
            "mod = importlib.import_module(MOD)\n",
        )
        _write(tmp_path, "pkg/b.py", "X = 1\n")
        nodes = _code_nodes("pkg/a.py", "pkg/b.py")
        edges = add_code_code_edges(nodes, tmp_path, _parse_code_trees(nodes, tmp_path))
        assert [e["target"] for e in edges] == ["pkg/b.py"]

    def test_relative_dynamic_import(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "pkg/a.py",
            "import importlib\n\n"
            "mod = importlib.import_module(\".b\", package=__name__)\n",
        )
        _write(tmp_path, "pkg/b.py", "X = 1\n")
        nodes = _code_nodes("pkg/a.py", "pkg/b.py")
        edges = add_code_code_edges(nodes, tmp_path, _parse_code_trees(nodes, tmp_path))
        assert [e["target"] for e in edges] == ["pkg/b.py"]

    def test_unresolvable_variable_silently_skipped(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "pkg/a.py",
            "import importlib\n\n"
            "def load(name):\n    return importlib.import_module(name)\n",
        )
        _write(tmp_path, "pkg/b.py", "X = 1\n")
        nodes = _code_nodes("pkg/a.py", "pkg/b.py")
        edges = add_code_code_edges(nodes, tmp_path, _parse_code_trees(nodes, tmp_path))
        assert [e["target"] for e in edges] == []


class TestDocstringEdges:
    def _build(
        self, tmp_path: Path, code: dict[str, str], extra_ids: set[str]
    ) -> list[dict]:
        for rel, content in code.items():
            _write(tmp_path, rel, content)
        nodes = _code_nodes(*code)
        trees = _parse_code_trees(nodes, tmp_path)
        all_ids = {n["id"] for n in nodes} | extra_ids
        return add_docstring_edges(nodes, all_ids, trees)

    def test_module_docstring_ref(self, tmp_path: Path) -> None:
        edges = self._build(
            tmp_path,
            {"pkg/a.py": '"""Core logic, see `pkg/b.py`."""\n\nX = 1\n'},
            {"pkg/b.py"},
        )
        assert edges == [
            {
                "source": "pkg/a.py",
                "target": "pkg/b.py",
                "type": "docstring",
                "weight": 1,
                "lines": [1],
            }
        ]

    def test_function_and_class_docstring_refs(self, tmp_path: Path) -> None:
        edges = self._build(
            tmp_path,
            {
                "pkg/a.py": (
                    "class C:\n"
                    '    """See `design.md`."""\n'
                    "\n"
                    "def f():\n"
                    '    """Uses `pkg/b.py`."""\n'
                )
            },
            {"pkg/b.py", "design.md"},
        )
        by_target = {e["target"]: e for e in edges}
        assert set(by_target) == {"design.md", "pkg/b.py"}
        assert by_target["design.md"]["lines"] == [1]  # class C lineno
        assert by_target["pkg/b.py"]["lines"] == [4]  # def f lineno

    def test_filename_resolves_to_unique_node(self, tmp_path: Path) -> None:
        # Ref is "docs/design.md" but the doc node id is "design.md" —
        # unambiguous filename match must connect them.
        edges = self._build(
            tmp_path,
            {"pkg/a.py": '"""See `docs/design.md`."""\n'},
            {"design.md"},
        )
        assert [e["target"] for e in edges] == ["design.md"]

    def test_ambiguous_filename_dropped(self, tmp_path: Path) -> None:
        edges = self._build(
            tmp_path,
            {"pkg/a.py": '"""See `util.py`."""\n'},
            {"x/util.py", "y/util.py"},
        )
        assert edges == []

    def test_self_reference_skipped(self, tmp_path: Path) -> None:
        edges = self._build(
            tmp_path,
            {"pkg/a.py": '"""This is `pkg/a.py`."""\n'},
            set(),
        )
        assert edges == []

    def test_repeat_refs_merge(self, tmp_path: Path) -> None:
        edges = self._build(
            tmp_path,
            {
                "pkg/a.py": (
                    '"""See `pkg/b.py`."""\n'
                    "\n"
                    "def f():\n"
                    '    """Also `pkg/b.py`."""\n'
                )
            },
            {"pkg/b.py"},
        )
        (edge,) = edges
        assert edge["weight"] == 2
        assert edge["lines"] == [1, 3]


class TestBuildDocEdges:
    def test_md_link_edge_with_lines(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "docs/a.md",
            "# A\n\nSee [b](b.md).\n\nAgain [b](b.md).\n",
        )
        _write(tmp_path, "docs/b.md", "# B\n")
        md_nodes = [
            {"id": "a.md", "path": "docs/a.md"},
            {"id": "b.md", "path": "docs/b.md"},
        ]
        edges = build_doc_edges(md_nodes, tmp_path)
        assert edges == [
            {
                "source": "a.md",
                "target": "b.md",
                "type": "doc->doc",
                "weight": 1,
                "lines": [3, 5],
            }
        ]

    def test_self_and_external_refs_skipped(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "docs/a.md",
            "See [self](a.md) and [gone](missing.md) and [ext](https://x.io/a.md).\n",
        )
        md_nodes = [{"id": "a.md", "path": "docs/a.md"}]
        assert build_doc_edges(md_nodes, tmp_path) == []
