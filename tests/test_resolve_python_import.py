"""Unit tests for Python import resolution used by code->code edges."""

from pathlib import Path

import pytest

from build_graph._build import _resolve_python_import, _split_dotted_module


@pytest.fixture()
def pkg_project(tmp_path: Path) -> Path:
    (tmp_path / "pkg" / "sub").mkdir(parents=True)
    (tmp_path / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "pkg" / "mod.py").write_text("", encoding="utf-8")
    (tmp_path / "pkg" / "sub" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "pkg" / "sub" / "deep.py").write_text("", encoding="utf-8")
    return tmp_path


def test_absolute_import_resolves(pkg_project: Path) -> None:
    got = _resolve_python_import("pkg.mod", 0, Path("other/file.py"), pkg_project)
    assert got == "pkg/mod.py"


def test_absolute_import_missing_target(pkg_project: Path) -> None:
    assert _resolve_python_import("pkg.nope", 0, Path("x.py"), pkg_project) is None


def test_absolute_import_empty_module(pkg_project: Path) -> None:
    assert _resolve_python_import("", 0, Path("x.py"), pkg_project) is None


def test_relative_level1_sibling(pkg_project: Path) -> None:
    got = _resolve_python_import("mod", 1, Path("pkg/main.py"), pkg_project)
    assert got == "pkg/mod.py"


def test_relative_level2_parent_package(pkg_project: Path) -> None:
    got = _resolve_python_import("mod", 2, Path("pkg/sub/deep.py"), pkg_project)
    assert got == "pkg/mod.py"


def test_relative_level_beyond_root(pkg_project: Path) -> None:
    assert _resolve_python_import("mod", 4, Path("pkg/mod.py"), pkg_project) is None


def test_absolute_import_src_layout(tmp_path: Path) -> None:
    # src-layout: import root is src/, returned path stays repo-relative.
    (tmp_path / "src" / "pkg").mkdir(parents=True)
    (tmp_path / "src" / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "src" / "pkg" / "mod.py").write_text("", encoding="utf-8")
    got = _resolve_python_import("pkg.mod", 0, Path("tests/test_mod.py"), tmp_path)
    assert got == "src/pkg/mod.py"


def test_absolute_import_root_wins_over_src(pkg_project: Path) -> None:
    # A flat-layout match takes priority over the src/ fallback.
    (pkg_project / "src" / "pkg").mkdir(parents=True)
    (pkg_project / "src" / "pkg" / "mod.py").write_text("", encoding="utf-8")
    got = _resolve_python_import("pkg.mod", 0, Path("x.py"), pkg_project)
    assert got == "pkg/mod.py"


def test_package_import_never_falls_back_to_init(pkg_project: Path) -> None:
    # `import pkg.sub` targets pkg/sub.py (absent), NOT pkg/sub/__init__.py.
    assert _resolve_python_import("pkg.sub", 0, Path("x.py"), pkg_project) is None


def test_split_dotted_module() -> None:
    assert _split_dotted_module("foo.bar") == ("foo.bar", 0)
    assert _split_dotted_module(".sibling") == ("sibling", 1)
    assert _split_dotted_module("..pkg.sub") == ("pkg.sub", 2)
    assert _split_dotted_module("...") == ("", 3)
