#!/usr/bin/env python3
"""Find documentation files that mention a given code file.

Usage:
    find-related-docs src/mypkg/core/access.py
    find-related-docs tests/core/test_access.py
    find-related-docs --git-added      # pre-commit: staged files
"""

import argparse
import re
import subprocess
from bisect import bisect_right
from collections import defaultdict
from pathlib import Path

from build_graph._console import ensure_utf8_stdout


# ANSI color codes


class Colors:
    """ANSI color codes for terminal output."""

    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BLUE = "\033[94m"
    RESET = "\033[0m"
    BOLD = "\033[1m"


def print_separator() -> None:
    """Print a visual separator line."""
    print("─" * 100)


def is_code_or_config_file(file_path: Path) -> bool:
    """Check if a file is a code or configuration file that should be checked.

    Returns:
        True if file is .py, .md, or config file
    """
    code_extensions = {".py", ".md"}
    config_extensions = {
        ".yaml",
        ".yml",
        ".toml",
        ".ini",
        ".cfg",
        ".json",
        ".conf",
        ".env",
        ".config",
    }
    return file_path.suffix.lower() in code_extensions | config_extensions


_RESOLVED_DIR_CACHE: dict[str, Path] = {}


def _resolved_dir(docs_dir: str | Path) -> Path:
    """Path.resolve() with memoisation.

    On Windows every resolve() is a chain of syscalls; the same docs dir is
    resolved once per process instead of once per lookup call.
    """
    key = str(docs_dir)
    p = _RESOLVED_DIR_CACHE.get(key)
    if p is None:
        p = Path(key).resolve()
        _RESOLVED_DIR_CACHE[key] = p
    return p


# Per-md-file scan metadata (computed lazily, cached for the process):
# str(path) → (line_starts, line_flags).
#   line_starts[i] — offset of 0-based line i in the raw content, plus a
#       final sentinel, so a substring offset maps to a line via bisect;
#   line_flags[i]  — (in_code_block, in_mermaid) for scannable lines, or
#       None for ``` fence lines the scanner skips entirely.
_MD_META_CACHE: dict[str, tuple[list[int], list]] = {}


def _md_scan_meta(
    md_file: Path, content: str, lines: list[str]
) -> tuple[list[int], list]:
    """Line offsets + code-block/mermaid state per line, cached per file."""
    key = str(md_file)
    meta = _MD_META_CACHE.get(key)
    if meta is not None:
        return meta
    starts: list[int] = []
    pos = 0
    for seg in content.splitlines(keepends=True):
        starts.append(pos)
        pos += len(seg)
    starts.append(pos + 1)  # sentinel for bisect
    flags: list = []
    in_code_block = False
    in_mermaid = False
    for line in lines:
        if "```mermaid" in line:
            in_mermaid = True
            in_code_block = True
            flags.append(None)
            continue
        if in_mermaid and line.strip() == "```":
            in_mermaid = False
            in_code_block = False
            flags.append(None)
            continue
        if line.strip().startswith("```"):
            in_code_block = not in_code_block
            flags.append(None)
            continue
        flags.append((in_code_block, in_mermaid))
    meta = (starts, flags)
    _MD_META_CACHE[key] = meta
    return meta


def _lines_containing(content: str, needle: str, starts: list[int]) -> set[int]:
    """0-based indexes of lines where `needle` occurs (C-speed str.find)."""
    out: set[int] = set()
    i = content.find(needle)
    while i != -1:
        out.add(bisect_right(starts, i) - 1)
        i = content.find(needle, i + 1)
    return out


def load_md_files(
    docs_dir: str = "docs",
    exclude_dirs: tuple[str, ...] = (),
) -> list[tuple[Path, str, list[str]]]:
    """Read all .md files into memory once.

    Args:
        docs_dir: Documentation directory to scan.
        exclude_dirs: Directory names to skip anywhere under docs_dir
            (e.g. internal/private notes folders).

    Returns:
        List of (path, content, lines) tuples
    """
    docs_path = Path(docs_dir).resolve()
    skip = set(exclude_dirs)
    md_files = [f for f in docs_path.rglob("*.md") if not (skip & set(f.parts))]
    result = []
    for md_file in md_files:
        try:
            content = md_file.read_text(encoding="utf-8")
            result.append((md_file, content, content.splitlines()))
        except Exception as e:
            print(f"Warning: Could not read {md_file}: {e}")
    return result


def find_related_docs_by_filename(
    filename: str,
    docs_dir: str = "docs",
    md_cache: list | None = None,
) -> tuple[dict[str, int], dict[str, list[tuple[int, str]]]]:
    """Find all .md files in docs_dir that mention a filename (for deleted files).

    Returns:
        Tuple of (results dict, verbose_output dict with line numbers)
    """
    docs_path = _resolved_dir(docs_dir)

    if not docs_path.exists():
        print(f"Error: Docs directory not found: {docs_path}")
        return {}, {}

    # Generate search patterns for filename only
    patterns = [
        f"`{filename}`",
        filename,
        f"├── {filename}",
        f"└── {filename}",
    ]

    # Extract test class name from test file
    test_class_pattern = None
    if filename.startswith("test_") and filename.endswith(".py"):
        class_name = "".join(
            word.capitalize()
            for word in filename.replace("test_", "").replace(".py", "").split("_")
        )
        test_class_pattern = f"Test{class_name}" if class_name else None

    loaded = md_cache if md_cache is not None else load_md_files(docs_dir)
    results = defaultdict(int)
    verbose_output = defaultdict(list)
    # Pre-compile once per call — the regex depends only on filename, not on
    # the per-line scan that follows.
    code_block_re = re.compile(rf"`[^`]*{re.escape(filename)}[^`]*`")

    for md_file, content, lines in loaded:
        try:
            # Whole-content prefilter (C-speed substring check): every
            # matching rule below requires the filename (or the derived
            # test-class name) to appear somewhere in the file. The vast
            # majority of (file, doc) pairs have no mention at all — skip
            # the expensive per-line scan entirely for them.
            if filename not in content and not (
                test_class_pattern and test_class_pattern in content
            ):
                continue

            md_rel = str(md_file.relative_to(docs_path))
            mentioned_lines = set()

            # Track if we're inside a code block
            in_code_block = False
            in_mermaid = False

            for line_num, line in enumerate(lines, 1):
                # Check for mermaid block first (before generic ``` check)
                if "```mermaid" in line:
                    in_mermaid = True
                    in_code_block = True
                    continue
                if in_mermaid and line.strip() == "```":
                    in_mermaid = False
                    in_code_block = False
                    continue

                # Check for code block boundaries
                if line.strip().startswith("```"):
                    if in_code_block:
                        in_code_block = False
                    else:
                        in_code_block = True
                    continue

                # Check if any pattern matches this line
                line_mentioned = False
                for pattern in patterns:
                    if pattern == filename:
                        if code_block_re.search(line):
                            line_mentioned = True
                            break
                    else:
                        if pattern in line:
                            line_mentioned = True
                            break

                # Check for test class name
                if test_class_pattern and test_class_pattern in line:
                    line_mentioned = True

                # Check in markdown tables
                if "|" in line and filename in line:
                    line_mentioned = True

                # Check in code blocks
                if in_code_block and filename in line:
                    line_mentioned = True

                # Check in mermaid diagrams
                if in_mermaid and filename in line:
                    line_mentioned = True

                if line_mentioned:
                    mentioned_lines.add(line_num)
                    verbose_output[md_rel].append((line_num, line.strip()))

            if mentioned_lines:
                results[md_rel] = len(mentioned_lines)

        except Exception as e:
            print(f"Warning: Could not read {md_file}: {e}")

    return results, verbose_output


def find_related_docs(
    file_path: str | Path,
    docs_dir: str = "docs",
    verbose: bool = False,
    md_cache: list | None = None,
) -> tuple[dict[str, int], dict[str, list[tuple[int, str]]]]:
    """Find all .md files in docs_dir that mention file_path.

    Returns:
        Tuple of (results dict, verbose_output dict with line numbers)
    """
    if isinstance(file_path, str):
        file_path = Path(file_path).resolve()
    else:
        file_path = file_path.resolve()
    docs_path = _resolved_dir(docs_dir)

    if not file_path.exists():
        print(f"Error: File not found: {file_path}")
        return {}, {}

    if not docs_path.exists():
        print(f"Error: Docs directory not found: {docs_path}")
        return {}, {}

    # Hoisted: pathlib recomputes .name on every property access, and the
    # scan below used to hit it millions of times per build.
    fname = file_path.name
    # Module path (e.g., smm_bot_async.core.security.access) — also used
    # by the whole-content prefilter below.
    module_pattern = (
        str(file_path).replace("/", ".").replace("\\", ".").replace(".py", "")
    )
    # Generate search patterns with context to reduce false positives
    patterns = [
        # Full path with backticks (code references)
        f"`{file_path}`",
        f"`{fname}`",
        # In code blocks or inline code
        fname,
        module_pattern,
        # In project trees (with ├── or └──)
        f"├── {fname}",
        f"└── {fname}",
    ]

    # Extract test class name from test file (e.g., test_access.py -> TestAccess)
    test_class_pattern = None
    if fname.startswith("test_") and fname.endswith(".py"):
        class_name = "".join(
            word.capitalize() for word in file_path.stem.replace("test_", "").split("_")
        )
        test_class_pattern = f"Test{class_name}" if class_name else None

    loaded = md_cache if md_cache is not None else load_md_files(docs_dir)
    results = defaultdict(int)
    verbose_output = defaultdict(list)
    # Pre-compile once per call — the regex depends only on filename, not on
    # the per-line scan that follows.
    code_block_re = re.compile(rf"`[^`]*{re.escape(fname)}[^`]*`")

    for md_file, content, lines in loaded:
        try:
            # Whole-content prefilter (C-speed substring check): every
            # matching rule below requires the filename, the derived
            # test-class name or the dotted module path to appear somewhere
            # in the file. The vast majority of (file, doc) pairs have no
            # mention at all — skip the scan entirely for them.
            if (
                fname not in content
                and module_pattern not in content
                and not (test_class_pattern and test_class_pattern in content)
            ):
                continue

            # Candidate lines: every matching rule requires the filename,
            # the dotted module path or the test-class name to occur ON the
            # line itself (all other patterns contain the filename as a
            # substring), so only lines with an actual occurrence need the
            # full checks. Occurrences are located with C-speed str.find
            # over the raw content and mapped to line numbers via bisect;
            # the code-block/mermaid state per line comes precomputed.
            starts, flags = _md_scan_meta(md_file, content, lines)
            cand = _lines_containing(content, fname, starts)
            if module_pattern in content:
                cand |= _lines_containing(content, module_pattern, starts)
            if test_class_pattern and test_class_pattern in content:
                cand |= _lines_containing(content, test_class_pattern, starts)

            md_rel = str(md_file.relative_to(docs_path))
            mentioned_lines = set()  # Track line numbers where file is mentioned

            for idx in sorted(cand):
                if idx >= len(flags):
                    continue
                state = flags[idx]
                if state is None:
                    continue  # ``` fence line — the line scanner skips these
                in_code_block, in_mermaid = state
                line = lines[idx]
                line_num = idx + 1

                # Check if any pattern matches this line
                line_mentioned = False
                for pattern in patterns:
                    # For filename without backticks, check if it's in a code context
                    if pattern == fname:
                        if code_block_re.search(line):
                            line_mentioned = True
                            break
                    else:
                        if pattern in line:
                            line_mentioned = True
                            break

                # Check for test class name
                if test_class_pattern and test_class_pattern in line:
                    line_mentioned = True

                # Check in markdown tables (lines with |)
                if "|" in line and fname in line:
                    line_mentioned = True

                # Check in code blocks
                if in_code_block and fname in line:
                    line_mentioned = True

                # Check in mermaid diagrams
                if in_mermaid and fname in line:
                    line_mentioned = True

                if line_mentioned:
                    mentioned_lines.add(line_num)
                    if verbose:
                        verbose_output[md_rel].append((line_num, line.strip()))

            if mentioned_lines:
                results[md_rel] = len(mentioned_lines)

        except Exception as e:
            print(f"Warning: Could not read {md_file}: {e}")

    return results, verbose_output


def find_related_docs_for_dir(
    dir_path: str | Path,
    docs_dir: str = "docs",
    verbose: bool = False,
    md_cache: list | None = None,
) -> dict[str, dict[str, int]]:
    """Find all .md files in docs_dir that mention any file in dir_path.

    Returns:
        Dict mapping code file path to dict of doc file path -> mention count
    """
    if isinstance(dir_path, str):
        dir_path = Path(dir_path).resolve()
    else:
        dir_path = dir_path.resolve()
    docs_path = Path(docs_dir).resolve()

    if not dir_path.exists() or not dir_path.is_dir():
        print(f"Error: Directory not found: {dir_path}")
        return {}

    if not docs_path.exists():
        print(f"Error: Docs directory not found: {docs_path}")
        return {}

    # Find all code/config files in the directory
    code_files = [
        f for f in dir_path.rglob("*") if f.is_file() and is_code_or_config_file(f)
    ]
    if not code_files:
        print(f"No code/config files found in: {dir_path}")
        return {}

    # Load md files once for all lookups
    loaded = md_cache if md_cache is not None else load_md_files(docs_dir)

    results = {}
    for code_file in code_files:
        file_results, _verbose_output = find_related_docs(
            str(code_file), docs_dir, verbose, loaded
        )
        if file_results:
            results[str(code_file.relative_to(dir_path.parent))] = file_results

    return results


def get_git_staged_files() -> tuple[list[Path], list[Path], list[Path]]:
    """Get list of files that are staged in git (added, renamed, deleted).

    Returns:
        Tuple of (added/renamed, deleted, all_staged)
    """
    try:
        # core.quotePath=false → non-ASCII paths come back as UTF-8, not octal
        # Get all staged files (added, renamed)
        result_ar = subprocess.run(
            [
                "git",
                "-c",
                "core.quotePath=false",
                "diff",
                "--cached",
                "--name-only",
                "--diff-filter=AR",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        files_ar = [Path(f) for f in result_ar.stdout.strip().splitlines() if f]

        # Get deleted files
        result_d = subprocess.run(
            [
                "git",
                "-c",
                "core.quotePath=false",
                "diff",
                "--cached",
                "--name-only",
                "--diff-filter=D",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        files_d = [Path(f) for f in result_d.stdout.strip().splitlines() if f]

        return files_ar, files_d, files_ar + files_d
    except subprocess.CalledProcessError as e:
        print(f"Error: Could not get git staged files: {e}")
        return [], [], []
    except FileNotFoundError:
        print("Error: git not found in PATH")
        return [], [], []


def get_git_modified_files() -> list[Path]:
    """Get list of files that are modified (committed before, now changed).

    Returns:
        List of Path objects for modified files
    """
    try:
        # core.quotePath=false → non-ASCII paths come back as UTF-8, not octal
        # Get modified files (staged and unstaged)
        result_staged = subprocess.run(
            [
                "git",
                "-c",
                "core.quotePath=false",
                "diff",
                "--cached",
                "--name-only",
                "--diff-filter=M",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        files_staged = [Path(f) for f in result_staged.stdout.strip().splitlines() if f]

        result_unstaged = subprocess.run(
            [
                "git",
                "-c",
                "core.quotePath=false",
                "diff",
                "--name-only",
                "--diff-filter=M",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        files_unstaged = [
            Path(f) for f in result_unstaged.stdout.strip().splitlines() if f
        ]

        # Combine and deduplicate
        all_modified = list(set(files_staged + files_unstaged))
        return all_modified
    except subprocess.CalledProcessError as e:
        print(f"Error: Could not get git modified files: {e}")
        return []
    except FileNotFoundError:
        print("Error: git not found in PATH")
        return []


def resolve_path(path_str: str) -> Path:
    """Resolve a path string to an actual Path.

    If it's just a filename (no directory separators), search for it in the project.
    """
    path = Path(path_str)

    # If path already exists or has directory separators, return as-is
    if path.exists() or "/" in path_str or "\\" in path_str:
        return path.resolve()

    # Search for files with this name in the project
    project_root = Path.cwd()
    matches = [
        m
        for m in project_root.rglob(path_str)
        if ".venv" not in m.parts and "__pycache__" not in m.parts
    ]

    if not matches:
        print(f"Error: File not found: {path_str}")
        raise SystemExit(1)

    if len(matches) == 1:
        return matches[0].resolve()

    # Multiple matches found
    print(f"Error: Multiple files found with name '{path_str}':")
    for match in matches:
        print(f"  {match.relative_to(project_root)}")
    print("\nPlease specify the full path.")
    raise SystemExit(1)


def _print_files_with_docs(
    files_with_docs: list[tuple],
    docs_path: str,
) -> None:
    for git_file, count, verbose_output in sorted(files_with_docs):
        print(f"{Colors.GREEN}✓{Colors.RESET} {git_file} mentioned in {count} doc(s):")
        for doc_file, lines in verbose_output.items():
            for line_num, _ in lines:
                full_path = f"{docs_path}/{doc_file}:{line_num}"
                print(f"    {full_path}")


def main() -> None:
    """Main entry point for the script."""
    ensure_utf8_stdout()
    parser = argparse.ArgumentParser(
        description="Find documentation files that mention a given code file or directory"  # noqa: E501
    )
    parser.add_argument(
        "path",
        nargs="?",
        help="Path to the code file or directory to search for (can be just a filename)",  # noqa: E501
    )
    parser.add_argument(
        "--docs-dir",
        default="docs",
        help="Path to docs directory (default: docs)",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="DIRNAME",
        help=(
            "Directory name to skip anywhere under the docs dir "
            "(repeatable), e.g. --exclude internal"
        ),
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show specific line numbers with mentions",
    )
    parser.add_argument(
        "--git-added",
        action="store_true",
        help="Check all staged files (added, renamed, deleted) for documentation mentions",  # noqa: E501
    )
    parser.add_argument(
        "--git-modified",
        action="store_true",
        help="Check all modified files (committed before, now changed) for documentation mentions",  # noqa: E501
    )

    args = parser.parse_args()

    docs_path = Path(args.docs_dir).resolve()

    # Git mode: check all staged files
    if args.git_added:
        files_amr, files_deleted, all_files = get_git_staged_files()
        if not all_files:
            print("No files staged in git (git add)")
            return

        print(f"Checking {len(all_files)} staged file(s) for documentation mentions:\n")

        # Load all md files once
        md_cache = load_md_files(args.docs_dir, tuple(args.exclude))

        files_with_docs = []
        files_without_docs = []
        files_not_found = []

        # Check all staged files
        for git_file in all_files:
            # Skip non-code/config files and docs
            if not is_code_or_config_file(git_file) or "docs/" in str(git_file):
                continue

            if not git_file.exists():
                # For deleted files, search by filename in docs
                result, verbose_output = find_related_docs_by_filename(
                    git_file.name, args.docs_dir, md_cache
                )
                if result:
                    files_not_found.append((git_file, len(result), verbose_output))
                continue

            result, verbose_output = find_related_docs(
                str(git_file), args.docs_dir, True, md_cache
            )

            if not result:
                files_without_docs.append(git_file)
            else:
                files_with_docs.append((git_file, len(result), verbose_output))

        # Print files with documentation mentions
        if files_with_docs:
            print_separator()
            _print_files_with_docs(files_with_docs, str(docs_path))

        # Print files not found (deleted files mentioned in docs)
        if files_not_found:
            print_separator()
            for git_file, count, verbose_output in files_not_found:
                print(
                    f"{Colors.YELLOW}⚠️{Colors.RESET} {Colors.YELLOW}WARNING{Colors.RESET}: "  # noqa: E501
                    f"File not found - mentioned in {count} doc(s): {git_file}"
                )
                for doc_file, lines in verbose_output.items():
                    for line_num, _ in lines:
                        full_path = f"{docs_path}/{doc_file}:{line_num}"
                        print(f"    {full_path}")

        # Print files without documentation mentions
        if files_without_docs:
            print_separator()
            for git_file in files_without_docs:
                print(
                    f"{Colors.RED}⚠️{Colors.RESET} {Colors.RED}ERROR{Colors.RESET}: "
                    f"No documentation mentions for {git_file}"
                )

        # Summary
        print_separator()
        if files_without_docs:
            print(
                f"{Colors.YELLOW}{len(files_without_docs)}{Colors.RESET} "
                f"file(s) without documentation mentions"
            )
        if files_not_found:
            print(
                f"{Colors.YELLOW}{len(files_not_found)}{Colors.RESET} "
                f"deleted file(s) mentioned in docs"
            )
        if not files_without_docs and not files_not_found:
            print(
                f"{Colors.GREEN}All staged files have "
                f"documentation mentions{Colors.RESET}"
            )

        return

    # Git mode: check all modified files
    if args.git_modified:
        modified_files = get_git_modified_files()
        if not modified_files:
            print("No modified files found")
            return

        print(
            f"Checking {len(modified_files)} modified file(s) "
            f"for documentation mentions:\n"
        )

        # Load all md files once
        md_cache = load_md_files(args.docs_dir, tuple(args.exclude))

        files_with_docs = []
        files_without_docs = []

        for git_file in modified_files:
            # Skip non-code/config files and docs
            if not is_code_or_config_file(git_file) or "docs/" in str(git_file):
                continue

            if not git_file.exists():
                continue

            result, verbose_output = find_related_docs(
                str(git_file), args.docs_dir, True, md_cache
            )

            if not result:
                files_without_docs.append(git_file)
            else:
                files_with_docs.append((git_file, len(result), verbose_output))

        # Print files with documentation mentions
        if files_with_docs:
            print_separator()
            _print_files_with_docs(files_with_docs, str(docs_path))

        # Print files without documentation mentions
        if files_without_docs:
            print_separator()
            for git_file in files_without_docs:
                print(
                    f"{Colors.RED}⚠️{Colors.RESET} {Colors.RED}ERROR{Colors.RESET}: "
                    f"No documentation mentions for {git_file}"
                )

        # Summary
        print_separator()
        if files_without_docs:
            print(
                f"{Colors.YELLOW}{len(files_without_docs)}{Colors.RESET} "
                f"file(s) without documentation mentions"
            )
        else:
            print(
                f"{Colors.GREEN}All modified files have "
                f"documentation mentions{Colors.RESET}"
            )

        return

    # Normal mode: require path argument
    if not args.path:
        parser.error("path is required unless --git-added or --git-modified is used")

    path = resolve_path(args.path)
    is_directory = path.is_dir()

    if is_directory:
        md_cache = load_md_files(args.docs_dir, tuple(args.exclude))
        results = find_related_docs_for_dir(
            str(path), args.docs_dir, args.verbose, md_cache
        )
        if not results:
            print(
                f"{Colors.RED}ERROR{Colors.RESET}: No documentation files "
                f"mention any files in: {path}"
            )
            return

        print(f"Documentation files mentioning files in {path}:\n")
        for code_file, doc_results in sorted(results.items()):
            print_separator()
            print(f"{code_file}:")
            for doc_file, count in sorted(doc_results.items(), key=lambda x: -x[1]):
                print(
                    f"  {Colors.GREEN}✓{Colors.RESET} {doc_file} "
                    f"({count} mention{'s' if count > 1 else ''})"
                )
        print_separator()
    else:
        md_cache = load_md_files(args.docs_dir, tuple(args.exclude))
        doc_results, verbose_output = find_related_docs(
            str(path), args.docs_dir, args.verbose, md_cache
        )

        if not doc_results:
            print(
                f"{Colors.RED}ERROR{Colors.RESET}: No documentation files "
                f"mention: {args.path}"
            )
            return

        print(f"Documentation files mentioning {args.path}:\n")
        for doc_file, count in sorted(doc_results.items(), key=lambda x: -x[1]):
            print_separator()
            print(
                f"{Colors.GREEN}✓{Colors.RESET} {doc_file} "
                f"({count} mention{'s' if count > 1 else ''})"
            )
            if args.verbose and doc_file in verbose_output:
                for line_num, _ in verbose_output[doc_file]:
                    # Use forward slashes for cross-platform compatibility
                    full_path = f"{docs_path}/{doc_file}:{line_num}"
                    print(f"    {full_path}")
        print_separator()


if __name__ == "__main__":
    main()
