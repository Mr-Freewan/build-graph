# Prompts for AI agents

`build-graph --compact` writes `graph-compact.json` — a token-efficient map of your
repository: nodes are files, edges are imports and documentation mentions, with a
self-describing `legend` key that decodes every field and code. This page is a set of
**ready-to-use prompts** that drive an LLM agent with that map for concrete tasks:
blast radius before a refactor, three-way doc-sync, hunting stale docs and dead code.

Copy a prompt, swap in your file paths, and hand it to the agent alongside the JSON.

## Why the map beats grep

Without the graph, an agent rediscovers your structure every session — dozens of
speculative greps and file reads, burned again per question. With `graph-compact.json`
in context it reads the structure once, cheaply (~2 % of the raw text's tokens), and
spends the budget on the actual task.

The map is **referential**, not semantic: it knows which files connect, not what the
code means. Semantics stay the agent's job — it reads a specific file when it needs to
know behaviour. If the graph shows no edge, a dynamic import may still exist (see
[Known limitations](../README.md#known-limitations)).

## The codes these prompts use

Straight from the `legend` key in the JSON:

- **Edge types** — `c2c` code imports · `c2d` doc mentions · `d2d` doc links ·
  `dcs` docstring refs · `typ` `TYPE_CHECKING`-only · `ren` git renames.
- **Git status on a node** — `s:"add"` new · `s:"mod"` modified · `s:"del"` deleted ·
  `s:"ren"` renamed. Deleted files ride along as **ghost nodes**, flagged `G:1`, so a
  doc that still links to them stays visible.

## Loading it into context

The base instruction to open a session with:

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

## Doc-sync workflow

After any batch of code changes — which docs to update, in three layers.

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

## Blast radius before a refactor

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

## Docs routing — what to read before editing code

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

## Ghost-detector — finding stale documentation

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

## Dead-code candidates

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

## Missing-edges — what should be documented but isn't

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
