# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-07-19

Initial public release.

### Added

- `build-graph` — single-file interactive HTML dependency graph of code and
  docs: canvas renderer with physics, autodiscovery with a `graph.toml`
  lifecycle (`--init` / `--diff` / `--merge`), git status overlay with ghost
  nodes and rename edges, dead-code detector, shortest-path and edge-focus
  views, sticky pins (`B` hotkey), 10 UI locales, shareable URL state, and
  Mermaid / JSON / token-efficient compact exports for LLM agents.
- `find-related-docs` — companion tool that finds markdown files affected by
  changed code (single file, directory, `--git-modified`, `--git-added`).
- `verify-doc-links` — CI-friendly checker for file references in docs;
  exits non-zero on broken links.
- Zero runtime dependencies (pure stdlib); Python 3.11+; the browser side
  uses D3.js, SRI-pinned from CDN or fully embedded via `--no-cdn`.

[0.1.0]: https://github.com/Mr-Freewan/build-graph/releases/tag/v0.1.0
