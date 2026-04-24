Your AI coding assistant can autocomplete a function. But can it tell you every caller of that function across 2,000 files?

I built **CodeGraph** -- an open-source tool that parses your entire repository into a structured code graph and exposes it to AI assistants via the Model Context Protocol (MCP).

What it does:

- Parses **Python, JavaScript, TypeScript, Go, and Java** into a unified graph of classes, functions, methods, and their relationships.
- Resolves cross-file imports with **confidence-scored edges** (1.0 for direct imports, 0.8 for barrel re-exports, 0.5 for star imports, 0.2 for dynamic calls) -- so your assistant knows which connections are certain and which are guesses.
- Exports **human-readable graphs**: every node gets **`label`** and **`display_name`** (symbol + file/line); edges can include **provenance** -- `EXTRACTED`, `INFERRED`, or `AMBIGUOUS` -- mapped from those confidence scores (similar idea to tools like [graphify](https://github.com/safishamsi/graphify), but focused on **code structure** and MCP-first workflows).
- Emits a deterministic **`GRAPH_REPORT.md`** -- hub symbols, type/language breakdown, sample cross-file edges, and suggested MCP queries -- so you orient in the graph before dumping raw JSON into a chat.
- Supports **incremental parsing** -- after a commit, only changed files are re-processed. Seconds, not minutes.
- Exposes MCP tools (`get_node`, `get_neighbors`, `search_nodes`, `get_call_chain`, `export_graph` with a `readable` flag, and more) that Cursor, Claude Desktop, or any MCP client can call directly.

Instead of pasting files into a chat window and hoping the model remembers context, your assistant can **query the actual structure** of your codebase: call chains, inheritance trees, cross-file dependencies -- with a single tool call.

MIT licensed. Python 3.11+. One-command install.

Try it: https://github.com/ritesd/codegraph

I wrote a deeper dive on Medium covering architecture, confidence vs provenance, exports, and Cursor -- link in the comments.

#OpenSource #DeveloperTools #AI #MCP #CodeGraph #Python #CursorIDE #SoftwareEngineering
