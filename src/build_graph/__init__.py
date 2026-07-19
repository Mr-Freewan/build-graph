"""build-graph — interactive code+docs dependency graph with doc-sync tooling.

Four CLI tools around one idea: keep code, documentation and git state on
a single dependency map that both humans (interactive HTML) and AI agents
(compact JSON) can navigate.

- ``build-graph`` — generate the interactive HTML graph + JSON snapshots
- ``find-related-docs`` — reverse lookup: which .md mention this code file
- ``verify-doc-links`` — check that file references in .md files exist
- ``graph-query`` — query a snapshot: blast radius, hubs, stale docs
"""

__version__ = "0.3.0"
__author__ = "Yuriy Totyshev"
__author_url__ = "https://github.com/Mr-Freewan"
