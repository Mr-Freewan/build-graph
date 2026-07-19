// === UTILS & INFO-PANEL ===
function esc(s) {
    return String(s)
        .replace(/&/g, "&amp;").replace(/</g, "&lt;")
        .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function buildFileHref(filePath, line) {
    const abs = PROJECT_ROOT + "/" + filePath;
    if (ideScheme === "vscode")
        return "vscode://file/" + abs + (line ? ":" + line : "");
    if (ideScheme === "cursor")
        return "cursor://file/" + abs + (line ? ":" + line : "");
    if (ideScheme === "pycharm") {
        const q = line ? "&line=" + line : "";
        return "pycharm://open?file=" + abs + q;
    }
    return null; // copy mode
}

// Info panel
const infoPanel    = document.getElementById("info-panel");
const infoTitle    = document.getElementById("info-title");
const infoPath     = document.getElementById("info-path");
const infoConns    = document.getElementById("info-connections");
infoConns.addEventListener("click", e => {
    const btn = e.target.closest(".conn-more");
    if (!btn) return;
    e.stopPropagation();
    const extra = btn.closest("li").querySelector(".conn-extra");
    if (!extra) return;
    const isOpen = extra.style.display !== "none";
    extra.style.display = isOpen ? "none" : "";
    const arrow = btn.querySelector(".conn-arrow");
    if (arrow) arrow.textContent = isOpen ? "▸" : "▾";
});
// Clickable breadcrumb segments in #info-path: clicking a directory
// segment writes its prefix into the search box, so the existing search
// machinery dims everything outside that subtree.
document.getElementById("info-path").addEventListener("click", e => {
    const seg = e.target.closest(".bc-seg");
    if (!seg) return;
    e.stopPropagation();
    e.preventDefault();
    const prefix = seg.dataset.prefix;
    const searchEl = document.getElementById("search");
    searchEl.value = prefix;
    searchEl.dispatchEvent(new Event("input"));
});
const infoTypeEl   = document.getElementById("info-type");
const infoConnCnt  = document.getElementById("info-conn-count");

function renderInfoPanel(d) {
    const connected = [];
    links.forEach(l => {
        const cd = l.type === "code->doc";
        if (l.source.id === d.id)
            connected.push({
                node: l.target, dir: cd ? "←" : "→", type: l.type, edge: l});
        if (l.target.id === d.id)
            connected.push({
                node: l.source, dir: cd ? "→" : "←", type: l.type, edge: l});
    });
    infoTitle.textContent = d.label;
    // Path as clickable breadcrumbs: each directory segment becomes a span
    // that, on click, filters the graph by that path prefix (via the search
    // box). The filename segment keeps its IDE-open / copy-path behavior.
    const segs = d.path.split("/");
    const filename = segs.pop();
    let bc = "";
    let acc = "";
    segs.forEach((seg, i) => {
        acc = i === 0 ? seg : acc + "/" + seg;
        bc += '<span class="bc-seg" data-prefix="' + esc(acc) + '" title="'
            + esc(acc) + '">' + esc(seg) + '</span>'
            + '<span class="bc-sep">/</span>';
    });
    const pathHref = buildFileHref(d.path, null);
    const fileLink = pathHref
        ? '<a href="' + esc(pathHref) + '" class="conn-link">'
            + esc(filename) + "</a>"
        : '<span class="conn-link conn-copy" data-copy="'
            + esc(PROJECT_ROOT + "/" + d.path)
            + '" title="' + esc(t("info.copyTitle")) + '">'
            + esc(filename) + "</span>";
    infoPath.innerHTML = bc + fileLink;
    const typeColor = activeColors[d.type] || "#999";
    infoTypeEl.innerHTML =
        '<span style="display:inline-block;width:9px;height:9px;'
        + 'border-radius:50%;background:' + esc(typeColor)
        + ';margin-right:6px;flex-shrink:0"></span>'
        + esc(d.type);
    infoTypeEl.style.color = "";
    const outgoing = connected.filter(c => c.dir === "→");
    const incoming = connected.filter(c => c.dir === "←");
    const n = connected.length;
    infoConnCnt.textContent = tFmt("connectionCount", n);

    function renderConnItem(c, isOutgoing, displayLabel) {
        const lns = c.edge.lines || [];
        const firstLine = lns.length ? lns[0] : null;
        const rest = lns.slice(1);
        const filePath = (isOutgoing && firstLine !== null) ? d.path : c.node.path;
        const href = buildFileHref(filePath, firstLine);
        const labelText = displayLabel(c) + (firstLine !== null ? ":" + firstLine : "");
        const inner = esc(labelText);
        const copyPath = PROJECT_ROOT + "/" + filePath
            + (firstLine !== null ? ":" + firstLine : "");
        const linkEl = href
            ? '<a href="' + esc(href) + '" class="conn-link">' + inner + "</a>"
            : '<span class="conn-link conn-copy" data-copy="' + esc(copyPath)
                + '" title="' + esc(t("info.copyTitle")) + '">' + inner + "</span>";
        let moreBtn = "";
        let extraList = "";
        if (rest.length) {
            moreBtn = ' <button class="conn-more"><span class="conn-arrow">▸</span> +'
                + rest.length + "</button>";
            const extraItems = rest.map(ln => {
                const lhref = buildFileHref(filePath, ln);
                const ec = PROJECT_ROOT + "/" + filePath + ":" + ln;
                return lhref
                    ? '<li><a class="conn-extra-ln" href="'
                        + esc(lhref) + '">:' + ln + "</a></li>"
                    : '<li><span class="conn-extra-ln conn-copy" data-copy="'
                        + esc(ec) + '">:' + ln + "</span></li>";
            }).join("");
            extraList = '<ul class="conn-extra" style="display:none">'
                + extraItems + "</ul>";
        }
        return "<li>" + linkEl + " "
            + '<span class="conn-type">[' + esc(c.type) + "]</span>"
            + moreBtn + extraList + "</li>";
    }

    function buildGroup(label, items, isOutgoing) {
        if (!items.length) return "";
        const counts = new Map();
        items.forEach(c =>
            counts.set(c.node.label, (counts.get(c.node.label) || 0) + 1));
        const displayLabel = c => {
            if ((counts.get(c.node.label) || 0) > 1) {
                const parts = c.node.path.split("/");
                if (parts.length >= 2)
                    return parts[parts.length - 2] + "/" + c.node.label;
            }
            return c.node.label;
        };
        const sorted = items.slice().sort(
            (a, b) => a.node.label.localeCompare(b.node.label)
                || (a.edge.lines[0] || 0) - (b.edge.lines[0] || 0));
        const rows = sorted.map(c => renderConnItem(c, isOutgoing, displayLabel));
        return '<div class="conn-group">'
            + '<div class="conn-group-hdr">' + label
            + ' <span class="conn-count">(' + items.length + ")</span></div>"
            + "<ul>" + rows.join("") + "</ul></div>";
    }

    infoConns.innerHTML =
        buildGroup(t("info.outgoing"), outgoing, true)
        + buildGroup(t("info.incoming"), incoming, false);

    infoConns.querySelectorAll(".conn-group-hdr").forEach(hdr => {
        hdr.addEventListener("click", () => {
            const ul = hdr.nextElementSibling;
            const isCollapsed = ul.style.display === "none";
            ul.style.display = isCollapsed ? "" : "none";
            hdr.classList.toggle("collapsed", !isCollapsed);
        });
    });
    applyPinDim(d);
    infoPanel.classList.remove("hidden");
    if (typeof updateUrlState === "function") updateUrlState();
}

// === CLICK HANDLERS ===
function dropAllSelections() {
    infoPanel.classList.add("hidden");
    clearPinDim();
    clearEdgeFocus();
    clearPath();
    hideEdgeTooltip();
    if (typeof updateUrlState === "function") updateUrlState();
}

// True when a node is faded out by the active pin/edge/path selection or
// by an exclusive highlight mode (dead / untracked / cycles).
function isNodeFaded(d) {
    if (isModeDimmedNode(d)) return true;
    if (pathActive()) return !pathNodeIds.has(d.id);
    if (activeNodeData && !infoPanel.classList.contains("hidden")) {
        const nb = neighborMap.get(activeNodeData.id);
        return !(nb && nb.has(d.id));
    }
    if (activeEdge) {
        return d.id !== activeEdge.source.id && d.id !== activeEdge.target.id;
    }
    return false;
}
// True when an edge is faded out by the active pin/edge/path selection or
// by an exclusive highlight mode (dead / untracked / cycles).
function isEdgeFaded(d) {
    if (isModeDimmedEdge(d)) return true;
    if (pathActive()) return !pathLinks.has(d);
    if (activeNodeData && !infoPanel.classList.contains("hidden")) {
        return d.source.id !== activeNodeData.id
            && d.target.id !== activeNodeData.id;
    }
    if (activeEdge) {
        return d !== activeEdge;
    }
    return false;
}

function onNodeClick(event, d) {
    // Shift+click — path mode: pick endpoints, draw shortest BFS path
    if (event.shiftKey) {
        if (!pathStart) {
            // First endpoint — the endpoint ring is drawn from pathStart
            clearPinDim();
            clearEdgeFocus();
            infoPanel.classList.add("hidden");
            pathStart = d;
            requestDraw();
        } else if (pathStart === d) {
            // Toggling off the start
            clearPath();
        } else {
            // Second endpoint — compute and show
            applyPath(pathStart, d);
        }
        return;
    }
    // A normal click while in path-pending mode cancels the pending start
    if (pathPending() || pathActive()) {
        clearPath();
    }
    if (isNodeFaded(d)) {
        dropAllSelections();
        return;
    }
    clearEdgeFocus();
    activeNodeData = d;
    renderInfoPanel(d);
}

// Double-click: toggle "sticky" — pin the node's position via fx/fy so the
// physics simulation stops moving it. Use a dedicated `_sticky` flag instead
// of inferring from fx/fy directly, because orphans already have fx/fy set
// permanently by the orphan-ring layout (tickRefitOrphanRing). For orphans
// the ring layout wins and a manual sticky would be lerped back over time —
// skip them.
function onNodeDblClick(d) {
    if (d.degree === 0) return;  // orphan: ring layout owns fx/fy
    if (d._sticky) {
        d._sticky = false;
        d.fx = null;
        d.fy = null;
    } else {
        d._sticky = true;
        d.fx = d.x;
        d.fy = d.y;
    }
    requestDraw();
}
document.getElementById("info-close").addEventListener("click", () => {
    infoPanel.classList.add("hidden");
    clearPinDim();
});
// Delegates to showToast so the shared #copy-toast element always gets its
// text (re)set — toggling only the class left whatever message a generic
// toast wrote there last, and the two timers raced on the same element.
function showCopyToast() {
    showToast(t("toast.copied"));
}

infoPanel.addEventListener("click", e => {
    const el = e.target.closest(".conn-copy");
    if (!el) return;
    e.stopPropagation();
    const text = el.dataset.copy || "";
    try {
        navigator.clipboard.writeText(text)
            .then(showCopyToast)
            .catch(() => prompt("Copy path:", text));
    } catch(_) { prompt("Copy path:", text); }
});

// === VISIBILITY FILTER ===
// Visibility filter: legend types + name exclusions + edge types
const hiddenTypes = new Set();
const excludedNames = new Set();
const hiddenEdgeTypes = new Set();

function baseNodeVisible(n) {
    // Ghost nodes exist only in git mode (was a CSS display rule).
    if (!gitMode && n.ghost) return false;
    if (gitMode && n.gitStatus && hiddenGitStatuses.has(n.gitStatus))
        return false;
    return !hiddenTypes.has(n.type)
        && !excludedNames.has(n.label)
        && !excludedNames.has(n.stem);
}
function isNodeVisible(n) { return baseNodeVisible(n); }

// Ghost links and rename edges exist only in git mode (was CSS too).
function linkGhostOk(l) {
    return gitMode || !(l.ghost || l.type === "rename");
}

// Recompute the `_vis` flag on every node and link; draw() and the
// hit-testing helpers consult the flags. Replaces the SVG display attrs.
function applyAllFilters() {
    if (showAll) {
        nodes.forEach(n => { n._vis = gitMode || !n.ghost; });
        links.forEach(l => { l._vis = linkGhostOk(l); });
        requestDraw();
        return;
    }
    if (orphansOnly) {
        nodes.forEach(n => {
            n._vis = n.degree === 0 && (gitMode || !n.ghost);
        });
        links.forEach(l => { l._vis = false; });
        requestDraw();
        return;
    }
    // When an edge-type filter is active, also hide nodes that no longer
    // participate in any visible edge — otherwise "isolate docstring"
    // leaves a swarm of disconnected blobs around the actual subgraph.
    const hasEdgeFilter = hiddenEdgeTypes.size > 0;
    let connectedIds = null;
    if (hasEdgeFilter) {
        connectedIds = new Set();
        links.forEach(l => {
            if (hiddenEdgeTypes.has(l.type)) return;
            if (!baseNodeVisible(l.source) || !baseNodeVisible(l.target)) return;
            connectedIds.add(l.source.id);
            connectedIds.add(l.target.id);
        });
    }
    nodes.forEach(n => {
        n._vis = baseNodeVisible(n)
            && (!hasEdgeFilter || connectedIds.has(n.id));
    });
    links.forEach(l => {
        l._vis = linkGhostOk(l)
            && !hiddenEdgeTypes.has(l.type)
            && baseNodeVisible(l.source) && baseNodeVisible(l.target);
    });
    requestDraw();
}

function deactivateShowAll() {
    showAll = false;
    document.getElementById("btn-show-all")
        .classList.remove("active");
}

// Preferences: auto-save to localStorage + manual export/import
// === PREFS ===
const PREF_KEY = "graph-prefs-v2";
let _prefLoading = false;

function savePrefs() {
    if (_prefLoading) return;
    const panelIds = [
        "controls-left", "legend", "exclude-panel",
        "info-panel", "controls", "theme-toggle", "help-panel"
    ];
    const panels = {};
    panelIds.forEach(id => {
        const el = document.getElementById(id);
        if (el && (el.style.left || el.style.width || el.style.height)) {
            // Persist desired position when set — so a clamp from a small
            // viewport doesn't permanently move the panel toward the edge.
            const left = el.dataset.desiredLeft !== undefined
                ? el.dataset.desiredLeft + "px" : el.style.left;
            const top = el.dataset.desiredTop !== undefined
                ? el.dataset.desiredTop + "px" : el.style.top;
            panels[id] = {
                left: left, top: top,
                right: el.style.right, bottom: el.style.bottom,
                transform: el.style.transform,
                width: el.style.width,
                height: el.style.height
            };
        }
    });
    const sliderIds = [
        "ctrl-contrast", "ctrl-node-scale", "ctrl-edge-width",
        "ctrl-edge-opacity", "ctrl-font-size", "ctrl-label-zoom",
        "ctrl-charge", "ctrl-link"
    ];
    const sliders = {};
    sliderIds.forEach(id => {
        const el = document.getElementById(id);
        if (el) sliders[id] = el.value;
    });
    const collapsedPanels = ["controls-left", "legend", "exclude-panel"]
        .filter(id => {
            const el = document.getElementById(id);
            return el && el.classList.contains("collapsed");
        });
    try {
        localStorage.setItem(PREF_KEY, JSON.stringify({
            sliders,
            hiddenTypes: [...hiddenTypes],
            hiddenEdgeTypes: [...hiddenEdgeTypes],
            theme: document.body.classList.contains("light"),
            palette: currentPalette,
            ide: ideScheme,
            lang: currentLang,
            gitMode,
            hiddenGitStatuses: [...hiddenGitStatuses],
            panels,
            collapsedPanels,
            showDead,
            showUntracked,
            showCycles
        }));
    } catch(e) {}
    updateUrlState();
}

// === URL STATE (shareable view via location.hash) ===
// Whitelist of shareable fields — only "view-defining" state, NOT per-user
// preferences (panel positions, sliders, IDE, collapsed panels). The hash
// is human-readable: `#theme=dark&hidden=docs,tests&pin=path/to/file`.
// On load, hash overrides equivalents from localStorage so a shared link
// preserves the recipient's panel layout but applies the sender's view.
function getShareableState() {
    return {
        lang: currentLang !== "en" ? currentLang : null,
        theme: document.body.classList.contains("light") ? "light" : null,
        palette: currentPalette === "saturated" ? "sat" : null,
        gitMode: gitMode ? "1" : null,
        showDead: showDead ? "1" : null,
        showUnmapped: showUntracked ? "1" : null,
        showCycles: showCycles ? "1" : null,
        hiddenTypes: hiddenTypes.size ? [...hiddenTypes].join(",") : null,
        hiddenEdges: hiddenEdgeTypes.size
            ? [...hiddenEdgeTypes].join(",") : null,
        hiddenGit: hiddenGitStatuses.size
            ? [...hiddenGitStatuses].join(",") : null,
        search: searchQuery || null,
        pin: (activeNodeData && !infoPanel.classList.contains("hidden"))
            ? activeNodeData.id : null,
    };
}
function encodeStateHash(state) {
    const parts = [];
    Object.entries(state).forEach(([k, v]) => {
        if (v === null || v === "" || v === undefined) return;
        parts.push(encodeURIComponent(k) + "=" + encodeURIComponent(v));
    });
    return parts.length ? "#" + parts.join("&") : "";
}
function decodeStateHash(hash) {
    const out = {};
    if (!hash || hash === "#") return out;
    const raw = hash.startsWith("#") ? hash.slice(1) : hash;
    raw.split("&").forEach(pair => {
        if (!pair) return;
        const eq = pair.indexOf("=");
        if (eq === -1) return;
        const k = decodeURIComponent(pair.slice(0, eq));
        const v = decodeURIComponent(pair.slice(eq + 1));
        out[k] = v;
    });
    return out;
}
let _suppressUrlUpdate = false;
function updateUrlState() {
    if (_suppressUrlUpdate) return;
    if (_prefLoading) return;
    const hash = encodeStateHash(getShareableState());
    // replaceState avoids spamming browser history with every toggle
    history.replaceState(null, "", location.pathname + location.search
        + (hash || "#"));
    if (!hash) {
        // Strip the trailing "#" entirely if state is empty
        history.replaceState(null, "", location.pathname + location.search);
    }
}
function applyShareableState(s) {
    if (!s || !Object.keys(s).length) return;
    _suppressUrlUpdate = true;
    try {
        if (s.lang && I18N[s.lang]) {
            applyI18n(s.lang);
            const sel = document.getElementById("select-lang");
            if (sel) sel.value = s.lang;
        }
        if (s.theme === "light") {
            document.body.classList.add("light");
            const cb = document.getElementById("theme-check");
            if (cb) cb.checked = true;
        }
        if (s.palette === "sat") {
            const chk = document.getElementById("palette-check");
            if (chk && !chk.checked) {
                chk.checked = true;
                chk.dispatchEvent(new Event("change"));
            }
        }
        if (s.hiddenTypes) {
            hiddenTypes.clear();
            s.hiddenTypes.split(",").forEach(t => hiddenTypes.add(t));
            document.querySelectorAll("[data-legend-type]").forEach(el => {
                el.classList.toggle("hidden-type",
                    hiddenTypes.has(el.getAttribute("data-legend-type")));
            });
        }
        if (s.hiddenEdges) {
            hiddenEdgeTypes.clear();
            s.hiddenEdges.split(",").forEach(t => hiddenEdgeTypes.add(t));
            document.querySelectorAll("[data-edge-type]").forEach(el => {
                el.classList.toggle("hidden-type",
                    hiddenEdgeTypes.has(el.getAttribute("data-edge-type")));
            });
        }
        if (s.hiddenGit) {
            hiddenGitStatuses.clear();
            s.hiddenGit.split(",").forEach(t => hiddenGitStatuses.add(t));
            document.querySelectorAll("[data-git-status]").forEach(el => {
                el.classList.toggle("hidden-type",
                    hiddenGitStatuses.has(el.getAttribute("data-git-status")));
            });
        }
        if (s.gitMode === "1" && GIT_DATA) applyGitMode(true);
        if (s.showDead === "1" && deadNodes.size > 0) {
            showDead = true;
            document.body.classList.add("show-dead");
            const btn = document.getElementById("btn-dead");
            if (btn) btn.classList.add("active");
        }
        if (s.showUnmapped === "1" && untrackedNodes.size > 0) {
            showUntracked = true;
            const btn = document.getElementById("btn-untracked");
            if (btn) btn.classList.add("active");
        }
        if (s.showCycles === "1" && cycleCount > 0) {
            showCycles = true;
            const btn = document.getElementById("btn-cycles");
            if (btn) btn.classList.add("active");
        }
        if (s.search) {
            const searchEl = document.getElementById("search");
            if (searchEl) {
                searchEl.value = s.search;
                applySearch(s.search.toLowerCase().trim());
            }
        }
        if (s.pin) {
            const node = nodes.find(n => n.id === s.pin);
            if (node) {
                activeNodeData = node;
                renderInfoPanel(node);
            }
        }
        applyAllFilters();
    } finally {
        _suppressUrlUpdate = false;
    }
    updateUrlState();
}

function loadPrefs() {
    let prefs;
    try {
        const raw = localStorage.getItem(PREF_KEY);
        if (!raw) return;
        prefs = JSON.parse(raw);
    } catch(e) { return; }
    _prefLoading = true;
    // Language (apply early so the rest of UI updates pick it up implicitly)
    if (prefs.lang && I18N[prefs.lang]) {
        applyI18n(prefs.lang);
    }
    // Theme
    if (prefs.theme) {
        document.getElementById("theme-check").checked = true;
        document.body.classList.add("light");
    }
    // Hidden node types
    if (prefs.hiddenTypes) {
        prefs.hiddenTypes.forEach(t => {
            hiddenTypes.add(t);
            const el = document.querySelector(
                '[data-legend-type="' + t + '"]');
            if (el) el.classList.add("hidden-type");
        });
    }
    // Hidden edge types
    if (prefs.hiddenEdgeTypes) {
        prefs.hiddenEdgeTypes.forEach(t => {
            hiddenEdgeTypes.add(t);
            const el = document.querySelector(
                '[data-edge-type="' + t + '"]');
            if (el) el.classList.add("hidden-type");
        });
    }
    // Sliders
    if (prefs.sliders) {
        Object.entries(prefs.sliders).forEach(([id, val]) => {
            const el = document.getElementById(id);
            if (el) {
                el.value = val;
                el.dispatchEvent(new Event("input"));
            }
        });
    }
    // Panel positions
    if (prefs.panels) {
        Object.entries(prefs.panels).forEach(([id, pos]) => {
            const el = document.getElementById(id);
            if (el && pos) {
                if (pos.left)  el.style.left = pos.left;
                if (pos.top)   el.style.top  = pos.top;
                // Only override the CSS anchor (right/bottom/transform) when
                // a real drag position was captured. A panel that was never
                // clamped/dragged can still pick up a saved `width` (e.g.
                // legend's syncLegendWidth) without pos.left/top ever being
                // set — blindly forcing right/bottom to "auto" here would
                // strip its CSS anchor (`right: 12px` etc.) and leave it
                // with no positioning at all.
                if (pos.left || pos.top) {
                    el.style.right     = pos.right     || "auto";
                    el.style.bottom    = pos.bottom    || "auto";
                    el.style.transform = pos.transform || "none";
                }
                if (pos.width) el.style.width = pos.width;
                if (pos.height) el.style.height = pos.height;
                // Mirror saved position into desired-* so clamp can restore
                // it if the viewport later grows.
                if (pos.left) el.dataset.desiredLeft = parseFloat(pos.left);
                if (pos.top)  el.dataset.desiredTop  = parseFloat(pos.top);
            }
        });
    }
    // Palette
    if (prefs.palette === "saturated") {
        const chk = document.getElementById("palette-check");
        if (chk) {
            chk.checked = true;
            chk.dispatchEvent(new Event("change"));
        }
    }
    // Git overlay state
    if (prefs.hiddenGitStatuses) {
        prefs.hiddenGitStatuses.forEach(s => {
            hiddenGitStatuses.add(s);
            const el = document.querySelector(
                '[data-git-status="' + s + '"]');
            if (el) el.classList.add("hidden-type");
        });
    }
    if (prefs.gitMode && GIT_DATA) {
        applyGitMode(true);
    }
    // IDE scheme
    if (prefs.ide) {
        ideScheme = prefs.ide;
        const sel = document.getElementById("ide-select");
        if (sel) sel.value = ideScheme;
    }
    // Collapsed panels
    if (Array.isArray(prefs.collapsedPanels)) {
        prefs.collapsedPanels.forEach(id => {
            const el = document.getElementById(id);
            if (el) el.classList.add("collapsed");
        });
    }
    if (prefs.showDead) {
        showDead = true;
        document.body.classList.add("show-dead");
        const btn = document.getElementById("btn-dead");
        if (btn) btn.classList.add("active");
    }
    if (prefs.showUntracked) {
        showUntracked = true;
        const btn = document.getElementById("btn-untracked");
        if (btn) btn.classList.add("active");
    }
    if (prefs.showCycles && cycleCount > 0) {
        showCycles = true;
        const btn = document.getElementById("btn-cycles");
        if (btn) btn.classList.add("active");
    }
    _prefLoading = false;
    applyAllFilters();
    // Theme may have changed (initial load or prefs import at runtime).
    refreshThemeColors();
}

// === LEGEND ===
// Lucide-style icon helper. iconPathsHtml is the inner SVG markup (paths,
// circles, etc.); the outer <svg> is shared. Returns a string ready for
// `.html()`. The data-i18n key is on the inner span — applyI18n updates
// only that, leaving the SVG and any post-i18n suffix intact.
//
// All icon constants and helpers live BEFORE the legend creation loops
// because const declarations are in TDZ until executed; the loops below
// invoke `attachIsolateBtn` which dereferences these constants.
const _SVG_OPEN = '<svg class="btn-icon-svg lucide" viewBox="0 0 24 24" '
    + 'fill="none" stroke="currentColor" stroke-width="2" '
    + 'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">';
function iconBtnHtml(iconInner, i18nKey, label, suffix) {
    return _SVG_OPEN + iconInner + '</svg>'
        + '<span data-i18n="' + i18nKey + '">' + label + '</span>'
        + (suffix || "");
}
const ICON_EYE = '<path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/>'
    + '<circle cx="12" cy="12" r="3"/>';
const ICON_EYE_OFF = '<path d="M9.88 9.88a3 3 0 1 0 4.24 4.24"/>'
    + '<path d="M10.73 5.08A10.43 10.43 0 0 1 12 5c7 0 10 7 10 7'
    + 'a13.16 13.16 0 0 1-1.67 2.68"/>'
    + '<path d="M6.61 6.61A13.526 13.526 0 0 0 2 12s3 7 10 7'
    + 'a9.74 9.74 0 0 0 5.39-1.61"/>'
    + '<line x1="2" x2="22" y1="2" y2="22"/>';
const ICON_CIRCLE_DASHED =
    '<circle cx="12" cy="12" r="9" stroke-dasharray="4 3"/>';
const ICON_SKULL = '<circle cx="9" cy="12" r="1"/>'
    + '<circle cx="15" cy="12" r="1"/>'
    + '<path d="M8 20v2h8v-2"/>'
    + '<path d="m12.5 17-.5-1-.5 1h1z"/>'
    + '<path d="M16 20a2 2 0 0 0 1.56-3.25 8 8 0 1 0-11.12 0'
    + 'A2 2 0 0 0 8 20"/>';
// Rotating arrow (lucide rotate-cw) — the import-cycles toggle.
const ICON_CYCLE =
    '<path d="M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8"/>'
    + '<path d="M21 3v5h-5"/>';
// Target / crosshair — used as "isolate this type" button in legend items.
const ICON_TARGET = '<circle cx="12" cy="12" r="10"/>'
    + '<circle cx="12" cy="12" r="6"/>'
    + '<circle cx="12" cy="12" r="2"/>';
// Circle-help (Lucide) — "unmapped" legend button.
const ICON_UNMAPPED = '<circle cx="12" cy="12" r="10"/>'
    + '<path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/>'
    + '<path d="M12 17h.01"/>';

// Attaches a small "isolate" target-icon button to a legend item. Click
// hides every type EXCEPT this one (re-click on the same one restores
// all). `getAllTypes()` returns the full set of types in this category;
// `hiddenSet` is the existing Set this section already tracks.
function attachIsolateBtn(item, currentType, getAllTypes, hiddenSet, applyAndSave) {
    const btn = item.append("button")
        .attr("class", "legend-isolate btn-icon")
        .attr("data-i18n-title", "legend.isolate")
        .attr("title", t("legend.isolate"))
        .html(_SVG_OPEN + ICON_TARGET + "</svg>");
    btn.on("click", function(event) {
        event.stopPropagation();
        const all = getAllTypes();
        const isOnlyOthersHidden = hiddenSet.size === all.length - 1
            && all.every(tt => tt === currentType || hiddenSet.has(tt));
        hiddenSet.clear();
        if (!isOnlyOthersHidden) {
            all.forEach(tt => {
                if (tt !== currentType) hiddenSet.add(tt);
            });
        }
        applyAndSave();
    });
}
// Refresh `.legend-isolate.active` and `.legend-item.hidden-type` classes
// across all three legend sections to reflect the current hidden* sets.
function refreshLegendState() {
    document.querySelectorAll(".legend-item[data-legend-type]").forEach(el => {
        const type = el.getAttribute("data-legend-type");
        el.classList.toggle("hidden-type", hiddenTypes.has(type));
        const all = Object.keys(activeColors);
        const isolated = !hiddenTypes.has(type)
            && hiddenTypes.size === all.length - 1
            && all.every(tt => tt === type || hiddenTypes.has(tt));
        const btn = el.querySelector(".legend-isolate");
        if (btn) btn.classList.toggle("active", isolated);
    });
    document.querySelectorAll(".legend-item[data-edge-type]").forEach(el => {
        const type = el.getAttribute("data-edge-type");
        el.classList.toggle("hidden-type", hiddenEdgeTypes.has(type));
        const all = ["doc->doc", "code->doc", "code->code",
                     "docstring", "type-only"];
        const isolated = !hiddenEdgeTypes.has(type)
            && hiddenEdgeTypes.size === all.length - 1
            && all.every(tt => tt === type || hiddenEdgeTypes.has(tt));
        const btn = el.querySelector(".legend-isolate");
        if (btn) btn.classList.toggle("active", isolated);
    });
    document.querySelectorAll(".legend-item[data-git-status]").forEach(el => {
        const type = el.getAttribute("data-git-status");
        el.classList.toggle("hidden-type", hiddenGitStatuses.has(type));
        const all = ["added", "modified", "renamed", "deleted", "clean"];
        const isolated = !hiddenGitStatuses.has(type)
            && hiddenGitStatuses.size === all.length - 1
            && all.every(tt => tt === type || hiddenGitStatuses.has(tt));
        const btn = el.querySelector(".legend-isolate");
        if (btn) btn.classList.toggle("active", isolated);
    });
}

// Legend: node type swatches — click to toggle visibility.
// Items live in a scroll container capped at ~10 rows — autodiscovery can
// mint 20+ categories and the panel must not swallow the screen.
const legendEl = d3.select("#legend");
const nodeTypeList = legendEl.append("div").attr("id", "legend-node-types");

Object.entries(activeColors).forEach(([type, color]) => {
    const item = nodeTypeList.append("div")
        .attr("class", "legend-item")
        .attr("data-legend-type", type);
    item.append("div")
        .attr("class", "legend-swatch")
        .style("background", color);
    item.append("span").text(type);
    attachIsolateBtn(
        item, type,
        () => Object.keys(activeColors),
        hiddenTypes,
        () => {
            refreshLegendState();
            deactivateShowAll(); applyAllFilters(); savePrefs();
        },
    );
    item.on("click", () => {
        if (hiddenTypes.has(type)) {
            hiddenTypes.delete(type);
        } else {
            hiddenTypes.add(type);
        }
        refreshLegendState();
        deactivateShowAll(); applyAllFilters(); savePrefs();
    });
});

// Legend: bulk-toggle for node types — Show all / Hide all
const legendActions = legendEl.append("div").attr("class", "legend-actions");
legendActions.append("button")
    .attr("id", "btn-legend-show-all")
    .attr("class", "btn btn--sm btn--ghost btn-icon-only")
    .attr("data-i18n-title", "legend.showAll")
    .attr("title", t("legend.showAll"))
    .html(_SVG_OPEN + ICON_EYE + "</svg>")
    .on("click", () => {
        hiddenTypes.clear();
        legendEl.selectAll("[data-legend-type]")
            .classed("hidden-type", false);
        deactivateShowAll(); applyAllFilters(); savePrefs();
    });
legendActions.append("button")
    .attr("id", "btn-legend-hide-all")
    .attr("class", "btn btn--sm btn--ghost btn-icon-only")
    .attr("data-i18n-title", "legend.hideAll")
    .attr("title", t("legend.hideAll"))
    .html(_SVG_OPEN + ICON_EYE_OFF + "</svg>")
    .on("click", () => {
        legendEl.selectAll("[data-legend-type]").each(function() {
            const type = this.getAttribute("data-legend-type");
            hiddenTypes.add(type);
            d3.select(this).classed("hidden-type", true);
        });
        deactivateShowAll(); applyAllFilters(); savePrefs();
    });

// Legend: edge type section — click to toggle edge visibility + orphans
legendEl.append("div").attr("class", "legend-sep");
legendEl.append("h4")
    .attr("data-i18n", "legend.edgeTypes")
    .text(t("legend.edgeTypes"));
[
    ["doc → doc",   null,  "doc->doc"],
    ["code → doc",  "5,3", "code->doc"],
    ["code → code", null,  "code->code"],
    ["docstring",   "1,3", "docstring"],
    ["type-only",   "3,4", "type-only"],
].forEach(([label, dash, edgeType]) => {
    const item = legendEl.append("div")
        .attr("class", "legend-item")
        .attr("data-edge-type", edgeType);
    const s = item.append("svg")
        .attr("width", 26).attr("height", 12)
        .style("flex-shrink", "0");
    const ln = s.append("svg:line")
        .attr("x1", 0).attr("y1", 6).attr("x2", 26).attr("y2", 6)
        .attr("stroke", EDGE_COLORS[edgeType] || "#999")
        .attr("stroke-width", 1.5)
        .attr("stroke-opacity", 0.8);
    if (dash) ln.attr("stroke-dasharray", dash);
    item.append("span").text(label);
    attachIsolateBtn(
        item, edgeType,
        () => ["doc->doc", "code->doc", "code->code", "docstring", "type-only"],
        hiddenEdgeTypes,
        () => {
            refreshLegendState();
            deactivateShowAll(); applyAllFilters(); savePrefs();
        },
    );
    item.on("click", () => {
        if (hiddenEdgeTypes.has(edgeType)) {
            hiddenEdgeTypes.delete(edgeType);
        } else {
            hiddenEdgeTypes.add(edgeType);
        }
        refreshLegendState();
        deactivateShowAll(); applyAllFilters(); savePrefs();
    });
});

// Orphans-only toggle — sits under the edge-types section since it's
// conceptually the inverse of "show edges" (show only nodes without any).
legendEl.append("button")
    .attr("id", "btn-orphans")
    .attr("class", "btn btn--sm btn--block btn--ghost view-btn btn-with-icon")
    .style("margin-top", "6px")
    .html(iconBtnHtml(ICON_CIRCLE_DASHED, "btn.orphans", t("btn.orphans")));

// Dead-code highlight toggle — only visible if there are any candidates.
// Count is appended OUTSIDE the data-i18n span so applyI18n doesn't strip it.
if (deadNodes.size > 0) {
    legendEl.append("button")
        .attr("id", "btn-dead")
        .attr("class", "btn btn--sm btn--block btn--ghost view-btn btn-with-icon")
        .attr("data-i18n-title", "btn.deadCodeTitle")
        .attr("title", t("btn.deadCodeTitle"))
        .style("margin-top", "4px")
        .html(iconBtnHtml(
            ICON_SKULL,
            "btn.deadCode",
            t("btn.deadCode"),
            " (" + deadNodes.size + ")"
        ));
}

// Import-cycle highlight toggle — only visible when Tarjan found any SCC
// of size > 1 over the runtime code->code edges. Count = number of cycles
// (components), not member nodes.
if (cycleCount > 0) {
    legendEl.append("button")
        .attr("id", "btn-cycles")
        .attr("class", "btn btn--sm btn--block btn--ghost view-btn btn-with-icon")
        .attr("data-i18n-title", "btn.cyclesTitle")
        .attr("title", t("btn.cyclesTitle"))
        .style("margin-top", "4px")
        .html(iconBtnHtml(
            ICON_CYCLE,
            "btn.cycles",
            t("btn.cycles"),
            " (" + cycleCount + ")"
        ));
}

// Unmapped highlight toggle — nodes not covered by an explicit graph.toml
// rule (autodiscovery fallback). Only visible when the build flagged any.
if (untrackedNodes.size > 0) {
    legendEl.append("button")
        .attr("id", "btn-untracked")
        .attr("class", "btn btn--sm btn--block btn--ghost view-btn btn-with-icon")
        .attr("data-i18n-title", "btn.untrackedTitle")
        .attr("title", t("btn.untrackedTitle"))
        .style("margin-top", "4px")
        .html(iconBtnHtml(
            ICON_UNMAPPED,
            "btn.untracked",
            t("btn.untracked"),
            " (" + untrackedNodes.size + ")"
        ));
}

function updateLegendSwatches(colors) {
    document.querySelectorAll("[data-legend-type]").forEach(el => {
        const type = el.getAttribute("data-legend-type");
        const sw = el.querySelector(".legend-swatch");
        if (!sw) return;
        const c = colors[type] || "#999";
        sw.style.background = nodeContrast > 0
            ? d3.color(c).darker(nodeContrast).formatHex() : c;
    });
}

function updateEdgeLegendSwatches() {
    document.querySelectorAll("[data-edge-type]").forEach(el => {
        const type = el.getAttribute("data-edge-type");
        const ln = el.querySelector("line");
        if (!ln) return;
        const c = EDGE_COLORS[type] || "#999";
        ln.setAttribute("stroke", nodeContrast > 0
            ? d3.color(c).darker(nodeContrast).formatHex() : c);
    });
}

document.getElementById("ide-select").addEventListener("change", function() {
    ideScheme = this.value;
    savePrefs();
    if (activeNodeData && !infoPanel.classList.contains("hidden"))
        renderInfoPanel(activeNodeData);
});

document.getElementById("select-lang").addEventListener("change", e => {
    applyI18n(e.target.value);
    savePrefs();
});

document.getElementById("palette-check").addEventListener("change", function() {
    if (this.checked) {
        currentPalette = "saturated";
        activeColors = NODE_COLORS_SATURATED;
        activeGitColors = GIT_COLORS_SATURATED;
        EDGE_COLORS = EDGE_COLORS_SATURATED;
    } else {
        currentPalette = "pastel";
        activeColors = NODE_COLORS;
        activeGitColors = GIT_COLORS_PASTEL;
        EDGE_COLORS = EDGE_COLORS_PASTEL;
    }
    updateLegendSwatches(activeColors);
    updateGitLegendSwatches();
    // applyNodeContrast clears the shade memo and queues a redraw with
    // the new active palettes; legend swatches are refreshed above.
    applyNodeContrast(nodeContrast);
    savePrefs();
});

// =============================================================================
// === GIT OVERLAY ===
// Git overlay: separate "view mode" — recolours nodes by git status,
// shows ghost (deleted/renamed-old) nodes and rename edges.
// State (GIT_COLORS / gitMode / hiddenGitStatuses / currentNodeColor) is
// declared earlier so initial node render doesn't hit a TDZ.
// =============================================================================
function setupGitButton() {
    const btn = document.getElementById("btn-git");
    if (!GIT_DATA) {
        btn.classList.add("disabled");
        // Switch tooltip key so applyI18n keeps the right text on language change.
        btn.dataset.i18nTitle = "btn.gitNotAvailable";
        btn.title = t("btn.gitNotAvailable");
        return;
    }
    btn.addEventListener("click", () => {
        if (btn.classList.contains("disabled")) return;
        applyGitMode(!gitMode);
        savePrefs();
    });
}

function applyGitMode(on) {
    if (!GIT_DATA && on) return;
    gitMode = on;
    document.body.classList.toggle("git-mode", on);
    document.getElementById("btn-git").classList.toggle("active", on);
    if (on) updateGitLegendCounts();
    applyAllFilters();
}

function buildGitLegend() {
    if (!GIT_DATA) return;
    const order = ["added", "modified", "renamed", "deleted", "clean"];
    const container = legendEl.append("div").attr("id", "legend-git");
    container.append("div").attr("class", "legend-sep");
    const gitH4 = container.append("h4")
        .attr("data-i18n", "legend.gitStatus")
        .text(t("legend.gitStatus"));
    // Drag-bind: must happen here because main makeDraggable section runs
    // before buildGitLegend, so the h4 didn't exist back then.
    if (typeof makeDraggable === "function") {
        makeDraggable(document.getElementById("legend"), gitH4.node());
    }
    order.forEach(status => {
        const item = container.append("div")
            .attr("class", "legend-item")
            .attr("data-git-status", status);
        item.append("div")
            .attr("class", "legend-swatch")
            .style("background", activeGitColors[status]);
        const label = item.append("span")
            .attr("class", "git-label")
            .attr("data-i18n", "git." + status);
        label.text(t("git." + status));
        item.append("span")
            .attr("class", "git-count")
            .style("color", "var(--muted)")
            .style("font-size", "10px");
        attachIsolateBtn(
            item, status,
            () => ["added", "modified", "renamed", "deleted", "clean"],
            hiddenGitStatuses,
            () => { refreshLegendState(); applyAllFilters(); savePrefs(); },
        );
        item.on("click", () => {
            if (hiddenGitStatuses.has(status)) {
                hiddenGitStatuses.delete(status);
            } else {
                hiddenGitStatuses.add(status);
            }
            refreshLegendState();
            applyAllFilters();
            savePrefs();
        });
    });
    // Show all / Hide all bulk toggles for git statuses
    const actions = container.append("div").attr("class", "legend-actions");
    actions.append("button")
        .attr("id", "btn-git-show-all")
        .attr("class", "btn btn--sm btn--ghost btn-icon-only")
        .attr("data-i18n-title", "legend.showAll")
        .attr("title", t("legend.showAll"))
        .html(_SVG_OPEN + ICON_EYE + "</svg>")
        .on("click", () => {
            hiddenGitStatuses.clear();
            container.selectAll("[data-git-status]")
                .classed("hidden-type", false);
            applyAllFilters(); savePrefs();
        });
    actions.append("button")
        .attr("id", "btn-git-hide-all")
        .attr("class", "btn btn--sm btn--ghost btn-icon-only")
        .attr("data-i18n-title", "legend.hideAll")
        .attr("title", t("legend.hideAll"))
        .html(_SVG_OPEN + ICON_EYE_OFF + "</svg>")
        .on("click", () => {
            container.selectAll("[data-git-status]").each(function() {
                const s = this.getAttribute("data-git-status");
                hiddenGitStatuses.add(s);
                d3.select(this).classed("hidden-type", true);
            });
            applyAllFilters(); savePrefs();
        });
}

function updateGitLegendSwatches() {
    document.querySelectorAll("[data-git-status]").forEach(el => {
        const status = el.getAttribute("data-git-status");
        const sw = el.querySelector(".legend-swatch");
        if (sw) sw.style.background = activeGitColors[status] || "#999";
    });
}

function updateGitLegendCounts() {
    if (!GIT_DATA) return;
    const counts = { added: 0, modified: 0, renamed: 0, deleted: 0, clean: 0 };
    nodes.forEach(n => {
        const s = n.gitStatus || "clean";
        if (s in counts) counts[s] += 1;
    });
    Object.entries(counts).forEach(([status, n]) => {
        const item = document.querySelector(
            '[data-git-status="' + status + '"]');
        if (!item) return;
        const c = item.querySelector(".git-count");
        if (c) c.textContent = "(" + n + ")";
    });
}

// Color contrast — darken nodes, edges and arrows uniformly. The graph
// itself picks the shading up from the memo inside draw().
function applyNodeContrast(v) {
    nodeContrast = v;
    _shadeMemo.clear();
    updateEdgeLegendSwatches();
    updateLegendSwatches(activeColors);
    if (activeNodeData && !infoPanel.classList.contains("hidden")) {
        const c = activeColors[activeNodeData.type] || "#999";
        const col = v > 0 ? d3.color(c).darker(v).formatHex() : c;
        const sp = infoTypeEl.querySelector("span");
        if (sp) sp.style.background = col;
    }
    requestDraw();
}

// === TOP-BAR HANDLERS (theme / search / exclude) ===
// Theme toggle
document.getElementById("theme-check").addEventListener("change", function() {
    document.body.classList.toggle("light", this.checked);
    refreshThemeColors();
    savePrefs();
});

// Search box: dim non-matching nodes; state persists across hover
function applySearch(q) {
    searchQuery = q;
    if (q && activeEdge) clearEdgeFocus();
    const clearBtn = document.getElementById("search-clear");
    if (!q) {
        searchMatching = new Set();
        dimNode = null;
        dimEdge = null;
        clearBtn.style.display = "none";
        if (typeof updateUrlState === "function") updateUrlState();
        requestDraw();
        return;
    }
    clearBtn.style.display = "inline";
    searchMatching = new Set(
        nodes
            .filter(n =>
                n.id.toLowerCase().includes(q) ||
                n.label.toLowerCase().includes(q) ||
                (n.path && n.path.toLowerCase().includes(q)))
            .map(n => n.id)
    );
    dimNode = n => !searchMatching.has(n.id);
    dimEdge = l =>
        !searchMatching.has(l.source.id) &&
        !searchMatching.has(l.target.id);
    if (typeof updateUrlState === "function") updateUrlState();
    requestDraw();
}
// Debounced input — recomputing the match set on every keystroke made
// typing stutter on large graphs.
let _searchDebounce = null;
document.getElementById("search").addEventListener("input", e => {
    clearTimeout(_searchDebounce);
    const v = e.target.value.toLowerCase().trim();
    _searchDebounce = setTimeout(() => applySearch(v), 150);
});
document.getElementById("search-clear").addEventListener("click", () => {
    document.getElementById("search").value = "";
    applySearch("");
});

// FAQ modal: open via "?" button, close via ✕, backdrop click, or Esc
const faqOverlay = document.getElementById("faq-overlay");
function openFaq() { faqOverlay.classList.add("visible"); }
function closeFaq() { faqOverlay.classList.remove("visible"); }
function isFaqOpen() { return faqOverlay.classList.contains("visible"); }
document.getElementById("btn-faq").addEventListener("click", openFaq);
document.getElementById("faq-close").addEventListener("click", closeFaq);
faqOverlay.addEventListener("click", e => {
    if (e.target === faqOverlay) closeFaq();
});

// Keyboard shortcuts: Esc (close FAQ / info-panel / reset search),
// Space (toggle physics), Ctrl/Cmd+K (focus search)
let physicsPaused = false;
function togglePhysics() {
    physicsPaused = !physicsPaused;
    if (physicsPaused) {
        simulation.stop();
    } else {
        simulation.alpha(0.3).restart();
    }
}
document.addEventListener("keydown", e => {
    const t = e.target;
    const inField = t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA"
        || t.isContentEditable);

    if (e.key === "Escape") {
        const fileMenu = document.getElementById("file-menu");
        if (fileMenu && !fileMenu.classList.contains("hidden")) {
            fileMenu.classList.add("hidden");
            e.preventDefault();
            return;
        }
        if (isFaqOpen()) {
            closeFaq();
            e.preventDefault();
            return;
        }
        if (!infoPanel.classList.contains("hidden")) {
            infoPanel.classList.add("hidden");
            clearPinDim();
            e.preventDefault();
            return;
        }
        if (pathStart || pathActive()) {
            clearPath();
            e.preventDefault();
            return;
        }
        if (activeEdge) {
            clearEdgeFocus();
            e.preventDefault();
            return;
        }
        const searchEl = document.getElementById("search");
        if (searchEl.value) {
            searchEl.value = "";
            applySearch("");
            searchEl.blur();
            e.preventDefault();
        }
        return;
    }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        const searchEl = document.getElementById("search");
        searchEl.focus();
        searchEl.select();
        return;
    }
    if (e.key === " " && !inField) {
        e.preventDefault();
        togglePhysics();
        return;
    }
    // B ("block") — pin/unpin the node being dragged or hovered. e.code is
    // layout-independent (works on non-Latin keyboard layouts too). Mid-drag
    // press marks the node sticky, so drag-end keeps its fx/fy in place.
    if (e.code === "KeyB" && !inField
        && !e.ctrlKey && !e.metaKey && !e.altKey) {
        const n = dragNode || hoverNode;
        if (n) {
            e.preventDefault();
            onNodeDblClick(n);
        }
        return;
    }
});

// Exclusion filter: hide nodes by label or stem
function renderExcludeList() {
    const ul = document.getElementById("exclude-list");
    ul.innerHTML = [...excludedNames]
        .map(name =>
            '<li><span class="excl-name">' + esc(name) + '</span>'
            + '<button class="excl-rm" data-name="'
            + esc(name) + '">\xd7</button></li>')
        .join("");
    ul.querySelectorAll(".excl-rm").forEach(btn => {
        btn.addEventListener("click", () => {
            excludedNames.delete(btn.dataset.name);
            renderExcludeList();
            deactivateShowAll(); applyAllFilters();
        });
    });
    document.getElementById("exclude-clear").style.display =
        excludedNames.size > 0 ? "block" : "none";
}

function addExclusion() {
    const input = document.getElementById("exclude-input");
    const val = input.value.trim();
    if (!val) return;
    const exists = nodes.some(n => n.label === val || n.stem === val);
    if (!exists) {
        input.style.borderColor = "#e74c3c";
        setTimeout(() => { input.style.borderColor = ""; }, 1200);
        return;
    }
    input.style.borderColor = "";
    excludedNames.add(val);
    input.value = "";
    renderExcludeList();
    deactivateShowAll(); applyAllFilters(); savePrefs();
}

document.getElementById("exclude-add")
    .addEventListener("click", addExclusion);
document.getElementById("exclude-input")
    .addEventListener("keydown", e => {
        if (e.key === "Enter") addExclusion();
    });
document.getElementById("exclude-clear")
    .addEventListener("click", () => {
        excludedNames.clear();
        renderExcludeList();
        deactivateShowAll(); applyAllFilters();
    });
renderExcludeList();

// Rebuild physics — freeze hidden nodes, unfreeze visible ones.
// Sticky (double-click pinned) nodes have priority over both branches:
// their fx/fy stays regardless of visibility, and the only way to free
// them is the explicit "Release pinned" button.
document.getElementById("exclude-rebuild").addEventListener("click", () => {
    nodes.forEach(d => {
        if (d._sticky) return;
        if (!isNodeVisible(d)) {
            d.fx = d.x; d.fy = d.y;
        } else {
            d.fx = null; d.fy = null;
        }
    });
    simulation.alpha(0.5).restart();
});

// Release pinned — drop all double-click sticky pins, keep everything else
// (excluded-frozen nodes stay frozen, orphan ring positions untouched).
document.getElementById("btn-release-pinned").addEventListener("click", () => {
    let released = 0;
    nodes.forEach(d => {
        if (d._sticky) {
            d._sticky = false;
            d.fx = null;
            d.fy = null;
            released++;
        }
    });
    if (released) {
        simulation.alpha(0.3).restart();
        requestDraw();
    }
});

// Draggable panels — drag by header, skip button clicks
// === DRAG (makeDraggable + bindings) ===
// Each panel has a "desired" position (set by drag or saved prefs) and a
// rendered position. clampPanelToViewport pulls a panel inside the visible
// area when the viewport shrinks, but never overrides the desired position —
// so when the viewport grows back, the panel returns to where the user put it.
function clampPanelToViewport(panel) {
    const margin = 4;
    const wasPositioned = panel.dataset.desiredLeft !== undefined || panel.style.left;
    if (!wasPositioned) {
        // Never dragged and never clamped before — it's still governed by
        // its CSS anchor (e.g. `#legend { right: 12px }`, `#controls {
        // left: 50%; transform: translateX(-50%) }`). If it already fits
        // fully on screen, leave it alone: converting it to inline
        // left/top here would freeze today's size and remove the CSS
        // anchor, so any later width change (font swap, i18n width lock,
        // syncLegendWidth) grows the box AWAY from its anchored edge
        // instead of toward it — pushing it off the opposite side with no
        // further correction. Only intervene when it genuinely overflows.
        const r = panel.getBoundingClientRect();
        if (
            r.left >= margin && r.top >= margin &&
            r.right <= window.innerWidth - margin &&
            r.bottom <= window.innerHeight - margin
        ) {
            return;
        }
    }

    const w = panel.offsetWidth, h = panel.offsetHeight;
    const maxX = Math.max(margin, window.innerWidth - w - margin);
    const maxY = Math.max(margin, window.innerHeight - h - margin);

    let targetLeft, targetTop;
    if (panel.dataset.desiredLeft !== undefined) {
        targetLeft = parseFloat(panel.dataset.desiredLeft);
        targetTop  = parseFloat(panel.dataset.desiredTop);
    } else if (panel.style.left) {
        targetLeft = parseFloat(panel.style.left);
        targetTop  = parseFloat(panel.style.top);
    } else {
        const r = panel.getBoundingClientRect();
        targetLeft = r.left;
        targetTop  = r.top;
    }

    const left = Math.min(Math.max(margin, targetLeft), maxX);
    const top  = Math.min(Math.max(margin, targetTop),  maxY);
    panel.style.left = left + "px";
    panel.style.top  = top  + "px";
    panel.style.right  = "auto";
    panel.style.bottom = "auto";
    panel.style.transform = "none";
}

function clampAllPanels() {
    [
        "controls-left", "legend", "exclude-panel", "info-panel",
        "controls", "theme-toggle", "help-panel"
    ].forEach(id => {
        const el = document.getElementById(id);
        if (el) clampPanelToViewport(el);
    });
}
window.addEventListener("resize", clampAllPanels);

function makeDraggable(panel, handle, onClick) {
    let ox = 0, oy = 0, sx = 0, sy = 0;
    handle.addEventListener("mousedown", e => {
        if (["BUTTON", "INPUT", "SELECT"].includes(e.target.tagName)) return;
        e.preventDefault();
        const r = panel.getBoundingClientRect();
        sx = e.clientX; sy = e.clientY;
        ox = r.left;    oy = r.top;
        let moved = false;
        function onMove(ev) {
            const dx = ev.clientX - sx, dy = ev.clientY - sy;
            if (!moved && Math.hypot(dx, dy) < 4) return;
            if (!moved) {
                // First significant movement — pin panel to absolute coords
                moved = true;
                panel.style.left = ox + "px";
                panel.style.top  = oy + "px";
                panel.style.right  = "auto";
                panel.style.bottom = "auto";
                panel.style.transform = "none";
            }
            const margin = 4;
            const w = panel.offsetWidth, h = panel.offsetHeight;
            const maxX = Math.max(margin, window.innerWidth - w - margin);
            const maxY = Math.max(margin, window.innerHeight - h - margin);
            const newLeft = ox + ev.clientX - sx;
            const newTop  = oy + ev.clientY - sy;
            // Remember where the user wanted the panel, even if it gets
            // clamped right now — restore on viewport growth.
            panel.dataset.desiredLeft = newLeft;
            panel.dataset.desiredTop  = newTop;
            panel.style.left = Math.min(Math.max(margin, newLeft), maxX) + "px";
            panel.style.top  = Math.min(Math.max(margin, newTop),  maxY) + "px";
        }
        function onUp() {
            document.removeEventListener("mousemove", onMove);
            document.removeEventListener("mouseup", onUp);
            if (moved) {
                savePrefs();
            } else if (onClick) {
                onClick(e);
            }
        }
        document.addEventListener("mousemove", onMove);
        document.addEventListener("mouseup", onUp);
    });
}

function togglePanelCollapsed(panelId) {
    const el = document.getElementById(panelId);
    if (!el) return;
    el.classList.toggle("collapsed");
    savePrefs();
}
makeDraggable(
    document.getElementById("controls-left"),
    document.querySelector("#controls-left h4"),
    () => togglePanelCollapsed("controls-left"));
// Drag-bind for the Node types h4. Git status h4 is bound inside
// buildGitLegend() since it's created later than this section runs.
// Click on the primary h4 toggles the entire legend; secondary h4s
// (Edge types, Git status) are drag-only.
makeDraggable(
    document.getElementById("legend"),
    document.querySelector("#legend > h4:first-of-type"),
    () => togglePanelCollapsed("legend"));
makeDraggable(
    document.getElementById("exclude-panel"),
    document.querySelector("#exclude-panel h4"),
    () => togglePanelCollapsed("exclude-panel"));
makeDraggable(
    document.getElementById("info-panel"),
    document.getElementById("info-header"));
// Also drag the top bar, theme toggle and help-panel
makeDraggable(
    document.getElementById("controls"),
    document.getElementById("controls"));
makeDraggable(
    document.getElementById("theme-toggle"),
    document.getElementById("theme-toggle"));
makeDraggable(
    document.getElementById("help-panel"),
    document.getElementById("help-panel"));
if (window.ResizeObserver) {
    const ro = new ResizeObserver(() => { if (!_prefLoading) savePrefs(); });
    ro.observe(document.getElementById("info-panel"));
    ro.observe(document.getElementById("controls-left"));
}

// View mode: Show all (reset all filters) / Orphans only
document.getElementById("btn-show-all").addEventListener("click", () => {
    // Reset all visibility filters
    hiddenTypes.clear();
    hiddenEdgeTypes.clear();
    excludedNames.clear();
    // Update legend UI
    document.querySelectorAll("[data-legend-type]").forEach(el =>
        el.classList.remove("hidden-type"));
    document.querySelectorAll("[data-edge-type]").forEach(el =>
        el.classList.remove("hidden-type"));
    renderExcludeList();
    // Deactivate orphans mode
    orphansOnly = false;
    document.getElementById("btn-orphans").classList.remove("active");
    applyAllFilters();
    savePrefs();
});
document.getElementById("btn-orphans").addEventListener("click", () => {
    showAll = false;
    document.getElementById("btn-show-all").classList.remove("active");
    orphansOnly = !orphansOnly;
    document.getElementById("btn-orphans")
        .classList.toggle("active", orphansOnly);
    applyAllFilters();
});
const btnDead = document.getElementById("btn-dead");
if (btnDead) {
    btnDead.addEventListener("click", () => {
        showDead = !showDead;
        document.body.classList.toggle("show-dead", showDead);
        btnDead.classList.toggle("active", showDead);
        savePrefs();
        requestDraw();
    });
}
const btnUntracked = document.getElementById("btn-untracked");
if (btnUntracked) {
    btnUntracked.addEventListener("click", () => {
        showUntracked = !showUntracked;
        btnUntracked.classList.toggle("active", showUntracked);
        savePrefs();
        requestDraw();
    });
}
const btnCycles = document.getElementById("btn-cycles");
if (btnCycles) {
    btnCycles.addEventListener("click", () => {
        showCycles = !showCycles;
        btnCycles.classList.toggle("active", showCycles);
        savePrefs();
        requestDraw();
    });
}

// Collapsible sections in graph controls
document.querySelectorAll(".ctrl-group-title").forEach(title => {
    const arrow = document.createElement("span");
    arrow.textContent = " ▾";
    arrow.style.cssText = "font-size:9px;opacity:0.7";
    title.appendChild(arrow);
    let collapsed = false;
    title.addEventListener("click", () => {
        collapsed = !collapsed;
        arrow.textContent = collapsed ? " ▸" : " ▾";
        let el = title.nextElementSibling;
        while (el && !el.classList.contains("ctrl-group-title")) {
            el.style.display = collapsed ? "none" : "";
            el = el.nextElementSibling;
        }
    });
});

// === TICK ===
// The canvas draws everything from node positions directly — a tick only
// needs to refit the orphan ring and queue one rAF-coalesced redraw.
simulation.on("tick", () => {
    tickRefitOrphanRing();
    requestDraw();
});

// === EDGE TOOLTIP ===
// Edge tooltip: type + source/target + line numbers
const edgeTooltip = document.getElementById("edge-tooltip");
function isEdgeVisuallyVisible(d) {
    if (d._vis === false) return false;
    if (dimEdge && dimEdge(d)) return false;
    return true;
}
function showEdgeTooltip(event, d) {
    // Suppress on dimmed (pin/search) or hidden (filter) edges
    if (!isEdgeVisuallyVisible(d)) {
        hideEdgeTooltip();
        return;
    }
    const lns = (d.lines && d.lines.length)
        ? '<div class="et-lines">' + esc(t("tooltip.lines")) + ": "
            + d.lines.join(", ") + '</div>'
        : "";
    edgeTooltip.innerHTML =
        '<div class="et-type">' + esc(d.type) + "</div>"
        + '<div class="et-files"><b>' + esc(d.source.label) + "</b>"
        + '<span class="et-arrow">→</span><b>' + esc(d.target.label) + "</b></div>"
        + lns;
    edgeTooltip.classList.remove("hidden");
    moveEdgeTooltip(event);
}
function moveEdgeTooltip(event) {
    const x = event.clientX + 14;
    const y = event.clientY + 14;
    const rect = edgeTooltip.getBoundingClientRect();
    const maxX = window.innerWidth - rect.width - 8;
    const maxY = window.innerHeight - rect.height - 8;
    edgeTooltip.style.left = Math.min(x, maxX) + "px";
    edgeTooltip.style.top  = Math.min(y, maxY) + "px";
}
function hideEdgeTooltip() {
    edgeTooltip.classList.add("hidden");
}

// Left-panel sliders
function bindSlider(id, valId, format, onChange) {
    const slider = document.getElementById(id);
    const valEl  = document.getElementById(valId);
    slider.addEventListener("input", () => {
        valEl.textContent = format(+slider.value);
        onChange(+slider.value);
        savePrefs();
    });
}
// Nodes & Edges group
bindSlider("ctrl-contrast", "val-contrast",
    v => v.toFixed(1),
    v => applyNodeContrast(v));
bindSlider("ctrl-node-scale", "val-node-scale",
    v => v.toFixed(2),
    v => {
        nodeScale = v;
        simulation.force("collide").radius(d => d.size * nodeScale + 4);
        simulation.alpha(0.1).restart();
        requestDraw();
    });
bindSlider("ctrl-edge-width", "val-edge-width",
    v => v.toFixed(2),
    v => { edgeWidth = +v; requestDraw(); });
bindSlider("ctrl-edge-opacity", "val-edge-opacity",
    v => v.toFixed(2),
    v => { edgeOpacity = +v; requestDraw(); });
// Labels group
bindSlider("ctrl-font-size", "val-font-size",
    v => v + "px",
    v => { labelFontSize = +v; requestDraw(); });
bindSlider("ctrl-label-zoom", "val-label-zoom",
    v => v.toFixed(2),
    v => { labelZoom = +v; requestDraw(); });
// Physics group
bindSlider("ctrl-charge", "val-charge",
    v => (v < 0 ? "−" : "") + Math.abs(v),
    v => { simulation.force("charge").strength(v); simulation.alpha(0.3).restart(); });
bindSlider("ctrl-link", "val-link",
    v => v.toFixed(2),
    v => { simulation.force("link").strength(v); simulation.alpha(0.3).restart(); });

