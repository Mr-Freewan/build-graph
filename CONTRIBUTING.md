# Contributing

Thanks for taking an interest in build-graph. Bug reports, false-positive
reports and small focused PRs are all welcome.

## Dev setup

```bash
git clone https://github.com/Mr-Freewan/build-graph
cd build-graph
uv sync            # or: pip install -e . pytest pytest-cov jsonschema
```

Run everything the CI runs before pushing:

```bash
uv run ruff check src tests
uv run ruff format --check src tests
uv run pytest -q --cov=build_graph --cov-fail-under=80
```

The test matrix covers Linux + Windows on Python 3.11–3.13, so avoid
platform-specific assumptions (path separators are the usual trap — use
`Path.as_posix()` when comparing).

## Ground rules

- **Zero runtime dependencies** is a hard constraint. The package must keep
  running on pure stdlib; new libraries are acceptable in the `dev` group
  only.
- **The output is a single self-contained HTML file** — that is a design
  invariant, not an implementation detail.
- The JS resources in `src/build_graph/resources/` are concatenated in a
  fixed order (`i18n.js → engine.js → ui.js → boot.js`); top-level init code
  relies on it.
- UI strings live in `resources/i18n.js` with 10 locales. A new string needs
  a key in **all** locales (English fallback text is fine).
- The exports are a versioned contract: any change to the `--json` /
  `--compact` shapes must update `schema/*.schema.json` and bump the schema
  version.

## Adding another language

Only the import resolver is language-specific — about 450 of the package's
~5,600 lines, all of them in `_build.py`. Everything else already works for
any language and needs no changes:

- files of other languages **already become nodes** (`_KIND_BY_EXT` in
  `_config.py` maps `.js`, `.sh`, `.sql`, … to the `code` kind), so they
  already appear on the map with their docs, git, heat and coverage layers;
- the **docs layer** scans markdown for file references — language-neutral;
- the **git layer**, the **ref diff** and the **heat map** shell out to git —
  language-neutral;
- the **coverage layer** reads Cobertura XML, which JaCoCo, istanbul/nyc,
  coverlet and gocover-cobertura all emit — language-neutral already;
- the HTML front-end, the three JSON exports, `graph-query`,
  `find-related-docs` and `verify-doc-links` never look at source syntax.

So a fork for Go, TypeScript or anything else means writing one resolver, not
a new tool.

**The contract.** Produce a list of edge dicts:

```python
{
    "source": "<node id of the importing file>",
    "target": "<node id of the imported file>",
    "type": "code->code",   # or "type-only" for imports that exist for types
    "weight": 1,            # bumped when the same pair repeats
    "lines": [12, 88],      # 1-based line numbers of the import statements
}
```

Node ids are what `build_all_nodes` assigned — resolve an import to a
project-relative path, then look the id up; drop anything that resolves
outside the project (third-party imports are not nodes). Merge duplicates by
`(source, target, type)` and keep `lines` sorted.

**Where to plug in** (`_build.py`, mirroring the Python implementation):

| Python version | What a new language needs |
|---|---|
| `_parse_code_trees` | parse each file once, cache the tree |
| `_ImportCollector` / `_collect_python_imports` | walk the tree, collect (module, line, is_type_only) |
| `_resolve_python_import` | turn a module reference into a project file path |
| `add_code_code_edges` | assemble the edges above |
| `add_docstring_edges` | *optional* — file mentions inside doc comments |

Keep it stdlib-only. Python gets this for free through `ast`; for another
language a hand-written scanner over import lines is usually enough, and it
stays deterministic — no grammars to compile, no native wheels, nothing that
turns the install into a build.

## Pull requests

- Keep PRs small and single-purpose; one logical change per commit,
  imperative English commit messages (`fix: …`, `feat: …`, `docs: …`).
- Add or extend a test for every behaviour change. Matching-logic changes
  (edge building, reference extraction) are easiest to verify by comparing
  `--json` output on a real repo before and after.
- If you change CLI flags or user-visible behaviour, add a line to
  `CHANGELOG.md` under *Unreleased*.

## Reporting issues

Use the issue templates. For wrong edges (a file pair that should not be
connected, or a missing connection) the **false positive / false negative**
template asks for the exact source line — that is usually all that is needed
to reproduce a matcher problem.
