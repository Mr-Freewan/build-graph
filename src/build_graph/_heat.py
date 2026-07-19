"""Git activity heatmap: per-file commit counts for the Heat overlay.

A third node-color mode alongside Type and Git status (see `_git.py`) —
independent data, no interaction with the git-status/diff/mock-git branches
in `graph.py`. Collected unconditionally whenever the build root is a real
git repository, mirroring `collect_git_status`.
"""

import subprocess
from collections import Counter
from pathlib import Path


def collect_heat_data(
    project_root: Path, days: int | None = None
) -> dict[str, int] | None:
    """Count commits touching each path.

    `days=None` (the default) scans the entire history; a number restricts
    the count to commits in the last N days (`git log --since=N.days`).
    Returns None when git is unavailable, this isn't a repo, or the repo
    has no commits at all. An empty dict is a valid result (real repo, no
    commits in the requested window) and is distinct from None — the UI
    treats it as "heat overlay available, everything cold".

    Renamed files are NOT followed: a path's count only covers commits
    recorded under its current name, so a recently-renamed file may read
    colder than its actual history. Documented as a known limitation
    rather than chasing full rename-tracking across an unbounded number
    of files.
    """
    try:
        subprocess.run(
            ["git", "-c", "core.quotePath=false", "rev-parse", "--is-inside-work-tree"],
            cwd=project_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=5,
            check=True,
        )
        args = [
            "git",
            "-c",
            "core.quotePath=false",
            "log",
            "--name-only",
            "--pretty=format:",
        ]
        if days is not None:
            args.append(f"--since={days}.days")
        result = subprocess.run(
            args,
            cwd=project_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            check=True,
        )
    except (
        subprocess.CalledProcessError,
        FileNotFoundError,
        subprocess.TimeoutExpired,
        OSError,
    ):
        return None
    counts: Counter[str] = Counter()
    for line in result.stdout.replace("\r\n", "\n").split("\n"):
        path = line.strip()
        if path:
            counts[path] += 1
    return dict(counts)
