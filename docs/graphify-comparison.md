# CodeGraph vs graphify: export and report model

This document locks the **first-pass** scope: readability of exports and a deterministic report, without porting graphify’s full multimodal pipeline.

## graphify (reference)

| Aspect | graphify (v3) |
|--------|----------------|
| Primary outputs | `graph.html`, `GRAPH_REPORT.md`, `graph.json`, `cache/` |
| Trust model | Edge tags: `EXTRACTED` / `INFERRED` / `AMBIGUOUS`; INFERRED carries `confidence_score` |
| Structure | NetworkX + Leiden communities; narrative “god nodes” and suggested questions |
| Scope | Code (tree-sitter) + docs/images (LLM); assistant hooks and MCP over static JSON |

## CodeGraph (this project)

| Aspect | CodeGraph |
|--------|-----------|
| Primary outputs | SQLite store; JSON (`nodes` map + `edges` list); GEXF/GraphML via NetworkX |
| Trust model | Numeric `confidence` (0.0–1.0) and `resolved` on each edge |
| Structure | Multi-language parse + import/call resolution; MCP tools for targeted queries |
| Gap (before readability pass) | UUID-centric nodes, minimal GEXF labels, no bundled markdown report |

## First-pass implementation (this repo)

1. **JSON / MCP exports**: Add `label`, `display_name` on nodes; add `provenance` on edges derived from confidence bands.
2. **GEXF/GraphML**: Set `label` and viz-friendly scalar attrs (`node_type`, `language`, `file_path`, `repo`).
3. **Report**: Generate `GRAPH_REPORT.md` deterministically (hubs, type/language breakdown, sample high-confidence edges, suggested MCP queries).
4. **Docs**: README + LinkedIn/Medium drafts updated to describe these outputs.

Future (out of scope for this pass): interactive HTML, Leiden clustering, `.codegraphignore`, LLM-written narratives.
