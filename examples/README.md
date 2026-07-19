# Examples

## tiny-project

The smallest project that exercises every core mechanic: a Python package
whose modules import each other and mention docs, plus a markdown file that
links back to the code.

```text
tiny-project/
  app/
    __init__.py
    core.py      # docstring mentions docs/design.md
    cli.py       # imports app.core
  docs/
    design.md    # mentions cli.py, links ../app/core.py
```

Build the graph and both JSON exports:

```bash
cd examples/tiny-project
build-graph --root . --json --compact
```

This writes three files into `docs/`:

- `graph.html` — the interactive graph (open in a browser),
- `graph.json` — verbose export, schema v1,
- `graph-compact.json` — token-efficient export, schema v2.

[`expected/`](expected/) holds the reference `graph.json` and
`graph-compact.json` for exactly this run (validated in CI, so they never
drift from the code). Two normalization notes:

- `project_root` in `graph.json` is your absolute path; the reference file
  uses the placeholder `/path/to/tiny-project`.
- The reference run has no git repo around it, so `git_available` is
  `false` and nodes carry no `gitStatus`. Running inside a git checkout
  adds the git overlay fields.

The exports are described by the JSON Schemas in
[`../schema/`](../schema/).
