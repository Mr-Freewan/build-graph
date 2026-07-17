"""Git overlay: working-tree status, ghost nodes, rename edges, mock data.

Everything here mutates the node/edge lists produced by `_config` /
`_build` in place; when git is unavailable the caller simply skips the
overlay (the graph itself never depends on it).
"""

import subprocess
from collections import defaultdict
from pathlib import Path

from build_graph.links import extract_file_references


def collect_git_status(project_root: Path) -> dict | None:
    """Collect git working-tree state grouped by category.

    Returns None when git is unavailable or this isn't a repo. Otherwise:
        {
            "added":    [path, ...],   # staged additions
            "modified": [path, ...],   # union of staged-M and unstaged-M
            "deleted":  [path, ...],   # union of staged-D and unstaged-D
            "renamed":  {old_path: new_path, ...},   # staged renames
        }
    Paths are POSIX, relative to project_root.
    """

    def _run(args: list[str]) -> list[str]:
        result = subprocess.run(
            args,
            cwd=project_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=5,
            check=True,
        )
        return [ln for ln in result.stdout.replace("\r\n", "\n").split("\n") if ln]

    try:
        # `git rev-parse --is-inside-work-tree` — fails fast if not a repo.
        subprocess.run(
            ["git", "-c", "core.quotePath=false", "rev-parse", "--is-inside-work-tree"],
            cwd=project_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=5,
            check=True,
        )
        # core.quotePath=false → non-ASCII paths come back as UTF-8, not octal
        # Staged status with rename detection: -M flag + --diff-filter
        staged = _run(
            [
                "git",
                "-c",
                "core.quotePath=false",
                "diff",
                "--cached",
                "--name-status",
                "-M",
                "--diff-filter=AMRD",
            ]
        )
        unstaged = _run(
            [
                "git",
                "-c",
                "core.quotePath=false",
                "diff",
                "--name-status",
                "--diff-filter=MD",
            ]
        )
    except (
        subprocess.CalledProcessError,
        FileNotFoundError,
        subprocess.TimeoutExpired,
        OSError,
    ):
        return None

    added: set[str] = set()
    modified: set[str] = set()
    deleted: set[str] = set()
    renamed: dict[str, str] = {}

    for line in staged:
        # Format: "A\tpath" or "R100\told\tnew" etc.
        parts = line.split("\t")
        if not parts:
            continue
        code = parts[0][:1]  # first letter
        if code == "A" and len(parts) >= 2:
            added.add(parts[1])
        elif code == "M" and len(parts) >= 2:
            modified.add(parts[1])
        elif code == "D" and len(parts) >= 2:
            deleted.add(parts[1])
        elif code == "R" and len(parts) >= 3:
            renamed[parts[1]] = parts[2]

    for line in unstaged:
        parts = line.split("\t")
        if not parts:
            continue
        code = parts[0][:1]
        if code == "M" and len(parts) >= 2:
            modified.add(parts[1])
        elif code == "D" and len(parts) >= 2:
            deleted.add(parts[1])

    # If a path is renamed (staged) AND further modified, keep it as renamed —
    # the rename pair already captures the change.
    for old in renamed:
        modified.discard(old)
        deleted.discard(old)

    return {
        "added": sorted(added),
        "modified": sorted(modified),
        "deleted": sorted(deleted),
        "renamed": dict(sorted(renamed.items())),
    }


def _classify_node_for_path(path: str) -> str:
    """Rough type classification for ghost nodes (no FS access required)."""
    if path.endswith(".md"):
        return "doc/ghost"
    if path.endswith(".py"):
        return "code/ghost"
    return "ghost/other"


def apply_git_status_to_live_nodes(
    nodes: list[dict],
    git_data: dict,
) -> None:
    """Annotate each live node with its gitStatus (added/modified/renamed/clean)."""
    added = set(git_data["added"])
    modified = set(git_data["modified"])
    renamed_new = set(git_data["renamed"].values())
    for node in nodes:
        # Node id for docs is relative to docs/, but path includes "docs/" prefix.
        # Compare against node["path"] which is project-root-relative.
        p = node["path"]
        if p in renamed_new:
            node["gitStatus"] = "renamed"
        elif p in added:
            node["gitStatus"] = "added"
        elif p in modified:
            node["gitStatus"] = "modified"
        else:
            node["gitStatus"] = "clean"


def add_ghost_nodes_and_edges(
    all_nodes: list[dict],
    all_edges: list[dict],
    git_data: dict,
    md_nodes: list[dict],
    project_root: Path,
) -> None:
    """Create ghost nodes for deleted + rename-old paths plus rename edges."""
    deleted = list(git_data["deleted"])
    rename_pairs = git_data["renamed"]
    rename_olds = list(rename_pairs.keys())

    ghost_paths: list[tuple[str, str]] = []  # (path, status)
    for p in deleted:
        ghost_paths.append((p, "deleted"))
    for p in rename_olds:
        ghost_paths.append((p, "renamed"))

    if not ghost_paths:
        return

    existing_ids = {n["id"] for n in all_nodes}
    path_to_id: dict[str, str] = {}
    for path, status in ghost_paths:
        # Prefixed id: doc nodes use "adr/foo.md" and code nodes use
        # "smm_bot_async/main.py" — prefixing avoids collisions and lets us
        # treat ghost ids as a separate namespace.
        node_id = "ghost::" + path
        if node_id in existing_ids:
            continue
        existing_ids.add(node_id)
        path_to_id[path] = node_id
        all_nodes.append(
            {
                "id": node_id,
                "label": Path(path).name,
                "stem": Path(path).stem,
                "type": _classify_node_for_path(path),
                "path": path,
                "degree": 0,
                "size": 6,
                "ghost": True,
                "gitStatus": status,
            }
        )

    # Rename edges (old ghost → new live)
    live_ids = {n["id"] for n in all_nodes if not n.get("ghost")}
    for old, new in rename_pairs.items():
        # Find the live node matching new path.
        new_node_id = None
        for n in all_nodes:
            if n.get("ghost"):
                continue
            if n["path"] == new:
                new_node_id = n["id"]
                break
        if not new_node_id:
            continue
        old_id = path_to_id.get(old)
        if not old_id:
            continue
        all_edges.append(
            {
                "source": old_id,
                "target": new_node_id,
                "type": "rename",
                "weight": 1,
                "lines": [],
                "ghost": True,
            }
        )

    # Doc → ghost references: scan live .md files for references to ghost paths.
    ghost_paths_set = {p for p, _ in ghost_paths}
    seen: set[tuple[str, str]] = set()
    for md_node in md_nodes:
        f = project_root / md_node["path"]
        src_id = md_node["id"]
        if src_id not in live_ids:
            continue
        try:
            file_lines = f.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        line_map: dict[str, list[int]] = defaultdict(list)
        for lineno, line_text in enumerate(file_lines, 1):
            for ref in extract_file_references(line_text):
                # Resolve ref against the source file's directory and check
                # if it lands inside the project root.
                try:
                    resolved = (f.parent / ref).resolve()
                    rel = resolved.relative_to(project_root).as_posix()
                except (ValueError, OSError):
                    continue
                if rel in ghost_paths_set:
                    line_map[rel].append(lineno)
        for ghost_path, lines in line_map.items():
            ghost_id = path_to_id.get(ghost_path)
            if not ghost_id:
                continue
            key = (src_id, ghost_id)
            if key in seen:
                continue
            seen.add(key)
            all_edges.append(
                {
                    "source": src_id,
                    "target": ghost_id,
                    "type": "doc->doc",
                    "weight": 1,
                    "lines": sorted(lines),
                    "ghost": True,
                }
            )


def apply_mock_git_status(
    all_nodes: list[dict],
    all_edges: list[dict],
) -> None:
    """Inject synthetic git overlay data covering all 5 categories.

    Used by --mock-git for visual testing without touching the real repo.
    Adds ghost nodes for deleted/renamed-old, a rename edge, a doc→ghost edge.
    """
    md_nodes = [
        n for n in all_nodes if not n.get("ghost") and n["path"].endswith(".md")
    ]
    py_nodes = [
        n for n in all_nodes if not n.get("ghost") and n["path"].endswith(".py")
    ]
    if not md_nodes or not py_nodes:
        return

    new_renamed_path = md_nodes[2]["path"] if len(md_nodes) > 2 else None

    # Build a synthetic git_data dict and run the standard annotator so every
    # other live node gets gitStatus="clean" by default.
    added = [md_nodes[0]["path"]]
    if len(py_nodes) > 1:
        added.append(py_nodes[1]["path"])
    modified = [py_nodes[0]["path"]]
    if len(md_nodes) > 1:
        modified.append(md_nodes[1]["path"])
    git_data = {
        "added": added,
        "modified": modified,
        "deleted": [],
        "renamed": (
            {"__demo_renamed_from.md": new_renamed_path} if new_renamed_path else {}
        ),
    }
    apply_git_status_to_live_nodes(all_nodes, git_data)

    def _ghost_node(path: str, status: str) -> dict:
        return {
            "id": "ghost::" + path,
            "label": Path(path).name,
            "stem": Path(path).stem,
            "type": _classify_node_for_path(path),
            "path": path,
            "degree": 0,
            "size": 6,
            "ghost": True,
            "gitStatus": status,
        }

    # Renamed pair: ghost-old → live-new
    if new_renamed_path:
        old = _ghost_node("__demo_renamed_from.md", "renamed")
        all_nodes.append(old)
        all_edges.append(
            {
                "source": old["id"],
                "target": md_nodes[2]["id"],
                "type": "rename",
                "weight": 1,
                "lines": [],
                "ghost": True,
            }
        )

    # Deleted with an incoming reference from a live md (stale link)
    ref_src = md_nodes[3] if len(md_nodes) > 3 else md_nodes[0]
    deleted_with_refs = _ghost_node("docs/__demo_deleted_with_refs.md", "deleted")
    all_nodes.append(deleted_with_refs)
    all_edges.append(
        {
            "source": ref_src["id"],
            "target": deleted_with_refs["id"],
            "type": "doc->doc",
            "weight": 1,
            "lines": [42],
            "ghost": True,
        }
    )

    # Standalone deleted (no refs anywhere)
    all_nodes.append(_ghost_node("__demo_deleted_orphan.md", "deleted"))
