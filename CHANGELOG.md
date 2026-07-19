# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] — 2026-07-19

### Added

- `graph-query` — a fourth CLI that answers questions over a `--json` /
  `--compact` snapshot without the browser: `blast-radius` (transitive
  importers + affected docs), `hubs`, `stale-docs` (last-commit times,
  `--check` CI gate) and `orphans`; all commands offer `--json` output.
- JSON Schemas for both exports (`schema/graph-v1.schema.json`,
  `schema/graph-compact-v2.schema.json`); the exports are validated against
  them in CI.
- `--bench` — context-cost report (raw corpus vs `--json` vs `--compact`
  sizes with token estimates) that reproduces the README numbers on any
  repo; writes no files.
- `examples/tiny-project` — a minimal runnable project with reference
  exports, kept in sync with the code by a test.
- Contributing guide and GitHub issue templates (bug, feature,
  false-positive/negative edge).

### Fixed

- code→doc edges no longer fan out across same-named files when a doc
  names one of them by an explicit path: `integrations/base/config.py`
  in a doc used to also link every other `config.py` in the repo.
  Bare-name mentions still credit the whole group. On a 1,070-node
  corpus this removes ~15 % of code→doc edges — all provably wrong —
  and stops falsely doc-exempting files from the dead-code detector.

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

### Notes

- The PyPI distribution is named `graph-build` — PyPI rejects `build-graph`
  as too similar to an existing unrelated project. The CLI commands keep the
  `build-graph` family of names.

[0.2.0]: https://github.com/Mr-Freewan/build-graph/releases/tag/v0.2.0
[0.1.0]: https://github.com/Mr-Freewan/build-graph/releases/tag/v0.1.0
