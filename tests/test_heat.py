"""Tests for the Heat overlay: per-file commit counts (--heat-days)."""

import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from build_graph._heat import collect_heat_data


def _git(repo: Path, *args: str, env: dict | None = None) -> None:
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=T", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        env=env,
    )


def _commit_at(repo: Path, path: str, content: str, iso_date: str) -> None:
    """Write `path`, stage it, commit with both author/committer dates forced."""
    (repo / path).write_text(content, encoding="utf-8")
    _git(repo, "add", path)
    env = {**os.environ, "GIT_AUTHOR_DATE": iso_date, "GIT_COMMITTER_DATE": iso_date}
    _git(repo, "commit", "-q", "-m", f"touch {path}", env=env)


class TestCollectHeatData:
    def test_not_a_repo(self, tmp_path: Path) -> None:
        assert collect_heat_data(tmp_path) is None

    def test_repo_with_no_commits(self, tmp_path: Path) -> None:
        _git(tmp_path, "init", "-q")
        assert collect_heat_data(tmp_path) is None

    def test_whole_history_counts_every_touching_commit(self, tmp_path: Path) -> None:
        _git(tmp_path, "init", "-q")
        _commit_at(tmp_path, "a.py", "A = 1\n", "2020-01-01T12:00:00")
        _commit_at(tmp_path, "a.py", "A = 2\n", "2020-01-02T12:00:00")
        _commit_at(tmp_path, "b.py", "B = 1\n", "2020-01-03T12:00:00")
        heat = collect_heat_data(tmp_path)
        assert heat == {"a.py": 2, "b.py": 1}

    def test_since_window_excludes_older_commits(self, tmp_path: Path) -> None:
        _git(tmp_path, "init", "-q")
        _commit_at(tmp_path, "old.py", "O = 1\n", "2020-01-01T12:00:00")
        now_iso = datetime.now(timezone.utc).isoformat()
        _commit_at(tmp_path, "recent.py", "R = 1\n", now_iso)
        # Whole history sees both paths.
        assert collect_heat_data(tmp_path) == {"old.py": 1, "recent.py": 1}
        # A 1-day window excludes the 2020 commit but keeps the one just made.
        windowed = collect_heat_data(tmp_path, days=1)
        assert windowed == {"recent.py": 1}

    def test_empty_window_is_empty_dict_not_none(self, tmp_path: Path) -> None:
        _git(tmp_path, "init", "-q")
        _commit_at(tmp_path, "a.py", "A = 1\n", "2020-01-01T12:00:00")
        # days=0 -> --since=0.days -> nothing in a repo whose only commit is
        # backdated to 2020; a valid (empty) result, not "git unavailable".
        assert collect_heat_data(tmp_path, days=0) == {}

    def test_multiple_paths_in_one_commit(self, tmp_path: Path) -> None:
        _git(tmp_path, "init", "-q")
        (tmp_path / "x.py").write_text("X = 1\n", encoding="utf-8")
        (tmp_path / "y.py").write_text("Y = 1\n", encoding="utf-8")
        _git(tmp_path, "add", "-A")
        env = {
            **os.environ,
            "GIT_AUTHOR_DATE": "2020-01-01T12:00:00",
            "GIT_COMMITTER_DATE": "2020-01-01T12:00:00",
        }
        _git(tmp_path, "commit", "-q", "-m", "init", env=env)
        assert collect_heat_data(tmp_path) == {"x.py": 1, "y.py": 1}
