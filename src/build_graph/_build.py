"""Edge building: doc->doc, code->doc, code->code (AST), docstring mentions.

All functions take pre-built node dicts and return edge dicts; nothing here
touches the CLI or rendering. The Python-import machinery (resolver, AST
collector, dynamic-import const-folding) lives here too.
"""

import ast
import re
from pathlib import Path

from build_graph.links import extract_file_references
from build_graph.related import find_related_docs


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


def _is_path_suffix(path: str, suffix: str) -> bool:
    """True when `suffix` matches `path` on whole segment boundaries."""
    return path == suffix or (path.endswith(suffix) and path[-len(suffix) - 1] == "/")


def _attribute_mention_lines(
    group: list[dict],
    name: str,
    mentions: list[tuple[int, str]],
) -> dict[str, list[int]]:
    """Split a doc's mention lines between same-named files.

    A line that names a group member by an explicit path (any `dir/<name>`
    suffix) credits only the members it matches; a bare-`<name>` line — or a
    path that resolves to no member — credits the whole group, as before.
    """
    pathish = re.compile(r"[\w\-.\\/]*" + re.escape(name))
    credited: dict[str, list[int]] = {n["id"]: [] for n in group}
    for lineno, text in mentions:
        explicit = [
            m.group(0).replace("\\", "/").lstrip("./")
            for m in pathish.finditer(text)
            if "/" in m.group(0)
        ]
        matched = [
            n for n in group if any(_is_path_suffix(n["path"], hit) for hit in explicit)
        ]
        for n in matched or group:
            credited[n["id"]].append(lineno)
    return credited


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
    # identical scan results. Scan once per unique filename; before fanning
    # the hits out to the group, mention lines that name a member by an
    # explicit path are credited to that member only (bare-name lines still
    # go to everyone) — otherwise `integrations/base/config.py` in a doc
    # would also link every other config.py in the repo.
    by_name: dict[str, list[dict]] = {}
    for node in source_nodes:
        path = project_root / node["path"]
        if not path.exists():
            continue
        by_name.setdefault(path.name, []).append(node)
    for name, group in by_name.items():
        rep_path = project_root / group[0]["path"]
        doc_results, verbose_out = find_related_docs(
            str(rep_path), root_str, True, md_cache
        )
        for doc_key, count in doc_results.items():
            doc_id = path_to_doc_id.get(doc_key.replace("\\", "/"))
            if doc_id is None:
                continue
            mentions = verbose_out.get(doc_key, [])
            if len(group) > 1 and mentions:
                credited = _attribute_mention_lines(group, name, mentions)
            else:
                all_lines = [ln for ln, _ in mentions]
                credited = {n["id"]: all_lines for n in group}
            for node in group:
                line_nums = sorted(set(credited[node["id"]]))
                if mentions and not line_nums:
                    continue  # every mention names another same-named file
                key = (node["id"], doc_id)
                if key in seen:
                    continue
                seen.add(key)
                edges.append(
                    {
                        "source": node["id"],
                        "target": doc_id,
                        "type": "code->doc",
                        "weight": len(line_nums) if mentions else count,
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
      `<project_root>/<module>.py`, with an `src/<module>.py` fallback for
      src-layout projects (where the import root is `src/`, not the repo
      root — the returned path stays repo-relative so it matches node ids).
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
    if level == 0:
        src_base = Path("src") / base
        if (project_root / src_base.with_suffix(".py")).is_file():
            return src_base.with_suffix(".py").as_posix()
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
        if not module and level == 0:
            return
        if module:
            target = _resolve_python_import(module, level, self.rel, self.project_root)
            if target:
                self.refs.append((target, node.lineno, bool(self._tc_depth)))
        # The imported names may be submodules rather than attributes —
        # `from pkg import mod` / `from .pkg import mod` never mention
        # pkg/mod.py in the module field. Probing <module>.<alias> is cheap:
        # attribute names simply fail the is_file check in the resolver.
        for alias in node.names:
            sub = f"{module}.{alias.name}" if module else alias.name
            target = _resolve_python_import(sub, level, self.rel, self.project_root)
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
