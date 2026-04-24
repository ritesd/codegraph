# CodeGraph

Multi-language code graph extraction, storage, and MCP tooling.

CodeGraph parses repositories written in **Python, JavaScript, TypeScript, Go, and Java**, builds a directed graph of classes, methods, functions, and their call/inheritance edges, resolves cross-file imports with confidence scoring, and exposes the result through a CLI, SQLite store, and an MCP server.

## Features

- **Multi-language parsing** -- Python (stdlib `ast`), JS/TS/Go/Java (tree-sitter).
- **Edge resolution with confidence** -- direct imports (1.0), barrel re-exports (0.8), star-import / name-match fallback (0.5), dynamic calls (0.2).
- **SQLite persistence** -- nodes stored as JSON blobs with indexed lookup columns.
- **Optional vector store** -- Qdrant or Chroma bridge for embedding-based search.
- **Optional LLM summaries** -- any OpenAI-compatible `/v1/chat/completions` endpoint.
- **MCP server** -- exposes `parse_repo`, `get_node`, `get_neighbors`, `search_nodes`, `get_call_chain`, and more as MCP tools over stdio, SSE, or streamable-HTTP.
- **Human-readable exports** -- JSON and GEXF/GraphML include `label` / `display_name` on nodes; edges include optional **provenance** (`EXTRACTED` / `INFERRED` / `AMBIGUOUS`) derived from confidence scores (see [docs/graphify-comparison.md](docs/graphify-comparison.md)).
- **GRAPH_REPORT.md** -- deterministic markdown summary (hubs, types, languages, sample cross-file edges, suggested MCP queries) via `codegraph report` or `export --report`.
- **CLI** -- `codegraph parse`, `query`, `export`, `report`, `serve`, `stats`, `list-repos`.

## Installation

Requires **Python 3.11+** and [uv](https://docs.astral.sh/uv/).

```bash
# one-liner (installs uv if missing, registers codegraph in PATH)
./install.sh

# or manually
uv tool install .
```

To install in development mode:

```bash
uv sync --dev
```

## CLI Usage

```bash
# parse a repository
codegraph parse /path/to/repo --mode full --export json

# query a node by name
codegraph query my-repo MyClassName --show-edges --show-code

# export stored graph (readable JSON by default; use --no-readable for minimal keys)
codegraph export my-repo --fmt json --json-mode graph

# write only GRAPH_REPORT.md from SQLite
codegraph report my-repo

# parse and also emit GRAPH_REPORT.md in the output dir
codegraph parse /path/to/repo --export json --report

# start MCP server (SSE on 127.0.0.1:8765)
codegraph serve --host 127.0.0.1 --port 8765 --transport sse

# list all parsed repos
codegraph list-repos

# print repo statistics
codegraph stats my-repo
```

## MCP Server

Run standalone:

```bash
python -m codegraph.mcp.server --transport sse --host 0.0.0.0 --port 8765
```

Available tools: `parse_repo`, `get_node`, `get_neighbors`, `search_nodes`, `get_class_tree`, `export_graph`, `incremental_update`, `list_repos`, `get_call_chain`, `get_nodes_by_id`, `get_change_impact`.

`export_graph` accepts **`readable`** (default `true`): when enabled, JSON exports include `label` and `display_name` on each node and `provenance` on each edge. Set `readable=false` for a slimmer payload.

### Cursor MCP (`mcp.json`)

Add CodeGraph to Cursor via **Settings → MCP** or by editing `~/.cursor/mcp.json`. Use the full path to `codegraph` if it is not on your PATH (often `~/.local/bin/codegraph` after `uv tool install`).

**Option 1 -- stdio (recommended)** -- Cursor starts the server; no separate process.

```json
{
  "mcpServers": {
    "codegraph": {
      "command": "/Users/yourname/.local/bin/codegraph",
      "args": ["serve", "--transport", "stdio"]
    }
  }
}
```

**Option 2 -- SSE** -- start the server yourself, then point Cursor at it:

```bash
codegraph serve --transport sse --host 127.0.0.1 --port 8765
```

```json
{
  "mcpServers": {
    "codegraph": {
      "url": "http://127.0.0.1:8765/sse"
    }
  }
}
```

**Optional env overrides** (stdio mode; otherwise `~/.codegraph/.env` is loaded automatically):

```json
{
  "mcpServers": {
    "codegraph": {
      "command": "/Users/yourname/.local/bin/codegraph",
      "args": ["serve", "--transport", "stdio"],
      "env": {
        "CODEGRAPH_SQLITE_PATH": "/Users/yourname/.codegraph/codegraph.db",
        "CODEGRAPH_VECTOR_DB_URL": "http://localhost:6333",
        "CODEGRAPH_VECTOR_DB_TYPE": "qdrant",
        "CODEGRAPH_EMBEDDING_ENDPOINT": "http://localhost:11434",
        "CODEGRAPH_EMBEDDING_MODEL": "nomic-embed-text"
      }
    }
  }
}
```

## Configuration

All settings are read from environment variables with `CODEGRAPH_` prefix.

| Variable | Default | Description |
|---|---|---|
| `CODEGRAPH_SQLITE_PATH` | `~/.codegraph/codegraph.db` | SQLite database path |
| `CODEGRAPH_VECTOR_DB_URL` | *(empty)* | Vector DB URL (empty = disabled) |
| `CODEGRAPH_VECTOR_DB_TYPE` | *(empty)* | `qdrant` or `chroma` |
| `CODEGRAPH_VECTOR_COLLECTION` | `codegraph` | Vector collection name |
| `CODEGRAPH_LLM_ENDPOINT` | *(empty)* | Summary endpoint (empty = disabled) |
| `CODEGRAPH_LLM_MODEL` | `mistral:7b-instruct-q4_K_M` | Model name for summaries |
| `CODEGRAPH_LLM_API_KEY` | *(empty)* | API key (Bearer token for OpenAI; api-key header for Azure) |
| `CODEGRAPH_LLM_API_VERSION` | *(empty)* | Azure API version (e.g. `2024-06-01`); enables Azure mode when set |
| `CODEGRAPH_EMBEDDING_ENDPOINT` | *(falls back to LLM_ENDPOINT)* | Embedding endpoint |
| `CODEGRAPH_EMBEDDING_MODEL` | `nomic-embed-text` | Model name for embeddings |
| `CODEGRAPH_EMBEDDING_API_KEY` | *(falls back to LLM_API_KEY)* | API key for embedding endpoint |
| `CODEGRAPH_EMBEDDING_API_VERSION` | *(falls back to LLM_API_VERSION)* | Azure API version for embedding endpoint |
| `CODEGRAPH_DEFAULT_MODE` | `full` | `full` or `incremental` |
| `CODEGRAPH_INCLUDE_EXTERNAL_NODES` | `true` | Create nodes for third-party symbols |
| `CODEGRAPH_MAX_FILE_SIZE_KB` | `500` | Skip files larger than this |
| `CODEGRAPH_DEFAULT_EXPORT_FORMAT` | `json` | `json` or `networkx` |
| `CODEGRAPH_OUTPUT_DIR` | `./codegraph_output` | Export output directory |
| `CODEGRAPH_MCP_HOST` | `127.0.0.1` | MCP server bind address |
| `CODEGRAPH_MCP_PORT` | `8765` | MCP server port |
| `CODEGRAPH_MCP_TRANSPORT` | `sse` | `stdio`, `sse`, or `streamable-http` |

### Using an env file

CodeGraph **automatically loads `.env` files** -- no need to `source` anything. It checks two locations (later overrides earlier):

1. `~/.codegraph/.env` -- global user defaults (applied everywhere)
2. `./.env` in the current working directory -- project-specific overrides
3. Real shell environment variables always take highest priority

An `example.env` is included in the repo. To get started:

```bash
# project-specific config
cp example.env .env
# uncomment and edit the values you want to change

# or set global defaults
mkdir -p ~/.codegraph
cp example.env ~/.codegraph/.env
```

Then just run commands normally -- values are picked up automatically:

```bash
codegraph parse /path/to/repo
codegraph serve
```

You can still pass one-off overrides inline:

```bash
CODEGRAPH_SQLITE_PATH=./custom.db CODEGRAPH_MCP_PORT=9999 codegraph serve
```

### Provider examples

**Local (Ollama)** -- no API key needed:

```env
CODEGRAPH_LLM_ENDPOINT=http://localhost:11434
CODEGRAPH_LLM_MODEL=mistral:7b-instruct-q4_K_M
CODEGRAPH_EMBEDDING_ENDPOINT=http://localhost:11434
CODEGRAPH_EMBEDDING_MODEL=nomic-embed-text
```

**OpenAI** -- uses `Authorization: Bearer <key>` header:

```env
CODEGRAPH_LLM_ENDPOINT=https://api.openai.com
CODEGRAPH_LLM_MODEL=gpt-4o-mini
CODEGRAPH_LLM_API_KEY=sk-...
CODEGRAPH_EMBEDDING_ENDPOINT=https://api.openai.com
CODEGRAPH_EMBEDDING_MODEL=text-embedding-3-small
CODEGRAPH_EMBEDDING_API_KEY=sk-...
```

**Azure OpenAI** -- uses `api-key` header and `api-version` query parameter:

```env
CODEGRAPH_LLM_ENDPOINT=https://myresource.openai.azure.com/openai/deployments/gpt-4o-mini
CODEGRAPH_LLM_MODEL=gpt-4o-mini
CODEGRAPH_LLM_API_KEY=<azure-key>
CODEGRAPH_LLM_API_VERSION=2024-06-01
CODEGRAPH_EMBEDDING_ENDPOINT=https://myresource.openai.azure.com/openai/deployments/text-embedding-3-small
CODEGRAPH_EMBEDDING_MODEL=text-embedding-3-small
CODEGRAPH_EMBEDDING_API_KEY=<azure-key>
CODEGRAPH_EMBEDDING_API_VERSION=2024-06-01
```

**Mix and match** -- use different providers for summaries and embeddings:

```env
CODEGRAPH_LLM_ENDPOINT=https://api.openai.com
CODEGRAPH_LLM_MODEL=gpt-4o-mini
CODEGRAPH_LLM_API_KEY=sk-...
CODEGRAPH_EMBEDDING_ENDPOINT=http://localhost:11434
CODEGRAPH_EMBEDDING_MODEL=nomic-embed-text
```

## Visualising the Code Graph

### Readable JSON and GEXF

- **JSON** (`codegraph export … --fmt json`): each node has **`label`** (symbol name) and **`display_name`** (name plus file basename and line). Each edge includes **`provenance`**: `EXTRACTED` (high confidence), `INFERRED` (medium), `AMBIGUOUS` (low / speculative). `meta.export_readable` records the mode. Use `codegraph export … --no-readable` to omit these fields.
- **GEXF / GraphML**: node attributes include `label`, `display_name`, `node_type`, `language`, `file_path`, `repo`, and line numbers so Gephi can colour/filter without UUID-only labels. Edges carry `provenance` alongside `confidence`.

For a comparison with the [graphify](https://github.com/safishamsi/graphify) output model (reports, multimodal scope), see [docs/graphify-comparison.md](docs/graphify-comparison.md).

### GRAPH_REPORT.md

After parsing or from the DB:

```bash
codegraph report my-repo
# or
codegraph export my-repo --fmt json --report
```

Writes `<repo>_GRAPH_REPORT.md` under `CODEGRAPH_OUTPUT_DIR` (default `./codegraph_output`): overview counts, hub symbols, sample cross-file edges, and copy-paste MCP query examples.

### Quick stats (terminal)

```bash
codegraph stats my-repo
```

Returns node counts by type and language, average edge confidence, and unresolved edge ratio.

### Export to JSON

```bash
codegraph export my-repo --fmt json --json-mode graph
```

Writes `./codegraph_output/my-repo.json` with `nodes`, `edges`, and `meta`. Use any JSON viewer, or feed the `edges` array (which has `source`/`target` keys) directly into a D3 force-directed graph.

### Export to GEXF and open in Gephi

```bash
codegraph export my-repo --fmt networkx
```

Writes `./codegraph_output/my-repo.gexf`. Open in [Gephi](https://gephi.org/) for an interactive graph -- colour nodes by `language` or `node_type`, size by degree, and use layout algorithms like ForceAtlas2.

### NetworkX + matplotlib (Python script)

```python
import json
import networkx as nx
import matplotlib.pyplot as plt

with open("./codegraph_output/my-repo.json") as f:
    data = json.load(f)

G = nx.DiGraph()
for nid, ndata in data["nodes"].items():
    G.add_node(nid, label=ndata["name"], node_type=ndata["node_type"])
for e in data["edges"]:
    G.add_edge(e["source"], e["target"])

color_map = {"CLASS": "#4285f4", "FUNCTION": "#34a853", "METHOD": "#fbbc05", "EXTERNAL": "#ea4335"}
colors = [color_map.get(G.nodes[n].get("node_type", ""), "#999") for n in G.nodes]

plt.figure(figsize=(16, 12))
pos = nx.spring_layout(G, k=0.5, iterations=50)
nx.draw(G, pos, node_color=colors, node_size=60, edge_color="#cccccc",
        with_labels=False, arrows=True, arrowsize=8)
plt.title("CodeGraph")
plt.savefig("codegraph-viz.png", dpi=150)
plt.show()
```

### Browse SQLite directly

The database is a standard SQLite file:

```bash
sqlite3 codegraph.db "SELECT name, node_type, language FROM nodes WHERE repo='my-repo' LIMIT 20"
```

Or open it in [DB Browser for SQLite](https://sqlitebrowser.org/) for interactive filtering.

## Development

```bash
uv sync --dev
python -m pytest tests/ -q
```

## License

[MIT](LICENSE)
