#!/usr/bin/env python3
"""Generate an interactive HTML dependency graph for the project.

Usage:
    build-graph
    build-graph --docs-only
    build-graph --no-tests --output docs/graph.html
    build-graph --no-cdn
    build-graph --config path/to/graph.toml
    build-graph --mock-git    # synthetic git data for testing

File layout (search for these anchors):

    Python (top-level):
        # ====== SECTION: imports & bootstrap ======
        # ====== SECTION: config & node classification ======
        # ====== SECTION: graph building (doc / code / edges) ======
        # ====== SECTION: git overlay (collect / annotate / ghost) ======
        # ====== SECTION: layout hints ======
        # ====== SECTION: HTML assembly (CSS / BODY / JS) ======
        # ====== SECTION: rendering & CLI entry point ======

    JS (inside build_graph/resources/main.js, search "// === ..."):
        STATE & EDGE COLORS
        I18N (dictionary, formatters, applyI18n)
        WIDTH LOCKING (lockAllI18nWidths)
        NEIGHBOR MAP & SIMULATION (nodes, links, forces)
        RENDER STATE & CANVAS ENGINE (draw loop, hit testing,
            node drag, pointer dispatch)
        PIN / EDGE FOCUS / DIM (overlay predicates)
        HOVER (onNodeEnter/onNodeLeave, hoverTimer)
        CLICK HANDLERS (onNodeClick, dropAllSelections, info-close)
        INFO-PANEL RENDERING
        EDGE TOOLTIP
        SEARCH (debounced)
        EXCLUSION FILTER
        VISIBILITY FILTER (showAll / orphansOnly / applyAllFilters)
        LEGEND (node types / edge types / orphans button)
        GIT OVERLAY (palettes, applyGitMode, buildGitLegend)
        FILE OPENING (IDE selector, buildFileHref)
        PREFS (savePrefs / loadPrefs)
        TOP-BAR HANDLERS (theme, palette, lang, ide, export/import)
        SLIDERS
        DRAG (makeDraggable + bindings — panels)
        TICK (orphan ring refit + requestDraw)
        INIT (applyI18n, loadPrefs, WARMUP & FIRST PAINT)
"""

# ====== SECTION: imports & bootstrap ======
import argparse
import ast
import base64
import colorsys
import fnmatch
import hashlib
import json
import os
import subprocess
import sys
import tomllib
import urllib.error
import urllib.request
from collections import defaultdict
from importlib import resources as _resources
from pathlib import Path
from typing import Any

from build_graph import __author__, __author_url__, __version__
from build_graph._console import ensure_utf8_stdout
from build_graph.links import extract_file_references
from build_graph.related import find_related_docs


# ====== SECTION: config & node classification ======
def load_config(config_path: Path) -> dict:
    """Load graph.toml configuration (empty dict when the file is absent).

    Since autodiscovery landed the TOML is override-only: without it the
    graph is built entirely from autodiscovered structure.
    """
    if not config_path.is_file():
        return {}
    with open(config_path, "rb") as f:
        return tomllib.load(f)


# --- autodiscovery: file enumeration ---------------------------------------
# Kinds are coarse node families; the category shown in the legend is
# "<kind>/<location>" (see classify_auto). Files whose kind is unknown never
# become nodes — that keeps binary/asset noise out without a .gitignore.
_KIND_BY_EXT: dict[str, str] = {
    # code
    ".py": "code",
    ".js": "code",
    ".css": "code",
    ".html": "code",
    ".mako": "code",
    ".sh": "code",
    ".ps1": "code",
    ".bat": "code",
    ".sql": "code",
    # docs
    ".md": "doc",
    # configuration / data the project treats as config
    ".json": "config",
    ".enc": "config",
    ".yaml": "config",
    ".yml": "config",
    ".toml": "config",
    ".ini": "config",
    ".cfg": "config",
    ".conf": "config",
    ".txt": "config",
    ".lock": "config",
    ".example": "config",
    # localisation sources
    ".po": "locale",
    ".pot": "locale",
}
_KIND_BY_NAME: dict[str, str] = {
    "makefile": "config",
    "license": "doc",
    ".gitignore": "config",
    ".gitattributes": "config",
    ".dockerignore": "config",
}
_WALK_EXCLUDE_DIRS = {"__pycache__", "node_modules", "dist", "build"}
_WALK_WARN_THRESHOLD = 20000


def classify_kind(filename: str) -> str | None:
    """Map a bare file name to a node kind, or None for unknown files."""
    lower = filename.lower()
    if lower in _KIND_BY_NAME:
        return _KIND_BY_NAME[lower]
    if lower.startswith("dockerfile"):
        return "config"
    if lower.startswith(".env"):
        return "config"
    return _KIND_BY_EXT.get(Path(filename).suffix.lower())


def list_project_files(project_root: Path) -> tuple[list[str], bool]:
    """Enumerate candidate files as POSIX paths relative to project_root.

    Primary source is git — `ls-files --cached --others --exclude-standard`
    gives tracked + untracked-but-not-ignored files, honouring .gitignore
    for free (plain `ls-files` would miss files created since the last
    `git add`). When git is unavailable (no binary / not a repo) falls back
    to a filesystem walk with built-in excludes only; .gitignore is
    deliberately NOT emulated there — a partial reimplementation is less
    predictable than none. Use `[scan] exclude` in graph.toml to trim the
    fallback. Returns (files, git_used).
    """
    try:
        result = subprocess.run(
            [
                "git",
                "-c",
                "core.quotePath=false",
                "ls-files",
                "--cached",
                "--others",
                "--exclude-standard",
            ],
            cwd=project_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=15,
            check=True,
        )
        rels = [ln for ln in result.stdout.replace("\r\n", "\n").split("\n") if ln]
        # ls-files still lists tracked files deleted from the working tree.
        return [r for r in rels if (project_root / r).is_file()], True
    except (
        subprocess.CalledProcessError,
        FileNotFoundError,
        subprocess.TimeoutExpired,
        OSError,
    ):
        pass
    print(
        "git unavailable — falling back to filesystem walk "
        "(built-in excludes only, .gitignore not applied)",
        file=sys.stderr,
    )
    files: list[str] = []
    for dirpath, dirnames, filenames in os.walk(project_root):
        dirnames[:] = [
            d
            for d in dirnames
            if not d.startswith(".")
            and d not in _WALK_EXCLUDE_DIRS
            and not d.endswith(".egg-info")
        ]
        for fn in filenames:
            files.append((Path(dirpath) / fn).relative_to(project_root).as_posix())
    if len(files) > _WALK_WARN_THRESHOLD:
        print(
            f"WARNING: walk found {len(files)} files — likely generated data. "
            "Add `[scan] exclude` patterns to graph.toml or init a git repo.",
            file=sys.stderr,
        )
    return files, False


# --- autodiscovery: classification ------------------------------------------
def detect_package_roots(files: list[str]) -> set[str]:
    """Top-level directories that are Python packages (have __init__.py).

    Conventional test dirs are excluded even when they are packages:
    sub-segment classification inside tests/ would mint categories like
    "code/parsers" for tests/parsers/, colliding with the real package's
    sub-packages. Test dirs classify as "<kind>/tests" via the generic
    top-segment rule instead.
    """
    return {
        f.split("/", 1)[0]
        for f in files
        if f.count("/") == 1
        and f.endswith("/__init__.py")
        and f.split("/", 1)[0] not in ("tests", "test")
    }


def detect_docs_dirname(files: list[str]) -> str | None:
    """Detect the documentation folder by convention: docs/ or doc/."""
    for cand in ("docs", "doc"):
        prefix = cand + "/"
        if any(f.startswith(prefix) and f.endswith(".md") for f in files):
            return cand
    return None


def classify_auto(
    rel: str,
    kind: str,
    package_roots: set[str],
    docs_dirname: str | None,
) -> str:
    """Category for a file with no explicit TOML rule: kind × location.

    - project-root files → "<kind>/_root"
    - inside the docs folder → "doc/<first subdir>" (Diátaxis falls out of
      this naturally), files directly in docs/ → "doc/<docs dirname>"
    - inside a Python package → "<kind>/<first subpackage>", files directly
      in the package root → "<kind>/<package name>"
    - anything else → "<kind>/<top-level dir>"
    """
    parts = rel.split("/")
    if len(parts) == 1:
        return f"{kind}/_root"
    top = parts[0]
    if docs_dirname and top == docs_dirname and kind == "doc":
        return f"doc/{parts[1]}" if len(parts) >= 3 else f"doc/{top}"
    if top in package_roots and len(parts) >= 3:
        return f"{kind}/{parts[1]}"
    return f"{kind}/{top}"


def _match_toml_doc(rel_to_docs: str, categories: list[dict]) -> str | None:
    """First matching [docs.categories] prefix rule, or None."""
    for cat in categories:
        prefix = cat["prefix"].rstrip("/")
        if rel_to_docs == prefix or rel_to_docs.startswith(prefix + "/"):
            return str(cat["type"])
    return None


def _match_toml_code(rel: str, code_configs: list[dict]) -> str | None:
    """First matching [[code]] dir rule, or None."""
    for cfg in code_configs:
        prefix = cfg["dir"].rstrip("/")
        if rel == prefix or rel.startswith(prefix + "/"):
            return str(cfg["type"])
    return None


def _match_toml_rule(rel: str, kind: str, rules: list[dict]) -> str | None:
    """First matching generic [[rules]] entry (any kind), or None.

    Entry shape: { dir = "cfg", type = "config/cfg" } with an optional
    `kind` field restricting the rule to one node kind — needed when one
    dir holds several kinds (tests/ has code AND fixture configs).
    """
    for rule in rules:
        rule_kind = rule.get("kind")
        if rule_kind and rule_kind != kind:
            continue
        prefix = rule["dir"].rstrip("/")
        if rel == prefix or rel.startswith(prefix + "/"):
            return str(rule["type"])
    return None


def build_all_nodes(
    files: list[str],
    config: dict,
    scope: str,
    include_tests: bool,
    docs_only: bool,
) -> tuple[list[dict], str | None]:
    """Build graph nodes from the discovered file list.

    Classification priority per file: explicit TOML rule ([docs.categories]
    for .md inside the docs folder, generic [[rules]] dir prefix, [[code]]
    dir prefix for code files) → autodiscovery (kind × location). A file is
    flagged `untracked` ("not covered by an explicit rule", surfaced in the
    legend) when a TOML exists, no prefix rule matched AND the resulting
    category is not pinned in [colors] — so a freshly `--init`-generated
    config covers everything, while files landing in categories the config
    never heard of light up.

    Node ids keep the historical convention: docs-folder .md files use the
    docs-relative path, everything else the project-relative path (on a
    collision the project-relative path wins as id).

    Returns (nodes, docs_dirname).
    """
    docs_cfg = config.get("docs") or {}
    code_configs: list[dict] = config.get("code", [])
    rules: list[dict] = config.get("rules", [])
    pinned_categories = set(config.get("colors", {}))
    toml_present = bool(config)
    package_roots = detect_package_roots(files)
    docs_dirname = docs_cfg.get("dir") or detect_docs_dirname(files)
    doc_exclude = set(docs_cfg.get("exclude", []))
    categories = docs_cfg.get("categories", [])
    default_type = docs_cfg.get("default_type")
    scan_exclude: list[str] = (config.get("scan") or {}).get("exclude", [])

    scope_roots: set[str] | None = None
    if scope == "package":
        if code_configs or docs_cfg.get("dir"):
            scope_roots = {cfg["dir"].rstrip("/").split("/")[0] for cfg in code_configs}
        else:
            scope_roots = set(package_roots) | {"tests"}
        if docs_dirname:
            scope_roots.add(docs_dirname)

    nodes: list[dict] = []
    taken_ids: set[str] = set()
    deferred: list[dict] = []  # non-docs nodes; docs ids claim their ids first
    for rel in sorted(files):
        name = rel.rsplit("/", 1)[-1]
        kind = classify_kind(name)
        if kind is None:
            continue
        if docs_only and kind != "doc":
            continue
        if scan_exclude and any(fnmatch.fnmatch(rel, pat) for pat in scan_exclude):
            continue
        parts = rel.split("/")
        top = parts[0]
        if scope_roots is not None and (len(parts) == 1 or top not in scope_roots):
            continue

        in_docs = bool(docs_dirname) and len(parts) > 1 and top == docs_dirname
        node_type: str | None = None
        explicit = False
        if in_docs and kind == "doc":
            rel_docs = rel.split("/", 1)[1]
            if any(part in doc_exclude for part in rel_docs.split("/")):
                continue
            matched = _match_toml_doc(rel_docs, categories)
            if matched:
                node_type, explicit = matched, True
            elif default_type:
                node_type = str(default_type)
        if node_type is None and rules:
            matched = _match_toml_rule(rel, kind, rules)
            if matched:
                node_type, explicit = matched, True
        if node_type is None and kind == "code":
            matched = _match_toml_code(rel, code_configs)
            if matched:
                node_type, explicit = matched, True
        if node_type is None:
            node_type = classify_auto(rel, kind, package_roots, docs_dirname)
        if not include_tests and (node_type == "code/tests" or top == "tests"):
            continue

        node = {
            "id": rel.split("/", 1)[1] if in_docs and kind == "doc" else rel,
            "label": name,
            "stem": Path(name).stem,
            "type": node_type,
            "path": rel,
            "degree": 0,
            "size": 5,
        }
        if toml_present and not explicit and node_type not in pinned_categories:
            node["untracked"] = True
        if in_docs and kind == "doc":
            taken_ids.add(node["id"])
            nodes.append(node)
        else:
            deferred.append(node)

    for node in deferred:
        if node["id"] in taken_ids:
            # A docs-relative doc id equals this project-relative path
            # (e.g. docs/README.md vs ./README.md) — disambiguate ours.
            node["id"] = "./" + node["id"]
        taken_ids.add(node["id"])
        nodes.append(node)
    return nodes, docs_dirname


# ====== SECTION: config bootstrap (--init / --diff / --merge) ======
def _discover_structure(
    files: list[str],
) -> tuple[str | None, list[str], dict[str, list[tuple[str, str, str]]], set[str]]:
    """Autodiscovery summary for config generation.

    Returns (docs_dirname, doc_subdirs, rules_by_dir, categories) where
    rules_by_dir maps a rule dir → [(dir, kind, category), ...] (multiple
    entries when one dir holds several kinds, e.g. tests/ code + fixtures).
    Root-level files produce no rules — their `<kind>/_root` categories are
    covered by palette pins alone.
    """
    package_roots = detect_package_roots(files)
    docs_dirname = detect_docs_dirname(files)
    doc_subdirs: set[str] = set()
    rules_by_dir: dict[str, dict[str, str]] = {}
    categories: set[str] = set()
    for rel in sorted(files):
        name = rel.rsplit("/", 1)[-1]
        kind = classify_kind(name)
        if kind is None:
            continue
        categories.add(classify_auto(rel, kind, package_roots, docs_dirname))
        parts = rel.split("/")
        top = parts[0]
        if docs_dirname and top == docs_dirname and kind == "doc":
            if len(parts) >= 3:
                doc_subdirs.add(parts[1])
            continue
        if len(parts) == 1:
            continue
        if top in package_roots and len(parts) >= 3:
            rule_dir = f"{top}/{parts[1]}"
        else:
            rule_dir = top
        rules_by_dir.setdefault(rule_dir, {})[kind] = classify_auto(
            rel, kind, package_roots, docs_dirname
        )
    # Most-specific dirs first: rules are prefix-matched in order, so a broad
    # "smm_bot_async" entry must not shadow "smm_bot_async/core".
    flat: dict[str, list[tuple[str, str, str]]] = {
        d: [(d, k, c) for k, c in sorted(kinds.items())]
        for d, kinds in sorted(
            rules_by_dir.items(), key=lambda kv: (-kv[0].count("/"), kv[0])
        )
    }
    return docs_dirname, sorted(doc_subdirs), flat, categories


def generate_toml(files: list[str]) -> str:
    """Render a graph.toml pinning the current autodiscovery state.

    The generated config classifies every current file explicitly (docs
    categories + [[rules]] + colour pins for the remaining `_root`
    categories), so nothing is marked unmapped right after --init; files
    added later into unknown places light up until the config is refreshed
    via --init --diff / --init --merge.

    `default_type` is deliberately NOT emitted: unmatched docs .md must fall
    through to autodiscovery so new docs sections get flagged instead of
    silently absorbed into a default category.
    """
    docs_dirname, doc_subdirs, rules_by_dir, categories = _discover_structure(files)
    colors, colors_sat = build_palette(categories, {}, {})

    out: list[str] = [
        "# graph.toml — generated by build-graph --init",
        "# Paths are relative to the project root.",
        "# Refresh after restructuring: --init --diff (report) / --init --merge",
        "# (append new rules and colour pins without touching your edits).",
        "",
        "[scan]",
        "# Extra exclude globs (matched against project-relative paths).",
        "exclude = []",
        "",
        "[dead_code]",
        "# Globs exempt from dead-code detection, on top of built-in",
        "# defaults (__init__.py, conftest.py, main.py, alembic/versions/).",
        "exempt = []",
        "",
        "[output]",
        'path = "docs/graph.html"',
    ]
    if docs_dirname:
        out += [
            "",
            "[docs]",
            f'dir = "{docs_dirname}"',
            "exclude = []",
            "# No default_type: unmatched .md falls through to autodiscovery",
            "# and shows up as unmapped — that is the drift detector.",
        ]
        for sub in doc_subdirs:
            out += [
                "",
                "[[docs.categories]]",
                f'prefix = "{sub}"',
                f'type   = "doc/{sub}"',
            ]
    if rules_by_dir:
        out += [
            "",
            "# Generic dir → category rules (any file kind). `kind` restricts",
            "# a rule when one dir holds several kinds (code vs config etc.).",
        ]
        for _dir, entries in rules_by_dir.items():
            for d, kind, cat in entries:
                out += ["", "[[rules]]", f'dir  = "{d}"']
                if len(entries) > 1:
                    out += [f'kind = "{kind}"']
                out += [f'type = "{cat}"']
    out += ["", "[colors]"]
    out += [f'"{cat}" = "{colors[cat]}"' for cat in sorted(colors)]
    out += ["", "[colors_saturated]"]
    out += [f'"{cat}" = "{colors_sat[cat]}"' for cat in sorted(colors_sat)]
    out += [""]
    return "\n".join(out)


def _uncovered_report(
    files: list[str],
    config: dict,
) -> tuple[dict[str, list[str]], set[str]]:
    """What the current config fails to cover.

    Returns (uncovered: category → sample paths, uncovered_categories).
    Reuses build_all_nodes — "uncovered" is exactly the untracked flag.
    """
    nodes, _ = build_all_nodes(
        files, config, scope="full", include_tests=True, docs_only=False
    )
    uncovered: dict[str, list[str]] = {}
    for n in nodes:
        if n.get("untracked"):
            uncovered.setdefault(n["type"], []).append(n["path"])
    return uncovered, set(uncovered)


def init_diff(files: list[str], config: dict, config_path: Path) -> None:
    """Print a drift report: scan state vs the existing graph.toml."""
    uncovered, uncovered_cats = _uncovered_report(files, config)
    print(f"Drift report for {config_path}:")
    if not uncovered:
        print("  config covers every discovered file — no drift.")
    else:
        total = sum(len(v) for v in uncovered.values())
        print(f"  {total} files not covered by an explicit rule (unmapped):")
        for cat in sorted(uncovered):
            paths = uncovered[cat]
            sample = ", ".join(paths[:3]) + (", ..." if len(paths) > 3 else "")
            print(f"    {cat:28} {len(paths):4}  e.g. {sample}")
    # Stale bits: pins and rules pointing at nothing.
    _, _, _, auto_categories = _discover_structure(files)
    known = auto_categories | {
        str(c["type"]) for c in (config.get("docs") or {}).get("categories", [])
    }
    known |= {str(c["type"]) for c in config.get("code", [])}
    known |= {str(r["type"]) for r in config.get("rules", [])}
    stale_pins = sorted(set(config.get("colors", {})) - known)
    if stale_pins:
        print(f"  stale colour pins (category no longer present): {stale_pins}")
    if uncovered:
        print("Run --init --merge to append rules + colour pins for the above.")


def _insert_into_section(lines: list[str], header: str, new_lines: list[str]) -> bool:
    """Insert lines at the end of a TOML section; False if header missing."""
    try:
        start = next(i for i, ln in enumerate(lines) if ln.strip() == header)
    except StopIteration:
        return False
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i].lstrip().startswith("["):
            end = i
            break
    while end > start + 1 and not lines[end - 1].strip():
        end -= 1
    lines[end:end] = new_lines
    return True


def init_merge(files: list[str], config: dict, config_path: Path) -> None:
    """Append coverage for drifted files to graph.toml, preserving edits.

    Text-level surgery: colour pins are inserted into the existing [colors]
    / [colors_saturated] sections (or the sections are appended when
    missing); [[rules]] blocks for uncovered dirs go to the end of file.
    Nothing the user wrote is modified or reordered.
    """
    uncovered, uncovered_cats = _uncovered_report(files, config)
    if not uncovered:
        print("Nothing to merge — config already covers every discovered file.")
        return
    docs_dirname, _, rules_by_dir, _ = _discover_structure(files)
    text = config_path.read_text(encoding="utf-8")
    lines = text.split("\n")

    # New [[rules]] for dirs that produce uncovered categories.
    new_rule_lines: list[str] = []
    for _dir, entries in rules_by_dir.items():
        for d, kind, cat in entries:
            if cat not in uncovered_cats:
                continue
            new_rule_lines += ["", "[[rules]]", f'dir  = "{d}"']
            if len(entries) > 1:
                new_rule_lines += [f'kind = "{kind}"']
            new_rule_lines += [f'type = "{cat}"']
    if new_rule_lines:
        new_rule_lines.insert(0, "# --- appended by --init --merge ---")
        new_rule_lines.insert(0, "")
        lines += new_rule_lines

    # Colour pins for every uncovered category, both palettes.
    colors, colors_sat = build_palette(uncovered_cats, {}, {})
    existing_pins = set(config.get("colors", {}))
    existing_pins_sat = set(config.get("colors_saturated", {}))
    add = [f'"{c}" = "{colors[c]}"' for c in sorted(uncovered_cats - existing_pins)]
    add_sat = [
        f'"{c}" = "{colors_sat[c]}"' for c in sorted(uncovered_cats - existing_pins_sat)
    ]
    if add and not _insert_into_section(lines, "[colors]", add):
        lines += ["", "[colors]", *add]
    if add_sat and not _insert_into_section(lines, "[colors_saturated]", add_sat):
        lines += ["", "[colors_saturated]", *add_sat]

    config_path.write_text("\n".join(lines), encoding="utf-8")
    rule_count = sum(1 for ln in new_rule_lines if ln == "[[rules]]")
    print(
        f"Merged into {config_path}: {rule_count} new rules, "
        f"{len(add)} colour pins, {len(add_sat)} saturated pins."
    )
    print("Review the appended blocks and adjust names/colours to taste.")


def handle_init(
    args: argparse.Namespace, project_root: Path, config_path: Path
) -> None:
    """Entry point for --init and its --diff / --merge modes."""
    files, _ = list_project_files(project_root)
    config = load_config(config_path)
    if args.diff or args.merge:
        if not config:
            print(f"No config at {config_path} — run --init first.", file=sys.stderr)
            sys.exit(2)
        if args.diff:
            init_diff(files, config, config_path)
        else:
            init_merge(files, config, config_path)
        return
    if config and not args.force:
        print(
            f"{config_path} already exists. Use --init --diff to see drift, "
            "--init --merge to append coverage, or --init --force to overwrite.",
            file=sys.stderr,
        )
        sys.exit(2)
    # The config file being written is itself a discoverable file, but the
    # scan above ran before it existed — include it, or the very first
    # `--init --diff` reports drift caused by --init itself.
    try:
        config_rel = config_path.resolve().relative_to(project_root).as_posix()
    except ValueError:
        config_rel = None
    if config_rel and config_rel not in files:
        files = [*files, config_rel]
    config_path.write_text(generate_toml(files), encoding="utf-8")
    print(f"Wrote {config_path} (autodiscovery snapshot pinned).")


# ====== SECTION: graph building (doc / code / edges) ======
def build_doc_edges(
    md_nodes: list[dict],
    project_root: Path,
) -> list[dict]:
    """Build doc->doc edges from markdown link references between doc nodes."""
    abs_to_id: dict[Path, str] = {}
    for n in md_nodes:
        try:
            abs_to_id[(project_root / n["path"]).resolve()] = n["id"]
        except OSError:
            continue

    edges: list[dict] = []
    edge_map: dict[tuple[str, str], dict] = {}
    for n in md_nodes:
        f = project_root / n["path"]
        src_id = n["id"]
        try:
            content = f.read_text(encoding="utf-8")
        except Exception:
            continue
        for ref in extract_file_references(content):
            if not ref.endswith(".md"):
                continue
            try:
                resolved = (f.parent / ref).resolve()
            except (ValueError, OSError):
                continue
            tgt_id = abs_to_id.get(resolved)
            if tgt_id is None or tgt_id == src_id:
                continue
            key = (src_id, tgt_id)
            if key in edge_map:
                continue
            e = {
                "source": src_id,
                "target": tgt_id,
                "type": "doc->doc",
                "weight": 1,
                "lines": [],
            }
            edges.append(e)
            edge_map[key] = e

    for n in md_nodes:
        f = project_root / n["path"]
        src_id = n["id"]
        try:
            file_lines = f.read_text(encoding="utf-8").splitlines()
        except Exception:
            continue
        for lineno, line_text in enumerate(file_lines, 1):
            for ref in extract_file_references(line_text):
                if not ref.endswith(".md"):
                    continue
                try:
                    resolved = (f.parent / ref).resolve()
                except (ValueError, OSError):
                    continue
                tgt_id = abs_to_id.get(resolved)
                if tgt_id is None:
                    continue
                key = (src_id, tgt_id)
                if key in edge_map and lineno not in edge_map[key]["lines"]:
                    edge_map[key]["lines"].append(lineno)

    for e in edges:
        e["lines"].sort()
    return edges


def add_code_doc_edges(
    source_nodes: list[dict],
    path_to_doc_id: dict[str, str],
    project_root: Path,
    md_cache: list,
) -> list[dict]:
    """Add code->doc edges: which docs mention each non-doc file.

    Sources are all non-doc nodes — .py as before, plus config / locale /
    web-asset files (the cfg→doc case): find_related_docs matches by
    filename, so nothing code-specific is required. The md corpus and the
    scan base dir are project-wide, hence doc keys come back relative to
    project_root and resolve through `path_to_doc_id`.
    """
    edges: list[dict] = []
    seen: set[tuple[str, str]] = set()
    root_str = str(project_root.resolve())
    # Matching in find_related_docs is filename-based (the absolute-path and
    # dotted-module patterns never occur in project docs), so files sharing
    # a name — ~100 __init__.py / conftest.py / callbacks.py etc. — produce
    # identical scan results. Scan once per unique filename and fan the hits
    # out to every file in the group.
    by_name: dict[str, list[dict]] = {}
    for node in source_nodes:
        path = project_root / node["path"]
        if not path.exists():
            continue
        by_name.setdefault(path.name, []).append(node)
    for group in by_name.values():
        rep_path = project_root / group[0]["path"]
        doc_results, verbose_out = find_related_docs(
            str(rep_path), root_str, True, md_cache
        )
        for node in group:
            for doc_key, count in doc_results.items():
                doc_id = path_to_doc_id.get(doc_key.replace("\\", "/"))
                if doc_id is None:
                    continue
                key = (node["id"], doc_id)
                if key in seen:
                    continue
                seen.add(key)
                line_nums = sorted(ln for ln, _ in verbose_out.get(doc_key, []))
                edges.append(
                    {
                        "source": node["id"],
                        "target": doc_id,
                        "type": "code->doc",
                        "weight": count,
                        "lines": line_nums,
                    }
                )
    return edges


def _resolve_python_import(
    module: str,
    level: int,
    source_relpath: Path,
    project_root: Path,
) -> str | None:
    """Resolve a Python import to a project-relative .py file path.

    - `level=0` → absolute import. The module dotted-path must resolve to
      `<project_root>/<module>.py`.
    - `level>0` → relative. Walk up `level - 1` directories from the source
      file's package, then append `module` (if any).
    - Always picks `foo.py`; never falls back to `foo/__init__.py`.
    Returns POSIX path relative to project_root, or None if the target
    isn't a real file in the project.
    """
    if level > 0:
        parts = list(source_relpath.parent.parts)
        drop = level - 1
        if drop > 0:
            if drop > len(parts):
                return None
            parts = parts[:-drop]
        base = Path(*parts) if parts else Path()
        if module:
            base = base / module.replace(".", "/")
    else:
        if not module:
            return None
        base = Path(module.replace(".", "/"))
    candidate = project_root / base.with_suffix(".py")
    if candidate.is_file():
        return base.with_suffix(".py").as_posix()
    return None


def _is_type_checking_test(test: ast.expr) -> bool:
    """True if an `If` test expression is `TYPE_CHECKING` (any prefix)."""
    if isinstance(test, ast.Name) and test.id == "TYPE_CHECKING":
        return True
    if isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING":
        return True
    return False


def _collect_module_string_consts(tree: ast.Module) -> dict[str, str]:
    """Collect top-level NAME = "string" assignments for const-folding.

    Used so dynamic imports via a named local — `MOD = "foo.bar";
    importlib.import_module(MOD)` — are still resolvable. Closes the
    common pattern that pure-literal detection misses; see backlog
    limitations for what it doesn't cover (multi-step rebinding,
    .format/f-strings, dict lookups, conditional branches).
    """
    consts: dict[str, str] = {}
    for stmt in tree.body:
        # NAME = "string"
        if (
            isinstance(stmt, ast.Assign)
            and len(stmt.targets) == 1
            and isinstance(stmt.targets[0], ast.Name)
            and isinstance(stmt.value, ast.Constant)
            and isinstance(stmt.value.value, str)
        ):
            consts[stmt.targets[0].id] = stmt.value.value
        # NAME: type = "string"
        elif (
            isinstance(stmt, ast.AnnAssign)
            and isinstance(stmt.target, ast.Name)
            and isinstance(stmt.value, ast.Constant)
            and isinstance(stmt.value.value, str)
        ):
            consts[stmt.target.id] = stmt.value.value
    return consts


def _split_dotted_module(s: str) -> tuple[str, int]:
    """Split a possibly-relative dotted module string into (module, level).

    Examples: ".sibling" → ("sibling", 1); "..pkg.sub" → ("pkg.sub", 2);
    "foo.bar" → ("foo.bar", 0). Used to handle relative dynamic imports
    via `importlib.import_module(".sibling", package=__name__)`.
    """
    level = 0
    while level < len(s) and s[level] == ".":
        level += 1
    return s[level:], level


def _extract_dynamic_import(
    call: ast.Call,
    consts: dict[str, str] | None = None,
) -> str | None:
    """Return the module string for an importlib / __import__ call.

    Recognised argument shapes:
    - `Constant("foo.bar")` — direct literal
    - `Name("MODULE_NAME")` where the name was assigned a string at the
      top level of this file (looked up in `consts`)
    Anything else (variable arg with non-string / non-top-level binding,
    f-strings, dict lookups, runtime concat) → None. Those are listed in
    the README's known-limitations as out of static scope.
    """
    func = call.func
    is_import_module = isinstance(func, ast.Attribute) and func.attr == "import_module"
    is_dunder_import = isinstance(func, ast.Name) and func.id == "__import__"
    if not (is_import_module or is_dunder_import):
        return None
    if not call.args:
        return None
    arg = call.args[0]
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return arg.value
    if consts and isinstance(arg, ast.Name) and arg.id in consts:
        return consts[arg.id]
    return None


class _ImportCollector(ast.NodeVisitor):
    """Collects (target_relpath, lineno, type_only) for project imports.

    Tracks `if TYPE_CHECKING:` block depth so imports inside those blocks
    can be tagged as type-only (typing-only zero-runtime relations) and
    emitted as a separate edge type by `add_code_code_edges`.

    Also catches dynamic imports via `importlib.import_module("literal")`
    and `__import__("literal")` — those ARE real runtime imports, just
    lazy, so they're emitted as regular code->code (type_only=False).
    Non-literal dynamic imports (variable arguments) are silently skipped:
    static analysis can't resolve them — they're listed in the README's
    known limitations.
    """

    def __init__(
        self,
        rel: Path,
        project_root: Path,
        module_consts: dict[str, str] | None = None,
    ) -> None:
        self.rel = rel
        self.project_root = project_root
        self.module_consts = module_consts or {}
        self.refs: list[tuple[str, int, bool]] = []
        self._tc_depth = 0

    def visit_If(self, node: ast.If) -> None:
        if _is_type_checking_test(node.test):
            self._tc_depth += 1
            for child in node.body:
                self.visit(child)
            self._tc_depth -= 1
            for child in node.orelse:
                self.visit(child)
        else:
            self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            target = _resolve_python_import(alias.name, 0, self.rel, self.project_root)
            if target:
                self.refs.append((target, node.lineno, bool(self._tc_depth)))

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        level = node.level or 0
        if module or level > 0:
            target = _resolve_python_import(module, level, self.rel, self.project_root)
            if target:
                self.refs.append((target, node.lineno, bool(self._tc_depth)))
        if level > 0 and not module:
            for alias in node.names:
                target = _resolve_python_import(
                    alias.name, level, self.rel, self.project_root
                )
                if target:
                    self.refs.append((target, node.lineno, bool(self._tc_depth)))

    def visit_Call(self, node: ast.Call) -> None:
        target_module = _extract_dynamic_import(node, self.module_consts)
        if target_module:
            # Handle relative dynamic imports: ".sibling" / "..pkg.sub"
            # The two-arg form `import_module(name, package=__name__)`
            # delegates relativity to the leading dots — `package` itself
            # is assumed to be __name__ (most common) and not parsed.
            mod_name, level = _split_dotted_module(target_module)
            target = _resolve_python_import(
                mod_name, level, self.rel, self.project_root
            )
            if target:
                self.refs.append((target, node.lineno, bool(self._tc_depth)))
        self.generic_visit(node)


def _parse_code_trees(
    code_nodes: list[dict],
    project_root: Path,
) -> dict[str, ast.AST]:
    """Read and parse every code file exactly once.

    The parsed trees are shared by the import collector and the docstring
    collector — previously each phase re-read and re-parsed all files.
    Files that fail to read or parse are simply absent from the mapping.
    """
    trees: dict[str, ast.AST] = {}
    for code_node in code_nodes:
        path = project_root / code_node["id"]
        try:
            source = path.read_text(encoding="utf-8")
            trees[code_node["id"]] = ast.parse(source, filename=str(path))
        except (SyntaxError, OSError, UnicodeDecodeError):
            continue
    return trees


def _collect_python_imports(
    tree: ast.AST,
    rel: Path,
    project_root: Path,
) -> list[tuple[str, int, bool]]:
    """Return [(target, lineno, type_only)...] from a parsed module tree.

    Skips external libraries and __init__-only resolutions. The `type_only`
    flag is True for imports inside `if TYPE_CHECKING:` blocks, which can
    be rendered as a distinct edge type (no runtime effect — only typing).
    """
    consts = _collect_module_string_consts(tree)
    collector = _ImportCollector(rel, project_root, consts)
    collector.visit(tree)
    return collector.refs


def _collect_docstring_refs(
    tree: ast.AST,
) -> list[tuple[str, int]]:
    """Extract file references from module / class / function docstrings.

    Returns [(reference_string, lineno), ...]. The reference is a raw string
    as it appears in the docstring (resolved to a project node later by
    `add_docstring_edges`). Lineno is the line where the docstring's owner
    is declared (close enough — full docstring spans are tedious to compute).
    """
    doc_blocks: list[tuple[str, int]] = []
    mod_doc = ast.get_docstring(tree)
    if mod_doc:
        doc_blocks.append((mod_doc, 1))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            doc = ast.get_docstring(node)
            if doc:
                doc_blocks.append((doc, node.lineno))
    refs: list[tuple[str, int]] = []
    for text, lineno in doc_blocks:
        for ref in extract_file_references(text):
            refs.append((ref, lineno))
    return refs


def _build_node_lookup(
    node_ids: set[str],
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Build two indexes for resolving docstring file refs to node ids.

    Returns (by_filename, by_stem): full filename (with extension) and
    stem (no extension) → list of matching node ids.
    """
    by_filename: dict[str, list[str]] = {}
    by_stem: dict[str, list[str]] = {}
    for node_id in node_ids:
        p = Path(node_id)
        by_filename.setdefault(p.name, []).append(node_id)
        by_stem.setdefault(p.stem, []).append(node_id)
    return by_filename, by_stem


def _resolve_docstring_ref(
    ref: str,
    node_ids: set[str],
    by_filename: dict[str, list[str]],
    by_stem: dict[str, list[str]],
) -> str | None:
    """Best-effort resolution of a docstring file reference to a node id."""
    if ref in node_ids:
        return ref
    name = Path(ref).name
    if name in by_filename and len(by_filename[name]) == 1:
        return by_filename[name][0]
    stem = Path(ref).stem
    if stem in by_stem and len(by_stem[stem]) == 1:
        return by_stem[stem][0]
    return None


def add_docstring_edges(
    code_nodes: list[dict],
    all_node_ids: set[str],
    code_trees: dict[str, ast.AST],
) -> list[dict]:
    """Add 'docstring' edges for files mentioned inside Python docstrings.

    Sources are code files; targets are any node (doc or code) referenced
    from a module / class / function docstring. Resolution is best-effort:
    full-path match first, then unambiguous filename match, then
    unambiguous stem match. Ambiguous refs are dropped. Self-references
    skipped.
    """
    by_filename, by_stem = _build_node_lookup(all_node_ids)
    edge_map: dict[tuple[str, str], dict] = {}
    edges: list[dict] = []
    for code_node in code_nodes:
        tree = code_trees.get(code_node["id"])
        if tree is None:
            continue
        for ref, lineno in _collect_docstring_refs(tree):
            target_id = _resolve_docstring_ref(ref, all_node_ids, by_filename, by_stem)
            if not target_id or target_id == code_node["id"]:
                continue
            key = (code_node["id"], target_id)
            existing = edge_map.get(key)
            if existing:
                if lineno not in existing["lines"]:
                    existing["lines"].append(lineno)
                existing["weight"] += 1
            else:
                edge = {
                    "source": code_node["id"],
                    "target": target_id,
                    "type": "docstring",
                    "weight": 1,
                    "lines": [lineno],
                }
                edges.append(edge)
                edge_map[key] = edge
    for e in edges:
        e["lines"].sort()
    return edges


def add_code_code_edges(
    code_nodes: list[dict],
    project_root: Path,
    code_trees: dict[str, ast.AST],
) -> list[dict]:
    """Add code→code edges from Python imports between project files.

    Splits by `type_only` flag from the AST collector:
    - regular runtime imports → edge type "code->code"
    - imports inside `if TYPE_CHECKING:` blocks → edge type "type-only"
    Both kinds between the same source/target produce two distinct edges
    (different types), so the legend can toggle them independently.
    """
    code_ids = {n["id"] for n in code_nodes}
    edge_map: dict[tuple[str, str, str], dict] = {}
    edges: list[dict] = []
    for code_node in code_nodes:
        tree = code_trees.get(code_node["id"])
        if tree is None:
            continue
        for target_relpath, lineno, type_only in _collect_python_imports(
            tree, Path(code_node["id"]), project_root
        ):
            if target_relpath == code_node["id"]:
                continue  # self-import (rare, but skip just in case)
            if target_relpath not in code_ids:
                continue  # target isn't part of the graph
            edge_type = "type-only" if type_only else "code->code"
            key = (code_node["id"], target_relpath, edge_type)
            existing = edge_map.get(key)
            if existing:
                if lineno not in existing["lines"]:
                    existing["lines"].append(lineno)
                existing["weight"] += 1
            else:
                edge = {
                    "source": code_node["id"],
                    "target": target_relpath,
                    "type": edge_type,
                    "weight": 1,
                    "lines": [lineno],
                }
                edges.append(edge)
                edge_map[key] = edge
    for e in edges:
        e["lines"].sort()
    return edges


# ====== SECTION: git overlay (collect / annotate / ghost) ======
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


# ====== SECTION: layout hints ======
def compute_layout_hints(nodes: list[dict], edges: list[dict]) -> None:
    """Compute degree and proportional node size (mutates nodes in-place)."""
    degree: dict[str, int] = defaultdict(int)
    for edge in edges:
        degree[edge["source"]] += 1
        degree[edge["target"]] += 1
    max_degree = max(degree.values()) if degree else 1
    min_size, max_size = 5, 20
    for node in nodes:
        d = degree[node["id"]]
        node["degree"] = d
        if node.get("ghost"):
            # Ghost nodes keep their fixed size (set in add_ghost_nodes_and_edges).
            continue
        node["size"] = min_size + (max_size - min_size) * (d / max_degree)


# ====== SECTION: HTML assembly (CSS / BODY / JS) ======
# Pinned D3.js v7. Regenerate the hash when bumping the upstream version:
#   curl -A 'Mozilla/5.0' -s https://d3js.org/d3.v7.min.js | sha256sum
D3_URL = "https://d3js.org/d3.v7.min.js"
D3_SHA256 = "f2094bbf6141b359722c4fe454eb6c4b0f0e42cc10cc7af921fc158fceb86539"


def _d3_sri() -> str:
    return "sha256-" + base64.b64encode(bytes.fromhex(D3_SHA256)).decode("ascii")


def _get_d3_script(embed: bool) -> str:
    """Return a D3.js <script> tag.

    CDN mode: pinned URL with Subresource Integrity (browser verifies hash).
    Embed mode: download, verify SHA-256 against D3_SHA256, inline the source.
    Mismatch in embed mode aborts the build — protects against MITM and
    surfaces upstream version bumps so the constant gets refreshed deliberately.
    """
    if not embed:
        return (
            f'<script src="{D3_URL}" '
            f'integrity="{_d3_sri()}" crossorigin="anonymous"></script>'
        )
    req = urllib.request.Request(D3_URL, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            d3_bytes = resp.read()
    except urllib.error.URLError as e:
        print(f"ERROR: Could not download D3.js: {e}", file=sys.stderr)
        sys.exit(1)
    actual = hashlib.sha256(d3_bytes).hexdigest()
    if actual != D3_SHA256:
        print(
            "ERROR: D3.js SHA-256 mismatch — refusing to embed.\n"
            f"  expected: {D3_SHA256}\n"
            f"  actual:   {actual}\n"
            f"  url:      {D3_URL}\n"
            "This may indicate a MITM attack, or an upstream D3 v7 release.\n"
            "If the new version is trusted, update D3_SHA256 in build-graph.py.",
            file=sys.stderr,
        )
        sys.exit(1)
    return f"<script>{d3_bytes.decode('utf-8')}</script>"


# ---------------------------------------------------------------------------
# HTML template parts (concatenated in render_html to avoid {}-escaping in JS)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# HTML template parts. The CSS/JS/HTML body are kept as separate package
# resources under build_graph/resources/ for IDE syntax highlighting and
# easier translator/styling work. They are concatenated verbatim in
# render_html — no template engine.
# ---------------------------------------------------------------------------
_ASSETS_DIR = _resources.files("build_graph") / "resources"
_CSS = (_ASSETS_DIR / "style.css").read_text(encoding="utf-8")
_BODY = (_ASSETS_DIR / "body.html").read_text(encoding="utf-8")
# main.js content is concatenated as-is; backslashes inside (e.g. JS \u
# escapes) must remain literal — that's handled by the file being raw text.
_JS = (_ASSETS_DIR / "main.js").read_text(encoding="utf-8")


# ====== SECTION: palette / category codes / dead-code exemptions ======
def _procedural_color(category: str, saturated: bool) -> str:
    """Deterministic category colour: hue = stable hash of the name.

    md5 (not `hash()`, which is seeded per process) keeps colours identical
    between builds and across machines. Pastel and saturated variants share
    the hue — the hue-aligned palette invariant holds for generated colours.
    """
    digest = hashlib.md5(category.encode("utf-8"), usedforsecurity=False).digest()
    hue = int.from_bytes(digest[:2], "big") % 360 / 360.0
    lightness, sat = (0.45, 0.65) if saturated else (0.82, 0.55)
    r, g, b = colorsys.hls_to_rgb(hue, lightness, sat)
    return f"#{round(r * 255):02x}{round(g * 255):02x}{round(b * 255):02x}"


def build_palette(
    categories: set[str],
    toml_colors: dict[str, str],
    toml_colors_saturated: dict[str, str],
) -> tuple[dict[str, str], dict[str, str]]:
    """Colour map for every category: TOML pins win, the rest is procedural."""
    colors: dict[str, str] = {}
    saturated: dict[str, str] = {}
    for cat in sorted(categories):
        colors[cat] = toml_colors.get(cat) or _procedural_color(cat, False)
        saturated[cat] = toml_colors_saturated.get(cat) or _procedural_color(cat, True)
    return colors, saturated


# Files that legitimately have no incoming imports / doc mentions — flagged
# so the UI's dead-code detector skips them. Extendable via [dead_code].exempt
# glob patterns in graph.toml. Test modules are entry points too: pytest
# collects them, nothing imports them.
_DEAD_EXEMPT_NAMES = {"__init__.py", "conftest.py", "main.py"}
_DEAD_EXEMPT_NAME_PATTERNS = ("test_*.py",)
_DEAD_EXEMPT_PATH_PARTS = ("alembic/versions/",)


def apply_dead_exemptions(nodes: list[dict], exempt_globs: list[str]) -> None:
    """Mark nodes the dead-code detector must ignore (mutates in place)."""
    for n in nodes:
        if n.get("ghost"):
            continue
        path = n["path"]
        if (
            n["label"] in _DEAD_EXEMPT_NAMES
            or any(fnmatch.fnmatch(n["label"], p) for p in _DEAD_EXEMPT_NAME_PATTERNS)
            or any(part in path for part in _DEAD_EXEMPT_PATH_PARTS)
            or any(fnmatch.fnmatch(path, pat) for pat in exempt_globs)
        ):
            n["deadExempt"] = True


# ====== SECTION: rendering & CLI entry point ======

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


def _safe_json(obj: object) -> str:
    r"""``json.dumps`` with ``</script>`` protection for inline-script embedding.

    Replaces ``</`` with ``<\\/`` so a payload like ``</script><script>...``
    inside any string field cannot terminate the host ``<script>`` block.
    JSON spec accepts ``\\/`` as a valid escape for ``/``; ``JSON.parse``
    and JS string literal both decode it back to ``/``, so the runtime
    payload is unchanged — only the on-the-wire serialisation differs.
    """
    return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")


def render_html(
    nodes: list[dict],
    edges: list[dict],
    colors: dict[str, str],
    colors_saturated: dict[str, str],
    project_root_posix: str,
    output_path: Path,
    embed_d3: bool = False,
    git_data: dict | None = None,
) -> None:
    """Write a self-contained HTML graph file to output_path."""
    graph_json = _safe_json({"nodes": nodes, "links": edges})
    colors_json = _safe_json(colors)
    colors_sat_json = _safe_json(colors_saturated)
    git_json = _safe_json(git_data) if git_data else "null"
    d3_tag = _get_d3_script(embed_d3)
    # --no-cdn means "no external requests at all": along with embedding D3,
    # drop the Google Fonts link — the CSS font stack falls back to system-ui.
    font_tags = (
        ""
        if embed_d3
        else (
            '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
            '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
            '<link href="https://fonts.googleapis.com/css2?family=Comic+Relief'
            '&display=swap" rel="stylesheet">\n'
        )
    )
    html = (
        '<!DOCTYPE html>\n<html lang="en">\n<head>\n'
        '<meta charset="UTF-8">\n'
        + font_tags
        + "<title>Project Dependency Graph</title>\n"
        + d3_tag
        + "\n<style>\n"
        + _CSS
        + "</style>\n</head>\n<body>\n"
        + _BODY
        + "<script>\nconst GRAPH_DATA = "
        + graph_json
        + ";\nconst NODE_COLORS = "
        + colors_json
        + ";\nconst NODE_COLORS_SATURATED = "
        + colors_sat_json
        + ";\nconst PROJECT_ROOT = "
        + _safe_json(project_root_posix)
        + ";\nconst GIT_DATA = "
        + git_json
        + ";\nconst APP_VERSION = "
        + _safe_json(__version__)
        + ";\nconst APP_AUTHOR = "
        + _safe_json(__author__)
        + ";\nconst APP_AUTHOR_URL = "
        + _safe_json(__author_url__)
        + ";\n"
        + _JS
        + "</script>\n</body>\n</html>\n"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")


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

    print(f"Discovering files (scope={args.scope})...")
    files, git_used = list_project_files(project_root)
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
    all_edges: list[dict] = build_doc_edges(md_nodes, project_root)
    print(f"  {len(all_edges)} doc->doc edges")

    if not args.docs_only:
        print("Finding code->doc references (this may take a moment)...")
        path_to_doc_id = {n["path"]: n["id"] for n in md_nodes}
        md_cache = []
        for n in md_nodes:
            f = project_root / n["path"]
            try:
                content = f.read_text(encoding="utf-8")
            except Exception as exc:  # mirror load_md_files behaviour
                print(f"Warning: Could not read {f}: {exc}")
                continue
            md_cache.append((f, content, content.splitlines()))
        code_edges = add_code_doc_edges(
            other_nodes, path_to_doc_id, project_root, md_cache
        )
        print(f"  {len(code_edges)} code->doc edges")
        all_edges.extend(code_edges)

        print("Finding code->code imports (AST)...")
        code_trees = _parse_code_trees(py_nodes, project_root)
        code_code_edges = add_code_code_edges(py_nodes, project_root, code_trees)
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
    if args.mock_git:
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

    print("Computing layout hints...")
    compute_layout_hints(all_nodes, all_edges)
    apply_dead_exemptions(all_nodes, (config.get("dead_code") or {}).get("exempt", []))

    categories = {n["type"] for n in all_nodes if not n.get("ghost")}
    colors, colors_saturated = build_palette(
        categories, config.get("colors", {}), config.get("colors_saturated", {})
    )
    cat_codes = build_cat_codes(categories)

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
