"""End-to-end tests for the graph.toml lifecycle: --init / --diff / --merge."""

import sys
import tomllib
from pathlib import Path

import pytest

from build_graph import graph


@pytest.fixture()
def tiny_project(tmp_path: Path) -> Path:
    (tmp_path / "app").mkdir(parents=True)
    (tmp_path / "docs" / "guides").mkdir(parents=True)
    (tmp_path / "app" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "app" / "core.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "docs" / "guides" / "intro.md").write_text(
        "# Intro\n", encoding="utf-8"
    )
    return tmp_path


def _run(argv: list[str], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["build-graph", *argv])
    graph.main()


def test_init_writes_config(
    tiny_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _run(["--root", str(tiny_project), "--init"], monkeypatch)
    config_path = tiny_project / "graph.toml"
    assert config_path.is_file()
    config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    assert config["docs"]["dir"] == "docs"
    assert {c["prefix"] for c in config["docs"]["categories"]} == {"guides"}
    rule_dirs = {r["dir"] for r in config["rules"]}
    assert "app" in rule_dirs
    # Every discovered category gets a colour pin in both palettes.
    assert set(config["colors"]) == set(config["colors_saturated"])
    assert "code/app" in config["colors"]


def test_init_refuses_overwrite_without_force(
    tiny_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _run(["--root", str(tiny_project), "--init"], monkeypatch)
    with pytest.raises(SystemExit) as exc:
        _run(["--root", str(tiny_project), "--init"], monkeypatch)
    assert exc.value.code == 2
    _run(["--root", str(tiny_project), "--init", "--force"], monkeypatch)


def test_diff_requires_existing_config(
    tiny_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(SystemExit) as exc:
        _run(["--root", str(tiny_project), "--init", "--diff"], monkeypatch)
    assert exc.value.code == 2


def test_diff_merge_roundtrip(
    tiny_project: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    _run(["--root", str(tiny_project), "--init"], monkeypatch)

    # Freshly generated config covers everything.
    _run(["--root", str(tiny_project), "--init", "--diff"], monkeypatch)
    assert "no drift" in capsys.readouterr().out

    # A file in an unknown top-level dir drifts.
    (tiny_project / "newmod").mkdir()
    (tiny_project / "newmod" / "thing.py").write_text("X = 1\n", encoding="utf-8")
    _run(["--root", str(tiny_project), "--init", "--diff"], monkeypatch)
    out = capsys.readouterr().out
    assert "code/newmod" in out
    assert "newmod/thing.py" in out

    # --merge appends coverage without touching existing content...
    before = (tiny_project / "graph.toml").read_text(encoding="utf-8")
    _run(["--root", str(tiny_project), "--init", "--merge"], monkeypatch)
    after = (tiny_project / "graph.toml").read_text(encoding="utf-8")
    assert after.startswith(before.rstrip("\n").rsplit("[colors]", 1)[0][:100])
    config = tomllib.loads(after)
    assert {"dir": "newmod", "type": "code/newmod"} in config["rules"]
    assert "code/newmod" in config["colors"]
    assert "code/newmod" in config["colors_saturated"]

    # ...after which the drift is gone.
    capsys.readouterr()
    _run(["--root", str(tiny_project), "--init", "--diff"], monkeypatch)
    assert "no drift" in capsys.readouterr().out
