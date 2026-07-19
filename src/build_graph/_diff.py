"""Ref-diff mode: compare the dependency graph against a git base ref.

`--diff-base REF` builds the usual graph of the working tree (the head),
then materializes REF via `git archive` into a temp dir, builds the same
graph there and overlays the difference. `--diff-head REF` swaps the
working tree for a second materialized ref, so both sides come from
`git archive` and the comparison is base_ref vs head_ref exactly (worktree
changes after head_ref are not part of the diff):

- file-level statuses (added / modified / renamed / deleted) come from
  `git diff --name-status -M REF` and flow through the existing git
  overlay (ghost nodes, rename edges, git legend) unchanged;
- edges present only in the head are marked ``diffStatus="added"``, edges
  present only in the base are appended as ghost links with
  ``diffStatus="removed"`` (their endpoints resolve to live nodes or to
  the ghosts the overlay already created).

Edges are compared by (source path, target path, type); base paths go
through the rename map first so a dependency that merely followed a file
rename doesn't show up as removed + added.
"""

import io
import subprocess
import tarfile
import tempfile
from pathlib import Path

from build_graph._build import (
    _parse_code_trees,
    add_code_code_edges,
    add_code_doc_edges,
    add_docstring_edges,
    build_doc_edges,
)
from build_graph._config import build_all_nodes, list_project_files


def collect_ref_diff(
    project_root: Path, base_ref: str, head_ref: str | None = None
) -> dict | None:
    """File statuses between `base_ref` and `head_ref` (default: working tree).

    Same shape as `collect_git_status` (added / modified / deleted /
    renamed), so the standard overlay machinery applies as-is. Returns
    None when git is unavailable or a ref doesn't resolve. Untracked
    files never show up in `git diff` — they simply have no status.
    """
    diff_args = [base_ref, head_ref] if head_ref else [base_ref]
    try:
        result = subprocess.run(
            [
                "git",
                "-c",
                "core.quotePath=false",
                "diff",
                "--name-status",
                "-M",
                "--diff-filter=AMRD",
                *diff_args,
            ],
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

    added: set[str] = set()
    modified: set[str] = set()
    deleted: set[str] = set()
    renamed: dict[str, str] = {}
    lines = [ln for ln in result.stdout.replace("\r\n", "\n").split("\n") if ln]
    for line in lines:
        parts = line.split("\t")
        code = parts[0][:1] if parts else ""
        if code == "A" and len(parts) >= 2:
            added.add(parts[1])
        elif code == "M" and len(parts) >= 2:
            modified.add(parts[1])
        elif code == "D" and len(parts) >= 2:
            deleted.add(parts[1])
        elif code == "R" and len(parts) >= 3:
            renamed[parts[1]] = parts[2]

    for old in renamed:
        modified.discard(old)
        deleted.discard(old)

    return {
        "added": sorted(added),
        "modified": sorted(modified),
        "deleted": sorted(deleted),
        "renamed": dict(sorted(renamed.items())),
    }


def materialize_ref(project_root: Path, ref: str, dest: Path) -> bool:
    """Extract the tracked tree of `ref` into `dest` via `git archive`."""
    try:
        result = subprocess.run(
            ["git", "archive", "--format=tar", ref],
            cwd=project_root,
            capture_output=True,
            timeout=120,
            check=True,
        )
    except (
        subprocess.CalledProcessError,
        FileNotFoundError,
        subprocess.TimeoutExpired,
        OSError,
    ):
        return False
    try:
        with tarfile.open(fileobj=io.BytesIO(result.stdout)) as tar:
            try:
                tar.extractall(dest, filter="data")
            except TypeError:  # pre-3.11.4 tarfile has no filter kwarg
                tar.extractall(dest)
    except (tarfile.TarError, OSError):
        return False
    return True


def _edge_path_keys(
    nodes: list[dict],
    edges: list[dict],
    rename_map: dict[str, str] | None = None,
) -> set[tuple[str, str, str]]:
    """Edge set keyed by (source path, target path, type).

    Node ids are not stable across builds (doc ids are docs-dir relative),
    paths are. `rename_map` (old → new) translates base paths into head
    terms so renamed files keep their edge identity.
    """
    id_to_path = {n["id"]: n["path"] for n in nodes}
    ren = rename_map or {}
    keys: set[tuple[str, str, str]] = set()
    for e in edges:
        sp = id_to_path.get(e["source"])
        tp = id_to_path.get(e["target"])
        if sp is None or tp is None:
            continue
        keys.add((ren.get(sp, sp), ren.get(tp, tp), e["type"]))
    return keys


def _build_snapshot(
    root: Path,
    config: dict,
    scope: str,
    include_tests: bool,
    docs_only: bool,
) -> tuple[list[dict], list[dict]]:
    """The head build pipeline, replayed quietly on a materialized tree."""
    files, _git_used = list_project_files(root)
    nodes, _docs_dirname = build_all_nodes(
        files,
        config,
        scope=scope,
        include_tests=include_tests,
        docs_only=docs_only,
    )
    md_nodes = [n for n in nodes if n["path"].endswith(".md")]
    other_nodes = [n for n in nodes if not n["path"].endswith(".md")]
    py_nodes = [n for n in other_nodes if n["path"].endswith(".py")]

    edges: list[dict] = build_doc_edges(md_nodes, root)
    if not docs_only:
        path_to_doc_id = {n["path"]: n["id"] for n in md_nodes}
        md_cache = []
        for n in md_nodes:
            f = root / n["path"]
            try:
                content = f.read_text(encoding="utf-8")
            except Exception:
                continue
            md_cache.append((f, content, content.splitlines()))
        edges.extend(add_code_doc_edges(other_nodes, path_to_doc_id, root, md_cache))
        code_trees = _parse_code_trees(py_nodes, root)
        edges.extend(add_code_code_edges(py_nodes, root, code_trees))
        node_ids = {n["id"] for n in nodes}
        edges.extend(add_docstring_edges(py_nodes, node_ids, code_trees))
    return nodes, edges


def apply_edge_diff(
    all_nodes: list[dict],
    all_edges: list[dict],
    project_root: Path,
    base_ref: str,
    rename_map: dict[str, str],
    config: dict,
    scope: str,
    include_tests: bool,
    docs_only: bool,
) -> dict | None:
    """Annotate head edges and append removed base edges.

    Head edges get ``diffStatus`` "added"/"same"; base-only edges are
    appended with ``diffStatus`` "removed" and ``ghost=True`` so they only
    show in git mode. Returns {"edgesAdded": N, "edgesRemoved": M} or None
    when the base ref can't be materialized. Classification uses the
    current config for both sides — one lens, comparable results.
    """
    with tempfile.TemporaryDirectory(prefix="build-graph-base-") as tmp:
        base_root = Path(tmp)
        if not materialize_ref(project_root, base_ref, base_root):
            return None
        base_nodes, base_edges = _build_snapshot(
            base_root, config, scope, include_tests, docs_only
        )

    base_keys = _edge_path_keys(base_nodes, base_edges, rename_map)

    live = [n for n in all_nodes if not n.get("ghost")]
    id_to_path = {n["id"]: n["path"] for n in live}
    added_count = 0
    head_keys: set[tuple[str, str, str]] = set()
    for e in all_edges:
        if e.get("ghost") or e["type"] == "rename":
            continue
        sp = id_to_path.get(e["source"])
        tp = id_to_path.get(e["target"])
        if sp is None or tp is None:
            continue
        key = (sp, tp, e["type"])
        head_keys.add(key)
        if key in base_keys:
            e["diffStatus"] = "same"
        else:
            e["diffStatus"] = "added"
            added_count += 1

    # Ghost nodes carry their (old) path too, so one map resolves both.
    path_to_id = {n["path"]: n["id"] for n in all_nodes}
    removed_count = 0
    for sp, tp, etype in sorted(base_keys - head_keys):
        sid = path_to_id.get(sp)
        tid = path_to_id.get(tp)
        if sid is None or tid is None:
            # Endpoint is outside the head graph (scope change, deletion
            # without a ghost) — nothing to anchor the edge to.
            continue
        all_edges.append(
            {
                "source": sid,
                "target": tid,
                "type": etype,
                "weight": 1,
                "lines": [],
                "ghost": True,
                "diffStatus": "removed",
            }
        )
        removed_count += 1

    return {"edgesAdded": added_count, "edgesRemoved": removed_count}
