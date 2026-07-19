# Contributing

Thanks for taking an interest in build-graph. Bug reports, false-positive
reports and small focused PRs are all welcome.

## Dev setup

```bash
git clone https://github.com/Mr-Freewan/build-graph
cd build-graph
uv sync            # or: pip install -e . pytest pytest-cov jsonschema
```

Run everything the CI runs before pushing:

```bash
uv run ruff check src tests
uv run ruff format --check src tests
uv run pytest -q --cov=build_graph --cov-fail-under=80
```

The test matrix covers Linux + Windows on Python 3.11–3.13, so avoid
platform-specific assumptions (path separators are the usual trap — use
`Path.as_posix()` when comparing).

## Ground rules

- **Zero runtime dependencies** is a hard constraint. The package must keep
  running on pure stdlib; new libraries are acceptable in the `dev` group
  only.
- **The output is a single self-contained HTML file** — that is a design
  invariant, not an implementation detail.
- The JS resources in `src/build_graph/resources/` are concatenated in a
  fixed order (`i18n.js → engine.js → ui.js → boot.js`); top-level init code
  relies on it.
- UI strings live in `resources/i18n.js` with 10 locales. A new string needs
  a key in **all** locales (English fallback text is fine).
- The exports are a versioned contract: any change to the `--json` /
  `--compact` shapes must update `schema/*.schema.json` and bump the schema
  version.

## Pull requests

- Keep PRs small and single-purpose; one logical change per commit,
  imperative English commit messages (`fix: …`, `feat: …`, `docs: …`).
- Add or extend a test for every behaviour change. Matching-logic changes
  (edge building, reference extraction) are easiest to verify by comparing
  `--json` output on a real repo before and after.
- If you change CLI flags or user-visible behaviour, add a line to
  `CHANGELOG.md` under *Unreleased*.

## Reporting issues

Use the issue templates. For wrong edges (a file pair that should not be
connected, or a missing connection) the **false positive / false negative**
template asks for the exact source line — that is usually all that is needed
to reproduce a matcher problem.
