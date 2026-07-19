#!/usr/bin/env python3
"""Query a graph snapshot from the command line.

Works on the JSON exports written by ``build-graph --json`` (schema v1)
or ``build-graph --compact`` (schema v2) — the format is auto-detected.

Usage:
    graph-query blast-radius app/core.py
    graph-query hubs --top 15
    graph-query stale-docs --check
    graph-query orphans --type code
"""

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from build_graph._common import Colors
from build_graph._console import ensure_utf8_stdout

# Edges that carry "depends on" semantics: source imports / references target.
_DEPENDENCY_TYPES = ("code->code", "type-only")
# Edges that link a code file to a doc that mentions it.
_DOC_LINK_TYPES = ("code->doc", "docstring")

_CODE_TO_NAME = {
    "c2d": "code->doc",
    "c2c": "code->code",
    "d2d": "doc->doc",
    "dcs": "docstring",
    "typ": "type-only",
    "ren": "rename",
}


@dataclass
class Snapshot:
    """Normalized graph snapshot, independent of the export schema."""

    paths: list[str]
    types: list[str]
    degrees: list[int]
    # (source_idx, target_idx, verbose_edge_type, lines)
    edges: list[tuple[int, int, str, list[int]]] = field(default_factory=list)
    ghosts: set[int] = field(default_factory=set)

    def is_live(self, idx: int) -> bool:
        return idx not in self.ghosts


def _load_v1(data: dict) -> Snapshot:
    nodes = data["nodes"]
    snap = Snapshot(
        paths=[n["path"] for n in nodes],
        types=[n["type"] for n in nodes],
        degrees=[n["degree"] for n in nodes],
        ghosts={i for i, n in enumerate(nodes) if n.get("ghost")},
    )
    id_to_idx = {n["id"]: i for i, n in enumerate(nodes)}
    for e in data["edges"]:
        si = id_to_idx.get(e["source"])
        ti = id_to_idx.get(e["target"])
        if si is None or ti is None or e["type"] == "rename":
            continue
        snap.edges.append((si, ti, e["type"], e.get("lines") or []))
    return snap


def _load_v2(data: dict) -> Snapshot:
    code_to_cat = {v: k for k, v in data["legend"]["c"].items()}
    code_to_type = {v: k for k, v in data["legend"]["t"].items()}
    code_to_type.update(_CODE_TO_NAME)  # safety net for a stripped legend
    nodes = data["n"]
    snap = Snapshot(
        paths=[n["p"] for n in nodes],
        types=[code_to_cat.get(n["t"], n["t"]) for n in nodes],
        degrees=[n["d"] for n in nodes],
        ghosts={i for i, n in enumerate(nodes) if n.get("G")},
    )
    for row in data["e"]:  # ghost edges ("ge") are deliberately skipped
        etype = code_to_type.get(row[2], row[2])
        if etype == "rename":
            continue
        lines = row[3] if len(row) > 3 else []
        snap.edges.append((row[0], row[1], etype, lines))
    return snap


def load_snapshot(input_path: Path) -> Snapshot:
    """Read a v1 or v2 export; the schema is detected from its keys."""
    data = json.loads(input_path.read_text(encoding="utf-8"))
    if data.get("v") == "2.0":
        return _load_v2(data)
    if data.get("schema_version") == "1.0":
        return _load_v1(data)
    raise ValueError(
        f"{input_path} is neither a --json (schema v1) nor a --compact "
        "(schema v2) export"
    )


def _default_input(root: Path) -> Path:
    for candidate in ("docs/graph-compact.json", "docs/graph.json"):
        p = root / candidate
        if p.is_file():
            return p
    print(
        f"No snapshot found under {root} (tried docs/graph-compact.json, "
        "docs/graph.json).\nRun `build-graph --compact` first, or pass --input.",
        file=sys.stderr,
    )
    sys.exit(2)


def _resolve_node(snap: Snapshot, query: str) -> int:
    """Match a user-supplied path against snapshot nodes.

    Exact path first, then unique suffix (so `core.py` works when there is
    only one). Ambiguity and no-match are fatal: candidates are listed.
    """
    q = query.replace("\\", "/").strip("/")
    matches = [
        i
        for i, p in enumerate(snap.paths)
        if snap.is_live(i) and (p == q or p.endswith("/" + q))
    ]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        print(f"No node matches '{query}'.", file=sys.stderr)
    else:
        print(f"'{query}' is ambiguous, matches:", file=sys.stderr)
        for i in matches:
            print(f"  {snap.paths[i]}", file=sys.stderr)
    sys.exit(2)


def _parse_edge_filter(raw: str) -> set[str]:
    out = set()
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        out.add(_CODE_TO_NAME.get(token, token))
    return out


# ---------------------------------------------------------------- blast-radius


def cmd_blast_radius(snap: Snapshot, args: argparse.Namespace) -> int:
    target = _resolve_node(snap, args.path)
    dep_types = _parse_edge_filter(args.edges) if args.edges else set(_DEPENDENCY_TYPES)

    # Reverse adjacency: who depends on me (edge source -> target = "source
    # imports/references target"), walked transitively from the target.
    reverse: dict[int, list[tuple[int, str, list[int]]]] = {}
    for si, ti, etype, lines in snap.edges:
        if etype in dep_types and snap.is_live(si) and snap.is_live(ti):
            reverse.setdefault(ti, []).append((si, etype, lines))

    hits: dict[int, tuple[int, int, str, list[int]]] = {}  # idx -> (depth, via, ...)
    frontier = [target]
    depth = 0
    while frontier and (args.depth is None or depth < args.depth):
        depth += 1
        next_frontier: list[int] = []
        for at in frontier:
            for si, etype, lines in reverse.get(at, []):
                if si == target or si in hits:
                    continue
                hits[si] = (depth, at, etype, lines)
                next_frontier.append(si)
        frontier = next_frontier

    # Docs mentioning the target or any affected file (one hop).
    affected = [target, *hits]
    doc_rows: dict[int, tuple[int, str, list[int]]] = {}
    for si, ti, etype, lines in snap.edges:
        if etype in _DOC_LINK_TYPES and si in affected and snap.is_live(ti):
            doc_rows.setdefault(ti, (si, etype, lines))

    if args.as_json:
        print(
            json.dumps(
                {
                    "target": snap.paths[target],
                    "dependents": [
                        {
                            "path": snap.paths[i],
                            "depth": d,
                            "via": snap.paths[via],
                            "type": etype,
                            "lines": lines,
                        }
                        for i, (d, via, etype, lines) in sorted(
                            hits.items(), key=lambda kv: (kv[1][0], snap.paths[kv[0]])
                        )
                    ],
                    "docs": [
                        {
                            "path": snap.paths[di],
                            "via": snap.paths[si],
                            "type": etype,
                            "lines": lines,
                        }
                        for di, (si, etype, lines) in sorted(
                            doc_rows.items(), key=lambda kv: snap.paths[kv[0]]
                        )
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    c = Colors
    print(
        f"\n{c.BOLD}Blast radius of {snap.paths[target]}{c.RESET} "
        f"({len(hits)} dependent(s), {len(doc_rows)} doc(s)):"
    )
    if not hits:
        print("  no dependents — nothing imports or references this file")
    by_depth: dict[int, list[int]] = {}
    for i, (d, *_rest) in hits.items():
        by_depth.setdefault(d, []).append(i)
    for d in sorted(by_depth):
        print(f"\n  depth {d}:")
        for i in sorted(by_depth[d], key=lambda i: snap.paths[i]):
            _, via, etype, lines = hits[i]
            loc = f" (line {', '.join(map(str, lines))})" if lines else ""
            via_note = f" via {snap.paths[via]}" if via != target else ""
            print(f"    {snap.paths[i]:<50} {etype}{loc}{via_note}")
    if doc_rows:
        print("\n  docs:")
        for di in sorted(doc_rows, key=lambda i: snap.paths[i]):
            si, etype, lines = doc_rows[di]
            loc = f" (line {', '.join(map(str, lines))})" if lines else ""
            print(f"    {snap.paths[di]:<50} {etype}{loc} via {snap.paths[si]}")
    print()
    return 0


# ------------------------------------------------------------------------ hubs


def cmd_hubs(snap: Snapshot, args: argparse.Namespace) -> int:
    incoming = [0] * len(snap.paths)
    outgoing = [0] * len(snap.paths)
    for si, ti, _etype, _lines in snap.edges:
        if snap.is_live(si) and snap.is_live(ti):
            outgoing[si] += 1
            incoming[ti] += 1
    ranked = sorted(
        (i for i in range(len(snap.paths)) if snap.is_live(i)),
        key=lambda i: (-(incoming[i] + outgoing[i]), snap.paths[i]),
    )[: args.top]

    if args.as_json:
        print(
            json.dumps(
                [
                    {
                        "path": snap.paths[i],
                        "type": snap.types[i],
                        "degree": incoming[i] + outgoing[i],
                        "in": incoming[i],
                        "out": outgoing[i],
                    }
                    for i in ranked
                ],
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    c = Colors
    print(f"\n{c.BOLD}Top {len(ranked)} hubs{c.RESET} (by in+out edges):\n")
    print(f"  {'deg':>4} {'in':>4} {'out':>4}  {'type':<20} path")
    for i in ranked:
        print(
            f"  {incoming[i] + outgoing[i]:>4} {incoming[i]:>4} {outgoing[i]:>4}"
            f"  {snap.types[i]:<20} {snap.paths[i]}"
        )
    print()
    return 0


# ------------------------------------------------------------------ stale-docs


def _git_commit_times(root: Path) -> dict[str, int] | None:
    """Last-commit unix time per file, from one full-history `git log` pass.

    The log is newest-first, so the first occurrence of a path wins.
    Returns ``None`` when git is unavailable — caller falls back to mtime.
    """
    try:
        result = subprocess.run(
            ["git", "log", "--format=%x01%ct", "--name-only"],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    times: dict[str, int] = {}
    current = 0
    for line in result.stdout.splitlines():
        if line.startswith("\x01"):
            current = int(line[1:] or 0)
        elif line.strip():
            times.setdefault(line.strip(), current)
    return times


def cmd_stale_docs(snap: Snapshot, args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    git_times = _git_commit_times(root)
    if git_times is None:
        print("(git unavailable — using filesystem mtimes)", file=sys.stderr)

    def timestamp(path: str) -> int | None:
        if git_times is not None and path in git_times:
            return git_times[path]
        try:
            return int((root / path).stat().st_mtime)
        except OSError:
            return None

    linked: dict[int, list[int]] = {}
    for si, ti, etype, _lines in snap.edges:
        if etype in _DOC_LINK_TYPES and snap.is_live(si) and snap.is_live(ti):
            linked.setdefault(ti, []).append(si)

    stale: list[tuple[int, str, int, str, int]] = []  # gap, doc, doc_ts, code, code_ts
    for di, sources in linked.items():
        doc_ts = timestamp(snap.paths[di])
        if doc_ts is None:
            continue
        newest_ts, newest_path = 0, ""
        for si in sources:
            ts = timestamp(snap.paths[si])
            if ts is not None and ts > newest_ts:
                newest_ts, newest_path = ts, snap.paths[si]
        if newest_ts > doc_ts:
            stale.append(
                (newest_ts - doc_ts, snap.paths[di], doc_ts, newest_path, newest_ts)
            )
    stale.sort(reverse=True)

    def day(ts: int) -> str:
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")

    if args.as_json:
        print(
            json.dumps(
                [
                    {
                        "doc": doc,
                        "doc_date": day(doc_ts),
                        "code": code,
                        "code_date": day(code_ts),
                        "gap_days": gap // 86400,
                    }
                    for gap, doc, doc_ts, code, code_ts in stale
                ],
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        c = Colors
        if not stale:
            print("No stale docs — every linked doc is newer than its code.")
        else:
            print(
                f"\n{c.BOLD}{len(stale)} doc(s) older than the code they "
                f"describe{c.RESET} (sorted by gap):\n"
            )
            for gap, doc, doc_ts, code, code_ts in stale:
                print(
                    f"  {doc:<50} {day(doc_ts)}  <-  {code} "
                    f"changed {day(code_ts)} (+{gap // 86400}d)"
                )
            print()
    return 1 if stale and args.check else 0


# --------------------------------------------------------------------- orphans


def cmd_orphans(snap: Snapshot, args: argparse.Namespace) -> int:
    rows = [
        i
        for i in range(len(snap.paths))
        if snap.is_live(i)
        and snap.degrees[i] == 0
        and (not args.type or args.type in snap.types[i])
    ]
    if args.as_json:
        print(
            json.dumps(
                [{"path": snap.paths[i], "type": snap.types[i]} for i in rows],
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    c = Colors
    label = f" of type *{args.type}*" if args.type else ""
    print(f"\n{c.BOLD}{len(rows)} orphan(s){label}{c.RESET} (degree 0):\n")
    for i in rows:
        print(f"  {snap.types[i]:<20} {snap.paths[i]}")
    print()
    return 0


# ------------------------------------------------------------------------- CLI


def main() -> None:
    """Entry point for the graph-query CLI."""
    ensure_utf8_stdout()
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--root",
        default=".",
        help="Project root the snapshot paths are relative to (default: cwd)",
    )
    common.add_argument(
        "--input",
        default=None,
        help=(
            "Snapshot to query: a --json or --compact export "
            "(default: <root>/docs/graph-compact.json, then docs/graph.json)"
        ),
    )
    common.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="Machine-readable JSON output",
    )

    p = argparse.ArgumentParser(
        description="Query a build-graph JSON snapshot from the command line"
    )
    sub = p.add_subparsers(dest="command", required=True)

    br = sub.add_parser(
        "blast-radius",
        parents=[common],
        help="Everything affected by changing a file: transitive importers + docs",
    )
    br.add_argument("path", help="File to analyse (project-relative, suffix ok)")
    br.add_argument(
        "--depth", type=int, default=None, help="Limit traversal depth (default: none)"
    )
    br.add_argument(
        "--edges",
        default=None,
        help=(
            "Comma-separated edge types to traverse "
            "(names or codes, default: code->code,type-only)"
        ),
    )

    hubs = sub.add_parser(
        "hubs", parents=[common], help="Most-connected nodes (in+out edges)"
    )
    hubs.add_argument("--top", type=int, default=10, help="How many rows (default 10)")

    sd = sub.add_parser(
        "stale-docs",
        parents=[common],
        help="Docs whose linked code changed after the doc was last touched",
    )
    sd.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 when stale docs are found (CI gate)",
    )

    orp = sub.add_parser(
        "orphans", parents=[common], help="Nodes with no edges at all (degree 0)"
    )
    orp.add_argument(
        "--type", default=None, help="Only categories containing this substring"
    )

    args = p.parse_args()
    root = Path(args.root).resolve()
    input_path = Path(args.input) if args.input else _default_input(root)
    try:
        snap = load_snapshot(input_path)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"Cannot load {input_path}: {exc}", file=sys.stderr)
        sys.exit(2)

    handler = {
        "blast-radius": cmd_blast_radius,
        "hubs": cmd_hubs,
        "stale-docs": cmd_stale_docs,
        "orphans": cmd_orphans,
    }[args.command]
    sys.exit(handler(snap, args))


if __name__ == "__main__":
    main()
