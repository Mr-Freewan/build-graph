"""Tests for the graph-query CLI: loading, commands, exit codes."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from build_graph import query
from build_graph.query import Snapshot, load_snapshot

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


# ------------------------------------------------------------------ fixtures


def _v1_snapshot() -> dict:
    """a.py imports b.py imports c.py; b mentioned in guide.md; lone.py orphan."""
    return {
        "schema_version": "1.0",
        "project_root": "/x",
        "stats": {
            "node_count": 5,
            "edge_count": 3,
            "categories": ["code/app", "doc/docs"],
            "edge_types": ["code->code", "code->doc"],
            "git_available": False,
        },
        "nodes": [
            {
                "id": "a.py",
                "label": "a.py",
                "path": "app/a.py",
                "type": "code/app",
                "degree": 1,
            },
            {
                "id": "b.py",
                "label": "b.py",
                "path": "app/b.py",
                "type": "code/app",
                "degree": 3,
            },
            {
                "id": "c.py",
                "label": "c.py",
                "path": "app/c.py",
                "type": "code/app",
                "degree": 1,
            },
            {
                "id": "guide.md",
                "label": "guide.md",
                "path": "docs/guide.md",
                "type": "doc/docs",
                "degree": 1,
            },
            {
                "id": "lone.py",
                "label": "lone.py",
                "path": "app/lone.py",
                "type": "code/app",
                "degree": 0,
            },
        ],
        "edges": [
            {"source": "a.py", "target": "b.py", "type": "code->code", "lines": [1]},
            {"source": "b.py", "target": "c.py", "type": "code->code", "lines": [2]},
            {"source": "b.py", "target": "guide.md", "type": "code->doc", "lines": [7]},
        ],
    }


def _v2_snapshot() -> dict:
    """Same graph as _v1_snapshot in compact form."""
    return {
        "v": "2.0",
        "legend": {
            "i": {
                "0": "app/a.py",
                "1": "app/b.py",
                "2": "app/c.py",
                "3": "docs/guide.md",
                "4": "app/lone.py",
            },
            "n": "…",
            "e": "…",
            "t": {"code->doc": "c2d", "code->code": "c2c"},
            "c": {"code/app": "app", "doc/docs": "doc"},
            "s": {"modified": "mod"},
        },
        "stats": {"nodes": 5, "ghosts": 0, "edges": 3},
        "n": [
            {"p": "app/a.py", "t": "app", "d": 1},
            {"p": "app/b.py", "t": "app", "d": 3},
            {"p": "app/c.py", "t": "app", "d": 1},
            {"p": "docs/guide.md", "t": "doc", "d": 1},
            {"p": "app/lone.py", "t": "app", "d": 0},
        ],
        "e": [
            [0, 1, "c2c", [1]],
            [1, 2, "c2c", [2]],
            [1, 3, "c2d", [7]],
        ],
    }


@pytest.fixture()
def snap_v1(tmp_path: Path) -> Snapshot:
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(_v1_snapshot()), encoding="utf-8")
    return load_snapshot(p)


def _run_cli(*argv: str) -> int:
    old = sys.argv
    sys.argv = ["graph-query", *argv]
    try:
        query.main()
    except SystemExit as exc:
        return int(exc.code or 0)
    finally:
        sys.argv = old
    return 0


# ------------------------------------------------------------------- loading


def test_both_schemas_normalize_identically(tmp_path: Path) -> None:
    p1 = tmp_path / "graph.json"
    p1.write_text(json.dumps(_v1_snapshot()), encoding="utf-8")
    p2 = tmp_path / "graph-compact.json"
    p2.write_text(json.dumps(_v2_snapshot()), encoding="utf-8")
    assert load_snapshot(p1) == load_snapshot(p2)


def test_unknown_format_rejected(tmp_path: Path) -> None:
    p = tmp_path / "other.json"
    p.write_text('{"hello": 1}', encoding="utf-8")
    with pytest.raises(ValueError):
        load_snapshot(p)


# -------------------------------------------------------------- blast-radius


def test_blast_radius_transitive_with_docs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(_v1_snapshot()), encoding="utf-8")
    code = _run_cli("blast-radius", "c.py", "--input", str(p), "--json")
    assert code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["target"] == "app/c.py"
    deps = {d["path"]: d["depth"] for d in data["dependents"]}
    assert deps == {"app/b.py": 1, "app/a.py": 2}
    assert [d["path"] for d in data["docs"]] == ["docs/guide.md"]


def test_blast_radius_depth_cap(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(_v1_snapshot()), encoding="utf-8")
    _run_cli("blast-radius", "c.py", "--input", str(p), "--json", "--depth", "1")
    data = json.loads(capsys.readouterr().out)
    assert {d["path"] for d in data["dependents"]} == {"app/b.py"}


def test_blast_radius_ambiguous_suffix_exits_2(tmp_path: Path) -> None:
    doc = _v1_snapshot()
    doc["nodes"].append(
        {
            "id": "sub/a.py",
            "label": "a.py",
            "path": "app/sub/a.py",
            "type": "code/app",
            "degree": 0,
        }
    )
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    assert _run_cli("blast-radius", "a.py", "--input", str(p)) == 2


# ---------------------------------------------------------------------- hubs


def test_hubs_ranking(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(_v1_snapshot()), encoding="utf-8")
    _run_cli("hubs", "--input", str(p), "--json", "--top", "2")
    data = json.loads(capsys.readouterr().out)
    assert data[0]["path"] == "app/b.py"
    assert data[0] == {
        "path": "app/b.py",
        "type": "code/app",
        "degree": 3,
        "in": 1,
        "out": 2,
    }
    assert len(data) == 2


# ------------------------------------------------------------------- orphans


def test_orphans(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(_v1_snapshot()), encoding="utf-8")
    _run_cli("orphans", "--input", str(p), "--json")
    data = json.loads(capsys.readouterr().out)
    assert [r["path"] for r in data] == ["app/lone.py"]


# ---------------------------------------------------------------- stale-docs


def _git(repo: Path, *args: str, env_time: int) -> None:
    ts = f"{env_time} +0000"
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=T", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        env={
            **os.environ,
            "GIT_AUTHOR_DATE": ts,
            "GIT_COMMITTER_DATE": ts,
        },
    )


def test_stale_docs_git_repo(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Doc committed first, code changed later -> doc is stale."""
    (tmp_path / "app").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / "app" / "b.py").write_text("B = 1\n", encoding="utf-8")
    (tmp_path / "app" / "a.py").write_text("import b\n", encoding="utf-8")
    (tmp_path / "app" / "c.py").write_text("C = 1\n", encoding="utf-8")
    (tmp_path / "app" / "lone.py").write_text("L = 1\n", encoding="utf-8")
    (tmp_path / "docs" / "guide.md").write_text("see b.py\n", encoding="utf-8")
    now = int(time.time())
    _git(tmp_path, "init", "-q", env_time=now - 200_000)
    _git(tmp_path, "add", "-A", env_time=now - 200_000)
    _git(tmp_path, "commit", "-q", "-m", "init", env_time=now - 200_000)
    (tmp_path / "app" / "b.py").write_text("B = 2\n", encoding="utf-8")
    _git(tmp_path, "add", "-A", env_time=now)
    _git(tmp_path, "commit", "-q", "-m", "later", env_time=now)

    # Snapshot paths must match the repo layout (b.py mentioned in guide.md).
    snapshot = _v1_snapshot()
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(snapshot), encoding="utf-8")

    code = _run_cli("stale-docs", "--input", str(p), "--root", str(tmp_path), "--json")
    assert code == 0
    data = json.loads(capsys.readouterr().out)
    assert len(data) == 1
    assert data[0]["doc"] == "docs/guide.md"
    assert data[0]["code"] == "app/b.py"
    assert data[0]["gap_days"] == 200_000 // 86400

    # --check turns findings into a failing exit code.
    assert (
        _run_cli("stale-docs", "--input", str(p), "--root", str(tmp_path), "--check")
        == 1
    )


def test_stale_docs_mtime_fallback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """No git repo -> mtimes are used instead."""
    (tmp_path / "app").mkdir()
    (tmp_path / "docs").mkdir()
    for rel in ("app/a.py", "app/b.py", "app/c.py", "app/lone.py"):
        (tmp_path / rel).write_text("X = 1\n", encoding="utf-8")
    (tmp_path / "docs" / "guide.md").write_text("see b.py\n", encoding="utf-8")

    old = time.time() - 100_000
    os.utime(tmp_path / "docs" / "guide.md", (old, old))

    snapshot = _v1_snapshot()
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(snapshot), encoding="utf-8")
    monkey_root = str(tmp_path)
    code = _run_cli("stale-docs", "--input", str(p), "--root", monkey_root, "--json")
    assert code == 0
    data = json.loads(capsys.readouterr().out)
    assert [row["doc"] for row in data] == ["docs/guide.md"]


# ---------------------------------------------------------------------- e2e


def test_e2e_on_example_snapshot(capsys: pytest.CaptureFixture[str]) -> None:
    compact = EXAMPLES / "expected" / "graph-compact.json"
    code = _run_cli("blast-radius", "app/core.py", "--input", str(compact), "--json")
    assert code == 0
    data = json.loads(capsys.readouterr().out)
    assert [d["path"] for d in data["dependents"]] == ["app/cli.py"]
    assert [d["path"] for d in data["docs"]] == ["docs/design.md"]
