"""Coverage overlay: per-file line coverage from a Cobertura XML report.

A fourth node-color mode alongside Type / Git / Heat (see `_git.py` /
`_heat.py`) — independent data, opt-in only (`--coverage PATH`), no
interaction with the git-status/heat collection in `graph.py`.
"""

import xml.etree.ElementTree as ET
import xml.parsers.expat as expat
from pathlib import Path


class _RejectedEntity(Exception):
    """Raised from an expat callback to abort a parse that declares entities."""


def _parse_hardened(xml_path: Path) -> ET.Element:
    """Parse XML with entity expansion disabled (no `defusedxml` dependency).

    This project is zero-runtime-dependency by design (see README), so the
    usual fix for XXE / billion-laughs — `defusedxml` — is off the table.
    `xml.etree.ElementTree`'s own parser already never resolves *external*
    entities (see the CPython docs' XML vulnerabilities table), so classic
    XXE file/URL-disclosure isn't reachable here regardless. What's left is
    internal entity expansion (the "billion laughs" DoS, declared inside a
    DOCTYPE's internal subset) — closed explicitly by wiring a raw
    `expat.ParserCreate()` (bypassing `ET.XMLParser`, whose C-accelerated
    form doesn't expose the underlying expat parser to attach handlers to)
    and rejecting any entity declaration outright. The DOCTYPE line itself
    is NOT rejected: real Cobertura reports commonly start with
    `<!DOCTYPE coverage SYSTEM "...">`, which must keep parsing.
    """
    parser = expat.ParserCreate()
    builder = ET.TreeBuilder()
    parser.StartElementHandler = builder.start
    parser.EndElementHandler = builder.end
    parser.CharacterDataHandler = builder.data

    def _reject(*_args: object) -> None:
        raise _RejectedEntity("entity declarations are not allowed")

    parser.EntityDeclHandler = _reject
    parser.UnparsedEntityDeclHandler = _reject
    # Falsy return tells expat to refuse the reference instead of resolving
    # (and potentially fetching) it.
    parser.ExternalEntityRefHandler = lambda *_args: 0

    with open(xml_path, "rb") as f:
        parser.ParseFile(f)
    return builder.close()


def collect_coverage_data(
    xml_path: Path, known_paths: set[str]
) -> dict[str, float] | None:
    """Parse a Cobertura ``coverage.xml`` into ``{path: percent covered}``.

    Returns None when the file is missing or isn't parseable XML. Cobertura's
    ``filename`` attribute is relative to whatever rootdir the coverage tool
    ran from — not guaranteed to match the graph's project-relative path
    under a src-layout (``build_graph/foo.py`` in the report vs
    ``src/build_graph/foo.py`` as the node's path).

    Two-pass resolution:

    1. Exact match against `known_paths`, else a *unique* suffix match
       (mirrors the import resolver's own src-layout fallback). Every
       filename in one report shares the same rootdir, so a resolved match
       also tells us that rootdir's prefix relative to the project root
       (``matched_path[:-len(filename)]``).
    2. If every resolution in pass 1 agreed on one prefix, apply it
       directly to whatever's left unresolved. This rescues the common
       case of a file living at the coverage rootdir itself — coverage.py's
       Cobertura writer reports those with a bare filename and no
       directory (``filename="config.py"``, ``package name="."``), which
       suffix-matches every same-named file in the project and would
       otherwise be dropped as ambiguous even though the other entries in
       the very same report already pin down the correct rootdir.

    Entries that stay unresolved after both passes (no exact/unique-suffix
    match, and either no inferred prefix or the prefixed path isn't a real
    node) are silently dropped — the file may have been renamed, deleted,
    or excluded from the report since it was generated, or the report mixes
    rootdirs in a way we can't safely disambiguate.
    """
    try:
        root = _parse_hardened(xml_path)
    except (expat.ExpatError, _RejectedEntity, OSError):
        return None

    raw: list[tuple[str, float]] = []
    for cls in root.iter("class"):
        filename = cls.get("filename")
        line_rate = cls.get("line-rate")
        if not filename or line_rate is None:
            continue
        try:
            percent = float(line_rate) * 100
        except ValueError:
            continue
        raw.append((Path(filename).as_posix(), percent))

    result: dict[str, float] = {}
    unresolved: list[tuple[str, float]] = []
    inferred_prefixes: set[str] = set()
    for posix_name, percent in raw:
        if posix_name in known_paths:
            result[posix_name] = percent
            continue
        candidates = [p for p in known_paths if p.endswith("/" + posix_name)]
        if len(candidates) == 1:
            result[candidates[0]] = percent
            inferred_prefixes.add(candidates[0][: -len(posix_name)])
        else:
            unresolved.append((posix_name, percent))

    if len(inferred_prefixes) == 1 and unresolved:
        (prefix,) = inferred_prefixes
        for posix_name, percent in unresolved:
            candidate = prefix + posix_name
            if candidate in known_paths:
                result[candidate] = percent

    return result
