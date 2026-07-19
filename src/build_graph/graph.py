#!/usr/bin/env python3
"""Generate an interactive HTML dependency graph for the project.

Usage:
    build-graph
    build-graph --docs-only
    build-graph --no-tests --output docs/graph.html
    build-graph --no-cdn
    build-graph --config path/to/graph.toml
    build-graph --mock-git    # synthetic git data for testing

Module layout:

    Python (build_graph package):
        _config.py — config load, autodiscovery classification, node
            building, graph.toml lifecycle (--init / --diff / --merge)
        _build.py  — edge building: doc->doc, code->doc, code->code
            (AST imports incl. TYPE_CHECKING / dynamic), docstring refs
        _git.py    — git overlay: status collection, ghost nodes,
            rename edges, --mock-git synthetic data
        _diff.py   — ref-diff mode (--diff-base[/--diff-head]): ref
            snapshots via git archive, edge-set diff, removed-edge ghosts
        _render.py — layout hints, palette, dead-code exemptions,
            packaged front-end resources, HTML assembly, D3 pinning
        graph.py   — LLM JSON exports (verbose + compact), CLI entry
            point and build orchestration (this file)

    JS (build_graph/resources/, search "// === ..."; concatenated in
    this order — it is a hard contract, see _render.py):
        i18n.js — I18N dictionary (10 locales), formatters, applyI18n
        engine.js:
        STATE & EDGE COLORS
        WIDTH LOCKING (lockAllI18nWidths)
        NEIGHBOR MAP & SIMULATION (nodes, links, forces)
        RENDER STATE & CANVAS ENGINE (draw loop, hit testing,
            node drag, pointer dispatch)
        PIN / EDGE FOCUS / DIM (overlay predicates)
        HOVER (onNodeEnter/onNodeLeave, hoverTimer)
        PATH MODE (shift+click BFS path)
        ui.js:
        CLICK HANDLERS (onNodeClick, dropAllSelections, info-close)
        INFO-PANEL RENDERING
        SEARCH (debounced)
        EXCLUSION FILTER
        VISIBILITY FILTER (showAll / orphansOnly / applyAllFilters)
        PREFS (savePrefs / loadPrefs)
        URL STATE (shareable view via location.hash)
        LEGEND (node types / edge types / orphans button)
        GIT OVERLAY (palettes, applyGitMode, buildGitLegend)
        FILE OPENING (IDE selector, buildFileHref)
        TOP-BAR HANDLERS (theme, palette, lang, ide, export/import)
        SLIDERS
        DRAG (makeDraggable + bindings — panels)
        TICK (orphan ring refit + requestDraw)
        EDGE TOOLTIP
        boot.js:
        INIT (applyI18n, loadPrefs, WARMUP & FIRST PAINT)
"""

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

from build_graph._build import (
    _parse_code_trees,
    add_code_code_edges,
    add_code_doc_edges,
    add_docstring_edges,
    build_doc_edges,
)
from build_graph._config import (
    build_all_nodes,
    handle_init,
    list_project_files,
    load_config,
)
from build_graph._console import ensure_utf8_stdout
from build_graph._diff import apply_edge_diff, collect_ref_diff, materialize_ref
from build_graph._git import (
    add_ghost_nodes_and_edges,
    apply_git_status_to_live_nodes,
    apply_mock_git_status,
    collect_git_status,
)
from build_graph._render import (
    apply_dead_exemptions,
    build_palette,
    collect_entry_point_modules,
    compute_layout_hints,
    render_html,
)

# 3-letter codes for compact LLM export (schema v2)
_TYPE_CODES: dict[str, str] = {
    "code->doc": "c2d",
    "code->code": "c2c",
    "doc->doc": "d2d",
    "docstring": "dcs",
    "type-only": "typ",
    "rename": "ren",
}
# Codes for the historical fixed category set stay pinned for output
# stability; categories introduced by autodiscovery get procedural codes
# via build_cat_codes.
_CAT_CODES_STATIC: dict[str, str] = {
    "doc/reference": "ref",
    "doc/explanation": "exp",
    "doc/how-to": "how",
    "doc/tutorials": "tut",
    "code/core": "cor",
    "code/infrastructure": "inf",
    "code/interfaces": "ifc",
    "code/parsers": "prs",
    "code/tests": "tst",
    "code/ghost": "gst",
    "doc/ghost": "dgh",
    "ghost/other": "ogh",
}
_GIT_CODES: dict[str, str] = {
    "modified": "mod",
    "added": "add",
    "deleted": "del",
    "renamed": "ren",
}


def build_cat_codes(categories: set[str]) -> dict[str, str]:
    """Short codes for every category present in this build.

    Static codes cover the historical set; new categories get a code derived
    from their last path segment, uniquified with a digit suffix on clash.
    """
    codes = {c: _CAT_CODES_STATIC[c] for c in categories if c in _CAT_CODES_STATIC}
    used = set(codes.values())
    for cat in sorted(categories - codes.keys()):
        base = "".join(ch for ch in cat.rsplit("/", 1)[-1].lower() if ch.isalnum())
        base = base or "cat"
        code = base[:3]
        n = 2
        while code in used:
            code = f"{base[:2]}{n}"
            n += 1
        codes[cat] = code
        used.add(code)
    return codes


def build_llm_export(
    nodes: list[dict],
    edges: list[dict],
    project_root: Path,
    git_available: bool,
) -> dict:
    """JSON snapshot of the graph for LLM consumption (schema v1).

    Drops UI-only fields (size, stem); keeps id, path, type, degree,
    git-status, and edge line numbers. Verbose but self-explanatory.
    """

    def _clean_node(n: dict) -> dict:
        keys = ("id", "label", "path", "type", "degree")
        out = {k: n[k] for k in keys if k in n}
        if "gitStatus" in n:
            out["gitStatus"] = n["gitStatus"]
        if n.get("ghost"):
            out["ghost"] = True
        return out

    def _clean_edge(e: dict) -> dict:
        out = {"source": e["source"], "target": e["target"], "type": e["type"]}
        if e.get("lines"):
            out["lines"] = e["lines"]
        if e.get("weight", 1) != 1:
            out["weight"] = e["weight"]
        if e.get("ghost"):
            out["ghost"] = True
        return out

    return {
        "schema_version": "1.0",
        "project_root": str(project_root).replace("\\", "/"),
        "stats": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "categories": sorted({n["type"] for n in nodes if n.get("type")}),
            "edge_types": sorted({e["type"] for e in edges if e.get("type")}),
            "git_available": git_available,
        },
        "nodes": [_clean_node(n) for n in nodes],
        "edges": [_clean_edge(e) for e in edges],
    }


def build_llm_export_compact(
    nodes: list[dict],
    edges: list[dict],
    project_root: Path,
    git_available: bool,
    cat_codes: dict[str, str],
) -> dict:
    """Compact JSON snapshot of the graph for LLM consumption (schema v2).

    Nodes become an indexed array; edges reference nodes by integer position.
    3-letter codes replace verbose type strings. Git status omitted when clean.
    ~5x smaller than v1 without losing any information.

    The "legend" key makes the format self-documenting — no external schema needed.
    """
    live_nodes = [n for n in nodes if not n.get("ghost")]
    ghost_nodes = [n for n in nodes if n.get("ghost")]
    ordered = live_nodes + ghost_nodes
    id_to_idx: dict[str, int] = {n["id"]: i for i, n in enumerate(ordered)}

    def _node(n: dict) -> dict[str, Any]:
        out: dict[str, Any] = {
            "p": n["path"],
            "t": cat_codes.get(n["type"], n["type"]),
            "d": n["degree"],
        }
        s = n.get("gitStatus", "clean")
        if s != "clean":
            out["s"] = _GIT_CODES.get(s, s)
        if n.get("ghost"):
            out["G"] = 1
        return out

    def _edge(e: dict) -> list | None:
        si = id_to_idx.get(e["source"])
        ti = id_to_idx.get(e["target"])
        if si is None or ti is None:
            return None
        row: list[Any] = [si, ti, _TYPE_CODES.get(e["type"], e["type"])]
        if e.get("lines"):
            row.append(e["lines"])
        return row

    live_edges = [e for e in edges if not e.get("ghost")]
    ghost_edges = [e for e in edges if e.get("ghost")]

    result: dict[str, Any] = {
        "v": "2.0",
        "legend": {
            "i": {str(i): n["path"] for i, n in enumerate(ordered)},
            "n": "nodes array; p=path t=category d=degree "
            "s=git(omitted if clean) G=1(ghost)",
            "e": "edges array; [src_idx, tgt_idx, type, [lines]?]",
            "t": _TYPE_CODES,
            "c": cat_codes,
            "s": _GIT_CODES,
        },
        "stats": {
            "nodes": len(live_nodes),
            "ghosts": len(ghost_nodes),
            "edges": len(live_edges),
        },
        "n": [_node(n) for n in ordered],
        "e": [row for e in live_edges if (row := _edge(e)) is not None],
    }
    ghost_edge_rows = [row for e in ghost_edges if (row := _edge(e)) is not None]
    if ghost_edge_rows:
        result["ge"] = ghost_edge_rows
    return result


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    p = argparse.ArgumentParser(
        description="Generate an interactive HTML dependency graph"
    )
    p.add_argument(
        "--config",
        default="graph.toml",
        help="Path to graph.toml config (default: <root>/graph.toml)",
    )
    p.add_argument(
        "--root",
        default=".",
        help="Project root to scan (default: current directory)",
    )
    p.add_argument(
        "--init",
        action="store_true",
        help=(
            "Generate graph.toml from autodiscovery (pins current structure "
            "and colours) instead of building the graph. Refuses to "
            "overwrite an existing config without --force."
        ),
    )
    p.add_argument(
        "--diff",
        action="store_true",
        help=(
            "With --init: print a drift report (files not covered by the "
            "existing config, stale pins) without touching anything."
        ),
    )
    p.add_argument(
        "--merge",
        action="store_true",
        help=(
            "With --init: append rules + colour pins for uncovered files to "
            "the existing config, preserving your edits and comments."
        ),
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="With --init: overwrite an existing graph.toml.",
    )
    p.add_argument(
        "--scope",
        choices=["full", "package"],
        default="full",
        help=(
            "full (default): scan the whole repo — every file of a known "
            "kind becomes a node. package: restrict to the package root(s), "
            "tests and docs (the historical whitelist view)."
        ),
    )
    p.add_argument(
        "--docs-only",
        action="store_true",
        help="Only include doc nodes, skip code file scanning",
    )
    p.add_argument(
        "--no-tests",
        action="store_true",
        help="Exclude test files from code nodes",
    )
    p.add_argument(
        "--output",
        default=None,
        help="Output file path (overrides config [output].path)",
    )
    p.add_argument(
        "--no-cdn",
        action="store_true",
        help="Embed D3.js inline instead of loading from CDN",
    )
    p.add_argument(
        "--mock-git",
        action="store_true",
        help=(
            "Inject synthetic git overlay data for visual testing "
            "(covers all 5 categories; no real git calls)"
        ),
    )
    p.add_argument(
        "--diff-base",
        metavar="REF",
        default=None,
        help=(
            "Compare a ref (branch, tag, commit) against the working tree "
            "or, with --diff-head, against a second ref: file statuses "
            "feed the Git overlay, new dependency edges show green and "
            "removed ones red in git mode."
        ),
    )
    p.add_argument(
        "--diff-head",
        metavar="REF",
        default=None,
        help=(
            "With --diff-base: compare against this ref instead of the "
            "working tree — both sides are built from git archive "
            "snapshots, so worktree changes after REF are not part of "
            "the diff."
        ),
    )
    p.add_argument(
        "--json",
        action="store_true",
        help=(
            "Also write a verbose JSON snapshot of the graph next to the HTML "
            "(<output>.json, schema v1)."
        ),
    )
    p.add_argument(
        "--compact",
        action="store_true",
        help=(
            "Also write a compact JSON snapshot next to the HTML "
            "(<output>-compact.json, schema v2). ~5x smaller than --json; "
            "integer node IDs, 3-letter type codes, legend embedded."
        ),
    )
    p.add_argument(
        "--bench",
        action="store_true",
        help=(
            "Print a context-cost report for this repo (raw corpus vs "
            "--json vs --compact sizes with token estimates) and exit "
            "without writing any files."
        ),
    )
    return p.parse_args()


def _compact_json(obj: dict) -> str:
    """Pretty-compact JSON: each node/edge on its own line.

    ``json.dumps`` alone cannot produce this layout — it either puts
    everything on one line (compact) or indents every field (pretty).
    Here, top-level scalars stay on one line while ``n`` and ``e``
    arrays get per-element newlines so line-oriented tools never
    truncate a mega-line.
    """
    multi_line_keys = {"n", "e", "ge"}
    parts: list[str] = ["{"]
    last_key = list(obj.keys())[-1]
    for key, val in obj.items():
        sep = "" if key == last_key else ","
        if key in multi_line_keys and isinstance(val, list):
            parts.append(f'  "{key}": [')
            for i, item in enumerate(val):
                s = json.dumps(item, ensure_ascii=False, separators=(",", ":"))
                comma = "," if i < len(val) - 1 else ""
                parts.append(f"    {s}{comma}")
            parts.append(f"  ]{sep}")
        else:
            s = json.dumps(val, ensure_ascii=False, separators=(",", ":"))
            parts.append(f'  "{key}": {s}{sep}')
    parts.append("}")
    return "\n".join(parts)


def _fmt_size(n: int) -> str:
    if n >= 1024 * 1024:
        return f"{n / (1024 * 1024):.1f} MB"
    if n >= 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n} B"


def print_bench_report(
    nodes: list[dict],
    edges: list[dict],
    project_root: Path,
    git_available: bool,
    cat_codes: dict[str, str],
) -> None:
    """Print a context-cost report: raw corpus vs the two JSON exports.

    Reproduces the README numbers on the user's own repo. Token counts use
    the usual rough estimate of one token per 4 bytes; nothing is written.
    """
    live = [n for n in nodes if not n.get("ghost")]
    corpus_bytes = 0
    corpus_files = 0
    for n in live:
        try:
            corpus_bytes += (project_root / n["path"]).stat().st_size
        except OSError:
            continue
        corpus_files += 1
    verbose = json.dumps(
        build_llm_export(nodes, edges, project_root, git_available),
        ensure_ascii=False,
        indent=2,
    ).encode("utf-8")
    compact = _compact_json(
        build_llm_export_compact(nodes, edges, project_root, git_available, cat_codes)
    ).encode("utf-8")

    def row(label: str, size: int) -> str:
        pct = f"{size / corpus_bytes * 100:.1f}%" if corpus_bytes else "n/a"
        return f"  {label:<29} {_fmt_size(size):>9}  {size // 4:>11,}  {pct:>9}"

    header = f"  {'What you put in context':<29} {'Size':>9}  {'~Tokens':>11}  {'vs corpus':>9}"
    print()
    print("Context cost on this repo (tokens ~= bytes / 4):")
    print()
    print(header)
    print(row(f"raw corpus ({corpus_files} files)", corpus_bytes))
    print(row("--json export (schema v1)", len(verbose)))
    print(row("--compact export (schema v2)", len(compact)))


def main() -> None:
    """Build and write the interactive dependency graph HTML."""
    ensure_utf8_stdout()
    args = parse_args()
    project_root = Path(args.root).resolve()

    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = project_root / config_path

    if args.diff or args.merge:
        if not args.init:
            print("--diff / --merge only make sense with --init.", file=sys.stderr)
            sys.exit(2)
    if args.diff_base and args.mock_git:
        print("--diff-base and --mock-git are mutually exclusive.", file=sys.stderr)
        sys.exit(2)
    if args.diff_head and not args.diff_base:
        print("--diff-head requires --diff-base.", file=sys.stderr)
        sys.exit(2)
    if args.init:
        handle_init(args, project_root, config_path)
        return

    config = load_config(config_path)
    if not config:
        print(f"No config at {config_path} — full autodiscovery mode.")

    output_str = args.output or config.get("output", {}).get("path", "docs/graph.html")
    output_path = Path(output_str)
    if not output_path.is_absolute():
        output_path = project_root / output_path

    build_root = project_root
    head_tmp: tempfile.TemporaryDirectory[str] | None = None
    if args.diff_head:
        print(f"Materializing head ref {args.diff_head} (git archive)...")
        head_tmp = tempfile.TemporaryDirectory(prefix="build-graph-head-")
        if not materialize_ref(project_root, args.diff_head, Path(head_tmp.name)):
            print(
                f"Error: could not materialize head ref: {args.diff_head}",
                file=sys.stderr,
            )
            sys.exit(1)
        build_root = Path(head_tmp.name)

    print(f"Discovering files (scope={args.scope})...")
    files, git_used = list_project_files(build_root)
    all_nodes, docs_dirname = build_all_nodes(
        files,
        config,
        scope=args.scope,
        include_tests=not args.no_tests,
        docs_only=args.docs_only,
    )
    md_nodes = [n for n in all_nodes if n["path"].endswith(".md")]
    other_nodes = [n for n in all_nodes if not n["path"].endswith(".md")]
    py_nodes = [n for n in other_nodes if n["path"].endswith(".py")]
    untracked_count = sum(1 for n in all_nodes if n.get("untracked"))
    print(
        f"  {len(files)} files ({'git' if git_used else 'walk'}) -> "
        f"{len(all_nodes)} nodes: {len(md_nodes)} doc, {len(py_nodes)} py, "
        f"{len(other_nodes) - len(py_nodes)} other; "
        f"untracked-by-config={untracked_count}"
    )

    print("Building doc->doc edges...")
    all_edges: list[dict] = build_doc_edges(md_nodes, build_root)
    print(f"  {len(all_edges)} doc->doc edges")

    if not args.docs_only:
        print("Finding code->doc references (this may take a moment)...")
        path_to_doc_id = {n["path"]: n["id"] for n in md_nodes}
        md_cache = []
        for n in md_nodes:
            f = build_root / n["path"]
            try:
                content = f.read_text(encoding="utf-8")
            except Exception as exc:  # mirror load_md_files behaviour
                print(f"Warning: Could not read {f}: {exc}")
                continue
            md_cache.append((f, content, content.splitlines()))
        code_edges, ambiguous_nodes = add_code_doc_edges(
            other_nodes, path_to_doc_id, build_root, md_cache
        )
        print(
            f"  {len(code_edges)} code->doc edges "
            f"({len(ambiguous_nodes)} ambiguous-group nodes)"
        )
        all_edges.extend(code_edges)
        all_nodes.extend(ambiguous_nodes)

        print("Finding code->code imports (AST)...")
        code_trees = _parse_code_trees(py_nodes, build_root)
        code_code_edges = add_code_code_edges(py_nodes, build_root, code_trees)
        runtime_count = sum(1 for e in code_code_edges if e["type"] == "code->code")
        type_only_count = sum(1 for e in code_code_edges if e["type"] == "type-only")
        print(f"  {runtime_count} code->code edges, {type_only_count} type-only edges")
        all_edges.extend(code_code_edges)

        print("Finding docstring file mentions...")
        all_node_ids_so_far = {n["id"] for n in all_nodes}
        docstring_edges = add_docstring_edges(py_nodes, all_node_ids_so_far, code_trees)
        print(f"  {len(docstring_edges)} docstring edges")
        all_edges.extend(docstring_edges)

    git_data: dict[str, Any] | None
    diff_info: dict[str, Any] | None = None
    if args.diff_base:
        print(f"Collecting ref diff vs {args.diff_base}...")
        git_data = collect_ref_diff(project_root, args.diff_base, args.diff_head)
        if git_data is None:
            print(
                f"Error: git unavailable or unknown ref: {args.diff_base}",
                file=sys.stderr,
            )
            sys.exit(1)
        apply_git_status_to_live_nodes(all_nodes, git_data)
        add_ghost_nodes_and_edges(all_nodes, all_edges, git_data, md_nodes, build_root)
        print(
            f"  added={len(git_data['added'])}, "
            f"modified={len(git_data['modified'])}, "
            f"renamed={len(git_data['renamed'])}, "
            f"deleted={len(git_data['deleted'])}"
        )
        print(f"Building base graph at {args.diff_base} (git archive)...")
        edge_diff = apply_edge_diff(
            all_nodes,
            all_edges,
            project_root,
            args.diff_base,
            git_data["renamed"],
            config,
            args.scope,
            not args.no_tests,
            args.docs_only,
        )
        if edge_diff is None:
            print(
                f"Error: could not materialize base ref {args.diff_base}",
                file=sys.stderr,
            )
            sys.exit(1)
        diff_info = {
            "base": args.diff_base,
            "head": args.diff_head or "worktree",
            **edge_diff,
        }
        print(
            f"  edges: +{edge_diff['edgesAdded']} new, "
            f"-{edge_diff['edgesRemoved']} removed"
        )
    elif args.mock_git:
        print("Collecting git status... [MOCK]")
        apply_mock_git_status(all_nodes, all_edges)
        # Non-empty placeholder so JS treats GIT_DATA as available.
        git_data = {"added": [], "modified": [], "deleted": [], "renamed": {}}
        ghost_count = sum(1 for n in all_nodes if n.get("ghost"))
        print(f"  synthetic data injected; ghost-nodes={ghost_count}")
    elif not git_used:
        git_data = None
        print("Collecting git status... skipped (no git — overlay disabled)")
    else:
        print("Collecting git status...")
        git_data = collect_git_status(project_root)
        if git_data:
            apply_git_status_to_live_nodes(all_nodes, git_data)
            add_ghost_nodes_and_edges(
                all_nodes, all_edges, git_data, md_nodes, project_root
            )
            ghost_count = sum(1 for n in all_nodes if n.get("ghost"))
            print(
                f"  added={len(git_data['added'])}, "
                f"modified={len(git_data['modified'])}, "
                f"renamed={len(git_data['renamed'])}, "
                f"deleted={len(git_data['deleted'])}, "
                f"ghost-nodes={ghost_count}"
            )
        else:
            print("  git unavailable; skipping git overlay")

    if head_tmp is not None:
        head_tmp.cleanup()

    print("Computing layout hints...")
    compute_layout_hints(all_nodes, all_edges)
    apply_dead_exemptions(
        all_nodes,
        (config.get("dead_code") or {}).get("exempt", []),
        collect_entry_point_modules(project_root),
    )

    categories = {n["type"] for n in all_nodes if not n.get("ghost")}
    colors, colors_saturated = build_palette(
        categories, config.get("colors", {}), config.get("colors_saturated", {})
    )
    cat_codes = build_cat_codes(categories)

    if args.bench:
        print_bench_report(
            all_nodes, all_edges, project_root, git_data is not None, cat_codes
        )
        return

    print(f"Rendering HTML to {output_path}...")
    project_root_posix = str(project_root).replace("\\", "/")
    render_html(
        all_nodes,
        all_edges,
        colors,
        colors_saturated,
        project_root_posix,
        output_path,
        embed_d3=args.no_cdn,
        git_data=git_data,
        diff_info=diff_info,
    )
    if args.json:
        json_path = output_path.with_suffix(".json")
        export = build_llm_export(
            all_nodes, all_edges, project_root, git_data is not None
        )
        json_path.write_text(
            json.dumps(export, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"  also wrote {json_path}")
    if args.compact:
        compact_path = output_path.with_stem(output_path.stem + "-compact").with_suffix(
            ".json"
        )
        export_compact = build_llm_export_compact(
            all_nodes, all_edges, project_root, git_data is not None, cat_codes
        )
        compact_path.write_text(
            _compact_json(export_compact),
            encoding="utf-8",
        )
        print(f"  also wrote {compact_path}")
    print(f"Done. Open {output_path} in your browser.")


if __name__ == "__main__":
    main()
