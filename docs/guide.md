# UI guide

Every feature of the interactive graph, one by one. Try them live on the
[demo](https://mr-freewan.github.io/build-graph/) — it's the graph of the
build-graph repository itself, with a synthetic git overlay enabled.

---

## Getting around

The graph is a single canvas: **scroll to zoom, drag the background to
pan, drag a node to move it**. Node labels fade in as you zoom past the
*Show at zoom* threshold (viewport culling and label LOD keep 1000+ nodes
smooth). The crosshair button in the top bar resets the view; the counter
in the bottom-left corner shows how many nodes and edges are on the map.

![Zoom, pan and label LOD](https://mr-freewan.github.io/build-graph/media/guide/01-navigation.gif)

Hovering a node highlights it with its direct neighbours and dims
everything else; hovering an edge shows a tooltip with the edge type,
source → target and the exact line numbers behind the relation.

![Hover highlight and edge tooltip](https://mr-freewan.github.io/build-graph/media/guide/02-hover.gif)

## Panels

All seven panels are **draggable** — grab the dotted handle in the header.
The three main panels (Graph controls, legend, Exclude by name) **collapse**
into their title bar on a header click (chevron shows the state). The
info-panel resizes on both axes, Graph controls — horizontally. Positions,
sizes and collapsed states persist in `localStorage` and survive a reload;
when the window shrinks, panels clamp into the viewport and return to their
saved spot when it grows back.

The top-right corner hosts the appearance switches: **10 UI languages**
(DE / EN / ES / FR / IT / JA / KO / PT / RU / ZH), **dark / light theme**,
and **pastel / saturated palette** — the two palettes are hue-aligned, so
switching never re-shuffles which colour means what. Edge colours and
legend swatches follow the palette too. The built-in FAQ (the `?` button,
50+ answers in all 10 languages) makes an appearance here as well.

![Panels, appearance switches and the FAQ](https://mr-freewan.github.io/build-graph/media/guide/03-panels.gif)

## Graph controls

The left panel tunes the picture and the physics:

- **Nodes & edges** — colour contrast, node scale, edge width, edge opacity.
- **Labels** — font size and the zoom level at which labels appear.
- **Physics** — repulsion and link force; changes restart the simulation
  live.
- **Release pinned** frees every sticky-pinned node; **Rebuild physics**
  reheats the layout (pinned nodes keep their place — sticky wins over
  rebuild).

![Tuning the view and the physics](https://mr-freewan.github.io/build-graph/media/guide/04-controls.gif)

## Search and exclusion

The search field (`Ctrl/Cmd+K`) matches node names **and paths** — typing
`handlers/` lights up the whole subtree. The `×` button or `Esc` clears it.

**Exclude by name** removes noise: add a pattern and matching nodes are
taken off the board; excluded nodes are frozen so the layout doesn't jump.
Rebuild physics re-flows the survivors into the freed space.

![Search and exclude-by-name](https://mr-freewan.github.io/build-graph/media/guide/05-search-exclude.gif)

## Legend filtering

The legend is interactive:

- **Click a node type** to hide/show it; the eye buttons show/hide all at
  once.
- **🎯 isolate** on any row keeps only that type (click again to undo).
- **Click an edge type** to hide those edges — nodes left with no visible
  connections disappear too, so "only `docstring` edges" gives you a clean
  docstring subgraph, not a cloud of disconnected dots.
- **Orphans only** shows just the files nothing links to.

![Type filters and isolation](https://mr-freewan.github.io/build-graph/media/guide/06-legend-filters.gif)

## Inspecting a node

Click a node — the **info-panel** opens and the selection stays highlighted
(pinned) after the cursor leaves:

- The path is rendered as **clickable breadcrumbs** — click a directory
  segment and it becomes the search query.
- Connections are grouped: `filename:line [type] ▸ +N` — expand to see
  every line where the relation occurs.
- The **IDE selector** (VS Code / Cursor / PyCharm / Copy path) turns every
  file into a deep link — open the exact file:line straight from the
  browser.

![Info-panel, breadcrumbs and IDE deep links](https://mr-freewan.github.io/build-graph/media/guide/07-info-panel.gif)

With a node pinned, hovering any of its neighbours peeks one level deeper:
the highlight becomes the union of both neighbourhoods — a quick two-step
walk of the dependency chain without losing your place.

![Two-step neighbourhood peek](https://mr-freewan.github.io/build-graph/media/guide/08-hover-peek.gif)

## Pinning nodes in place

Two ways to nail a node to the canvas:

- **Double-click** it, or
- press **B** while hovering — works even mid-drag: drag a node aside,
  hit B, release — it stays.

Pinned nodes show a 📌 marker, survive Rebuild physics, and are released
either by another double-click or globally with **Release pinned**.

![Sticky pins with the B hotkey](https://mr-freewan.github.io/build-graph/media/guide/09-sticky-pins.gif)

## Path between two nodes

**Shift+click** two nodes to get the shortest dependency path between them
(undirected BFS): endpoints and the path edges turn purple, the rest dims.
If no path exists, a toast says so. `Esc` or a background click clears it.

![Shortest path via Shift+click](https://mr-freewan.github.io/build-graph/media/guide/10-path.gif)

## Focusing an edge

Click an edge to isolate it: only the source and target stay lit (with
their labels forced on), so you can read exactly which two files the
relation binds. `Esc` or a background click releases.

![Edge focus](https://mr-freewan.github.io/build-graph/media/guide/11-edge-focus.gif)

## Git mode

The **Git** button switches node colours from types to **working-tree
status**: added / modified / renamed / deleted / clean. Extras appear that
plain colouring can't show:

- **Ghost nodes** (dashed outline) — deleted files that docs still
  reference, and the old halves of renames.
- **Rename edges** (dashed, no arrow) — old ghost → new live node.
- The legend switches to git statuses with the same click-to-filter,
  eye buttons and 🎯 isolation.

The button is disabled (with a tooltip) when git isn't available. For demos
and screenshots, `--mock-git` bakes a synthetic overlay covering all five
categories.

![Git overlay with ghost nodes and rename edges](https://mr-freewan.github.io/build-graph/media/guide/12-git-mode.gif)

## Analysis aids

**💀 Dead code** (legend, appears when there are candidates) highlights
files with no incoming imports and no documentation mentions. Entry points
are exempt automatically: `[project.scripts]` from `pyproject.toml`,
`main.py`, `__init__.py`, `conftest.py`, `test_*.py`, plus anything matched
by `[dead_code].exempt` globs in `graph.toml`. The 💀 toggle is shown at
the end of the Git-mode clip above.

**Cycles** (legend, appears when import loops exist) highlights strongly
connected components in the runtime `code->code` import graph: loop edges
turn coral, loop members get a coral ring, everything else fades. Type-only
(`TYPE_CHECKING`) imports don't count — they are the legal way to break a
cycle. The counter is the number of independent loops, and while a mode
like this is active, faded nodes and edges ignore the pointer — hovering
past them won't light them up.

![Import cycles highlighted](media/guide/15-cycles.png)

**Orphan ring** — zero-degree files aren't scattered; they sit on a circle
around the live cluster, so "connected core vs loose files" is readable at
a glance. Files that autodiscovery couldn't classify get an amber ring and
their own counter button in the top bar.

![Orphan ring](media/guide/13-orphan-ring.png)

## Sharing and export

The **File menu** collects the outputs:

- **Copy link** — the current view (language, theme, palette, filters,
  git mode, search, pinned selection) encoded in the URL hash. Open the
  link — see the same picture. Personal prefs (panel positions, sliders,
  IDE choice) deliberately stay out of the URL.
- **Copy as Mermaid** — the focused subgraph (path > edge focus >
  pinned node + neighbours > search results) as a `flowchart LR` snippet,
  arrow style encoding the edge type. Paste it into a PR description.
- **Copy JSON** — the full graph data for an LLM agent (same data as the
  `--json` / `--compact` CLI flags).
- **Export / Import prefs** — move your entire setup (positions, sliders,
  filters, theme) to another machine as a JSON file.

A real *Copy as Mermaid* example — one admin subsystem isolated via search,
exported, pasted into markdown as-is:

![Copy-as-Mermaid output rendered](media/guide/14-mermaid-example.png)

<details>
<summary>The exported Mermaid source behind that picture</summary>


```mermaid
flowchart LR
    n0["api-manager-admin-api.md"]:::doc_reference
    n1["authorization-api.md"]:::doc_reference
    n2["doc-contract-testing.md"]:::doc_reference
    n3["football-db-admin-menu.md"]:::doc_reference
    n4["monitoring-admin-api.md"]:::doc_reference
    n5["parsers-admin-api.md"]:::doc_reference
    n6["patterns.md"]:::doc_reference
    n7["project-structure.md"]:::doc_reference
    n8["colors.py"]:::code_interfaces
    n9["conversation.py"]:::code_interfaces
    n10["deleted.py"]:::code_interfaces
    n11["fetch_meta.py"]:::code_interfaces
    n12["groups.py"]:::code_interfaces
    n13["identity_meta.py"]:::code_interfaces
    n14["initial_cap.py"]:::code_interfaces
    n15["main.py"]:::code_interfaces
    n16["shared.py"]:::code_interfaces
    n17["site_meta.py"]:::code_interfaces
    n18["sources.py"]:::code_interfaces
    n19["tier_management.py"]:::code_interfaces
    n20["types_tiers.py"]:::code_interfaces
    n21["states.py"]:::code_interfaces
    n22["test_parsers_menu.py"]:::code_tests
    n23["test_parsers_menu_colors.py"]:::code_tests
    n24["test_parsers_menu_export.py"]:::code_tests
    n25["test_parsers_menu_extended.py"]:::code_tests
    n26["test_parsers_menu_fetch_meta.py"]:::code_tests
    n27["test_parsers_menu_identity.py"]:::code_tests
    n28["test_parsers_menu_settings.py"]:::code_tests
    n29["test_parsers_menu_site_meta.py"]:::code_tests
    n30["test_tier_management.py"]:::code_tests
    n2 --> n1
    n2 --> n6
    n4 --> n0
    n4 --> n5
    n7 --> n2
    n21 -.-> n0
    n21 -.-> n1
    n21 -.-> n2
    n21 -.-> n3
    n21 -.-> n4
    n21 -.-> n5
    n21 -.-> n6
    n21 -.-> n7
    n15 -.-> n0
    n15 -.-> n1
    n15 -.-> n3
    n15 -.-> n4
    n15 -.-> n5
    n15 -.-> n6
    n15 -.-> n7
    n16 -.-> n0
    n16 -.-> n1
    n16 -.-> n3
    n16 -.-> n7
    n9 -.-> n0
    n9 -.-> n7
    n10 -.-> n5
    n10 -.-> n7
    n11 -.-> n5
    n11 -.-> n7
    n12 -.-> n5
    n12 -.-> n7
    n13 -.-> n5
    n13 -.-> n7
    n14 -.-> n7
    n17 -.-> n5
    n17 -.-> n7
    n18 -.-> n5
    n18 -.-> n7
    n19 -.-> n5
    n19 -.-> n7
    n20 -.-> n5
    n20 -.-> n7
    n22 -.-> n5
    n22 -.-> n7
    n24 -.-> n5
    n24 -.-> n7
    n25 -.-> n5
    n25 -.-> n7
    n26 -.-> n5
    n26 -.-> n7
    n27 -.-> n5
    n27 -.-> n7
    n28 -.-> n5
    n28 -.-> n7
    n29 -.-> n5
    n29 -.-> n7
    n30 -.-> n5
    n30 -.-> n7
    n8 ==> n21
    n9 ==> n8
    n9 ==> n10
    n9 ==> n11
    n9 ==> n12
    n9 ==> n13
    n9 ==> n14
    n9 ==> n15
    n9 ==> n17
    n9 ==> n18
    n9 ==> n19
    n9 ==> n20
    n9 ==> n21
    n10 ==> n21
    n11 ==> n21
    n12 ==> n21
    n13 ==> n21
    n14 ==> n21
    n15 ==> n21
    n16 ==> n21
    n17 ==> n21
    n18 ==> n21
    n19 ==> n21
    n20 ==> n21
    n22 ==> n21
    n23 ==> n8
    n23 ==> n21
    n24 ==> n21
    n25 ==> n21
    n26 ==> n11
    n26 ==> n14
    n26 ==> n21
    n27 ==> n13
    n27 ==> n21
    n28 ==> n21
    n29 ==> n17
    n29 ==> n21
    n30 ==> n19
    n30 ==> n21
    n27 --> n13
    n30 --> n22
    classDef doc_reference fill:#ffd6a5,stroke:#444,color:#000
    classDef code_interfaces fill:#fdffb6,stroke:#444,color:#000
    classDef code_tests fill:#d4d4d8,stroke:#444,color:#000
```

</details>

## FAQ and shortcuts

The `?` button opens a built-in FAQ — 50+ answers in all 10 languages,
covering everything on this page (you can see it opened in the Panels clip
above).

| Key | Action |
|-----|--------|
| `Esc` | close things, in order: File menu → FAQ → info-panel → edge focus → clear search |
| `Space` | pause / resume the physics |
| `Ctrl/Cmd+K` | focus the search field |
| `B` | pin/unpin the node under the cursor (works mid-drag) |
| `Shift+click` × 2 | shortest path between two nodes |
| double-click | pin/unpin a node in place |
