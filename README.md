# build-graph

[![CI](https://github.com/Mr-Freewan/build-graph/actions/workflows/ci.yml/badge.svg)](https://github.com/Mr-Freewan/build-graph/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/graph-build)](https://pypi.org/project/graph-build/)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
![Zero dependencies](https://img.shields.io/badge/dependencies-0-brightgreen)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![LLM-Agent friendly](https://img.shields.io/badge/LLM--Agent-friendly-blueviolet)](#designed-for-ai-agents)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen)](CONTRIBUTING.md)

[![Live demo](https://img.shields.io/badge/demo-online-blueviolet?style=for-the-badge&logo=googlechrome&logoColor=white)](https://mr-freewan.github.io/build-graph/)
[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/Mr-Freewan/build-graph)

> **Architectural memory for your refactors.** See the blast radius of your
> changes across code, docs, and git — on one interactive map that both you
> and your AI agent can read.

`build-graph` renders a **single-file interactive HTML graph** connecting
three layers no other tool combines:

- **code → code** — Python imports (AST-based, `TYPE_CHECKING`-aware)
- **code ↔ docs** — which markdown files mention which source files
- **git drift** — added / modified / renamed / deleted overlay with ghost
  nodes for files that no longer exist

…and exports the same map as a **compact, token-efficient JSON** designed to
drop into an LLM agent's context.

All of that with **zero dependencies** — pure Python stdlib, `pip install`
brings in nothing else. The only third-party code is D3.js in the browser,
SRI-pinned from CDN or fully embedded with `--no-cdn`.

![Force layout settling on a real project — 1070 nodes / 6279 edges, dark theme](docs/media/hero.gif)

**[▶ Live demo](https://mr-freewan.github.io/build-graph/)** — the graph of
this very repository (dogfood), with a synthetic `--mock-git` overlay so the
Git mode is clickable too.
**[📖 UI guide](docs/guide.md)** — every feature, one by one.

## Install

```bash
pip install graph-build        # or: uv tool install graph-build
```

No PyPI needed — install straight from GitHub:

```bash
pip install git+https://github.com/Mr-Freewan/build-graph.git

# or from a clone:
git clone https://github.com/Mr-Freewan/build-graph.git
pip install ./build-graph
```

Zero dependencies — stdlib only, Python 3.11+. The HTML output needs only a
browser (D3.js from CDN with SRI pinning, or fully embedded via `--no-cdn`).

> The PyPI distribution is named `graph-build` (the straight name is taken);
> the installed commands keep their names: `build-graph`, `find-related-docs`,
> `verify-doc-links`.

## Quick start

```bash
cd your-project
build-graph                    # autodiscovery, no config needed → docs/graph.html
build-graph --compact          # + docs/graph-compact.json for AI agents
build-graph --init             # optional: pin discovered structure to graph.toml
```

Two companion CLIs — `find-related-docs` (reverse lookup: code → docs) and
`verify-doc-links` (broken-reference gate for CI) — ship in the same package;
see [Companion tools](#companion-tools).

## Why not X?

- **pydeps / Import Linter** — imports only; no docs layer, no git drift.
- **lychee & co.** — dead-URL checkers; no map, no code layer.
- **Obsidian graph view** — notes only; doesn't see your code.
- **Repomix / Gitingest** — pack the repo *text* for LLMs; build-graph gives
  the *structure*: ~2 % of the tokens the raw text would cost (see
  [the numbers](#what-it-costs-in-context)).

## Designed for AI agents

`--compact` writes a self-documenting JSON snapshot (embedded legend, indexed
nodes, 3-letter type codes) that agents use for:

1. **Blast radius** — incoming imports of the file you're about to change,
   without grep.
2. **Docs routing** — which ADR / reference doc to read *before* editing a
   file.
3. **Three-way doc-sync** — the graph reveals (1) what's documented, (2) what
   should be documented but isn't, and (3) what's documented but no longer
   exists (ghost nodes = staleness detector).

Add `build-graph --compact` to a pre-commit hook or CI step to keep the map
fresh for every agent session.

### The compact format

`--compact` writes `graph-compact.json` (schema v2): nodes as an indexed
array, edges as `[source_idx, target_idx, type, [line_numbers]]` rows,
3-letter codes for every category and edge type. The `legend` key embeds the
full decoding table — an agent needs no external schema, the file explains
itself:

```jsonc
{
  "v": "2.0",
  "legend": { "...": "what every field and code below means" },
  "stats": { "nodes": 1070, "ghosts": 0, "edges": 6279 },
  "n": [
    { "p": "smm_bot_async/core/security/access.py", "t": "cor", "d": 56 },
    { "p": "docs/explanation/adr/0009-parser-framework.md", "t": "adr",
      "d": 11, "s": "mod" }
  ],
  "e": [
    [ 1, 75, "d2d", [186] ]
  ]
}
```

`p` — path, `t` — category, `d` — degree, `s` — git status (omitted when
clean). Edge types: `c2c` imports, `c2d` doc mentions, `d2d` doc links,
`dcs` docstring refs, `typ` `TYPE_CHECKING`-only, `ren` git renames.
Deleted-but-still-referenced files ride along as ghost nodes (`"G": 1`).

### What it costs in context

Real numbers from a production repo — 1,070 mapped files, 6,279 edges
(tokens ≈ bytes / 4, the usual rough estimate):

| What you put in context             |   Size | ≈ Tokens   |
|-------------------------------------|-------:|-----------:|
| The mapped files themselves         |  15 MB | ~3,700,000 |
| `--json` (verbose snapshot)         | 1.6 MB |   ~410,000 |
| **`--compact`**                     | **0.33 MB** | **~80,000** |

The whole architecture — every import, every doc mention, every stale
reference — lands in ~2 % of what the raw text would cost, and fits in a
single 200 k-context session with room to work. Without the map an agent
rediscovers this structure every session: dozens of speculative greps and
file reads that burn comparable tokens *per question*, not once. On small
projects the map is almost free — the compact snapshot of this very repo is
4 KB ≈ ~1,000 tokens.

Don't take these numbers on faith — measure your own repo:

```bash
$ build-graph --root . --bench

Context cost on this repo (tokens ~= bytes / 4):

  What you put in context            Size      ~Tokens  vs corpus
  raw corpus (1070 files)         14.3 MB    3,757,913     100.0%
  --json export (schema v1)        1.5 MB      397,419      10.6%
  --compact export (schema v2)   311.4 KB       79,729       2.1%
```

`--bench` only measures — it writes no files.

### A prompt to start from

```text
graph-compact.json is a dependency map of this repository: nodes are
files, edges are imports and documentation mentions. Read the embedded
"legend" key first — it explains every field and code.

Using the map (before any grep):
1. Lay of the land: the 10 highest-degree hubs, grouped by category,
   with one line each on why they're central.
2. I'm about to modify <path/to/file.py>. List the blast radius:
   direct and 2-hop incoming importers, plus every doc that mentions
   the file — and tell me which of those docs to read first.
3. Anything suspicious: ghost nodes (docs pointing at deleted files),
   zero-degree modules, docs nothing links to.

Verify any surprising claim against the actual source before acting.
```

## The interactive graph

- **Canvas renderer** — smooth at 1000+ nodes / 6000+ edges (pre-warmed
  layout, viewport culling, label LOD).
- **6 edge types** — doc→doc, code→doc, code→code, type-only
  (`TYPE_CHECKING`), docstring mentions, git renames.
- **Git overlay** — status colours + ghost nodes + rename edges; `--mock-git`
  for a synthetic demo.
- **Analysis aids** — dead-code candidates, import-cycle detector (Tarjan
  SCC over runtime imports; `TYPE_CHECKING` edges don't count), orphan ring,
  shortest path between two nodes (Shift+click), isolate-a-type,
  exclude-by-name.
- **Sharing** — URL-encoded views (Copy link), Mermaid export of the focused
  subgraph, full/compact JSON export.
- **Comfort** — 10 UI languages, dark/light themes, hue-aligned
  pastel/saturated palettes, draggable glass panels, IDE deep links
  (VS Code / Cursor / PyCharm), FAQ built in (`?`).

Everything lands in **one self-contained HTML file** — attach it to a PR,
send it in chat, open it offline.

## Configuration (optional)

Autodiscovery classifies every tracked file by kind (code / doc / config /
locale) × location, detects your package and docs layout, and generates
deterministic colours. A `graph.toml` is only an override:

```bash
build-graph --init           # generate graph.toml pinning current structure
build-graph --init --diff    # report drift (new folders, stale pins), change nothing
build-graph --init --merge   # append coverage for new folders, keep your edits
```

See [`graph.example.toml`](graph.example.toml) for the annotated format
(`[docs]` categories, `[[code]]` dirs, `[[rules]]`, `[scan]` excludes,
`[dead_code]` exemptions, colour pins).

Two optional plain-text companions, both looked up in the project root:

- `known-brokens.txt` — whitelist for `verify-doc-links` false positives
  (one exact path per line).
- `exclude-dirs.txt` — directory-name skip list used only when git is
  unavailable (with git, `.gitignore` is the source of truth).

## CLI reference (build-graph)

| Flag | Effect |
|---|---|
| `--root PATH` | project root to scan (default: cwd) |
| `--config PATH` | graph.toml location (default: `<root>/graph.toml`) |
| `--output PATH` | HTML output (default: `docs/graph.html` or `[output].path`) |
| `--scope full\|package` | whole repo (default) or package+tests+docs only |
| `--json` / `--compact` | verbose / agent-oriented JSON snapshots next to the HTML |
| `--docs-only` / `--no-tests` | trim the node set |
| `--no-cdn` | fully offline output: embed D3.js inline (SHA-256 verified) and drop the external font link |
| `--mock-git` | synthetic git overlay for demos/testing |
| `--init [--diff\|--merge\|--force]` | config lifecycle (see above) |

## Companion tools

`find-related-docs` and `verify-doc-links` run the same reference scanner the
graph is built from — what the map draws as a code↔docs edge is exactly what
they look up and verify. `graph-query` answers questions over an
already-built snapshot.

### find-related-docs

Reverse lookup: which docs mention a given code file. Run it before editing a
file to know which pages need updating afterwards, or wire `--git-added` into
a pre-commit hook so undocumented changes get flagged before they land.

```bash
find-related-docs src/mypkg/core/access.py   # single file (bare filename works too)
find-related-docs --git-added -v             # pre-commit: staged files, with doc line numbers
find-related-docs --git-modified             # working tree: staged + unstaged modifications
```

| Flag | Effect |
|---|---|
| `path` | file or directory to look up (a bare filename is searched project-wide) |
| `--docs-dir PATH` | documentation directory (default: `docs`) |
| `--exclude DIRNAME` | skip a folder name anywhere under the docs dir (repeatable) |
| `--git-added` | check all staged files; also warns about deleted files still mentioned in docs |
| `--git-modified` | check all modified files (staged + unstaged) |
| `-v` / `--verbose` | print `docs/<file>.md:<line>` for every mention |

### verify-doc-links

Check that every file reference in your `.md` files points to a real file.
Exit codes make it a drop-in CI gate:

| Exit | Meaning |
|---|---|
| `0` | all references valid |
| `1` | broken references found |
| `2` | target path invalid (not found, or not a `.md` file) |

```bash
verify-doc-links                     # whole docs/ against the project root
verify-doc-links docs/reference -v   # one subtree, with the offending lines
```

```yaml
# CI step (GitHub Actions)
- run: pip install graph-build
- run: verify-doc-links --root .
```

| Flag | Effect |
|---|---|
| `path` | `.md` file or directory to check (default: `docs`) |
| `--root PATH` | project root the references resolve against (default: cwd) |
| `--known-brokens PATH` | whitelist file (default: `<root>/known-brokens.txt`) |
| `-v` / `--verbose` | show the offending lines |

Besides `known-brokens.txt`, false positives can be silenced inline with HTML
comments (invisible in rendered Markdown): `<!-- broken-link-ok -->` on the
same line, `<!-- broken-links-ok-start -->` / `<!-- broken-links-ok-end -->`
around a block, or `<!-- ignore-ref: path/to/file.py -->` anywhere in the file.

### graph-query

Ask the graph questions without opening a browser. Works on the JSON written
by `--json` or `--compact` (auto-detected; defaults to
`docs/graph-compact.json`):

```bash
graph-query blast-radius app/core.py   # transitive importers + every doc mentioning them
graph-query hubs --top 15              # most-connected files, in/out breakdown
graph-query stale-docs --check         # docs older than the code they describe (CI gate: exit 1)
graph-query orphans --type code        # files with no edges at all
```

| Command | Answers |
|---|---|
| `blast-radius <path>` | "what breaks if I touch this file" — transitive incoming imports (`--depth`, `--edges` to tune), plus affected docs |
| `hubs` | "where is the center of gravity" — top nodes by in+out edges (`--top N`) |
| `stale-docs` | "which docs lag behind the code" — compares last-commit times (one `git log` pass; mtime fallback), `--check` for CI |
| `orphans` | "what is connected to nothing" — degree-0 nodes, filterable by category |

Every command takes `--json` for machine-readable output — pipe it to `jq`
or feed it to an agent.

## Known limitations

Static analysis has natural borders — the graph is a referential map, not a
semantic one:

- Dynamic imports resolve only literal / top-level-constant module names
  (f-strings, dict lookups, conditional rebinding are skipped).
- `eval` / `exec` and DI-by-string are invisible. `[project.scripts]` /
  `[project.gui-scripts]` entry points in `pyproject.toml` are read, but only
  to exempt those modules from dead-code flagging — they don't create edges.
- Markdown templating (`{{ ref }}`, Jekyll/Hugo shortcodes) isn't parsed.
- Links resolve to whole files — section anchors (`file.md#part`) map to the
  file node.
- code→code edges are Python-only for now (the markdown/doc layers are
  language-agnostic).
- One repo per graph; symlinks are treated as physical paths.

## License

[MIT](LICENSE) © Yuriy Totyshev
