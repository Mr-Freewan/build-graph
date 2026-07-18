# UI guide

Every feature of the interactive graph, one by one. Try them live on the
[demo](https://mr-freewan.github.io/build-graph/) — it's the graph of the
build-graph repository itself, with a synthetic git overlay enabled.

Media conventions in this file: `SHOT NN` comments describe what each
screenshot/GIF should show; the image line below each is uncommented once
the file lands in `docs/media/guide/`.

---

## Getting around

The graph is a single canvas: **scroll to zoom, drag the background to
pan, drag a node to move it**. Node labels fade in as you zoom past the
*Show at zoom* threshold (viewport culling and label LOD keep 1000+ nodes
smooth). The crosshair button in the top bar resets the view; the counter
in the bottom-left corner shows how many nodes and edges are on the map.

<!-- SHOT 01 (GIF, ~8s): start zoomed out, zoom into a cluster until labels
     appear, pan, then click the reset-zoom button. -->
<!-- ![Zoom, pan and label LOD](media/guide/01-navigation.gif) -->

Hovering a node highlights it with its direct neighbours and dims
everything else; hovering an edge shows a tooltip with the edge type,
source → target and the exact line numbers behind the relation.

<!-- SHOT 02 (GIF, ~6s): hover a mid-degree node (highlight), move off it,
     then hover an edge until the tooltip appears. -->
<!-- ![Hover highlight and edge tooltip](media/guide/02-hover.gif) -->

## Panels

All seven panels are **draggable** — grab the dotted handle in the header.
The three main panels (Graph controls, legend, Exclude by name) **collapse**
into their title bar on a header click (chevron shows the state). The
info-panel resizes on both axes, Graph controls — horizontally. Positions,
sizes and collapsed states persist in `localStorage` and survive a reload;
when the window shrinks, panels clamp into the viewport and return to their
saved spot when it grows back.

<!-- SHOT 03 (GIF, ~10s): drag the legend to a new spot, collapse it,
     collapse Graph controls, resize the info-panel, reload the page —
     everything stays. -->
<!-- ![Dragging, collapsing and persistence](media/guide/03-panels.gif) -->

The top-right corner hosts the appearance switches: **10 UI languages**
(DE / EN / ES / FR / IT / JA / KO / PT / RU / ZH), **dark / light theme**,
and **pastel / saturated palette** — the two palettes are hue-aligned, so
switching never re-shuffles which colour means what. Edge colours and
legend swatches follow the palette too.

<!-- SHOT 04 (GIF, ~10s): switch language EN → RU (labels change width-
     stable), toggle theme dark → light, flip palette pastel → saturated. -->
<!-- ![Language, theme and palette](media/guide/04-appearance.gif) -->

## Graph controls

The left panel tunes the picture and the physics:

- **Nodes & edges** — colour contrast, node scale, edge width, edge opacity.
- **Labels** — font size and the zoom level at which labels appear.
- **Physics** — repulsion and link force; changes restart the simulation
  live.
- **Release pinned** frees every sticky-pinned node; **Rebuild physics**
  reheats the layout (pinned nodes keep their place — sticky wins over
  rebuild).

<!-- SHOT 05 (GIF, ~12s): drag node scale up, edge opacity down, then pull
     repulsion stronger and watch the layout breathe, finish with Rebuild
     physics. -->
<!-- ![Tuning the view and the physics](media/guide/05-controls.gif) -->

## Search and exclusion

The search field (`Ctrl/Cmd+K`) matches node names **and paths** — typing
`handlers/` lights up the whole subtree. The `×` button or `Esc` clears it.

**Exclude by name** removes noise: add a pattern and matching nodes are
taken off the board; excluded nodes are frozen so the layout doesn't jump.
Rebuild physics re-flows the survivors into the freed space.

<!-- SHOT 06 (GIF, ~10s): Ctrl+K, type a directory prefix, clear with ×;
     then exclude "test" via the panel, Rebuild physics. -->
<!-- ![Search and exclude-by-name](media/guide/06-search-exclude.gif) -->

## Legend filtering

The legend is interactive:

- **Click a node type** to hide/show it; the eye buttons show/hide all at
  once.
- **🎯 isolate** on any row keeps only that type (click again to undo).
- **Click an edge type** to hide those edges — nodes left with no visible
  connections disappear too, so "only `docstring` edges" gives you a clean
  docstring subgraph, not a cloud of disconnected dots.
- **Orphans only** shows just the files nothing links to.

<!-- SHOT 07 (GIF, ~12s): hide a couple of node types, Show all, then 🎯
     isolate one edge type (docstring) — note the orphan cleanup — and
     undo. -->
<!-- ![Type filters and isolation](media/guide/07-legend-filters.gif) -->

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

<!-- SHOT 08 (GIF, ~12s): click a node, expand a "+N" connection group,
     click a breadcrumb segment (search fills), then open a file in
     VS Code via the link. -->
<!-- ![Info-panel, breadcrumbs and IDE deep links](media/guide/08-info-panel.gif) -->

With a node pinned, hovering any of its neighbours peeks one level deeper:
the highlight becomes the union of both neighbourhoods — a quick two-step
walk of the dependency chain without losing your place.

<!-- SHOT 09 (GIF, ~8s): pin a hub node, hover two of its neighbours in
     turn — watch the second-level connections light up and fall back. -->
<!-- ![Two-step neighbourhood peek](media/guide/09-hover-peek.gif) -->

## Pinning nodes in place

Two ways to nail a node to the canvas:

- **Double-click** it, or
- press **B** while hovering — works even mid-drag: drag a node aside,
  hit B, release — it stays.

Pinned nodes show a 📌 marker, survive Rebuild physics, and are released
either by another double-click or globally with **Release pinned**.

<!-- SHOT 10 (GIF, ~10s): double-click a node (pin appears), drag another
     one aside and press B mid-drag, then Release pinned frees both. -->
<!-- ![Sticky pins with the B hotkey](media/guide/10-sticky-pins.gif) -->

## Path between two nodes

**Shift+click** two nodes to get the shortest dependency path between them
(undirected BFS): endpoints and the path edges turn purple, the rest dims.
If no path exists, a toast says so. `Esc` or a background click clears it.

<!-- SHOT 11 (GIF, ~8s): Shift+click a doc node, Shift+click a distant code
     node, the path lights up; Esc clears. -->
<!-- ![Shortest path via Shift+click](media/guide/11-path.gif) -->

## Focusing an edge

Click an edge to isolate it: only the source and target stay lit (with
their labels forced on), so you can read exactly which two files the
relation binds. `Esc` or a background click releases.

<!-- SHOT 12 (GIF, ~6s): click a long edge crossing the graph, both ends
     highlight with labels; Esc. -->
<!-- ![Edge focus](media/guide/12-edge-focus.gif) -->

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

<!-- SHOT 13 (GIF, ~10s; build with --mock-git): toggle Git mode, point at
     a ghost node and its rename edge, filter to modified-only, toggle
     back. -->
<!-- ![Git overlay with ghost nodes and rename edges](media/guide/13-git-mode.gif) -->

## Analysis aids

**💀 Dead code** (legend, appears when there are candidates) highlights
files with no incoming imports and no documentation mentions. Entry points
are exempt automatically: `[project.scripts]` from `pyproject.toml`,
`main.py`, `__init__.py`, `conftest.py`, `test_*.py`, plus anything matched
by `[dead_code].exempt` globs in `graph.toml`.

<!-- SHOT 14 (screenshot): dead-code mode on — red-outlined candidates on a
     dimmed graph, counter visible on the button. -->
<!-- ![Dead-code candidates](media/guide/14-dead-code.png) -->

**Orphan ring** — zero-degree files aren't scattered; they sit on a circle
around the live cluster, so "connected core vs loose files" is readable at
a glance. Files that autodiscovery couldn't classify get an amber ring and
their own counter button in the top bar.

<!-- SHOT 15 (screenshot): zoomed-out view showing the orphan ring around
     the cluster. -->
<!-- ![Orphan ring](media/guide/15-orphan-ring.png) -->

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

<!-- SHOT 16 (GIF, ~10s): open File menu, Copy link, open the link in a new
     tab — identical view; then Copy as Mermaid and show the pasted
     snippet rendered. -->
<!-- ![Shareable links and Mermaid export](media/guide/16-share-export.gif) -->

## FAQ and shortcuts

The `?` button opens a built-in FAQ — 50+ answers in all 10 languages,
covering everything on this page.

<!-- SHOT 17 (screenshot): FAQ overlay open on the Navigation section. -->
<!-- ![Built-in FAQ](media/guide/17-faq.png) -->

| Key | Action |
|-----|--------|
| `Esc` | close things, in order: File menu → FAQ → info-panel → edge focus → clear search |
| `Space` | pause / resume the physics |
| `Ctrl/Cmd+K` | focus the search field |
| `B` | pin/unpin the node under the cursor (works mid-drag) |
| `Shift+click` × 2 | shortest path between two nodes |
| double-click | pin/unpin a node in place |
