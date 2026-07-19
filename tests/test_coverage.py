"""Tests for the coverage overlay: Cobertura XML parsing, path resolution."""

from pathlib import Path

from build_graph._coverage import collect_coverage_data

_NORMAL_XML = """<?xml version="1.0"?>
<!DOCTYPE coverage SYSTEM "http://cobertura.sourceforge.net/xml/coverage-04.dtd">
<coverage>
<packages><package><classes>
<class filename="build_graph/_heat.py" line-rate="0.85"/>
<class filename="build_graph/graph.py" line-rate="0.42"/>
</classes></package></packages>
</coverage>
"""

_BILLION_LAUGHS_XML = """<?xml version="1.0"?>
<!DOCTYPE coverage [
  <!ENTITY lol "lol">
  <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
]>
<coverage><packages><package><classes>
<class filename="&lol2;.py" line-rate="0.1"/>
</classes></package></packages></coverage>
"""


class TestCollectCoverageData:
    def test_exact_path_match(self, tmp_path: Path) -> None:
        xml_path = tmp_path / "coverage.xml"
        xml_path.write_text(_NORMAL_XML, encoding="utf-8")
        known = {"build_graph/_heat.py", "build_graph/graph.py"}
        assert collect_coverage_data(xml_path, known) == {
            "build_graph/_heat.py": 85.0,
            "build_graph/graph.py": 42.0,
        }

    def test_src_layout_suffix_match(self, tmp_path: Path) -> None:
        xml_path = tmp_path / "coverage.xml"
        xml_path.write_text(
            "<coverage><packages><package><classes>"
            '<class filename="build_graph/_heat.py" line-rate="0.85"/>'
            "</classes></package></packages></coverage>",
            encoding="utf-8",
        )
        known = {"src/build_graph/_heat.py"}
        assert collect_coverage_data(xml_path, known) == {
            "src/build_graph/_heat.py": 85.0
        }

    def test_ambiguous_suffix_is_dropped(self, tmp_path: Path) -> None:
        xml_path = tmp_path / "coverage.xml"
        xml_path.write_text(
            "<coverage><packages><package><classes>"
            '<class filename="pkg/mod.py" line-rate="0.5"/>'
            "</classes></package></packages></coverage>",
            encoding="utf-8",
        )
        known = {"a/pkg/mod.py", "b/pkg/mod.py"}
        assert collect_coverage_data(xml_path, known) == {}

    def test_root_level_bare_filename_rescued_by_inferred_prefix(
        self, tmp_path: Path
    ) -> None:
        """Cobertura reports root-package files with no directory at all
        (``filename="config.py"``, ``package name="."``) — bare "config.py"
        alone suffix-matches every same-named file in the tree. Other
        entries in the same report (with real subdirectories) resolve
        uniquely and pin down the rootdir, which then rescues the bare one.
        """
        xml_path = tmp_path / "coverage.xml"
        xml_path.write_text(
            "<coverage><packages>"
            '<package name="."><classes>'
            '<class filename="config.py" line-rate="0.9"/>'
            "</classes></package>"
            '<package name="integrations.base"><classes>'
            '<class filename="integrations/base/config.py" line-rate="0.7"/>'
            "</classes></package>"
            "</packages></coverage>",
            encoding="utf-8",
        )
        known = {
            "smm_bot_async/config.py",
            "smm_bot_async/integrations/base/config.py",
            "smm_bot_async/parsers/news/config.py",  # a THIRD config.py elsewhere
        }
        assert collect_coverage_data(xml_path, known) == {
            "smm_bot_async/config.py": 90.0,
            "smm_bot_async/integrations/base/config.py": 70.0,
        }

    def test_inconsistent_prefixes_leave_bare_filename_dropped(
        self, tmp_path: Path
    ) -> None:
        """If the unique-suffix matches in one report don't agree on a
        single rootdir, don't guess — leave the bare/ambiguous entry
        dropped rather than picking one prefix arbitrarily.
        """
        xml_path = tmp_path / "coverage.xml"
        xml_path.write_text(
            "<coverage><packages><package><classes>"
            '<class filename="config.py" line-rate="0.9"/>'
            '<class filename="sub/util.py" line-rate="0.5"/>'
            '<class filename="other/util.py" line-rate="0.4"/>'
            "</classes></package></packages></coverage>",
            encoding="utf-8",
        )
        known = {
            "pkg_a/sub/util.py",
            "pkg_b/other/util.py",
            "pkg_a/config.py",
            "pkg_b/config.py",
        }
        result = collect_coverage_data(xml_path, known)
        assert result == {
            "pkg_a/sub/util.py": 50.0,
            "pkg_b/other/util.py": 40.0,
        }

    def test_unmatched_filename_is_dropped(self, tmp_path: Path) -> None:
        xml_path = tmp_path / "coverage.xml"
        xml_path.write_text(
            "<coverage><packages><package><classes>"
            '<class filename="gone_since.py" line-rate="0.5"/>'
            "</classes></package></packages></coverage>",
            encoding="utf-8",
        )
        assert collect_coverage_data(xml_path, {"keep.py"}) == {}

    def test_missing_file(self, tmp_path: Path) -> None:
        assert collect_coverage_data(tmp_path / "nope.xml", {"keep.py"}) is None

    def test_malformed_xml(self, tmp_path: Path) -> None:
        xml_path = tmp_path / "coverage.xml"
        xml_path.write_text("<not><valid", encoding="utf-8")
        assert collect_coverage_data(xml_path, {"keep.py"}) is None

    def test_billion_laughs_is_rejected(self, tmp_path: Path) -> None:
        xml_path = tmp_path / "evil.xml"
        xml_path.write_text(_BILLION_LAUGHS_XML, encoding="utf-8")
        assert (
            collect_coverage_data(xml_path, {"lollollollollollollollollollol.py"})
            is None
        )

    def test_class_missing_attributes_is_skipped(self, tmp_path: Path) -> None:
        xml_path = tmp_path / "coverage.xml"
        xml_path.write_text(
            "<coverage><packages><package><classes>"
            '<class filename="no_rate.py"/>'
            '<class line-rate="0.5"/>'
            "</classes></package></packages></coverage>",
            encoding="utf-8",
        )
        assert collect_coverage_data(xml_path, {"no_rate.py"}) == {}

    def test_non_numeric_line_rate_is_skipped(self, tmp_path: Path) -> None:
        xml_path = tmp_path / "coverage.xml"
        xml_path.write_text(
            "<coverage><packages><package><classes>"
            '<class filename="weird.py" line-rate="not-a-number"/>'
            "</classes></package></packages></coverage>",
            encoding="utf-8",
        )
        assert collect_coverage_data(xml_path, {"weird.py"}) == {}
