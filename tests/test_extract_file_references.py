"""Unit tests for the markdown reference scanner (links.extract_file_references)."""

from build_graph.links import extract_file_references


def test_inline_link() -> None:
    refs = extract_file_references("See [setup](docs/how-to/setup.md) for details.")
    assert refs == ["docs/how-to/setup.md"]


def test_image_syntax() -> None:
    refs = extract_file_references("![schema](assets/config.yaml)")
    assert refs == ["assets/config.yaml"]


def test_title_is_stripped() -> None:
    refs = extract_file_references('[cfg](docs/config.md "The config guide")')
    assert refs == ["docs/config.md"]


def test_fragment_and_query_are_stripped() -> None:
    content = "[a](./file.md#section) and [b](./other.md?v=2)"
    assert extract_file_references(content) == ["./file.md", "./other.md"]


def test_url_encoding_is_decoded() -> None:
    refs = extract_file_references("[doc](my%20file.md)")
    assert refs == ["my file.md"]


def test_reference_style_definition() -> None:
    refs = extract_file_references("[ref]: docs/reference/config.md\n")
    assert refs == ["docs/reference/config.md"]


def test_wiki_links() -> None:
    content = "[[notes.md]] [[guide.md|alias]] [[api.md#section]] [[log.md^block]]"
    assert extract_file_references(content) == [
        "notes.md",
        "guide.md",
        "api.md",
        "log.md",
    ]


def test_html_anchor_and_img() -> None:
    content = '<a href="docs/x.md">x</a> <img src="cfg/settings.json">'
    assert extract_file_references(content) == ["docs/x.md", "cfg/settings.json"]


def test_backtick_path() -> None:
    refs = extract_file_references("Edit `config.py` before running.")
    assert refs == ["config.py"]


def test_backtick_command_line_is_skipped() -> None:
    refs = extract_file_references("Run `pytest tests/test_x.py` locally.")
    assert refs == []


def test_tree_listing() -> None:
    content = "```\nproject/\n├── core.py\n└── utils.py\n```"
    refs = extract_file_references(content)
    assert "core.py" in refs
    assert "utils.py" in refs


def test_external_urls_are_skipped() -> None:
    content = (
        "[a](https://example.com/readme.md) "
        "[b](mailto:x@example.com) "
        "[c](/etc/nginx/nginx.conf) "
        "[d](C:\\temp\\notes.md)"
    )
    assert extract_file_references(content) == []


def test_glob_is_skipped() -> None:
    assert extract_file_references("Watch `cfg/*.json` for changes.") == []


def test_unknown_extension_is_skipped() -> None:
    assert extract_file_references("[license](LICENSE.txt2) [bin](tool.exe)") == []


def test_duplicates_are_deduplicated() -> None:
    content = "[a](docs/a.md) then again [a](docs/a.md)"
    assert extract_file_references(content) == ["docs/a.md"]


def test_multiline_link_text() -> None:
    content = "[some\nwrapped text](docs/a.md)"
    assert extract_file_references(content) == ["docs/a.md"]
