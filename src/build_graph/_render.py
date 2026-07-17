"""HTML assembly, palette and node post-processing (layout hints, dead-code).

Holds the packaged front-end resources (style.css / body.html / main.js —
read once at import), the pinned D3.js handling and `render_html` which
concatenates everything into the single self-contained output file.
"""

import base64
import colorsys
import fnmatch
import hashlib
import json
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from importlib import resources as _resources
from pathlib import Path

from build_graph import __author__, __author_url__, __version__


def compute_layout_hints(nodes: list[dict], edges: list[dict]) -> None:
    """Compute degree and proportional node size (mutates nodes in-place)."""
    degree: dict[str, int] = defaultdict(int)
    for edge in edges:
        degree[edge["source"]] += 1
        degree[edge["target"]] += 1
    max_degree = max(degree.values()) if degree else 1
    min_size, max_size = 5, 20
    for node in nodes:
        d = degree[node["id"]]
        node["degree"] = d
        if node.get("ghost"):
            # Ghost nodes keep their fixed size (set in add_ghost_nodes_and_edges).
            continue
        node["size"] = min_size + (max_size - min_size) * (d / max_degree)


# Pinned D3.js v7. Regenerate the hash when bumping the upstream version:
#   curl -A 'Mozilla/5.0' -s https://d3js.org/d3.v7.min.js | sha256sum
D3_URL = "https://d3js.org/d3.v7.min.js"
D3_SHA256 = "f2094bbf6141b359722c4fe454eb6c4b0f0e42cc10cc7af921fc158fceb86539"


def _d3_sri() -> str:
    return "sha256-" + base64.b64encode(bytes.fromhex(D3_SHA256)).decode("ascii")


def _get_d3_script(embed: bool) -> str:
    """Return a D3.js <script> tag.

    CDN mode: pinned URL with Subresource Integrity (browser verifies hash).
    Embed mode: download, verify SHA-256 against D3_SHA256, inline the source.
    Mismatch in embed mode aborts the build — protects against MITM and
    surfaces upstream version bumps so the constant gets refreshed deliberately.
    """
    if not embed:
        return (
            f'<script src="{D3_URL}" '
            f'integrity="{_d3_sri()}" crossorigin="anonymous"></script>'
        )
    req = urllib.request.Request(D3_URL, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            d3_bytes = resp.read()
    except urllib.error.URLError as e:
        print(f"ERROR: Could not download D3.js: {e}", file=sys.stderr)
        sys.exit(1)
    actual = hashlib.sha256(d3_bytes).hexdigest()
    if actual != D3_SHA256:
        print(
            "ERROR: D3.js SHA-256 mismatch — refusing to embed.\n"
            f"  expected: {D3_SHA256}\n"
            f"  actual:   {actual}\n"
            f"  url:      {D3_URL}\n"
            "This may indicate a MITM attack, or an upstream D3 v7 release.\n"
            "If the new version is trusted, update D3_SHA256 in _render.py.",
            file=sys.stderr,
        )
        sys.exit(1)
    return f"<script>{d3_bytes.decode('utf-8')}</script>"


# ---------------------------------------------------------------------------
# HTML template parts. The CSS/JS/HTML body are kept as separate package
# resources under build_graph/resources/ for IDE syntax highlighting and
# easier translator/styling work. They are concatenated verbatim in
# render_html — no template engine.
# ---------------------------------------------------------------------------
_ASSETS_DIR = _resources.files("build_graph") / "resources"
_CSS = (_ASSETS_DIR / "style.css").read_text(encoding="utf-8")
_BODY = (_ASSETS_DIR / "body.html").read_text(encoding="utf-8")
# JS content is concatenated as-is; backslashes inside (e.g. JS \u escapes)
# must remain literal — that's handled by the files being raw text. i18n.js
# MUST precede main.js: main.js top-level init code calls applyI18n / reads
# I18N at evaluation time.
_JS_I18N = (_ASSETS_DIR / "i18n.js").read_text(encoding="utf-8")
_JS = (_ASSETS_DIR / "main.js").read_text(encoding="utf-8")


# --- palette / dead-code exemptions ----------------------------------------
def _procedural_color(category: str, saturated: bool) -> str:
    """Deterministic category colour: hue = stable hash of the name.

    md5 (not `hash()`, which is seeded per process) keeps colours identical
    between builds and across machines. Pastel and saturated variants share
    the hue — the hue-aligned palette invariant holds for generated colours.
    """
    digest = hashlib.md5(category.encode("utf-8"), usedforsecurity=False).digest()
    hue = int.from_bytes(digest[:2], "big") % 360 / 360.0
    lightness, sat = (0.45, 0.65) if saturated else (0.82, 0.55)
    r, g, b = colorsys.hls_to_rgb(hue, lightness, sat)
    return f"#{round(r * 255):02x}{round(g * 255):02x}{round(b * 255):02x}"


def build_palette(
    categories: set[str],
    toml_colors: dict[str, str],
    toml_colors_saturated: dict[str, str],
) -> tuple[dict[str, str], dict[str, str]]:
    """Colour map for every category: TOML pins win, the rest is procedural."""
    colors: dict[str, str] = {}
    saturated: dict[str, str] = {}
    for cat in sorted(categories):
        colors[cat] = toml_colors.get(cat) or _procedural_color(cat, False)
        saturated[cat] = toml_colors_saturated.get(cat) or _procedural_color(cat, True)
    return colors, saturated


# Files that legitimately have no incoming imports / doc mentions — flagged
# so the UI's dead-code detector skips them. Extendable via [dead_code].exempt
# glob patterns in graph.toml. Test modules are entry points too: pytest
# collects them, nothing imports them.
_DEAD_EXEMPT_NAMES = {"__init__.py", "conftest.py", "main.py"}
_DEAD_EXEMPT_NAME_PATTERNS = ("test_*.py",)
_DEAD_EXEMPT_PATH_PARTS = ("alembic/versions/",)


def apply_dead_exemptions(nodes: list[dict], exempt_globs: list[str]) -> None:
    """Mark nodes the dead-code detector must ignore (mutates in place)."""
    for n in nodes:
        if n.get("ghost"):
            continue
        path = n["path"]
        if (
            n["label"] in _DEAD_EXEMPT_NAMES
            or any(fnmatch.fnmatch(n["label"], p) for p in _DEAD_EXEMPT_NAME_PATTERNS)
            or any(part in path for part in _DEAD_EXEMPT_PATH_PARTS)
            or any(fnmatch.fnmatch(path, pat) for pat in exempt_globs)
        ):
            n["deadExempt"] = True


def _safe_json(obj: object) -> str:
    r"""``json.dumps`` with ``</script>`` protection for inline-script embedding.

    Replaces ``</`` with ``<\\/`` so a payload like ``</script><script>...``
    inside any string field cannot terminate the host ``<script>`` block.
    JSON spec accepts ``\\/`` as a valid escape for ``/``; ``JSON.parse``
    and JS string literal both decode it back to ``/``, so the runtime
    payload is unchanged — only the on-the-wire serialisation differs.
    """
    return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")


def render_html(
    nodes: list[dict],
    edges: list[dict],
    colors: dict[str, str],
    colors_saturated: dict[str, str],
    project_root_posix: str,
    output_path: Path,
    embed_d3: bool = False,
    git_data: dict | None = None,
) -> None:
    """Write a self-contained HTML graph file to output_path."""
    graph_json = _safe_json({"nodes": nodes, "links": edges})
    colors_json = _safe_json(colors)
    colors_sat_json = _safe_json(colors_saturated)
    git_json = _safe_json(git_data) if git_data else "null"
    d3_tag = _get_d3_script(embed_d3)
    # --no-cdn means "no external requests at all": along with embedding D3,
    # drop the Google Fonts link — the CSS font stack falls back to system-ui.
    font_tags = (
        ""
        if embed_d3
        else (
            '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
            '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
            '<link href="https://fonts.googleapis.com/css2?family=Comic+Relief'
            '&display=swap" rel="stylesheet">\n'
        )
    )
    html = (
        '<!DOCTYPE html>\n<html lang="en">\n<head>\n'
        '<meta charset="UTF-8">\n'
        + font_tags
        + "<title>Project Dependency Graph</title>\n"
        + d3_tag
        + "\n<style>\n"
        + _CSS
        + "</style>\n</head>\n<body>\n"
        + _BODY
        + "<script>\nconst GRAPH_DATA = "
        + graph_json
        + ";\nconst NODE_COLORS = "
        + colors_json
        + ";\nconst NODE_COLORS_SATURATED = "
        + colors_sat_json
        + ";\nconst PROJECT_ROOT = "
        + _safe_json(project_root_posix)
        + ";\nconst GIT_DATA = "
        + git_json
        + ";\nconst APP_VERSION = "
        + _safe_json(__version__)
        + ";\nconst APP_AUTHOR = "
        + _safe_json(__author__)
        + ";\nconst APP_AUTHOR_URL = "
        + _safe_json(__author_url__)
        + ";\n"
        + _JS_I18N
        + _JS
        + "</script>\n</body>\n</html>\n"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
