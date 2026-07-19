
// === STATE & EDGE COLORS ===
// Edge palettes mirror the node palette swap: hue stays, saturation flips.
// `code->code` uses green (well-separated from blue/orange) instead of indigo
// which was too close to the doc->doc blue.
const EDGE_COLORS_PASTEL = {
    "doc->doc":   "#a0c4ff",
    "code->doc":  "#ffd6a5",
    "code->code": "#86efac",
    "rename":     "#ce93d8",
    "docstring":  "#f8bbd0",
    "type-only":  "#b2dfdb"
};
const EDGE_COLORS_SATURATED = {
    "doc->doc":   "#2563eb",
    "code->doc":  "#f97316",
    "code->code": "#16a34a",
    "rename":     "#9b59b6",
    "docstring":  "#ec4899",
    "type-only":  "#0d9488"
};
let EDGE_COLORS = EDGE_COLORS_PASTEL;

// === WIDTH LOCKING ===
// Lock min-width on i18n elements so RU/EN switch doesn't reflow the UI.
// Measures each element with every locale's text, picks the max width.
let _i18nWidthsLocked = false;
function lockAllI18nWidths() {
    if (_i18nWidthsLocked) return;
    _i18nWidthsLocked = true;
    const measure = (el, candidates) => {
        const original = el.textContent;
        let maxW = 0;
        candidates.forEach(text => {
            el.textContent = text;
            const w = el.getBoundingClientRect().width;
            if (w > maxW) maxW = w;
        });
        el.textContent = original;
        el.style.minWidth = Math.ceil(maxW) + "px";
    };
    // Static data-i18n elements (skip FAQ modal — its width is fixed;
    // skip #controls-left because it's a resizable panel and a baked-in
    // min-width from the longest locale (DE/IT) would lock its content
    // way wider than English/RU need, fighting the user's resize).
    document.querySelectorAll("[data-i18n]").forEach(el => {
        if (el.closest("#faq-overlay")) return;
        if (el.closest("#controls-left")) return;
        if (getComputedStyle(el).display === "inline") return;
        const key = el.dataset.i18n;
        const candidates = Object.keys(I18N).map(lang =>
            (I18N[lang] && I18N[lang][key]) || I18N.en[key] || key);
        measure(el, candidates);
    });
    // Stats — formatter output for each locale at current node/edge counts
    const statsEl = document.getElementById("stats");
    if (statsEl && typeof nodes !== "undefined" && typeof links !== "undefined") {
        const candidates = Object.keys(FORMATTERS).map(lang =>
            FORMATTERS[lang].stats(nodes.length, links.length));
        measure(statsEl, candidates);
    }
    // Node-types Show/Hide pair — equalize widths
    const sa = document.getElementById("btn-legend-show-all");
    const ha = document.getElementById("btn-legend-hide-all");
    if (sa && ha) {
        const w = Math.max(
            parseFloat(sa.style.minWidth) || sa.getBoundingClientRect().width,
            parseFloat(ha.style.minWidth) || ha.getBoundingClientRect().width);
        sa.style.minWidth = Math.ceil(w) + "px";
        ha.style.minWidth = Math.ceil(w) + "px";
        // Git-legend Show/Hide pair lives inside a hidden section until git
        // mode is on, so its boundingRect reads as 0 here. Mirror the widths
        // from the node-types pair (same i18n keys, same content widths).
        const gsa = document.getElementById("btn-git-show-all");
        const gha = document.getElementById("btn-git-hide-all");
        if (gsa && gha) {
            gsa.style.minWidth = sa.style.minWidth;
            gha.style.minWidth = ha.style.minWidth;
        }
    }
}

// === PALETTE & GLOBAL STATE ===
let activeColors = NODE_COLORS;
let currentPalette = "pastel";

const nodes = GRAPH_DATA.nodes;
const links = GRAPH_DATA.links;

const canvas = document.getElementById("graph");
const ctx = canvas.getContext("2d");
const canvasSel = d3.select(canvas);
let width = window.innerWidth;
let height = window.innerHeight;
// Current pan/zoom — applied as a canvas transform inside draw().
let transform = d3.zoomIdentity;

function resizeCanvas() {
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
}
resizeCanvas();

const zoom = d3.zoom()
    .scaleExtent([0.1, 8])
    .filter(event => {
        // Default zoom guards (primary button, no ctrl+drag), plus: a
        // mousedown / dblclick that lands on a node belongs to node drag /
        // sticky toggle — not to pan / dblclick-zoom.
        if (event.type === "wheel") return !event.button;
        if (event.ctrlKey || event.button) return false;
        if ((event.type === "mousedown" || event.type === "dblclick")
            && pickNodeAtEvent(event)) return false;
        return true;
    })
    .on("zoom", (event) => {
        transform = event.transform;
        requestDraw();
    });

// Fine-grained wheel zoom — direct transform for performance
function bindCanvasZoom() {
    canvasSel.call(zoom);
    canvasSel.on("wheel.zoom", function(event) {
        event.preventDefault();
        const delta = event.deltaY *
            (event.deltaMode === 1 ? 20 : event.deltaMode === 2 ? 400 : 1);
        const factor = Math.pow(2, -delta / 800);
        const t = d3.zoomTransform(this);
        const [mx, my] = d3.pointer(event);
        const newK = Math.max(0.1, Math.min(8, t.k * factor));
        const tx = mx - (newK / t.k) * (mx - t.x);
        const ty = my - (newK / t.k) * (my - t.y);
        canvasSel.call(zoom.transform,
            d3.zoomIdentity.translate(tx, ty).scale(newK));
    }, { passive: false });
}

d3.select("#reset-zoom").on("click", () =>
    canvasSel.transition().duration(500)
       .call(zoom.transform, d3.zoomIdentity)
);

// Build before simulation mutates l.source/l.target to node objects
// === NEIGHBOR MAP & SIMULATION ===
const neighborMap = new Map();
nodes.forEach(n => neighborMap.set(n.id, new Set([n.id])));
links.forEach(l => {
    neighborMap.get(l.source)?.add(l.target);
    neighborMap.get(l.target)?.add(l.source);
});

// Dead-code candidates: code-typed nodes with zero incoming code->code edges
// (no one imports them) AND zero adjacent code->doc edges (not mentioned in
// any doc). Computed once at init from the still-string-id'd link refs.
// `deadNodes` is declared here (not later with the rest of the selection
// state) because this computation must run before D3 mutates link.source /
// link.target into node objects, and we need the binding visible already.
const deadNodes = new Set();
{
    const importedTargets = new Set();
    const docTouched = new Set();
    links.forEach(l => {
        if (l.type === "code->code") importedTargets.add(l.target);
        else if (l.type === "code->doc") {
            docTouched.add(l.source);
            docTouched.add(l.target);
        }
    });
    nodes.forEach(n => {
        // deadExempt: build-time flag for files that legitimately have no
        // incoming imports (__init__.py, conftest.py, entry points, tests,
        // migrations; extendable via [dead_code].exempt in graph.toml).
        // Only .py participates: "nothing imports it" is an import-graph
        // concept — templates, static JS/CSS and fixtures can't be imported,
        // so the heuristic would flag all of them.
        if (n.type && n.type.startsWith("code/")
            && n.path.endsWith(".py")
            && !n.deadExempt
            && !importedTargets.has(n.id)
            && !docTouched.has(n.id)) {
            deadNodes.add(n.id);
        }
    });
}

// Unmapped nodes: classified by autodiscovery fallback while a graph.toml
// exists — "not covered by an explicit rule". Build-time flag.
const untrackedNodes = new Set();
nodes.forEach(n => {
    if (n.untracked && !n.ghost) untrackedNodes.add(n.id);
});

// Import cycles: strongly connected components (size > 1) over runtime
// code->code edges only — type-only (TYPE_CHECKING) imports exist precisely
// to break cycles, so they don't participate. Computed once at init from
// the still-string-id'd link refs (same constraint as deadNodes above).
// Tarjan, iterative — the recursive form can blow the call stack on big
// graphs. O(V+E), so effectively free.
const cycleNodes = new Set();
const cycleLinks = new Set();
let cycleCount = 0;
{
    const adj = new Map();
    links.forEach(l => {
        if (l.type !== "code->code") return;
        if (!adj.has(l.source)) adj.set(l.source, []);
        adj.get(l.source).push(l.target);
    });
    const index = new Map();
    const low = new Map();
    const onStack = new Set();
    const sccOf = new Map();
    const stack = [];
    let counter = 0;
    for (const start of adj.keys()) {
        if (index.has(start)) continue;
        const work = [[start, 0]];  // [node id, next-neighbour position]
        while (work.length) {
            const frame = work[work.length - 1];
            const v = frame[0];
            if (frame[1] === 0) {
                index.set(v, counter);
                low.set(v, counter);
                counter++;
                stack.push(v);
                onStack.add(v);
            }
            const nbrs = adj.get(v) || [];
            let descended = false;
            while (frame[1] < nbrs.length) {
                const w = nbrs[frame[1]++];
                if (!index.has(w)) {
                    work.push([w, 0]);
                    descended = true;
                    break;
                } else if (onStack.has(w)) {
                    low.set(v, Math.min(low.get(v), index.get(w)));
                }
            }
            if (descended) continue;
            if (low.get(v) === index.get(v)) {
                const comp = [];
                let w;
                do {
                    w = stack.pop();
                    onStack.delete(w);
                    comp.push(w);
                } while (w !== v);
                if (comp.length > 1) {
                    cycleCount++;
                    comp.forEach(id => {
                        cycleNodes.add(id);
                        sccOf.set(id, cycleCount);
                    });
                }
            }
            work.pop();
            if (work.length) {
                const parent = work[work.length - 1][0];
                low.set(parent, Math.min(low.get(parent), low.get(v)));
            }
        }
    }
    links.forEach(l => {
        if (l.type === "code->code"
            && sccOf.has(l.source)
            && sccOf.get(l.source) === sccOf.get(l.target)) {
            cycleLinks.add(l);
        }
    });
}

const simulation = d3.forceSimulation(nodes)
    .force("link", d3.forceLink(links).id(d => d.id)
        .distance(d => d.type === "code->doc" ? 120 : 80)
        .strength(0.3))
    .force("charge",
        d3.forceManyBody().strength(-300).distanceMax(400))
    .force("center",
        d3.forceCenter(width / 2, height / 2))
    // iterations(2): with 800+ nodes the dense clusters oscillate when a
    // single collide pass fights the link force in antiphase every tick —
    // visible as node "vibration" at full canvas frame rate (the old SVG
    // renderer masked it by lagging). A second pass damps the tug-of-war.
    .force("collide",
        d3.forceCollide().radius(d => d.size + 4).iterations(2))
    .force("x", d3.forceX(width / 2).strength(0.05))
    .force("y", d3.forceY(height / 2).strength(0.05))
    // High velocityDecay kills idle jitter. Higher alphaMin means the
    // simulation stops earlier — no perpetual micro-vibration once the
    // graph has settled. Re-tuned for the 800+ node graph (0.7/0.01 was
    // calibrated at ~200 nodes and lets dense clusters buzz): more
    // friction per tick + an earlier sleep threshold.
    .alphaDecay(0.012)
    .velocityDecay(0.8)
    .alphaMin(0.02);

// Orphans (degree === 0) — pinned via fx/fy on a ring that's recomputed
// every tick to track the live cluster's actual size and centre.
// Each orphan keeps its `_ringAngle`; tickRefitOrphanRing() picks up cluster
// bounds and damped-lerps fx/fy toward the slot on the current ring.
(function assignOrphanAngles() {
    const orphans = nodes.filter(n => n.degree === 0);
    if (!orphans.length) return;
    const ringR = Math.min(width, height) * 0.42;
    const cx = width / 2, cy = height / 2;
    orphans.forEach((n, i) => {
        const angle = (i / orphans.length) * 2 * Math.PI - Math.PI / 2;
        n._ringAngle = angle;
        // Initial positions so the first tick has something sensible
        n.fx = cx + ringR * Math.cos(angle);
        n.fy = cy + ringR * Math.sin(angle);
    });
})();

// Window resize: re-centre forces and bump alpha so the cluster (and
// orphan ring) re-fits the new viewport.
window.addEventListener("resize", () => {
    width = window.innerWidth;
    height = window.innerHeight;
    resizeCanvas();
    simulation
        .force("center", d3.forceCenter(width / 2, height / 2))
        .force("x", d3.forceX(width / 2).strength(0.05))
        .force("y", d3.forceY(height / 2).strength(0.05))
        .alpha(0.3).restart();
    requestDraw();
});

function tickRefitOrphanRing() {
    let live = 0;
    let cx = 0, cy = 0;
    nodes.forEach(n => {
        if (n.degree > 0 && Number.isFinite(n.x)) {
            cx += n.x; cy += n.y; live += 1;
        }
    });
    if (live === 0) return;
    cx /= live; cy /= live;
    let maxR = 0;
    nodes.forEach(n => {
        if (n.degree > 0 && Number.isFinite(n.x)) {
            const dx = n.x - cx, dy = n.y - cy;
            const r = Math.hypot(dx, dy) + (n.size || 0);
            if (r > maxR) maxR = r;
        }
    });
    const minR = Math.min(width, height) * 0.22;
    const ringR = Math.max(maxR + 50, minR);
    // Lower damping → orphans glide instead of snapping (matches the slower
    // simulation); after drag-end the return takes ~0.5–1s.
    const damp = 0.08;
    nodes.forEach(n => {
        if (n.degree !== 0 || n._ringAngle === undefined || n._dragging) return;
        const tx = cx + ringR * Math.cos(n._ringAngle);
        const ty = cy + ringR * Math.sin(n._ringAngle);
        const fx = n.fx ?? tx, fy = n.fy ?? ty;
        n.fx = fx + (tx - fx) * damp;
        n.fy = fy + (ty - fy) * damp;
    });
}

// === RENDER STATE & CANVAS ENGINE ===
let isDragging = false;
let nodeScale = 1.0;
let labelZoom = 1.74;
let labelFontSize = 10;
let nodeContrast = 0;
let edgeOpacity = 0.28;
let edgeWidth = 0.75;
let activeNodeData = null;
let activeEdge = null;
// Path mode (shift+click two nodes to highlight the shortest path between
// them in the undirected adjacency graph).
let pathStart = null;
let pathEnd = null;
let pathNodeIds = new Set();
let pathLinks = new Set();
// Dead-code highlight toggle (draw() renders the red ring + glow; the
// body class only drives the legend button state).
// `deadNodes` itself is declared earlier — see the dead-code computation
// block right after neighborMap.
let showDead = false;
// "Unmapped" highlight toggle — nodes classified by autodiscovery fallback
// (no explicit graph.toml rule covers them). Set is filled at build time
// via the node.untracked flag.
let showUntracked = false;
// Import-cycle highlight toggle — cycleNodes/cycleLinks are computed at
// init right after the dead-code block.
let showCycles = false;
// Git overlay state — declared before currentNodeColor() so draw() doesn't
// hit the TDZ for these `let` bindings.
const GIT_COLORS_PASTEL = {
    added:    "#a5d6a7",
    modified: "#ffd180",
    renamed:  "#ce93d8",
    deleted:  "#ef9a9a",
    clean:    "#bbb"
};
const GIT_COLORS_SATURATED = {
    added:    "#00b86b",
    modified: "#f5a524",
    renamed:  "#9b59b6",
    deleted:  "#e74c3c",
    clean:    "#888"
};
let activeGitColors = GIT_COLORS_PASTEL;
let gitMode = false;
const hiddenGitStatuses = new Set();
function currentNodeColor(d) {
    if (gitMode && d.gitStatus) return activeGitColors[d.gitStatus] || "#999";
    return activeColors[d.type] || "#999";
}
let searchQuery = "";
let searchMatching = new Set();
let showAll = false;
let orphansOnly = false;
let ideScheme = "vscode";

// Visual overlay predicates — the canvas replacement for the CSS classes
// that used to be toggled on SVG elements ("dimmed", stroke-opacity: 1).
// Every selection mode (hover / pin / peek / edge focus / path / search)
// installs its own predicates; draw() consults them per element.
let dimNode = null;   // (n) => true when the node is faded out
let dimEdge = null;   // (l) => true when the edge is faded out
let hotEdge = null;   // (l) => true when the edge is highlighted (alpha 1)
let hoverNode = null; // node under cursor — gets the brightness bump
let dragNode = null;  // node currently being dragged — target for the B hotkey

// Theme-dependent colors read from CSS variables. Cached — calling
// getComputedStyle per frame would force a style recalc on every tick.
let themeFg = "#eee";
let themeNodeText = "#ccc";
function refreshThemeColors() {
    const cs = getComputedStyle(document.body);
    themeFg = (cs.getPropertyValue("--fg") || "").trim() || "#eee";
    themeNodeText = (cs.getPropertyValue("--node-text") || "").trim() || "#ccc";
    requestDraw();
}

// Contrast-shaded color memo: base hex → [fill, stroke]. Cleared when the
// contrast slider changes (palette switches change the base strings, so
// stale entries are unreachable anyway). Avoids d3.color().darker() per
// node per frame.
const _shadeMemo = new Map();
function shadedPair(base) {
    let pair = _shadeMemo.get(base);
    if (!pair) {
        const fill = nodeContrast > 0
            ? d3.color(base).darker(nodeContrast).formatHex() : base;
        const stroke = d3.color(fill).darker(0.6).formatHex();
        pair = [fill, stroke];
        _shadeMemo.set(base, pair);
    }
    return pair;
}

// Render-side smoothing factor: drawn positions chase the physics
// positions through an exponential lerp (per frame). In dense clusters
// the collide and link forces flip direction almost every tick, so raw
// positions buzz at frame rate — the smoothed ones glide. 1 = no
// smoothing; lower = calmer but laggier. 0.18 ≈ 10x attenuation of
// per-tick oscillation, time constant ~5 frames — floaty but calm.
const RENDER_SMOOTH = 0.18;

// Dash patterns per edge type — mirrors the old CSS .link.* rules.
const EDGE_DASH = {
    "code->doc": [5, 3],
    "docstring": [1, 3],
    "type-only": [3, 4],
    "rename":    [2, 3]
};

// === DRAW LOOP ===
// All graph rendering happens in one rAF-coalesced pass over the canvas.
// State changes never touch the DOM — they update predicates/flags and
// call requestDraw(). When the simulation is asleep and nothing changes,
// nothing is drawn at all.
let _drawQueued = false;
function requestDraw() {
    if (_drawQueued) return;
    _drawQueued = true;
    requestAnimationFrame(() => { _drawQueued = false; draw(); });
}

// Forced labels: path nodes and edge-focus endpoints keep their label
// visible regardless of zoom level (old CSS class "label-forced").
function isLabelForced(n) {
    if (pathActive() && pathNodeIds.has(n.id)) return true;
    if (activeEdge && (n.id === activeEdge.source.id
        || n.id === activeEdge.target.id)) return true;
    return false;
}

function draw() {
    const dpr = window.devicePixelRatio || 1;
    const k = transform.k;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);
    ctx.translate(transform.x, transform.y);
    ctx.scale(k, k);

    // World-space viewport (with margin) for culling.
    const pad = 50;
    const vx0 = -transform.x / k - pad, vy0 = -transform.y / k - pad;
    const vx1 = (width - transform.x) / k + pad;
    const vy1 = (height - transform.y) / k + pad;

    // Arrowheads: 0 at reset (k=1), max 0.45 at k≈1.74 (~4 scrolls).
    // Labels: fade in from k≈labelZoom over ~0.27 of zoom.
    const labelFade = Math.max(0, Math.min(1, (k - labelZoom) / 0.27));
    const arrowFade = Math.max(0, Math.min(0.45, (k - 1) / 0.74 * 0.45));
    const pinned = _pinActive() ? activeNodeData : null;

    // --- render-side smoothing: update drawn coordinates (_rx/_ry).
    // Dragged nodes snap 1:1 so the cursor never lags behind. ---
    let settling = false;
    for (const n of nodes) {
        if (n._rx === undefined || n._dragging) {
            n._rx = n.x; n._ry = n.y;
            continue;
        }
        const sdx = n.x - n._rx, sdy = n.y - n._ry;
        if (Math.abs(sdx) + Math.abs(sdy) < 0.05) {
            n._rx = n.x; n._ry = n.y;
            continue;
        }
        n._rx += sdx * RENDER_SMOOTH;
        n._ry += sdy * RENDER_SMOOTH;
        settling = true;
    }
    // Keep animating until the drawn positions converge on the physics
    // ones (the simulation may already have gone to sleep).
    if (settling) requestDraw();

    // --- edges: batched by resolved style (color / alpha / width / dash),
    // one beginPath+stroke per bucket instead of one per edge ---
    const buckets = new Map();
    const arrows = [];
    for (const l of links) {
        if (l._vis === false) continue;
        const sx = l.source._rx, sy = l.source._ry;
        const txx = l.target._rx, tyy = l.target._ry;
        if ((sx < vx0 && txx < vx0) || (sx > vx1 && txx > vx1)
            || (sy < vy0 && tyy < vy0) || (sy > vy1 && tyy > vy1)) continue;
        const dx = txx - sx, dy = tyy - sy;
        const dist = Math.sqrt(dx * dx + dy * dy) || 1;
        const srcR = l.source.size * nodeScale;
        const tgtR = l.target.size * nodeScale;
        const x1 = dist > srcR ? sx + dx * (srcR / dist) : sx;
        const y1 = dist > srcR ? sy + dy * (srcR / dist) : sy;
        const x2 = dist > tgtR + 2 ? txx - dx * ((tgtR + 2) / dist) : sx;
        const y2 = dist > tgtR + 2 ? tyy - dy * ((tgtR + 2) / dist) : sy;

        const isPath = pathLinks.has(l);
        let color, strokeAlpha, w, dash;
        // Element opacity channel (old CSS `opacity` on .link): dimmed
        // and dead-mode multiply; stroke-opacity channel sits on top.
        let elemAlpha = 1;
        const isCycleEdge = cycleLinks.has(l);
        if (dimEdge && dimEdge(l)) elemAlpha *= 0.1;
        if (showDead && !isPath) elemAlpha *= 0.1;
        if (showUntracked && !isPath) elemAlpha *= 0.1;
        if (showCycles && !isPath && !isCycleEdge) elemAlpha *= 0.1;
        if (isPath) {
            color = "#a855f7"; strokeAlpha = 0.9; w = 3; dash = null;
        } else if (showCycles && isCycleEdge) {
            // Cycle mode highlights the loop edges instead of dimming them.
            color = "#fb7185"; strokeAlpha = 0.9;
            w = Math.max(edgeWidth * 2, 1.6); dash = null;
        } else {
            color = shadedPair(EDGE_COLORS[l.type] || "#999")[0];
            w = edgeWidth;
            dash = EDGE_DASH[l.type] || null;
            strokeAlpha = (hotEdge && hotEdge(l)) ? 1.0
                : (l.type === "rename" ? 0.6 : edgeOpacity);
        }
        const alpha = elemAlpha * strokeAlpha;
        if (alpha < 0.004) continue;

        const key = color + "|" + alpha.toFixed(3) + "|" + w + "|"
            + (dash ? dash.join(",") : "");
        let b = buckets.get(key);
        if (!b) {
            b = { color, alpha, width: w, dash, pts: [] };
            buckets.set(key, b);
        }
        b.pts.push(x1, y1, x2, y2);

        if (arrowFade > 0 && l.type !== "rename") {
            const aAlpha = arrowFade * elemAlpha;
            if (aAlpha > 0.01) {
                arrows.push({
                    x: x2, y: y2, ux: dx / dist, uy: dy / dist,
                    color, alpha: aAlpha
                });
            }
        }
    }
    ctx.lineCap = "butt";
    for (const b of buckets.values()) {
        ctx.globalAlpha = b.alpha;
        ctx.strokeStyle = b.color;
        ctx.lineWidth = b.width;
        ctx.setLineDash(b.dash || []);
        ctx.beginPath();
        const p = b.pts;
        for (let i = 0; i < p.length; i += 4) {
            ctx.moveTo(p[i], p[i + 1]);
            ctx.lineTo(p[i + 2], p[i + 3]);
        }
        ctx.stroke();
    }
    ctx.setLineDash([]);

    // --- arrowheads: open chevron at the trimmed target end ---
    if (arrows.length) {
        ctx.lineWidth = 1;
        ctx.lineJoin = "round";
        for (const a of arrows) {
            ctx.globalAlpha = a.alpha;
            ctx.strokeStyle = a.color;
            const bx = a.x - a.ux * 4, by = a.y - a.uy * 4;
            const px = -a.uy * 1.5, py = a.ux * 1.5;
            ctx.beginPath();
            ctx.moveTo(bx + px, by + py);
            ctx.lineTo(a.x, a.y);
            ctx.lineTo(bx - px, by - py);
            ctx.stroke();
        }
    }

    // --- nodes ---
    for (const n of nodes) {
        if (n._vis === false) continue;
        const r = n.size * nodeScale;
        if (n._rx < vx0 - r || n._rx > vx1 + r
            || n._ry < vy0 - r || n._ry > vy1 + r) continue;
        const isDead = deadNodes.has(n.id);
        const isUntracked = untrackedNodes.has(n.id);
        const isCycle = cycleNodes.has(n.id);
        const isEndpoint = n === pathStart || n === pathEnd;
        const isPinned = pinned !== null && n.id === pinned.id;
        let circleAlpha = (dimNode && dimNode(n)) ? 0.2 : 1;
        if (showDead && !isDead && !isPinned && !isEndpoint) {
            circleAlpha = Math.min(circleAlpha, 0.22);
        }
        if (showUntracked && !isUntracked && !isPinned && !isEndpoint) {
            circleAlpha = Math.min(circleAlpha, 0.22);
        }
        if (showCycles && !isCycle && !isPinned && !isEndpoint) {
            circleAlpha = Math.min(circleAlpha, 0.22);
        }
        if (circleAlpha < 0.004) continue;
        const pair = shadedPair(currentNodeColor(n));
        let fill = pair[0];
        if (n === hoverNode) {
            fill = d3.color(fill).brighter(0.4).formatHex();
        }
        // Ring override priority mirrors the old CSS specificity:
        // dead (in dead-mode) > path endpoint > pinned > sticky > base.
        let ringColor = pair[1], ringWidth = 1.5;
        let ringDash = n.ghost ? [3, 2] : null;
        if (showDead && isDead) {
            ringColor = "#ef4444"; ringWidth = 3; ringDash = null;
        } else if (showUntracked && isUntracked) {
            ringColor = "#f59e0b"; ringWidth = 3; ringDash = [4, 3];
        } else if (showCycles && isCycle) {
            ringColor = "#fb7185"; ringWidth = 3; ringDash = null;
        } else if (isEndpoint) {
            ringColor = "#a855f7"; ringWidth = 3; ringDash = null;
        } else if (isPinned) {
            ringColor = themeFg; ringWidth = 2.5;
            if (n._sticky) ringDash = [3, 2];
        } else if (n._sticky) {
            ringColor = themeFg; ringWidth = 2; ringDash = [3, 2];
        }
        ctx.globalAlpha = circleAlpha;
        ctx.beginPath();
        ctx.arc(n._rx, n._ry, r, 0, 2 * Math.PI);
        ctx.fillStyle = fill;
        if (showDead && isDead) {
            // Soft red glow (old CSS drop-shadow). Shadow params live in
            // device space — scale by zoom and DPR manually.
            ctx.shadowColor = "rgba(239, 68, 68, 0.7)";
            ctx.shadowBlur = 3 * k * dpr;
            ctx.fill();
            ctx.shadowBlur = 0;
        } else {
            ctx.fill();
        }
        ctx.strokeStyle = ringColor;
        ctx.lineWidth = ringWidth;
        ctx.setLineDash(ringDash || []);
        ctx.stroke();
    }
    ctx.setLineDash([]);

    // --- labels ---
    if (labelFade > 0 || pathActive() || activeEdge) {
        ctx.textAlign = "left";
        ctx.textBaseline = "middle";
        ctx.font = labelFontSize
            + "px 'Comic Relief', system-ui, sans-serif";
        ctx.fillStyle = themeNodeText;
        for (const n of nodes) {
            if (n._vis === false) continue;
            if (n._rx < vx0 || n._rx > vx1
                || n._ry < vy0 || n._ry > vy1) continue;
            let a;
            if (isLabelForced(n)) {
                a = 1;
            } else {
                a = labelFade;
                if (dimNode && dimNode(n)) a = 0;
                else if (showDead && !deadNodes.has(n.id)
                    && !(pinned !== null && n.id === pinned.id)
                    && n !== pathStart && n !== pathEnd) {
                    a = Math.min(a, 0.10);
                }
                else if (showUntracked && !untrackedNodes.has(n.id)
                    && !(pinned !== null && n.id === pinned.id)
                    && n !== pathStart && n !== pathEnd) {
                    a = Math.min(a, 0.10);
                }
                else if (showCycles && !cycleNodes.has(n.id)
                    && !(pinned !== null && n.id === pinned.id)
                    && n !== pathStart && n !== pathEnd) {
                    a = Math.min(a, 0.10);
                }
            }
            if (a > 0.01) {
                ctx.globalAlpha = a;
                ctx.fillText(n.label,
                    n._rx + n.size * nodeScale + 3, n._ry);
            }
        }
    }

    // --- sticky markers: pin emoji whose needle tip sits at the node
    // center; offsets tuned for Segoe UI Emoji / Twemoji proportions ---
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.globalAlpha = 1;
    for (const n of nodes) {
        if (!n._sticky || n._vis === false) continue;
        const fs = Math.max(12, n.size * 1.6);
        ctx.font = fs + "px 'Segoe UI Emoji', sans-serif";
        ctx.fillText("📌", n._rx + fs * 0.38, n._ry - fs * 0.42);
    }
    ctx.globalAlpha = 1;
}

// === HIT TESTING ===
// Exclusive highlight modes (dead / untracked / cycles) dim everything
// outside their target set. Dimmed elements must not react to the pointer
// (no hover focus, no tooltip, no pointer cursor, no click-pin) — otherwise
// sweeping the mouse across the graph lights up faded nodes on the way.
function isModeDimmedNode(n) {
    return (showDead && !deadNodes.has(n.id))
        || (showUntracked && !untrackedNodes.has(n.id))
        || (showCycles && !cycleNodes.has(n.id));
}
function isModeDimmedEdge(l) {
    // Dead / untracked modes dim every edge; cycles keeps loop edges hot.
    return showDead || showUntracked
        || (showCycles && !cycleLinks.has(l));
}

function pickNode(wx, wy) {
    const grace = 2 / transform.k;
    let best = null, bestD2 = Infinity;
    // Iterate in reverse so the top-most drawn node wins ties.
    for (let i = nodes.length - 1; i >= 0; i--) {
        const n = nodes[i];
        if (n._vis === false) continue;
        const r = n.size * nodeScale + grace;
        // Test against the DRAWN (smoothed) position — that's what the
        // user is aiming at; falls back to physics coords pre-first-draw.
        const dx = wx - (n._rx ?? n.x), dy = wy - (n._ry ?? n.y);
        const d2 = dx * dx + dy * dy;
        if (d2 <= r * r && d2 < bestD2) { best = n; bestD2 = d2; }
    }
    return best;
}

function pickEdge(wx, wy) {
    // 5 world units each side — matches the old invisible 10-wide
    // hit-area strokes (they scaled with zoom too).
    const tol = 5;
    let best = null, bestD = Infinity;
    for (const l of links) {
        if (l._vis === false) continue;
        const x1 = l.source._rx ?? l.source.x, y1 = l.source._ry ?? l.source.y;
        const x2 = l.target._rx ?? l.target.x, y2 = l.target._ry ?? l.target.y;
        if (wx < Math.min(x1, x2) - tol || wx > Math.max(x1, x2) + tol
            || wy < Math.min(y1, y2) - tol || wy > Math.max(y1, y2) + tol)
            continue;
        const ddx = x2 - x1, ddy = y2 - y1;
        const len2 = ddx * ddx + ddy * ddy || 1;
        let t = ((wx - x1) * ddx + (wy - y1) * ddy) / len2;
        t = Math.max(0, Math.min(1, t));
        const px = x1 + t * ddx, py = y1 + t * ddy;
        const d = Math.hypot(wx - px, wy - py);
        if (d <= tol && d < bestD) { best = l; bestD = d; }
    }
    return best;
}

function pickNodeAtEvent(event) {
    const [px, py] = d3.pointer(event, canvas);
    const [wx, wy] = transform.invert([px, py]);
    return pickNode(wx, wy);
}

// === DRAG (nodes) ===
const drag = d3.drag()
    .container(canvas)
    .subject(event => pickNodeAtEvent(event.sourceEvent || event))
    .on("start", (event) => {
        const d = event.subject;
        isDragging = true;
        dragNode = d;
        d._dragging = true;
        // Drop any hover dim while dragging (old behavior).
        dimNode = null; dimEdge = null; hotEdge = null;
        const [wx, wy] = transform.invert(
            d3.pointer(event.sourceEvent, canvas));
        // Keep the grab offset so the node doesn't snap to the cursor.
        d._grabDx = d.x - wx;
        d._grabDy = d.y - wy;
        if (!event.active) simulation.alphaTarget(0.3).restart();
        d.fx = d.x; d.fy = d.y;
        requestDraw();
    })
    .on("drag", (event) => {
        const d = event.subject;
        const [wx, wy] = transform.invert(
            d3.pointer(event.sourceEvent, canvas));
        d.fx = wx + d._grabDx;
        d.fy = wy + d._grabDy;
    })
    .on("end", (event) => {
        const d = event.subject;
        isDragging = false;
        dragNode = null;
        d._dragging = false;
        if (activeNodeData && !infoPanel.classList.contains("hidden")) {
            applyPinDim(activeNodeData);
        }
        if (!event.active) simulation.alphaTarget(0);
        // Zero velocity at release → no whip on snap-back.
        d.vx = 0; d.vy = 0;
        // Orphans: fx/fy stays — tickRefitOrphanRing() will lerp them back.
        // Sticky (double-click pinned) nodes: fx/fy stays — that's the point.
        // Otherwise release back to the simulation.
        if (d.degree !== 0 && !d._sticky) {
            d.fx = null; d.fy = null;
        }
        requestDraw();
    });
// Drag binds its mousedown first and claims node hits (stops propagation);
// zoom's filter additionally rejects node hits for dblclick-zoom.
canvasSel.call(drag);
bindCanvasZoom();

// === POINTER DISPATCH (hover / click / dblclick) ===
// One set of listeners on the canvas replaces per-element SVG handlers.
// Priority mirrors the old DOM stacking: nodes on top, then edges, then
// the background.
let _lastHoverEdge = null;
canvas.addEventListener("mousemove", (event) => {
    if (isDragging) return;
    const [wx, wy] = transform.invert(d3.pointer(event, canvas));
    let n = pickNode(wx, wy);
    if (n && isModeDimmedNode(n)) n = null;
    let l = n ? null : pickEdge(wx, wy);
    if (l && isModeDimmedEdge(l)) l = null;
    canvas.style.cursor = n ? "pointer" : (l ? "help" : "default");
    if (n !== hoverNode) {
        if (hoverNode) onNodeLeave();
        hoverNode = n;
        if (n) onNodeEnter(n);
        requestDraw();
    }
    if (l !== _lastHoverEdge) {
        _lastHoverEdge = l;
        if (l) showEdgeTooltip(event, l);
        else hideEdgeTooltip();
    } else if (l) {
        moveEdgeTooltip(event);
    }
});
canvas.addEventListener("mouseleave", () => {
    if (hoverNode) {
        onNodeLeave();
        hoverNode = null;
        requestDraw();
    }
    if (_lastHoverEdge) {
        hideEdgeTooltip();
        _lastHoverEdge = null;
    }
    canvas.style.cursor = "default";
});
canvas.addEventListener("click", (event) => {
    const [wx, wy] = transform.invert(d3.pointer(event, canvas));
    const n = pickNode(wx, wy);
    if (n) { onNodeClick(event, n); return; }
    const l = pickEdge(wx, wy);
    if (l) { onEdgeClick(l); return; }
    dropAllSelections();
});
canvas.addEventListener("dblclick", (event) => {
    const n = pickNodeAtEvent(event);
    if (!n) return;  // background dblclick → d3.zoom's dblclick-zoom
    onNodeDblClick(n);
});

// Edge click: focus the edge, or drop selections when it's faded.
function onEdgeClick(d) {
    if (isEdgeFaded(d)) {
        dropAllSelections();
        return;
    }
    if (!isEdgeVisuallyVisible(d)) return;
    clearPinDim();
    infoPanel.classList.add("hidden");
    applyEdgeFocus(d);
    hideEdgeTooltip();
}

// === HOVER ===
// Hover: debounced highlight to prevent flicker during rapid mouse moves
let hoverTimer = null;

// === PIN / EDGE FOCUS / DIM ===
// Restore the search dim (or clear all dims) — shared tail of every
// clear* function below; replaces the repeated SVG class resets.
function restoreSearchDim() {
    if (searchQuery) {
        dimNode = n => !searchMatching.has(n.id);
        dimEdge = l =>
            !searchMatching.has(l.source.id) &&
            !searchMatching.has(l.target.id);
    } else {
        dimNode = null;
        dimEdge = null;
    }
    hotEdge = null;
}

function applyPinDim(d) {
    const nb = neighborMap.get(d.id) || new Set([d.id]);
    dimNode = n => !nb.has(n.id);
    dimEdge = l => l.source.id !== d.id && l.target.id !== d.id;
    hotEdge = l => l.source.id === d.id || l.target.id === d.id;
    requestDraw();
}

function clearPinDim() {
    activeNodeData = null;
    restoreSearchDim();
    requestDraw();
}

// Edge focus: click on a link → keep source/target nodes + the edge,
// dim everything else. No info-panel is opened.
function applyEdgeFocus(d) {
    activeEdge = d;
    activeNodeData = null;
    infoPanel.classList.add("hidden");
    dimNode = n => n.id !== d.source.id && n.id !== d.target.id;
    dimEdge = l => l !== d;
    hotEdge = l => l === d;
    requestDraw();
}
function clearEdgeFocus() {
    if (!activeEdge) return;
    activeEdge = null;
    restoreSearchDim();
    requestDraw();
}
function _pinActive() {
    return activeNodeData && !infoPanel.classList.contains("hidden");
}

// === PATH MODE (shift+click two nodes) ===
// BFS over the undirected adjacency built into neighborMap. Returns an
// array of node ids from `from` to `to` (inclusive), or [] if unreachable.
function bfsPath(fromId, toId) {
    if (fromId === toId) return [fromId];
    const parent = new Map();
    parent.set(fromId, null);
    const queue = [fromId];
    while (queue.length) {
        const cur = queue.shift();
        const nb = neighborMap.get(cur);
        if (!nb) continue;
        for (const next of nb) {
            if (next === cur || parent.has(next)) continue;
            parent.set(next, cur);
            if (next === toId) {
                const path = [];
                let n = toId;
                while (n !== null) { path.unshift(n); n = parent.get(n); }
                return path;
            }
            queue.push(next);
        }
    }
    return [];
}
function applyPath(fromNode, toNode) {
    const ids = bfsPath(fromNode.id, toNode.id);
    if (!ids.length) {
        showToast(t("toast.noPath"));
        return false;
    }
    pathStart = fromNode;
    pathEnd = toNode;
    pathNodeIds = new Set(ids);
    pathLinks = new Set();
    // Build edge set: for each consecutive pair in the path, find a link
    // connecting them in either direction.
    for (let i = 0; i + 1 < ids.length; i++) {
        const a = ids[i], b = ids[i + 1];
        const link = links.find(l => {
            const s = l.source.id ?? l.source;
            const tg = l.target.id ?? l.target;
            return (s === a && tg === b) || (s === b && tg === a);
        });
        if (link) pathLinks.add(link);
    }
    // Visual: dim everything outside the path; endpoints, path edges and
    // forced labels are resolved inside draw() from the path state.
    dimNode = n => !pathNodeIds.has(n.id);
    dimEdge = l => !pathLinks.has(l);
    hotEdge = null;
    requestDraw();
    return true;
}
function clearPath() {
    if (!pathStart && !pathEnd) return;
    pathStart = null;
    pathEnd = null;
    pathNodeIds = new Set();
    pathLinks = new Set();
    restoreSearchDim();
    requestDraw();
}
function pathActive() { return pathStart !== null && pathEnd !== null; }
function pathPending() { return pathStart !== null && pathEnd === null; }

// Toast (shared with copy-toast element).
let _genericToastTimer = null;
function showToast(msg) {
    const toast = document.getElementById("copy-toast");
    if (!toast) return;
    toast.textContent = msg;
    toast.classList.add("visible");
    clearTimeout(_genericToastTimer);
    _genericToastTimer = setTimeout(
        () => toast.classList.remove("visible"), 1600);
}
function onNodeEnter(d) {
    if (isDragging || activeEdge) return;
    // Path mode owns the dim state — hover must not touch it.
    if (pathActive() || pathPending()) return;
    // Pin mode: peek second-level neighbors when hovering an in-set node;
    // ignore hover on faded nodes (don't break the pin highlight).
    if (_pinActive()) {
        const pinNb = neighborMap.get(activeNodeData.id)
            || new Set([activeNodeData.id]);
        if (!pinNb.has(d.id)) return;  // hovered node is faded
        clearTimeout(hoverTimer);
        hoverTimer = setTimeout(() => {
            if (isDragging || activeEdge || !_pinActive()) return;
            const pinId = activeNodeData.id;
            const pinNbNow = neighborMap.get(pinId) || new Set([pinId]);
            if (!pinNbNow.has(d.id)) return;
            const hoverNb = neighborMap.get(d.id) || new Set([d.id]);
            const showSet = new Set([...pinNbNow, ...hoverNb]);
            const isPinEdge = l =>
                l.source.id === pinId || l.target.id === pinId;
            const isHoverEdge = l =>
                l.source.id === d.id || l.target.id === d.id;
            dimNode = n => !showSet.has(n.id);
            dimEdge = l => !(isPinEdge(l) || isHoverEdge(l));
            hotEdge = l => isPinEdge(l) || isHoverEdge(l);
            requestDraw();
        }, 80);
        return;
    }
    // No active selection — original hover-highlight behavior
    clearTimeout(hoverTimer);
    hoverTimer = setTimeout(() => {
        if (isDragging || activeEdge || _pinActive()) return;
        const nb = neighborMap.get(d.id) || new Set([d.id]);
        dimNode = n => !nb.has(n.id);
        dimEdge = l => l.source.id !== d.id && l.target.id !== d.id;
        hotEdge = l => l.source.id === d.id || l.target.id === d.id;
        requestDraw();
    }, 80);
}

function onNodeLeave() {
    if (isDragging || activeEdge) return;
    // Path mode owns the dim state — keep it intact on mouseout.
    if (pathActive() || pathPending()) return;
    clearTimeout(hoverTimer);
    // Pin mode: drop the hover-peek layer, keep pin highlight intact.
    if (_pinActive()) {
        applyPinDim(activeNodeData);
        return;
    }
    hoverTimer = setTimeout(() => {
        if (isDragging || activeEdge || _pinActive()) return;
        restoreSearchDim();
        requestDraw();
    }, 80);
}

