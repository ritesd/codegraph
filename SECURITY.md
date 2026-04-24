# Security Audit -- CodeGraph

Last reviewed: 2026-04-05

## Overview

CodeGraph is a local-first code indexer and MCP server. It parses source repositories, resolves cross-file relationships, persists the graph to SQLite, and exposes query tools over MCP (stdio / SSE / streamable-HTTP).

This document summarises a manual security review of the codebase. No automated SAST or dependency-audit tooling was run; findings are based on source-code inspection.

### Positive findings

| Area | Detail |
|------|--------|
| SQL injection | All SQLite queries use parameterised placeholders (`?`). No string-interpolated SQL found. |
| Shell injection | `subprocess.run` calls in `core/graph.py` use list argv (`["git", ...]`) with `cwd=repo_root`. No `shell=True`. |
| Code execution | No use of `eval`, `exec`, `pickle`, `yaml.load`, or `__import__` anywhere in first-party code. |
| AST-only parsing | Python files are parsed with `ast.parse`; JS/TS/Go/Java use tree-sitter. Neither executes the target code. |
| File-size guard | `CODEGRAPH_MAX_FILE_SIZE_KB` (default 500) is enforced in both `GraphBuilder._walk_repo` and `ParserRegistry.parse_file`. |

---

## Findings

| # | Severity | Title | Location | Description | Recommended mitigation |
|---|----------|-------|----------|-------------|------------------------|
| 1 | **High** | No MCP authentication or authorisation | `mcp/server.py`, `config.py` | The HTTP/SSE transport can bind to any interface (including `0.0.0.0`). There are no API keys, tokens, or ACLs. Anyone who can reach the port can call every tool -- including `parse_repo` on arbitrary paths. | Add API-key middleware (e.g. a `Bearer` token checked in a FastMCP middleware/hook). Default bind should remain `127.0.0.1`. Document that `0.0.0.0` requires an auth layer. |
| 2 | **High** | Unrestricted `repo_path` in `parse_repo` / `incremental_update` | `mcp/tools.py` lines 37-39, 139-141 | `repo_path` is passed directly to `GraphBuilder.build` with only `os.path.abspath` normalisation. A malicious MCP client can index `/etc`, `$HOME`, or any path readable by the process user. | Introduce `CODEGRAPH_ALLOWED_ROOTS` (comma-separated allowlist). Validate with `os.path.commonpath([repo_path, allowed]) == allowed` before parsing. Reject paths outside the allowlist. |
| 3 | **Medium** | Path traversal in relative-import resolution | `resolver/import_tracer.py` `_resolve_relative` (lines 149-181) | Relative `..` imports walk up from the source file's directory with no boundary check. Resolved candidates can land **outside `repo_root`**, and the file is then opened for barrel/star-export inspection. | Guard every resolved candidate: `os.path.commonpath([candidate, self.repo_root]) == self.repo_root`. Skip or return `found=False` for paths that escape the repo boundary. |
| 4 | **Medium** | Denial-of-service via unbounded MCP responses | `mcp/tools.py` -- `export_graph`, `search_nodes`, `get_neighbors`, `get_call_chain` | `export_graph` loads every node (including full `code_str`) into memory and serialises the entire graph. `search_nodes` loads the full repo then filters in Python. On large codebases these responses can reach tens of MB, exhausting client token budgets or server memory. | Add `limit`/`offset` pagination to `search_nodes`. Cap `export_graph` at a configurable max node count. Add an `include_code: bool = False` parameter to heavy tools so callers can opt out of `code_str`. |
| 5 | **Medium** | LLM summariser sends code without auth headers | `llm/summarizer.py` lines 57-63, 94-100 | HTTP requests to the configured LLM endpoint carry only `Content-Type`. There is no `Authorization` header. If the endpoint requires authentication, calls silently fail. If the endpoint is on an untrusted network, code snippets are sent in cleartext. | Add `CODEGRAPH_LLM_API_KEY` env var. Send as `Authorization: Bearer <key>`. Log a warning at startup if `llm_endpoint` is set but `llm_api_key` is empty. Consider TLS validation. |
| 6 | **Low** | No lockfile committed -- floating dependencies | `pyproject.toml`, `.gitignore` | `uv.lock` is listed in `.gitignore`. Dependency versions use lower-bounded ranges (e.g. `tree-sitter>=0.21.0,<0.22`). A future `uv sync` could pull a compromised or incompatible release. | Remove `uv.lock` from `.gitignore` and commit it. Alternatively, pin exact versions in `pyproject.toml` and run `pip-audit` / `osv-scanner` in CI. |
| 7 | **Low** | `install.sh` pipes curl output to shell | `install.sh` line 18 | `curl -LsSf https://astral.sh/uv/install.sh \| sh` is standard for the `uv` installer but is a supply-chain risk if the upstream URL is compromised or MITM'd. | Document this trade-off. Optionally provide a checksum-verified download path or recommend users install `uv` via their OS package manager. |
| 8 | **Low** | Module-level `CONFIG` singleton vs per-call config | `config.py` line 51, `mcp/tools.py` lines 44, 64, ... | `CONFIG = load_config()` runs at import time. MCP tool functions reference this singleton. If environment variables change after import, the tools still use stale values. `GraphBuilder` correctly calls `load_config()` per invocation, but `SQLiteStore` path inside tools uses `CONFIG`. | Either remove the module-level singleton and always call `load_config()`, or document that env changes require a process restart. |
| 9 | **Info** | Output export writes to arbitrary paths | `output/json_exporter.py`, `output/networkx_exporter.py`, `cli.py` | The CLI `export` subcommand writes files under `--output-dir` (or `CODEGRAPH_OUTPUT_DIR`). There is no path-sanitisation beyond `os.path.join`. The MCP `export_graph` tool returns data in-memory (not to disk), so this only affects CLI usage. | For CLI: validate that the resolved output path is under the intended directory. For MCP: no action needed (response-only). |

---

## Threat model summary

```
Threat actor         Attack surface          Key risk
─────────────────    ─────────────────────   ─────────────────────────────
Network attacker     MCP HTTP/SSE endpoint   Full tool access (no auth)
Malicious repo       Parsed source files     Path traversal via imports;
                                             DoS via large/many files
Malicious MCP        MCP tool arguments      Arbitrary FS read via
  client                                     repo_path; large responses
Supply chain         pip/uv dependencies     Floating versions; curl|sh
```

## Recommendations (priority order)

1. **Add MCP authentication** -- even a simple shared-secret `Bearer` token blocks unauthenticated access.
2. **Allowlist `repo_path`** -- reject paths outside explicitly permitted roots.
3. **Bound import resolution to `repo_root`** -- `commonpath` guard in `ImportTracer`.
4. **Paginate / cap heavy tool responses** -- `limit`, `offset`, and optional `include_code`.
5. **Add LLM auth header** -- `CODEGRAPH_LLM_API_KEY` as `Bearer` token.
6. **Commit lockfile** -- pin reproducible builds; add dependency auditing to CI.
