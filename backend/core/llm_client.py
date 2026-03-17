# Async HTTP client to llama-cpp-python server

import json
import logging
import os
import re
from typing import AsyncGenerator

import httpx

logger = logging.getLogger(__name__)


class LLMClient:
    """Async client for a llama-cpp-python server (OpenAI-compatible API)."""

    def __init__(
        self,
        base_url: str | None = None,
        timeout: int = 120,
    ) -> None:
        host = os.getenv("LLAMA_SERVER_HOST", "localhost")
        port = os.getenv("LLAMA_SERVER_PORT", "8080")
        self.base_url = base_url or f"http://{host}:{port}"
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    # -- async context manager --------------------------------------------------

    async def __aenter__(self) -> "LLMClient":
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(self.timeout),
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:  # noqa: ANN001
        if self._client:
            await self._client.aclose()
            self._client = None

    # -- helpers ----------------------------------------------------------------

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError(
                "LLMClient must be used as an async context manager "
                "(async with LLMClient() as client: ...)"
            )
        return self._client

    @staticmethod
    def _strip_think_tags(text: str) -> str:
        """Remove <think>…</think> blocks emitted by some Qwen models."""
        return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)

    # -- public API -------------------------------------------------------------

    async def stream_chat(
        self,
        messages: list[dict],
        max_tokens: int = 1024,
        temperature: float = 0.3,
        top_p: float = 0.95,
        repeat_penalty: float = 1.1,
    ) -> AsyncGenerator[str, None]:
        """Stream chat completion tokens via SSE."""
        client = self._ensure_client()

        payload = {
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "repeat_penalty": repeat_penalty,
            "stream": True,
        }

        try:
            async with client.stream(
                "POST",
                "/v1/chat/completions",
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[len("data: "):]
                    if data.strip() == "[DONE]":
                        break
                    try:
                        chunk_json = json.loads(data)
                        content = (
                            chunk_json.get("choices", [{}])[0]
                            .get("delta", {})
                            .get("content", "")
                        )
                        if content:
                            content = self._strip_think_tags(content)
                            if content:
                                yield content
                    except json.JSONDecodeError:
                        logger.warning("Skipping malformed SSE chunk: %s", data)

        except httpx.TimeoutException:
            logger.error("LLM request timed out after %ds", self.timeout)
            yield "[error: LLM request timed out]"
        except httpx.ConnectError as exc:
            logger.error("Cannot connect to LLM server at %s: %s", self.base_url, exc)
            yield "[error: cannot connect to LLM server]"
        except httpx.HTTPStatusError as exc:
            logger.error("LLM server returned HTTP %s", exc.response.status_code)
            yield f"[error: LLM server returned HTTP {exc.response.status_code}]"

    async def health_check(self) -> dict:
        """Check LLM server health. Never raises."""
        try:
            client = self._ensure_client()
            resp = await client.get("/health")
            resp.raise_for_status()
            body = resp.json()
            return {"status": "ok", "model": body.get("model", "unknown")}
        except Exception as exc:
            logger.error("LLM health check failed: %s", exc)
            return {"status": "error", "detail": str(exc)}

    async def get_model_info(self) -> dict:
        """Fetch model metadata from /v1/models. Never raises."""
        try:
            client = self._ensure_client()
            resp = await client.get("/v1/models")
            resp.raise_for_status()
            body = resp.json()
            models = body.get("data", [])
            if models:
                model = models[0]
                return {"id": model.get("id"), "meta": model}
            return {"id": None, "meta": {}}
        except Exception as exc:
            logger.error("Failed to fetch model info: %s", exc)
            return {"id": None, "meta": {}, "error": str(exc)}
