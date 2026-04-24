# What If Your AI Coding Assistant Could See Your Entire Codebase as a Graph?

*Give Cursor, Claude, and other MCP-capable tools a structured map of every class, function, and call chain in your repository -- across five languages.*

---

## The problem with AI and large codebases

AI coding assistants are remarkably good at working within a single file. But real software does not live in a single file. A function in `graph.py` calls a method defined in `edge_resolver.py`, which imports a tracer from `import_tracer.py`, which reads barrel files discovered by the Python `ast` module.

When you ask your assistant "what calls `build`?", it has two options: grep the repo and hope the results fit in the context window, or ask you to paste the relevant files. Neither scales. The assistant cannot see the **structure** of your code -- the inheritance trees, the call chains, the cross-file import relationships -- because that structure is implicit, scattered across thousands of files, and impossible to reconstruct from keyword search alone.

## CodeGraph: a structured code graph for AI tools

[CodeGraph](https://github.com/ritesd/codegraph) is an open-source Python tool that solves this problem. It parses your repository, builds a directed graph of classes, methods, functions, and their relationships, and exposes the graph through an MCP (Model Context Protocol) server that AI assistants can query directly.

Here is what the pipeline looks like:

**Parse** -- Walk the repo, parse each file with language-specific parsers (stdlib `ast` for Python; tree-sitter for JavaScript, TypeScript, Go, and Java). Extract classes, methods, functions, imports, and call sites.

**Resolve** -- Map every import and call site to its defining file using `ImportTracer`. Handle relative imports, barrel re-exports (`__init__.py`, `index.ts`), star imports, and dynamic calls. Every resolved edge gets a **confidence score**: 1.0 for a direct file match, 0.8 for a barrel re-export, 0.5 for a star-import or name-match fallback, 0.2 for a dynamic call.

**Store** -- Persist the graph to SQLite. Nodes are stored as JSON blobs with indexed lookup columns for fast queries by name, type, file, repo, and language.

**Query** -- Expose MCP tools: `parse_repo`, `get_node`, `get_neighbors`, `search_nodes`, `get_class_tree`, `export_graph`, `incremental_update`, `list_repos`, `get_call_chain`, `get_nodes_by_id`, and `get_change_impact`. AI assistants call these tools through the Model Context Protocol over stdio, SSE, or streamable-HTTP.

## Readable exports (and how this differs from graphify)

Raw graphs are hard to read: UUID node ids, huge JSON blobs, and no sense of what is trustworthy.

CodeGraph now optimizes for **human and LLM-friendly exports**:

- **JSON** exports add **`label`** (symbol name) and **`display_name`** (symbol plus file basename and line) on every node. The top-level **`edges`** list includes **`provenance`** on each edge: **`EXTRACTED`** (high confidence), **`INFERRED`** (medium), **`AMBIGUOUS`** (low / speculative). That mirrors the spirit of graphify’s `EXTRACTED` / `INFERRED` / `AMBIGUOUS` tags, but is derived from CodeGraph’s existing numeric confidence scores. Set `export_graph(..., readable=false)` or use `codegraph export … --no-readable` when you want a slimmer payload.
- **GEXF / GraphML** (via NetworkX) carry the same **`label`**, **`display_name`**, **`node_type`**, **`language`**, **`file_path`**, and **`repo`** as scalar attributes so tools like Gephi show meaningful names instead of anonymous ids.
- **`GRAPH_REPORT.md`** -- A deterministic markdown summary (no LLM required): overview counts, hub symbols by degree, nodes by type and language, a sample of notable cross-file edges, and copy-paste MCP query examples. Generate it with `codegraph report <repo>` or `codegraph export <repo> --report`.

[graphify](https://github.com/safishamsi/graphify) casts a wider net: multimodal corpora (docs, PDFs, images), interactive `graph.html`, Leiden clustering, and assistant hooks. CodeGraph stays focused on **multi-language code intelligence**, **SQLite + MCP**, and **import/call resolution** with explicit confidence. See [docs/graphify-comparison.md](https://github.com/ritesd/codegraph/blob/main/docs/graphify-comparison.md) in the repo for a concise side-by-side of output models.

## Why confidence scores (and provenance) matter

Not all edges are created equal. A direct `from foo import Bar` is certain. A symbol resolved through a star-import barrel is plausible but not guaranteed. A `getattr(obj, method_name)` call is speculative. CodeGraph tracks this distinction as a float between 0.0 and 1.0 on every edge, and maps it to **provenance** in exports so you can filter noise:

```
get_neighbors(node_id="...", edge_types=["CALLED_BY"], min_confidence=0.5)
```

This single call replaces a manual grep, a context-window juggling act, and a prayer that the assistant remembers what it saw three messages ago.

## Incremental parsing

Full re-parses are expensive on large repos. CodeGraph supports incremental mode: it runs `git diff HEAD~1 --name-only`, deletes only the changed nodes, re-parses only the changed files, then re-resolves all edges. On a typical commit touching 5-10 files in a 2,000-file monorepo, this takes seconds instead of minutes.

## Five languages, one graph

Python, JavaScript, TypeScript, Go, and Java all live in the same graph. Cross-language edges are not yet resolved (a Python service calling a Go gRPC endpoint), but within each language, imports, calls, inheritance, and containment are fully tracked. The unified schema means your assistant can search and traverse the entire polyglot codebase with the same set of tools.

## Getting started

CodeGraph requires Python 3.11+ and [uv](https://docs.astral.sh/uv/). Install with a single command:

```bash
./install.sh
```

Parse a repository:

```bash
codegraph parse /path/to/your/repo
```

Write a readable report from the database:

```bash
codegraph report my-repo
```

Start the MCP server for your AI assistant:

```bash
codegraph serve --transport sse --host 127.0.0.1 --port 8765
```

Then point your MCP-capable client (Cursor, Claude Desktop, etc.) at `http://127.0.0.1:8765/sse` and start asking structural questions about your code.

## What is next

CodeGraph is early-stage and open source under the MIT license. Planned improvements include pagination for large tool responses, MCP authentication, cross-language edge resolution, optional interactive HTML exports, and deeper graph-topology analysis inspired by knowledge-graph tooling.

If you work on a codebase large enough to confuse your AI assistant, give CodeGraph a try and let me know how it goes.

GitHub: [github.com/ritesd/codegraph](https://github.com/ritesd/codegraph)

---

*Built by [Ritesh Dubey](https://github.com/ritesd).*
