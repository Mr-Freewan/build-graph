# Prompts for AI agents

`build-graph --compact` writes `graph-compact.json` — a token-efficient map of your
repository: nodes are files, edges are imports and documentation mentions, with a
self-describing `legend` key that decodes every field and code. This page is a set of
**ready-to-use prompts** that drive an LLM agent with that map for concrete tasks:
blast radius before a refactor, three-way doc-sync, hunting stale docs and dead code.

Copy a prompt, swap in your file paths, and hand it to the agent alongside the JSON.

**Two snapshot formats, so every prompt below is labelled.** `--compact` writes
schema v2 (`graph-compact.json`); `--ultra-compact` writes schema v3
(`graph-ultra.json`) — same graph, about a third of the tokens, and the only one
carrying the Heat and Coverage layers. They name things differently: v2 puts a
3-letter type code on every edge row, v3 groups edges into named sections. Use the
prompt that matches the file you're handing over.

## Why the map beats grep

Without the graph, an agent rediscovers your structure every session — dozens of
speculative greps and file reads, burned again per question. With the snapshot in
context it reads the structure once, cheaply — around 2 % of the raw text's tokens
for `graph-compact.json`, under 1 % for `graph-ultra.json` — and spends the budget
on the actual task.

The map is **referential**, not semantic: it knows which files connect, not what the
code means. Semantics stay the agent's job — it reads a specific file when it needs to
know behaviour. If the graph shows no edge, a dynamic import may still exist (see
[Known limitations](../README.md#known-limitations)).

## The codes these prompts use

Straight from the `legend` key in the JSON.

**Schema v2** (`graph-compact.json`):

- **Edge types** — `c2c` code imports · `c2d` doc mentions · `d2d` doc links ·
  `dcs` docstring refs · `typ` `TYPE_CHECKING`-only · `ren` git renames.
- **Git status on a node** — `s:"add"` new · `s:"mod"` modified · `s:"del"` deleted ·
  `s:"ren"` renamed. Deleted files ride along as **ghost nodes**, flagged `G:1`, so a
  doc that still links to them stays visible.

**Schema v3** (`graph-ultra.json`) — the same facts, arranged differently:

- **Edge sections**, each named after what its group key is, so a row reads
  key-first: `imported_by` keyed by the imported module · `type_only_imported_by`
  the `TYPE_CHECKING`-only variant · `doc_mentions` keyed by the doc doing the
  mentioning · `doc_links` keyed by the linking doc · `docstring_refs` keyed by the
  file whose docstring mentions something · `renamed_to` git renames.
- **Nodes** are grouped under their directory; a row is `[id, filename, category]`
  plus `heat` (commit count) and `cov` (line coverage %, `-1` unmeasured) columns
  when those layers were collected — `cols` says which are present.
- **Optional layers**: `git` lists `[id, status]` for files that aren't clean,
  `ghosts` lists deleted-but-referenced files, `ge` holds the edges touching them.
- **No `degree` field** — it is the number of edges a node appears in.

## Loading it into context

The base instruction to open a session with.

**Schema v2** (`graph-compact.json`):

```text
This repository ships docs/graph-compact.json — a dependency map built by build-graph.

Before any task about structure, blast radius, or doc-sync:
1. Load docs/graph-compact.json and read the "legend" key first — it decodes
   every field and code.
2. If you have added or removed many files, regenerate it first
   (build-graph --compact) so the map is current.

The compact JSON is a map of connections, not semantics. Read a specific file
when you need to know what the code does. It is referential, not semantic — if it
shows no edge, a dynamic import may still exist (see the README's Known limitations).

When unsure whether a .md needs editing, go through the ghost-detector and
missing-edges prompts below rather than guessing.
```

**Schema v3** (`graph-ultra.json`):

```text
This repository ships docs/graph-ultra.json — a dependency map built by build-graph.

Before any task about structure, blast radius, or doc-sync:
1. Load docs/graph-ultra.json and read the "legend" and "cols" keys first — they
   describe every section and node column in the file.
2. Note how edges are stored: each section is named after what its group key is,
   so [key, [items]] always reads key-first. In "imported_by" the key is the
   module being imported and the items are the files importing it; in
   "doc_mentions" the key is the doc and the items are the files it mentions.
   An item is a bare node id, [id, line], or [id, [lines]].
3. If you have added or removed many files, regenerate it first
   (build-graph --ultra-compact) so the map is current.

The map is connections, not semantics. Read a specific file when you need to know
what the code does. It is referential, not semantic — if it shows no edge, a
dynamic import may still exist (see the README's Known limitations).

When unsure whether a .md needs editing, go through the ghost-detector and
missing-edges prompts below rather than guessing.
```

## Doc-sync workflow

After any batch of code changes — which docs to update, in three layers.

**Schema v2** (`graph-compact.json`):

```text
In docs/graph-compact.json the git status field marks:
- s:"add" — new file
- s:"mod" — modified
- s:"del" — deleted (node carries G:1, a ghost)
- s:"ren" — renamed

Produce a documentation-update plan for my changes, split into three layers:

1. DIRECT — the changed code file has a c2d edge to a .md. Explicit, undeniable.

2. HYPOTHETICAL (missing-edges) — no c2d edge, but one should exist by meaning.
   Reason from file names and architectural layers. E.g. a new file under an
   HTTP-interface package should probably be mentioned in the API reference and
   in the localization doc, if the project has one.

3. STALE (ghost-detector) — .md files with a c2d edge to a G:1 node. These docs
   mention a deleted file and need editing.

Sort by priority: edge degree + doc category (reference high, tutorial low) + how
critical the file is. Justify each item. Don't assume a doc's contents — ask me to
read the ones you pick.
```

**Schema v3** (`graph-ultra.json`):

```text
In docs/graph-ultra.json the "git" section lists [node id, status] for files that
are not clean: "add" new, "mod" modified, "del" deleted, "ren" renamed. Deleted
files also appear in "ghosts", and edges touching them live in "ge".

Produce a documentation-update plan for my changes, split into three layers:

1. DIRECT — the changed code file appears in some "doc_mentions" group. The group
   key is the .md that mentions it. Explicit, undeniable.

2. HYPOTHETICAL (missing-edges) — the file appears in no "doc_mentions" group, but
   should by meaning. Reason from file names and architectural layers. E.g. a new
   file under an HTTP-interface package should probably be mentioned in the API
   reference and in the localization doc, if the project has one.

3. STALE (ghost-detector) — .md files whose "doc_mentions" group in "ge" points at
   an id listed in "ghosts". These docs mention a deleted file and need editing.

Sort by priority: how many edges the node appears in + doc category (reference
high, tutorial low) + how critical the file is. Justify each item. Don't assume a
doc's contents — ask me to read the ones you pick.
```

## Blast radius before a refactor

**Schema v2** (`graph-compact.json`):

```text
I plan to change path/to/module. From docs/graph-compact.json:

1. Incoming c2c edges (modules importing it) — which files must change in sync?
2. Outgoing c2c — what it imports; can any be decoupled, or is it a contract?
3. type-only edges (typ) — a circular-dependency break via TYPE_CHECKING. Not a
   runtime dependency, but a type contract.
4. docstring edges (dcs) — where docstrings mention this file; do texts need updating?
5. test nodes with a c2c edge to this file — which tests will break?

Give a table: [file] [edge type] [change required / optional / none] with reasons.
No code yet — just the impact map.
```

**Schema v3** (`graph-ultra.json`):

```text
I plan to change path/to/module. Find its node id, then from docs/graph-ultra.json:

1. The "imported_by" group keyed by that id — every file importing it. Which must
   change in sync?
2. Groups in "imported_by" where that id appears among the items — what it imports
   itself; can any be decoupled, or is it a contract?
3. "type_only_imported_by" — a circular-dependency break via TYPE_CHECKING. Not a
   runtime dependency, but a type contract.
4. "docstring_refs" mentioning it — do those texts need updating?
5. Among the importers, the ones in a test category — which tests will break?

Mind the direction: in "imported_by" the key is the module being imported.

Give a table: [file] [relationship] [change required / optional / none] with
reasons. No code yet — just the impact map.
```

## Docs routing — what to read before editing code

**Schema v2** (`graph-compact.json`):

```text
I'm about to edit path/to/module. Don't write code yet.

Find the c2d edges from this file to docs/. For each .md show:
- category (reference / explanation / how-to / tutorial; ADRs separately)
- the doc's total degree (how central it is)
- the line numbers where my file is mentioned (edge.lines)

Flag especially:
- ADRs (architecture decision records) — may forbid the change I'm planning
- explanation/ — design rationale
- reference/ — API and contracts

Which of these must I read before editing? Ask me for the contents — don't assume them.
```

**Schema v3** (`graph-ultra.json`):

```text
I'm about to edit path/to/module. Don't write code yet.

Find its node id, then every "doc_mentions" group whose items include it — the
group key is the .md that mentions my file. For each such doc show:
- category (reference / explanation / how-to / tutorial; ADRs separately)
- how many edges that doc appears in overall (how central it is)
- the line numbers where my file is mentioned (the number carried by the item)

Flag especially:
- ADRs (architecture decision records) — may forbid the change I'm planning
- explanation/ — design rationale
- reference/ — API and contracts

Which of these must I read before editing? Ask me for the contents — don't assume them.
```

## Ghost-detector — finding stale documentation

**Schema v2** (`graph-compact.json`):

```text
In docs/graph-compact.json, nodes with G:1 are deleted files (s:"del").

Find every .md with a c2d edge to a ghost node. For each:
1. Which ghost is mentioned?
2. On which lines (edge.lines)?
3. Context type: tutorial prose / API description / code example / section heading?

The more load-bearing the context (a section heading about a deleted file, an API
that no longer exists), the higher the edit priority. Give a sorted list with the
concrete per-line fix.
```

**Schema v3** (`graph-ultra.json`):

```text
In docs/graph-ultra.json the "ghosts" section lists the ids of deleted files, and
"ge" holds the edges that touch them.

In ge."doc_mentions", find every group whose items include a ghost id — the group
key is a .md still mentioning a deleted file. For each:
1. Which ghost is mentioned? (resolve the id back to its path via "n")
2. On which lines? (the number carried by the item)
3. Context type: tutorial prose / API description / code example / section heading?

The more load-bearing the context (a section heading about a deleted file, an API
that no longer exists), the higher the edit priority. Give a sorted list with the
concrete per-line fix.
```

## Dead-code candidates

**Schema v2** (`graph-compact.json`):

```text
From the graph, find code files (t starts with a code category) with any of:
- degree 0 (no imports, no doc mentions)
- only outgoing edges, no incoming c2c
- only type-only incoming, no regular import

Whitelist (don't count as dead):
- __init__.py — namespace placeholders
- conftest.py — test infrastructure
- entry points (main.py, [project.scripts])
- parametrized fixtures with no explicit importer
- migration files invoked by discovery

Group by category. For each suspect, note why it might be a false positive
(external call via entry point, dynamic import, plugin registry).
```

**Schema v3** (`graph-ultra.json`):

```text
From docs/graph-ultra.json, find code files (third column of a node row is a code
category) with any of:
- an id that appears nowhere in "e" — no imports, no doc mentions
- an id that appears only among the items of "imported_by" groups, never as a
  group key — it imports others, nobody imports it
- an id that is a group key only in "type_only_imported_by" — no regular import

Whitelist (don't count as dead):
- __init__.py — namespace placeholders
- conftest.py — test infrastructure
- entry points (main.py, [project.scripts])
- parametrized fixtures with no explicit importer
- migration files invoked by discovery

Group by category. For each suspect, note why it might be a false positive
(external call via entry point, dynamic import, plugin registry).
```

## Missing-edges — what should be documented but isn't

**Schema v2** (`graph-compact.json`):

```text
docs/graph-compact.json has code nodes with no c2d edge (mentioned in no .md).

For each, decide by its semantics whether it *should* be documented somewhere,
following the docs structure:
- core modules — usually in reference (config / database / patterns) and/or an
  explanation for design-level rationale
- interface modules — reference for the API + how-to for setup
- parsers / adapters — reference plus a design explanation
- tests — a test-infrastructure reference if they introduce a new strategy

Skip files that legitimately have no docs (private helpers, internal utilities).
Give a table: [code file] [hypothesised doc] [reasoning].
```

**Schema v3** (`graph-ultra.json`):

```text
In docs/graph-ultra.json, find code node ids that appear in no "doc_mentions"
group's items — mentioned in no .md.

For each, decide by its semantics whether it *should* be documented somewhere,
following the docs structure:
- core modules — usually in reference (config / database / patterns) and/or an
  explanation for design-level rationale
- interface modules — reference for the API + how-to for setup
- parsers / adapters — reference plus a design explanation
- tests — a test-infrastructure reference if they introduce a new strategy

Skip files that legitimately have no docs (private helpers, internal utilities).
Give a table: [code file] [hypothesised doc] [reasoning].
```

## What the graph is not for

Tasks an agent should **not** try to answer from the graph:

- **Semantics inside a file** — function behaviour, class invariants. The graph knows
  module-level connections, not symbols. Read the file.
- **Code smells / anti-patterns** — that's a linter's job (ruff, mypy, …), not the map's.
- **Dynamic imports via runtime binding** — AST misses f-strings, dict lookups and
  local bindings ([Known limitations](../README.md#known-limitations)). A missing edge
  doesn't prove there's no dependency.
- **Cross-repo dependencies** — each graph is one repository.
- **External docs** (Confluence, Notion, wikis) — the graph is file-based.

If a task falls here, drop the graph and take another path: grep the code, read the
whole file, or ask for the external link.

<!-- ignore-ref: conftest.py -->  the bare filename above is an example, not a link
