"""Runtime configuration loaded from .env files and environment variables.

Single source of truth for CodeGraph settings. Does NOT define node shapes or I/O behavior.

Load order (later overrides earlier):
  1. ~/.codegraph/.env   -- global user defaults
  2. ./.env              -- project-specific overrides
  3. Real env vars       -- explicit shell exports always win
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

_CODEGRAPH_DIR = os.path.join(os.path.expanduser("~"), ".codegraph")

load_dotenv(os.path.join(_CODEGRAPH_DIR, ".env"), override=False)
load_dotenv(override=True)


@dataclass
class CodeGraphConfig:
    sqlite_path: str
    vector_db_url: str
    vector_db_type: str
    vector_collection: str
    llm_endpoint: str
    llm_model: str
    default_mode: str
    include_external_nodes: bool
    max_file_size_kb: int
    default_export_format: str
    output_dir: str
    mcp_host: str
    mcp_port: int
    mcp_transport: str


def _default_sqlite_path() -> str:
    return os.path.join(_CODEGRAPH_DIR, "codegraph.db")


def load_config() -> CodeGraphConfig:
    """Load configuration from CODEGRAPH_* environment variables."""
    return CodeGraphConfig(
        sqlite_path=os.environ.get("CODEGRAPH_SQLITE_PATH", _default_sqlite_path()),
        vector_db_url=os.environ.get("CODEGRAPH_VECTOR_DB_URL", ""),
        vector_db_type=os.environ.get("CODEGRAPH_VECTOR_DB_TYPE", ""),
        vector_collection=os.environ.get("CODEGRAPH_VECTOR_COLLECTION", "codegraph"),
        llm_endpoint=os.environ.get("CODEGRAPH_LLM_ENDPOINT", ""),
        llm_model=os.environ.get("CODEGRAPH_LLM_MODEL", "mistral:7b-instruct-q4_K_M"),
        default_mode=os.environ.get("CODEGRAPH_DEFAULT_MODE", "full"),
        include_external_nodes=os.environ.get("CODEGRAPH_INCLUDE_EXTERNAL_NODES", "true").lower()
        in ("1", "true", "yes"),
        max_file_size_kb=int(os.environ.get("CODEGRAPH_MAX_FILE_SIZE_KB", "500")),
        default_export_format=os.environ.get("CODEGRAPH_DEFAULT_EXPORT_FORMAT", "json"),
        output_dir=os.environ.get("CODEGRAPH_OUTPUT_DIR", "./codegraph_output"),
        mcp_host=os.environ.get("CODEGRAPH_MCP_HOST", "127.0.0.1"),
        mcp_port=int(os.environ.get("CODEGRAPH_MCP_PORT", "8765")),
        mcp_transport=os.environ.get("CODEGRAPH_MCP_TRANSPORT", "sse"),
    )


CONFIG = load_config()
