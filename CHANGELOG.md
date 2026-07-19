# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `docs/agent-prompts.md` — ready-made prompts for driving an LLM agent with
  `graph-compact.json` (blast radius, three-way doc-sync, ghost detection,
  dead-code and missing-edges hunts), linked from the README.

## [0.3.0] — 2026-07-19

### Added

- Import-cycle detector: a legend toggle (visible only when cycles exist)
  highlights circular `import` chains in coral — Tarjan SCC over runtime
  `code->code` edges, `TYPE_CHECKING`-only imports excluded. Shareable via
  the URL state, persisted in prefs.
- Graph diff: `--diff-base REF` compares the working tree against a git
  ref. File statuses (added / modified / renamed / deleted) feed the
  existing Git overlay; dependency edges new since the ref render bright
  green and removed ones red (dashed, anchored to ghost nodes when the
  file is gone), while unchanged edges recede — the diff is readable at a
  glance — with counters in the git legend. Renames are followed, so an
  edge that merely moved with a renamed file stays neutral. The build
  opens with the Git overlay already on.
- Graph diff: `--diff-head REF` compares two specific refs instead of the
  working tree — both sides are built from `git archive` snapshots, so
  worktree changes made after the head ref are excluded from the diff.
- Heat overlay: a third node-coloring mode, alongside Type and Git status —
  a blue→red gradient by how often each file has changed in git (commit
  count over the whole history, or the last N days with `--heat-days N`).
  Mutually exclusive with the Git overlay (both recolor nodes), but unlike
  Git mode it's additive — Node types, Edge types and the rest of the
  legend stay exactly as they are. The legend shows the collection period,
  the raw commit-count range, and a min-edits slider that hides anything
  colder than the chosen threshold (edges follow).
- Coverage overlay: a fourth node-coloring mode from a Cobertura
  `coverage.xml` (`--coverage PATH`, e.g. `pytest --cov=your_pkg --cov-report=xml`) — a
  green→red gradient by test-line coverage. Reversed direction from Heat
  on purpose: the point of this overlay is finding badly-covered files,
  so green (good) sits on the left, and the slider is a ceiling — it
  hides anything covered *more* than the chosen percentage, isolating
  the worst-covered files as you lower it. Turning it on also auto-hides
  every Node type except code in the legend (a coverage report can't say
  anything about docs/config files); any category can be shown again from
  there. Additive like Heat mode otherwise; mutually exclusive with both
  Git and Heat. Off by default, and its button is hidden entirely (not
  just disabled) when no report is given — unlike git, most builds won't
  have one.
- Node tooltip: hovering any node now shows its name and path after a
  short delay; in Heat or Coverage mode it also shows the edit count or
  coverage percentage behind the color, so the number doesn't require
  opening the info-panel. Edge tooltips are suppressed while Heat or
  Coverage mode is on — edges keep their type-based color there, so
  hovering one is just noise.

### Changed

- In the exclusive highlight modes (dead code, untracked, cycles) faded
  nodes and edges no longer react to the pointer: no hover highlight, no
  tooltip, no pointer cursor, and clicking one clears selections instead
  of pinning it.
- The Cycles and Untracked legend toggles hide in git mode, and turning
  the git overlay on drops their active highlight; Dead code stays
  available on top of git colouring.

### Fixed

- Bare entries of tree listings in docs no longer fan out across
  same-named files: the directory context is reconstructed from the
  tree's indentation, so `keyboards.py` under `api_manager/` links only
  that file (previously `__init__.py` in a tree linked every
  `__init__.py` in the repo). Tree entries whose name merely contains
  another file's name (`input_screens.py` vs `screens.py`) no longer
  count as mentions of that file. Unparseable tree shapes now route to
  the ambiguous-group node below instead of the old whole-group fan-out.
- A doc's bare mention of a same-named file — no explicit path, no tree
  context — no longer fans out real code→doc edges to every file sharing
  that name. It is credited to one synthetic node per basename instead, in
  its own `ambiguous` legend category (`__init__.py (×N)`, N = group
  size), with the doc + line number still visible in its Connections list.

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

[0.3.0]: https://github.com/Mr-Freewan/build-graph/releases/tag/v0.3.0
[0.2.0]: https://github.com/Mr-Freewan/build-graph/releases/tag/v0.2.0
[0.1.0]: https://github.com/Mr-Freewan/build-graph/releases/tag/v0.1.0
