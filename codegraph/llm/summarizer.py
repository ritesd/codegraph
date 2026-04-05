"""Optional OpenAI-compatible LLM summaries and embeddings.

Supports three provider modes (auto-detected from config):
  - Local / Ollama:  no api_key, no api_version  -> /v1/... path, no auth header
  - OpenAI:          api_key set, no api_version  -> /v1/... path, Bearer token
  - Azure OpenAI:    api_key set, api_version set -> ?api-version=... query param, api-key header
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Optional

from codegraph.config import CodeGraphConfig
from codegraph.core.node import BaseNode

log = logging.getLogger("codegraph")

_PROMPT = """You are a code documentation assistant. Given the following {language} {node_type} named
"{name}", write a 1-2 sentence plain English summary of what it does. Be specific.
Do not start with "This function" or "This method". Do not repeat the name.

Code:
{code_str}

Docstring (if any):
{docstring}

Summary:
"""


def _build_request(
    endpoint: str,
    path: str,
    api_key: str,
    api_version: str,
    body: dict[str, Any],
) -> urllib.request.Request:
    """Build an HTTP request adapting to local, OpenAI, or Azure conventions."""
    base = endpoint.rstrip("/")
    headers: dict[str, str] = {"Content-Type": "application/json"}

    if api_version:
        sep = "&" if "?" in base else "?"
        url = f"{base}{path}{sep}api-version={api_version}"
        if api_key:
            headers["api-key"] = api_key
    else:
        url = f"{base}/v1{path}"
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

    return urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )


class Summarizer:
    """Chat completions and embeddings against OpenAI-compatible servers."""

    def __init__(self, config: CodeGraphConfig) -> None:
        self.config = config

    @property
    def enabled(self) -> bool:
        return bool(self.config.llm_endpoint)

    @property
    def embedding_enabled(self) -> bool:
        return bool(self.config.embedding_endpoint)

    def summarize(self, node: BaseNode) -> BaseNode:
        if not self.enabled:
            return node
        prompt = _PROMPT.format(
            language=node.language.value.lower(),
            node_type=node.node_type.value.lower(),
            name=node.name,
            code_str=node.code_str[:8000],
            docstring=node.docstring or "",
        )
        try:
            body = {
                "model": self.config.llm_model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
            }
            req = _build_request(
                endpoint=self.config.llm_endpoint,
                path="/chat/completions",
                api_key=self.config.llm_api_key,
                api_version=self.config.llm_api_version,
                body=body,
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
            text = raw["choices"][0]["message"]["content"].strip()
            sentences = text.replace("\n", " ").split(". ")
            summary = ". ".join(sentences[:2]).strip()
            if summary and not summary.endswith("."):
                summary += "."
            node.summary = summary[:500]
        except (urllib.error.URLError, TimeoutError, KeyError, IndexError, ValueError, OSError) as ex:
            log.warning("LLM summarize failed: %s", ex)
            node.summary = None
        return node

    def summarize_batch(self, nodes: list[BaseNode], max_workers: int = 4) -> list[BaseNode]:
        if not self.enabled:
            return nodes
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futs = {ex.submit(self.summarize, n): n for n in nodes}
            for fut in as_completed(futs):
                try:
                    fut.result()
                except Exception as e:  # noqa: BLE001
                    log.warning("summarize_batch worker: %s", e)
        return nodes

    def generate_embedding(self, node: BaseNode) -> Optional[list[float]]:
        if not self.embedding_enabled:
            return None
        text = f"{node.name}\n{node.docstring or ''}\n{node.summary or ''}"
        try:
            body = {"model": self.config.embedding_model, "input": text[:8000]}
            req = _build_request(
                endpoint=self.config.embedding_endpoint,
                path="/embeddings",
                api_key=self.config.embedding_api_key,
                api_version=self.config.embedding_api_version,
                body=body,
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
            return raw["data"][0]["embedding"]
        except (urllib.error.URLError, TimeoutError, KeyError, IndexError, ValueError, OSError) as ex:
            log.warning("embedding failed: %s", ex)
            return None
