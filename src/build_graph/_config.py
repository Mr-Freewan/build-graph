"""Config loading, autodiscovery classification and graph.toml lifecycle.

Covers three concerns that share the discovery machinery:
- file enumeration (git ls-files with a filesystem-walk fallback) and
  kind/category classification (TOML rules over autodiscovery),
- node building (`build_all_nodes`),
- the --init / --diff / --merge config bootstrap.
"""

import argparse
import fnmatch
import os
import subprocess
import sys
import tomllib
from pathlib import Path

from build_graph._render import build_palette


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


# --- config bootstrap (--init / --diff / --merge) ---------------------------
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
