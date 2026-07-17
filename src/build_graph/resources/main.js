
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
        if (dimEdge && dimEdge(l)) elemAlpha *= 0.1;
        if (showDead && !isPath) elemAlpha *= 0.1;
        if (showUntracked && !isPath) elemAlpha *= 0.1;
        if (isPath) {
            color = "#a855f7"; strokeAlpha = 0.9; w = 3; dash = null;
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
        const isEndpoint = n === pathStart || n === pathEnd;
        const isPinned = pinned !== null && n.id === pinned.id;
        let circleAlpha = (dimNode && dimNode(n)) ? 0.2 : 1;
        if (showDead && !isDead && !isPinned && !isEndpoint) {
            circleAlpha = Math.min(circleAlpha, 0.22);
        }
        if (showUntracked && !isUntracked && !isPinned && !isEndpoint) {
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
    const n = pickNode(wx, wy);
    const l = n ? null : pickEdge(wx, wy);
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

// True when a node is faded out by the active pin/edge/path selection.
function isNodeFaded(d) {
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
// True when an edge is faded out by the active pin/edge/path selection.
function isEdgeFaded(d) {
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
let _copyToastTimer = null;
function showCopyToast() {
    const toast = document.getElementById("copy-toast");
    toast.classList.add("visible");
    clearTimeout(_copyToastTimer);
    _copyToastTimer = setTimeout(() => toast.classList.remove("visible"), 1600);
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
            showUntracked
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
