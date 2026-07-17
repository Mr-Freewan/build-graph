#!/usr/bin/env python3
"""Verify that file references in .md files actually exist.

Usage:
    verify-doc-links
    verify-doc-links docs/reference/
    verify-doc-links docs/reference/project-structure.md -v
"""

import argparse
import re
import subprocess
import sys
import urllib.parse
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

from build_graph._common import Colors, print_separator
from build_graph._console import ensure_utf8_stdout

# Source of truth for excludes — git: we query once below
# `git ls-files --others --ignored --exclude-standard --directory`. This
# gives exact .gitignore picture (nested, negation `!keep`, globs) without
# custom parser. What's in .gitignore — the script doesn't touch: `.venv/`,
# `__pycache__/`, any dot-folder.
#
# Fallback when git is not available (`.gitignore` also has no meaning without git) —
# read `<project root>/exclude-dirs.txt` (catalog names, one per line).
# If missing — last resort is hardcoded inline.
EXCLUDE_DIRS_NAME = "exclude-dirs.txt"
LAST_RESORT_SKIP_DIRS = frozenset({".git", "__pycache__"})


@lru_cache(maxsize=4)
def _gitignored_paths(project_root: Path) -> frozenset[Path] | None:
    """Resolved paths that git considers ignored per .gitignore.

    Includes untracked files and directories under exclude-standard rules
    (`.gitignore` of all levels, `.git/info/exclude`, global excludesfile).
    `.git/` itself is not in .gitignore — added manually.

    Returns ``None`` if git is unavailable or not a repo — caller
    should switch to fallback by catalog names.
    """
    try:
        result = subprocess.run(
            [
                "git",
                "ls-files",
                "--others",
                "--ignored",
                "--exclude-standard",
                "--directory",
            ],
            cwd=project_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=15,
            check=True,
        )
    except (
        subprocess.CalledProcessError,
        FileNotFoundError,
        subprocess.TimeoutExpired,
        OSError,
    ):
        return None
    paths: set[Path] = {(project_root / ".git").resolve()}
    for line in result.stdout.splitlines():
        line = line.strip()
        if line:
            paths.add((project_root / line).resolve())
    return frozenset(paths)


@lru_cache(maxsize=4)
def _fallback_skip_names(project_root: Path) -> frozenset[str]:
    """Catalog names from <project root>/exclude-dirs.txt (one per line).

    Used when `_gitignored_paths` returned ``None`` (git unavailable).
    If file is missing — return ``LAST_RESORT_SKIP_DIRS``.
    """
    try:
        text = (project_root / EXCLUDE_DIRS_NAME).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return LAST_RESORT_SKIP_DIRS
    names: set[str] = set()
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        names.add(line)
    return frozenset(names) or LAST_RESORT_SKIP_DIRS


def _is_skipped(file_path: Path, project_root: Path) -> bool:
    """True if file_path is git-ignored or its component in fallback list.

    Two-tier strategy:
      1) if git returned ignored paths list → check hit in them.
      2) if git unavailable → read `<project root>/exclude-dirs.txt` (or
         `LAST_RESORT_SKIP_DIRS`) and match by any path component name.
    """
    ignored = _gitignored_paths(project_root)
    if ignored is None:
        skip_names = _fallback_skip_names(project_root)
        return any(part in skip_names for part in file_path.parts)
    try:
        resolved = file_path.resolve()
    except (OSError, ValueError):
        return False
    # Walk up the file's own ancestry and hash-probe the ignored set —
    # O(depth) per file instead of O(len(ignored) * depth).
    if resolved in ignored:
        return True
    return any(parent in ignored for parent in resolved.parents)


def build_file_index(project_root: Path) -> tuple[dict[str, Path], dict[str, Path]]:
    """Build an index of all files in the project by filename and by path suffix.

    Returns:
        Tuple of (filename_index, suffix_index)
        filename_index: filename -> Path (only unique filenames)
        suffix_index: normalized relative path -> Path (all files)
    """
    filename_index = {}
    suffix_index = {}
    for file_path in project_root.rglob("*"):
        if file_path.is_file() and not _is_skipped(file_path, project_root):
            filename = file_path.name
            if filename not in filename_index:
                filename_index[filename] = file_path.resolve()
            # Index by all possible relative path suffixes
            # e.g. smm_bot_async/core/security/access.py
            # also core/security/access.py, security/access.py, access.py
            parts = file_path.relative_to(project_root).parts
            for i in range(len(parts)):
                suffix = "/".join(parts[i:])
                if suffix not in suffix_index:
                    suffix_index[suffix] = file_path.resolve()
    return filename_index, suffix_index


def resolve_file_reference(
    ref: str,
    md_file: Path,
    project_root: Path,
    filename_index: dict[str, Path],
    suffix_index: dict[str, Path],
    path_cache: dict[str, Path | None],
) -> Path | None:
    """Resolve a file reference to an actual path.

    Returns:
        Path if file exists, None otherwise
    """
    ref_normalized = ref.replace("\\", "/")

    # Check cache first
    if ref_normalized in path_cache:
        return path_cache[ref_normalized]

    # Try as absolute path
    if Path(ref).exists():
        abs_path = Path(ref).resolve()
        path_cache[ref_normalized] = abs_path
        return abs_path

    # If reference has directory separators, try relative paths
    if "/" in ref or "\\" in ref:
        # Try relative to the .md file's directory (handles ../ and ./)
        rel_to_md = (md_file.parent / ref).resolve()
        if rel_to_md.exists():
            path_cache[ref_normalized] = rel_to_md
            return rel_to_md

        # Try relative to project root
        rel_path = (project_root / ref).resolve()
        if rel_path.exists():
            path_cache[ref_normalized] = rel_path
            return rel_path

        # Look up in suffix index (replaces rglob)
        suffix_match: Path | None = suffix_index.get(
            ref_normalized
        ) or suffix_index.get(ref_normalized.lstrip("/"))
        if suffix_match:
            path_cache[ref_normalized] = suffix_match
            return suffix_match
    else:
        # Search for file by name using pre-built index
        filename_match: Path | None = filename_index.get(ref)
        if filename_match:
            path_cache[ref_normalized] = filename_match
            return filename_match

    path_cache[ref_normalized] = None
    return None


# =============================================================================
# extract_file_references — robust markdown reference scanner
# =============================================================================
# Each regex matches a different Markdown / common-extension flavour. Captures
# raw URL/path strings; cleaning (fragment/query strip, urldecode, title strip)
# happens in `_clean_url`. Final extension validation happens after cleaning,
# so the regexes themselves don't need to enumerate extensions — they capture
# anything paren/bracket-shaped, and post-processing filters by extension.
#
# Supported flavours:
#   - inline link        [text](path)        / [text](path "title") / [text](path#frag)
#   - image syntax       ![alt](path)        — same shape with optional `!`
#   - reference defs     [ref]: path         (multi-line, possibly <wrapped>)
#   - wiki-links         [[file]] / [[file|alias]] / [[file#section]] / [[file^block]]
#   - HTML anchors       <a href="path">     (GFM allows raw HTML)
#   - HTML images        <img src="path">
#   - inline code        `path.ext`          (filename in backticks)
#   - tree listings      ├── / └── / +-- / |-- etc. (broadened from previous)
#
# Multi-line links (where the [text] wraps across lines) are supported because
# `[^\]]*` matches newlines — no `re.DOTALL` needed for the simple cases.
# Known limitations (documented in build-graph backlog):
#   - angle-bracket auto-links <https://...> — almost always external URLs
#   - footnote definitions [^1]: ... — payload is rarely a file path
#   - Hugo / Jekyll templating ({{< ref >}}, {% link %}) — project-specific
# -----------------------------------------------------------------------------
_RE_BACKTICK = re.compile(r"`([^`\n]+)`")
# Bare extension like `.md` / `.py` / `.yaml` is a format mention, not a path.
# Applied AFTER resolve fails — real dot-files (.env, .gitignore) resolve via
# filename_index and never reach this check.
_RE_BARE_EXT = re.compile(r"\.[A-Za-z0-9]+")
_RE_INLINE_LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
_RE_REFLINK = re.compile(
    r"^[ \t]*\[[^\]\n]+\]:[ \t]+(\S+(?:\s+\"[^\"]*\")?)",
    re.MULTILINE,
)
_RE_WIKI = re.compile(r"!?\[\[([^\[\]|#^\n]+)(?:[|#^][^\]\n]*)?\]\]")
_RE_HTML_A = re.compile(r'<a\b[^>]*\bhref=(["\'])([^"\']+)\1', re.IGNORECASE)
_RE_HTML_IMG = re.compile(r'<img\b[^>]*\bsrc=(["\'])([^"\']+)\1', re.IGNORECASE)
# Tree-listing prefix: one or more box-drawing / ASCII connector chars,
# followed by whitespace, followed by a path-like token. Covers ├── / └──
# / │   / +-- / |-- / \-- variants from different tree-tools.
_RE_TREE = re.compile(
    r"(?:^|\n)[ \t]*[│├└─\-+\\|]+[ \t]+(\S+)",
    re.MULTILINE,
)
# In-file ignore markers (HTML comments, invisible in rendered Markdown):
#   <!-- broken-link-ok: reason --> on the SAME line as a broken ref → skip
#   <!-- broken-links-ok-start --> ... <!-- broken-links-ok-end --> → skip range
#   <!-- ignore-ref: path/to/file.py --> anywhere in file → skip that exact ref
_RE_INLINE_OK = re.compile(r"<!--\s*broken-link-ok\b[^>]*-->")
_RE_BLOCK_START = re.compile(r"<!--\s*broken-links-ok-start\s*-->")
_RE_BLOCK_END = re.compile(r"<!--\s*broken-links-ok-end\s*-->")
_RE_IGNORE_REF = re.compile(r"<!--\s*ignore-ref:\s*(\S+?)\s*-->")

_VALID_EXTENSIONS = {
    "py",
    "md",
    "yaml",
    "yml",
    "toml",
    "ini",
    "cfg",
    "json",
    "conf",
    "env",
    "config",
}
_EXT_RE = re.compile(r"\.([A-Za-z0-9]+)$")


def _clean_url(raw: str) -> str:
    """Normalise a captured URL/path string for resolution.

    Steps:
    - strip surrounding whitespace and angle-bracket auto-link wrappers
    - strip optional title (e.g. `path "Title"` or `path 'Title'`)
    - strip fragment (`#section`) and query (`?v=2`)
    - URL-decode (`%20` → space, etc.)
    """
    url = raw.strip()
    if url.startswith("<") and url.endswith(">"):
        url = url[1:-1].strip()
    # Title: `path "T"` or `path 'T'` — split on first space-quote pair.
    for q in (' "', " '"):
        idx = url.find(q)
        if idx > 0:
            url = url[:idx].strip()
            break
    # Strip fragment / query.
    for sep in ("#", "?"):
        idx = url.find(sep)
        if idx > 0:
            url = url[:idx]
    try:
        url = urllib.parse.unquote(url)
    except Exception:
        pass
    return url.strip()


def _is_external(url: str) -> bool:
    """Skip URLs that clearly point outside the project."""
    if url.startswith(
        (
            "http://",
            "https://",
            "mailto:",
            "ftp://",
            "ftps://",
            "tel:",
            "data:",
            "ws://",
            "wss://",
        )
    ):
        return True
    if url.startswith("//"):  # protocol-relative
        return True
    # Absolute Unix sys paths (filter same as the prior heuristic).
    if url.startswith(("/etc/", "/var/", "/usr/", "/tmp/", "/opt/", "/proc/")):
        return True
    # Absolute Windows paths.
    if len(url) > 2 and url[1] == ":" and url[2] in ("\\", "/"):
        return True
    return False


def _has_valid_extension(url: str) -> bool:
    m = _EXT_RE.search(url)
    return bool(m and m.group(1).lower() in _VALID_EXTENSIONS)


def extract_file_references(content: str) -> list[str]:
    """Extract project-relative file references from markdown content.

    Captures candidates from many markdown flavours (inline links, image
    syntax, reference-style definitions, wiki-links, raw HTML, inline code,
    tree listings), normalises each (strips fragment/query/title, decodes
    URL-encoding), filters externals (http/mailto/abs-system-paths) and
    keeps only refs ending in a known extension (py / md / yaml / etc.).

    Returns:
        List of raw file-reference strings (cleaned, but not resolved to
        actual filesystem paths). Order preserves first-seen.
    """
    candidates: list[str] = []

    for m in _RE_INLINE_LINK.finditer(content):
        candidates.append(m.group(1))
    for m in _RE_REFLINK.finditer(content):
        candidates.append(m.group(1))
    for m in _RE_WIKI.finditer(content):
        candidates.append(m.group(1))
    for m in _RE_HTML_A.finditer(content):
        candidates.append(m.group(2))
    for m in _RE_HTML_IMG.finditer(content):
        candidates.append(m.group(2))
    for m in _RE_BACKTICK.finditer(content):
        raw = m.group(1)
        # Backtick content is noisy — drop command-line examples (pytest foo.py,
        # make build, git log -- file.py) before they get parsed as paths.
        if " " in raw or "\t" in raw:
            continue
        candidates.append(raw)
    for m in _RE_TREE.finditer(content):
        candidates.append(m.group(1))

    references: list[str] = []
    seen: set[str] = set()
    for raw in candidates:
        url = _clean_url(raw)
        if not url:
            continue
        if "*" in url:  # glob — not a literal path reference
            continue
        if _is_external(url):
            continue
        if not _has_valid_extension(url):
            continue
        if url in seen:
            continue
        seen.add(url)
        references.append(url)
    return references


def _collect_ignore_markers(
    lines: list[str],
) -> tuple[set[int], set[int], set[str]]:
    """Pre-scan lines for ignore markers.

    Returns:
        Tuple of (block_lines, inline_lines, ignored_paths):
        - block_lines: line numbers (1-based) inside an open ok-block
        - inline_lines: line numbers carrying an on-the-same-line broken-link-ok
        - ignored_paths: refs explicitly silenced via <!-- ignore-ref: path -->
    """
    block_lines: set[int] = set()
    inline_lines: set[int] = set()
    ignored_paths: set[str] = set()
    in_block = False
    for line_num, line in enumerate(lines, 1):
        if _RE_BLOCK_START.search(line):
            in_block = True
        if in_block:
            block_lines.add(line_num)
        if _RE_BLOCK_END.search(line):
            in_block = False
        if _RE_INLINE_OK.search(line):
            inline_lines.add(line_num)
        for m in _RE_IGNORE_REF.finditer(line):
            ignored_paths.add(m.group(1))
    return block_lines, inline_lines, ignored_paths


def check_md_file(
    md_file: Path,
    project_root: Path,
    filename_index: dict[str, Path],
    suffix_index: dict[str, Path],
    path_cache: dict[str, Path | None],
    known_brokens: set[str],
) -> dict:
    """Check a single .md file for broken file references.

    Returns:
        Dict with broken references and their line numbers
    """
    try:
        content = md_file.read_text(encoding="utf-8")
        lines = content.splitlines()
        references = extract_file_references(content)
        block_lines, inline_lines, ignored_paths = _collect_ignore_markers(lines)

        broken_refs = defaultdict(list)

        for ref in references:
            if ref in known_brokens:
                continue
            if ref in ignored_paths:
                continue

            resolved = resolve_file_reference(
                ref, md_file, project_root, filename_index, suffix_index, path_cache
            )
            if resolved is None:
                # Bare extension (`.md`, `.py`, `.yaml`, ...) that didn't
                # resolve is a format mention, not a real reference.
                # Real dot-files (`.env`) resolve via filename_index above.
                if _RE_BARE_EXT.fullmatch(ref):
                    continue
                for line_num, line in enumerate(lines, 1):
                    if ref in line:
                        if line_num in block_lines or line_num in inline_lines:
                            continue
                        broken_refs[ref].append((line_num, line.strip()))

        return broken_refs
    except Exception as e:
        print(f"Warning: Could not read {md_file}: {e}")
        return {}


def load_known_brokens(known_brokens_file: Path) -> set[str]:
    """Load known broken references from a file.

    Returns:
        Set of reference patterns to ignore
    """
    if not known_brokens_file.exists():
        return set()

    try:
        content = known_brokens_file.read_text(encoding="utf-8")
        # Each line is a reference pattern, skip comments (#) and empty lines
        return set(
            line.strip()
            for line in content.splitlines()
            if line.strip() and not line.strip().startswith("#")
        )
    except Exception as e:
        print(f"Warning: Could not read known brokens file: {e}")
        return set()


def main() -> None:
    """Main entry point for the script."""
    ensure_utf8_stdout()
    parser = argparse.ArgumentParser(
        description="Verify that file references in .md files actually exist"
    )
    parser.add_argument(
        "path",
        nargs="?",
        help="Path to .md file or directory to check (default: docs/)",
        default="docs",
    )
    parser.add_argument(
        "--root",
        default=".",
        help="Project root the references resolve against (default: cwd)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show specific lines with broken references",
    )
    parser.add_argument(
        "--known-brokens",
        type=str,
        default=None,
        help="Path to file with known broken references to ignore",
    )

    args = parser.parse_args()

    project_root = Path(args.root).resolve()
    target_path = Path(args.path)

    # Load known brokens if specified or use default
    known_brokens = set()
    if args.known_brokens:
        known_brokens_file = Path(args.known_brokens)
        if not known_brokens_file.is_absolute():
            known_brokens_file = project_root / known_brokens_file
    else:
        # Default to known-brokens.txt in the project root
        known_brokens_file = project_root / "known-brokens.txt"

    known_brokens = load_known_brokens(known_brokens_file)
    if known_brokens:
        print(f"Loaded {len(known_brokens)} known broken references to ignore\n")

    # Resolve target path relative to project root if needed
    if not target_path.is_absolute():
        target_path = project_root / target_path

    # Find all .md files to check
    if target_path.is_file():
        if target_path.suffix != ".md":
            print(f"ERROR: Not a .md file: {target_path}")
            sys.exit(2)
        md_files = [target_path]
    elif target_path.is_dir():
        md_files = [
            f for f in target_path.rglob("*.md") if not _is_skipped(f, project_root)
        ]
    else:
        print(f"ERROR: Path not found: {target_path}")
        sys.exit(2)

    if not md_files:
        print("No .md files found")
        return

    print(f"Checking {len(md_files)} .md file(s) for broken file references:\n")

    # Build file index once for fast lookups
    print("Building file index...")
    filename_index, suffix_index = build_file_index(project_root)
    print(
        f"Indexed {len(filename_index)} unique filenames, "
        f"{len(suffix_index)} path suffixes\n"
    )

    files_with_broken_refs = []
    total_unique = 0
    total_occurrences = 0
    path_cache: dict[str, Path | None] = {}

    for md_file in md_files:
        broken_refs = check_md_file(
            md_file,
            project_root,
            filename_index,
            suffix_index,
            path_cache,
            known_brokens,
        )
        if broken_refs:
            files_with_broken_refs.append((md_file, broken_refs))
            total_unique += len(broken_refs)
            total_occurrences += sum(len(lines) for lines in broken_refs.values())

    # Print results
    if files_with_broken_refs:
        for md_file, broken_refs in sorted(files_with_broken_refs):
            print_separator()
            rel = md_file.relative_to(project_root)
            occ = sum(len(lines) for lines in broken_refs.values())
            print(
                f"{Colors.RED}⚠️  {rel}{Colors.RESET}  "
                f"({len(broken_refs)} unique, {occ} occurrence(s))"
            )
            for ref, lines in broken_refs.items():
                for line_num, _ in lines:
                    print(
                        f"    {md_file}:{line_num}  "
                        f"{Colors.RED}{Colors.BOLD}{ref}{Colors.RESET}"
                    )
        print_separator()
        print(
            f"{Colors.RED}{total_unique}{Colors.RESET} unique broken ref(s), "
            f"{Colors.RED}{total_occurrences}{Colors.RESET} occurrence(s) "
            f"across {len(files_with_broken_refs)} file(s)"
        )
        # Non-zero exit so CI / pre-commit hooks can gate on broken refs.
        sys.exit(1)
    else:
        print(f"{Colors.GREEN}All file references are valid{Colors.RESET}")


if __name__ == "__main__":
    main()
