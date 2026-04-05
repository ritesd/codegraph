"""Command-line interface for CodeGraph (parse, query, export, serve)."""

from __future__ import annotations

import argparse
import json
import logging
import os

from codegraph.config import CONFIG, load_config
from codegraph.core.graph import GraphBuilder
from codegraph.llm.summarizer import Summarizer
from codegraph.output.json_exporter import JsonExporter
from codegraph.output.networkx_exporter import NetworkXExporter
from codegraph.storage.sqlite_store import SQLiteStore
from codegraph.storage.vector_store import VectorStore


def _setup_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")


def main() -> None:
    _setup_logging()
    parser = argparse.ArgumentParser(prog="codegraph")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_parse = sub.add_parser("parse", help="Parse a repository")
    p_parse.add_argument("repo_path")
    p_parse.add_argument("--mode", choices=("full", "incremental"), default=CONFIG.default_mode)
    p_parse.add_argument("--export", choices=("json", "networkx", "none"), default="none")
    p_parse.add_argument("--export-fmt", choices=("graph", "flat"), default="graph")
    p_parse.add_argument("--output-dir", default=CONFIG.output_dir)
    p_parse.add_argument("--llm-endpoint", default="")
    p_parse.add_argument("--vector-db-url", default="")

    p_query = sub.add_parser("query", help="Query nodes by name")
    p_query.add_argument("repo")
    p_query.add_argument("node_name")
    p_query.add_argument("--show-edges", action="store_true")
    p_query.add_argument("--show-code", action="store_true")
    p_query.add_argument("--min-confidence", type=float, default=0.0)

    p_exp = sub.add_parser("export", help="Export stored graph")
    p_exp.add_argument("repo")
    p_exp.add_argument("--fmt", choices=("json", "networkx"), default="json")
    p_exp.add_argument("--json-mode", choices=("flat", "graph"), default="graph")
    p_exp.add_argument("--output-dir", default=CONFIG.output_dir)

    p_serve = sub.add_parser("serve", help="Run MCP server")
    p_serve.add_argument("--host", default=CONFIG.mcp_host)
    p_serve.add_argument("--port", type=int, default=CONFIG.mcp_port)
    p_serve.add_argument("--transport", choices=("stdio", "sse", "streamable-http"), default=CONFIG.mcp_transport)

    sub.add_parser("list-repos", help="List repos in DB")

    p_stats = sub.add_parser("stats", help="Repo statistics")
    p_stats.add_argument("repo")

    args = parser.parse_args()
    cfg = load_config()
    if args.cmd == "parse":
        if getattr(args, "llm_endpoint", ""):
            os.environ["CODEGRAPH_LLM_ENDPOINT"] = args.llm_endpoint
            cfg = load_config()
        if getattr(args, "vector_db_url", ""):
            os.environ["CODEGRAPH_VECTOR_DB_URL"] = args.vector_db_url
            cfg = load_config()
        gb = GraphBuilder(cfg)
        g = gb.build(args.repo_path, mode=args.mode)
        summer = Summarizer(cfg)
        if summer.enabled:
            summer.summarize_batch(g.nodes)
        vec = VectorStore(cfg)
        if vec.enabled:
            for n in g.nodes:
                emb = summer.generate_embedding(n)
                if emb:
                    vec.upsert_node(n, emb)
        if args.export == "json":
            out = os.path.join(args.output_dir, f"{g.repo}.json")
            JsonExporter().to_file(g, out, mode=args.export_fmt)
        elif args.export == "networkx":
            out = os.path.join(args.output_dir, f"{g.repo}.gexf")
            NetworkXExporter().to_file(g, out, fmt="gexf")
        print(json.dumps({"repo": g.repo, "nodes": len(g.nodes), "errors": len(g.parse_errors)}))
    elif args.cmd == "query":
        store = SQLiteStore(cfg.sqlite_path)
        store.init_db()
        nodes = store.get_by_name(args.node_name, args.repo)
        for n in nodes:
            d = n.to_dict()
            if not args.show_code:
                d.pop("code_str", None)
            if not args.show_edges:
                d.pop("edges", None)
                d.pop("calls", None)
                d.pop("called_by", None)
            print(json.dumps(d, indent=2))
    elif args.cmd == "export":
        store = SQLiteStore(cfg.sqlite_path)
        nodes = store.get_by_repo(args.repo)
        from codegraph.core.graph import CodeGraph

        cg = CodeGraph(
            repo=args.repo,
            repo_root="",
            git_hash="",
            nodes=nodes,
            language_summary={},
            parse_errors=[],
            parsed_at="",
        )
        if args.fmt == "json":
            JsonExporter().to_file(cg, os.path.join(args.output_dir, f"{args.repo}.json"), mode=args.json_mode)
        else:
            NetworkXExporter().to_file(cg, os.path.join(args.output_dir, f"{args.repo}.gexf"))
    elif args.cmd == "serve":
        from codegraph.mcp.server import main as serve_main

        serve_main(host=args.host, port=args.port, transport=args.transport)
    elif args.cmd == "list-repos":
        store = SQLiteStore(cfg.sqlite_path)
        for r in store.list_repos():
            print(r)
    elif args.cmd == "stats":
        store = SQLiteStore(cfg.sqlite_path)
        nodes = store.get_by_repo(args.repo)
        by_type: dict[str, int] = {}
        by_lang: dict[str, int] = {}
        unresolved = 0
        total_e = 0
        conf_sum = 0.0
        for n in nodes:
            by_type[n.node_type.value] = by_type.get(n.node_type.value, 0) + 1
            by_lang[n.language.value] = by_lang.get(n.language.value, 0) + 1
            for e in n.edges:
                total_e += 1
                conf_sum += e.confidence
                if not e.resolved:
                    unresolved += 1
        avg_c = conf_sum / total_e if total_e else 0.0
        print(
            json.dumps(
                {
                    "node_count": len(nodes),
                    "by_type": by_type,
                    "by_language": by_lang,
                    "unresolved_edge_ratio": (unresolved / total_e) if total_e else 0.0,
                    "avg_confidence": avg_c,
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
