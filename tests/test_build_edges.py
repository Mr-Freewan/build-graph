"""Tests for edge building: code->code, type-only, dynamic imports, docstrings."""

from pathlib import Path

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

    def test_from_package_import_submodule(self, tmp_path: Path) -> None:
        # `from pkg import b` — b is a submodule, not an attribute.
        _write(tmp_path, "app.py", "from pkg import b\n")
        _write(tmp_path, "pkg/b.py", "X = 1\n")
        nodes = _code_nodes("app.py", "pkg/b.py")
        (edge,) = add_code_code_edges(
            nodes, tmp_path, _parse_code_trees(nodes, tmp_path)
        )
        assert edge["target"] == "pkg/b.py"

    def test_from_src_layout_package_import_submodule(self, tmp_path: Path) -> None:
        _write(tmp_path, "tests/test_x.py", "from pkg import b\n")
        _write(tmp_path, "src/pkg/b.py", "X = 1\n")
        nodes = _code_nodes("tests/test_x.py", "src/pkg/b.py")
        (edge,) = add_code_code_edges(
            nodes, tmp_path, _parse_code_trees(nodes, tmp_path)
        )
        assert edge["target"] == "src/pkg/b.py"

    def test_relative_from_package_import_submodule(self, tmp_path: Path) -> None:
        # `from .sub import mod` — mod is a submodule of the sibling package.
        _write(tmp_path, "pkg/a.py", "from .sub import mod\n")
        _write(tmp_path, "pkg/sub/mod.py", "X = 1\n")
        nodes = _code_nodes("pkg/a.py", "pkg/sub/mod.py")
        (edge,) = add_code_code_edges(
            nodes, tmp_path, _parse_code_trees(nodes, tmp_path)
        )
        assert edge["target"] == "pkg/sub/mod.py"

    def test_attribute_import_not_resolved_as_submodule(self, tmp_path: Path) -> None:
        # `from pkg.b import X` — X is an attribute; only pkg/b.py is the edge.
        _write(tmp_path, "app.py", "from pkg.b import X\n")
        _write(tmp_path, "pkg/b.py", "X = 1\n")
        nodes = _code_nodes("app.py", "pkg/b.py")
        edges = add_code_code_edges(nodes, tmp_path, _parse_code_trees(nodes, tmp_path))
        assert [e["target"] for e in edges] == ["pkg/b.py"]

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
            'import importlib\n\nmod = importlib.import_module("pkg.b")\n',
        )
        _write(tmp_path, "pkg/b.py", "X = 1\n")
        nodes = _code_nodes("pkg/a.py", "pkg/b.py")
        edges = add_code_code_edges(nodes, tmp_path, _parse_code_trees(nodes, tmp_path))
        dynamic = [e for e in edges if e["target"] == "pkg/b.py"]
        assert len(dynamic) == 1
        assert dynamic[0]["type"] == "code->code"
        assert dynamic[0]["lines"] == [3]

    def test_dunder_import_literal(self, tmp_path: Path) -> None:
        _write(tmp_path, "pkg/a.py", 'mod = __import__("pkg.b")\n')
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
            'import importlib\n\nMOD = "pkg.b"\n\n'
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
            'import importlib\n\nMOD: str = "pkg.b"\n\n'
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
            'mod = importlib.import_module(".b", package=__name__)\n',
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
                    '"""See `pkg/b.py`."""\n\ndef f():\n    """Also `pkg/b.py`."""\n'
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


class TestCodeDocAttribution:
    """Basename fan-out: explicit-path mentions credit only the named file."""

    def _setup(self, tmp_path: Path) -> list[dict]:
        _write(tmp_path, "a/config.py", "A = 1\n")
        _write(tmp_path, "b/config.py", "B = 1\n")
        return [
            {"id": "a/config.py", "path": "a/config.py"},
            {"id": "b/config.py", "path": "b/config.py"},
        ]

    def _md_cache(self, *files: Path) -> list:
        cache = []
        for f in files:
            content = f.read_text(encoding="utf-8")
            cache.append((f, content, content.splitlines()))
        return cache

    def _run(self, tmp_path: Path, nodes: list[dict], doc_body: str) -> list[dict]:
        from build_graph._build import add_code_doc_edges

        doc = tmp_path / "docs" / "d.md"
        _write(tmp_path, "docs/d.md", doc_body)
        return add_code_doc_edges(
            nodes, {"docs/d.md": "d.md"}, tmp_path, self._md_cache(doc)
        )

    def test_explicit_path_credits_only_named_member(self, tmp_path: Path) -> None:
        nodes = self._setup(tmp_path)
        edges = self._run(tmp_path, nodes, "See `a/config.py` for details.\n")
        assert [(e["source"], e["lines"], e["weight"]) for e in edges] == [
            ("a/config.py", [1], 1)
        ]

    def test_bare_name_still_credits_whole_group(self, tmp_path: Path) -> None:
        nodes = self._setup(tmp_path)
        edges = self._run(tmp_path, nodes, "Every module has a `config.py`.\n")
        assert sorted(e["source"] for e in edges) == ["a/config.py", "b/config.py"]
        assert all(e["lines"] == [1] for e in edges)

    def test_mixed_lines_split_correctly(self, tmp_path: Path) -> None:
        nodes = self._setup(tmp_path)
        edges = self._run(
            tmp_path,
            nodes,
            "Start from `a/config.py`.\nThen check every `config.py`.\n",
        )
        by_src = {e["source"]: e for e in edges}
        assert by_src["a/config.py"]["lines"] == [1, 2]
        assert by_src["a/config.py"]["weight"] == 2
        assert by_src["b/config.py"]["lines"] == [2]
        assert by_src["b/config.py"]["weight"] == 1

    def test_unresolvable_path_falls_back_to_group(self, tmp_path: Path) -> None:
        nodes = self._setup(tmp_path)
        edges = self._run(tmp_path, nodes, "Legacy `old/gone/config.py` note.\n")
        assert sorted(e["source"] for e in edges) == ["a/config.py", "b/config.py"]

    def test_segment_boundary_not_substring(self, tmp_path: Path) -> None:
        # `b/config.py` must not match a path ending in `web/config.py`.
        _write(tmp_path, "web/config.py", "W = 1\n")
        _write(tmp_path, "b/config.py", "B = 1\n")
        nodes = [
            {"id": "web/config.py", "path": "web/config.py"},
            {"id": "b/config.py", "path": "b/config.py"},
        ]
        edges = self._run(tmp_path, nodes, "See `b/config.py`.\n")
        assert [e["source"] for e in edges] == ["b/config.py"]


class TestTreeListingAttribution:
    """Bare tree entries credit the file their reconstructed path names."""

    def _setup(self, tmp_path: Path) -> list[dict]:
        _write(tmp_path, "a/config.py", "A = 1\n")
        _write(tmp_path, "b/config.py", "B = 1\n")
        return [
            {"id": "a/config.py", "path": "a/config.py"},
            {"id": "b/config.py", "path": "b/config.py"},
        ]

    def _run(self, tmp_path: Path, nodes: list[dict], doc_body: str) -> list[dict]:
        from build_graph._build import add_code_doc_edges

        doc = tmp_path / "docs" / "d.md"
        _write(tmp_path, "docs/d.md", doc_body)
        content = doc.read_text(encoding="utf-8")
        cache = [(doc, content, content.splitlines())]
        return add_code_doc_edges(nodes, {"docs/d.md": "d.md"}, tmp_path, cache)

    def test_tree_entry_credits_only_tree_member(self, tmp_path: Path) -> None:
        nodes = self._setup(tmp_path)
        # The tree root (`proj/`) is not part of node paths — the suffix
        # ladder must still land on a/config.py, and only on it.
        body = (
            "Layout:\n\n```text\nproj/\n    a/\n        config.py"
            "      # the one\n    b/\n        other.py\n```\n"
        )
        edges = self._run(tmp_path, nodes, body)
        assert [(e["source"], e["lines"]) for e in edges] == [("a/config.py", [6])]

    def test_dir_and_files_on_one_line(self, tmp_path: Path) -> None:
        nodes = self._setup(tmp_path)
        body = "```text\nproj/\n    a/    config.py, extra.py\n```\n"
        edges = self._run(tmp_path, nodes, body)
        assert [(e["source"], e["lines"]) for e in edges] == [("a/config.py", [3])]

    def test_multi_dir_line_taints_branch(self, tmp_path: Path) -> None:
        nodes = self._setup(tmp_path)
        body = "```text\nproj/\n    a/ b/\n        config.py\n```\n"
        edges = self._run(tmp_path, nodes, body)
        assert sorted(e["source"] for e in edges) == ["a/config.py", "b/config.py"]

    def test_brace_dir_taints_branch(self, tmp_path: Path) -> None:
        nodes = self._setup(tmp_path)
        body = "```text\nproj/\n    a/{x,y}/\n        config.py\n```\n"
        edges = self._run(tmp_path, nodes, body)
        assert sorted(e["source"] for e in edges) == ["a/config.py", "b/config.py"]

    def test_unresolvable_tree_path_falls_back(self, tmp_path: Path) -> None:
        nodes = self._setup(tmp_path)
        body = "```text\nproj/\n    zzz/\n        config.py\n```\n"
        edges = self._run(tmp_path, nodes, body)
        assert sorted(e["source"] for e in edges) == ["a/config.py", "b/config.py"]

    def test_tree_paths_by_line_shapes(self) -> None:
        from build_graph._build import _tree_paths_by_line

        lines = [
            "prose config.py",  # outside a fence — ignored
            "```text",
            "pkg/sub/",
            "    deep/",
            "        one.py  # comment column",
            "    two.py",
            "```",
        ]
        assert _tree_paths_by_line(lines) == {
            5: ["pkg/sub/deep/one.py"],
            6: ["pkg/sub/two.py"],
        }

    def test_tree_entry_for_other_file_credits_nobody(self, tmp_path: Path) -> None:
        nodes = self._setup(tmp_path)
        # `model_config.py` contains `config.py` as a substring, so mention
        # detection fires — but the tree says which file the line is about.
        body = "```text\nproj/\n    a/\n        model_config.py\n```\n"
        edges = self._run(tmp_path, nodes, body)
        assert edges == []

    def test_tree_paths_box_drawing_indent(self) -> None:
        from build_graph._build import _tree_paths_by_line

        lines = ["```", "root/", "├── a/", "│   └── x.py", "```"]
        assert _tree_paths_by_line(lines) == {4: ["root/a/x.py"]}
