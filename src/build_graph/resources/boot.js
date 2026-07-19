// === INIT ===
// Watermark with version + author (set once on load — values injected by Python).
// Author name is wrapped in an <a> linking to the author's repo; the link
// re-enables pointer-events (the watermark itself disables them via CSS).
(function setWatermark() {
    const el = document.getElementById("watermark");
    if (!el) return;
    el.innerHTML = "v" + esc(APP_VERSION) + " · by "
        + '<a href="' + esc(APP_AUTHOR_URL) + '" target="_blank" '
        + 'rel="noopener noreferrer">' + esc(APP_AUTHOR) + "</a>";
})();

// Build git legend + bind git button BEFORE applyI18n so labels get translated
// and BEFORE loadPrefs so saved gitMode state can be restored.
buildGitLegend();
updateGitLegendCounts();
setupGitButton();

// Apply default language (RU) to all data-i18n* elements before loadPrefs
// may overwrite it. The stats line uses tFmt — set after applyI18n.
applyI18n(currentLang);
document.getElementById("stats").textContent =
    tFmt("stats", nodes.length, links.length);
lockAllI18nWidths();

// Export / import preferences
// File menu — popup with Export / Import / Copy JSON
(function setupFileMenu() {
    const btn = document.getElementById("btn-file-menu");
    const menu = document.getElementById("file-menu");
    if (!btn || !menu) return;
    btn.addEventListener("click", e => {
        e.stopPropagation();
        menu.classList.toggle("hidden");
    });
    // Click on any popup item closes the menu (the item's own listener still fires)
    menu.addEventListener("click", () => {
        menu.classList.add("hidden");
    });
    // Click outside closes too
    document.addEventListener("click", e => {
        if (!menu.classList.contains("hidden")
            && !menu.contains(e.target) && e.target !== btn) {
            menu.classList.add("hidden");
        }
    });
})();

document.getElementById("btn-export-prefs").addEventListener("click", () => {
    const data = localStorage.getItem(PREF_KEY) || "{}";
    const blob = new Blob([data], {type: "application/json"});
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "graph-prefs.json";
    a.click();
    URL.revokeObjectURL(a.href);
});

// LLM-export: compact JSON snapshot of the graph copied to clipboard.
// Drops UI-only fields (size, x/y); keeps id/path/type/degree/gitStatus +
// edge source/target/type/lines so a model can reason about structure.
document.getElementById("btn-copy-llm").addEventListener("click", () => {
    const cleanNode = n => {
        const out = {
            id: n.id, label: n.label, path: n.path,
            type: n.type, degree: n.degree
        };
        if (n.gitStatus) out.gitStatus = n.gitStatus;
        if (n.ghost) out.ghost = true;
        return out;
    };
    const cleanEdge = e => {
        const src = typeof e.source === "object" ? e.source.id : e.source;
        const tgt = typeof e.target === "object" ? e.target.id : e.target;
        const out = { source: src, target: tgt, type: e.type };
        if (e.lines && e.lines.length) out.lines = e.lines;
        if (e.weight && e.weight !== 1) out.weight = e.weight;
        if (e.ghost) out.ghost = true;
        return out;
    };
    const cats = [...new Set(nodes.map(n => n.type).filter(Boolean))].sort();
    const eTypes = [...new Set(links.map(l => l.type).filter(Boolean))].sort();
    const data = {
        schema_version: "1.0",
        project_root: PROJECT_ROOT,
        stats: {
            node_count: nodes.length,
            edge_count: links.length,
            categories: cats,
            edge_types: eTypes,
            git_available: !!GIT_DATA
        },
        nodes: nodes.map(cleanNode),
        edges: links.map(cleanEdge)
    };
    const text = JSON.stringify(data, null, 2);
    const fallback = () => {
        // Fallback: if Clipboard API isn't available, dump as a download.
        const blob = new Blob([text], {type: "application/json"});
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = "graph-data.json";
        a.click();
        URL.revokeObjectURL(a.href);
    };
    try {
        navigator.clipboard.writeText(text)
            .then(showCopyToast)
            .catch(fallback);
    } catch (_) { fallback(); }
});
// Mermaid export — flowchart LR over the FOCUSED subgraph (whatever the
// user is actually looking at), not the full visible set. Priority order:
//   - path between nodes  → path nodes + path edges only
//   - edge focus          → two endpoints + the focused edge
//   - pinned info-panel   → pin + immediate neighbors
//   - search active       → matched nodes (edges between them only)
//   - nothing focused     → "" (caller shows toast)
// Mermaid IDs must be alphanumeric, so we alias real ids to n0/n1/... and
// put the label in [..]. Edge styles encode the edge type:
//   doc->doc   -->   (solid)
//   code->doc  -.->  (dashed)
//   code->code ==>   (thick)
// Rename edges (git overlay only) are dropped.
function generateMermaid() {
    let focusIds = null;
    let focusEdges = null;
    if (pathActive() && pathNodeIds.size) {
        focusIds = pathNodeIds;
        focusEdges = pathLinks;
    } else if (activeEdge) {
        focusIds = new Set([activeEdge.source.id, activeEdge.target.id]);
        focusEdges = new Set([activeEdge]);
    } else if (activeNodeData && !infoPanel.classList.contains("hidden")) {
        focusIds = neighborMap.get(activeNodeData.id)
            || new Set([activeNodeData.id]);
    } else if (searchQuery && searchMatching.size) {
        focusIds = searchMatching;
    } else {
        return "";
    }
    const visible = nodes.filter(n => focusIds.has(n.id));
    if (!visible.length) return "";
    const idMap = new Map();
    visible.forEach((n, i) => idMap.set(n.id, "n" + i));
    const safeLabel = s => '"' + String(s).replace(/"/g, "&quot;") + '"';
    const safeClass = type => type.replace(/[^a-z0-9_]/gi, "_");
    const lines = ["flowchart LR"];
    // Inline class assignment via `:::cls` is more portable across Mermaid
    // versions than the standalone `class id1,id2 cls` statement, which
    // some parsers reject on indentation / comma-spacing edge cases.
    visible.forEach(n => {
        const cls = n.type ? safeClass(n.type) : null;
        let line = "    " + idMap.get(n.id) + "[" + safeLabel(n.label) + "]";
        if (cls) line += ":::" + cls;
        lines.push(line);
    });
    let edges;
    if (focusEdges) {
        edges = Array.from(focusEdges);
    } else {
        edges = links.filter(l => {
            const s = typeof l.source === "object" ? l.source.id : l.source;
            const tg = typeof l.target === "object" ? l.target.id : l.target;
            return focusIds.has(s) && focusIds.has(tg)
                && !hiddenEdgeTypes.has(l.type)
                && l.type !== "rename";
        });
    }
    const arrowFor = type =>
        type === "code->doc"  ? "-.->" :
        type === "code->code" ? "==>" :
        "-->";
    edges.forEach(e => {
        const s = typeof e.source === "object" ? e.source.id : e.source;
        const tg = typeof e.target === "object" ? e.target.id : e.target;
        lines.push("    " + idMap.get(s) + " " + arrowFor(e.type)
            + " " + idMap.get(tg));
    });
    // One classDef per unique type; nodes already reference them inline.
    const seenTypes = new Set();
    visible.forEach(n => {
        if (!n.type || seenTypes.has(n.type)) return;
        seenTypes.add(n.type);
        const fill = activeColors[n.type] || "#888";
        lines.push("    classDef " + safeClass(n.type)
            + " fill:" + fill + ",stroke:#444,color:#000");
    });
    return lines.join("\n");
}
document.getElementById("btn-copy-mermaid").addEventListener("click", () => {
    const text = generateMermaid();
    if (!text) {
        showToast(t("toast.nothingToExport"));
        return;
    }
    const fallback = () => {
        const blob = new Blob([text], {type: "text/plain"});
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = "graph.mmd";
        a.click();
        URL.revokeObjectURL(a.href);
    };
    try {
        navigator.clipboard.writeText(text)
            .then(showCopyToast).catch(fallback);
    } catch (_) { fallback(); }
});

// Copy link — current URL with hash-encoded shareable view state. Receiver
// gets the same view (filters, theme, language, pin, search) but keeps
// their own panel positions / sliders / IDE preference.
document.getElementById("btn-copy-link").addEventListener("click", () => {
    const hash = encodeStateHash(getShareableState());
    const url = location.origin + location.pathname + location.search + hash;
    const fallback = () => {
        const ta = document.createElement("textarea");
        ta.value = url;
        document.body.appendChild(ta);
        ta.select();
        try { document.execCommand("copy"); } catch (_) {}
        document.body.removeChild(ta);
    };
    try {
        navigator.clipboard.writeText(url)
            .then(showCopyToast)
            .catch(() => { fallback(); showCopyToast(); });
    } catch (_) { fallback(); showCopyToast(); }
});
document.getElementById("btn-import-prefs").addEventListener("click", () => {
    document.getElementById("import-file").click();
});
document.getElementById("import-file").addEventListener("change", e => {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = ev => {
        try {
            JSON.parse(ev.target.result);
            localStorage.setItem(PREF_KEY, ev.target.result);
            loadPrefs();
        } catch(err) { alert(t("alert.invalidPrefs")); }
    };
    reader.readAsText(file);
    e.target.value = "";
});

loadPrefs();
// Apply URL hash state on top of loaded prefs (shared link wins for the
// view-defining subset, but recipient's panel layout etc. is preserved).
if (location.hash && location.hash.length > 1) {
    applyShareableState(decodeStateHash(location.hash));
}
// A ref-diff build is meaningless without the overlay — start in git mode
// regardless of saved prefs (the user can still toggle it off).
if (DIFF_INFO && GIT_DATA && !gitMode) applyGitMode(true);
// Match legend width to exclude-panel so they look balanced on the right side
// (theme-toggle & help-panel widths are pinned via CSS). MUST run before
// clampAllPanels(): on a fresh session (no saved prefs) #legend is still
// right-anchored (CSS `right: 12px`, no inline `left`), so widening it here
// grows the box LEFTWARD — safe. clampAllPanels() then bakes an inline
// `left` from the final (already-synced) width. Doing this the other way
// around — clamp first, resize after — bakes `left` from the pre-sync
// (CSS-only) width, converts the panel to left-anchored (`right: auto`),
// and the subsequent width change grows it RIGHTWARD with no re-clamp,
// pushing it off the viewport on first load.
(function syncLegendWidth() {
    const exclude = document.getElementById("exclude-panel");
    const legend = document.getElementById("legend");
    if (exclude && legend) {
        legend.style.width = exclude.getBoundingClientRect().width + "px";
    }
})();
// In case saved panel positions were captured at a larger viewport
// (or a different zoom level), pull anything sticking out back inside.
clampAllPanels();

// === WARMUP & FIRST PAINT ===
// Make sure every node/link carries a `_vis` flag even when no prefs
// or hash state triggered applyAllFilters above (ghosts must hide).
applyAllFilters();
// Pre-settle the simulation headlessly so the first painted frame is a
// calm, already-untangled graph instead of the initial explosion.
// simulation.tick() doesn't fire tick events, so nothing renders during
// the loop. On very large graphs, freeze physics entirely after settling
// — Space (or the sliders) re-enables it.
(function warmupAndStart() {
    const FREEZE_THRESHOLD = 2000;
    let guard = 300;
    while (simulation.alpha() > 0.05 && guard-- > 0) {
        tickRefitOrphanRing();
        simulation.tick();
    }
    if (nodes.length > FREEZE_THRESHOLD) {
        simulation.stop();
        physicsPaused = true;
    }
    refreshThemeColors();  // reads CSS vars + queues the first draw
})();
