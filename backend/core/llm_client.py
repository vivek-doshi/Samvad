# Async HTTP client to llama-cpp-python server
# Note 1: This module provides the LLMClient class — a thin async wrapper that
# communicates with the local llama-cpp-python model server over HTTP.
# llama-cpp-python runs quantised LLM models (like Arthvidya) locally and
# exposes an OpenAI-compatible REST API, so the same client code works whether
# the backend model is local or remote.

import json
# Note 2: 'json' parses the Server-Sent Events (SSE) payload from the LLM server.
# Each SSE line carries a JSON-encoded delta (a fragment of the generated text).
import logging
import os
import re
# Note 3: 're' (regular expressions) is used here to strip <think>...</think>
# blocks that some Qwen/reasoning models include before their final answer.
from typing import AsyncGenerator
# Note 4: AsyncGenerator[str, None] is the return type of stream_chat(). It means
# this function yields 'str' values one at a time and never sends a final value
# when it finishes. The 'async for token in ...' loop consumes it chunk-by-chunk.

import httpx
# Note 5: httpx is an async HTTP client library for Python — the async equivalent
# of the popular 'requests' library. Using async HTTP is important in a FastAPI
# server so that waiting for the LLM to respond does not block other requests.

logger = logging.getLogger(__name__)


class LLMClient:
    """Async client for a llama-cpp-python server (OpenAI-compatible API)."""
    # Note 6: This class follows the async context manager protocol (__aenter__
    # and __aexit__). This means it must be used with 'async with LLMClient() as c:'
    # or, for a long-lived instance, by calling __aenter__ and __aexit__ manually
    # (as done in main.py during startup/shutdown).

    def __init__(
        self,
        base_url: str | None = None,
        timeout: int = 120,
    ) -> None:
        host = os.getenv("LLAMA_SERVER_HOST", "localhost")
        port = os.getenv("LLAMA_SERVER_PORT", "8080")
        # Note 7: 'base_url or f"http://{host}:{port}"' — the 'or' short-circuit
        # means: use base_url if it was provided (and is truthy), otherwise build
        # a default URL from the environment variables. This allows callers to
        # override the URL in unit tests without touching environment variables.
        self.base_url = base_url or f"http://{host}:{port}"
        self.timeout = timeout
        # Note 8: The httpx client is stored as None until __aenter__ is called.
        # The 'httpx.AsyncClient | None' type annotation documents this lifecycle:
        # None = not yet connected, AsyncClient = ready to make requests.
        self._client: httpx.AsyncClient | None = None

    # -- async context manager --------------------------------------------------
    # Note 9: '__aenter__' is called when the 'async with' block is entered. It
    # creates the httpx.AsyncClient, which opens a connection pool. The method
    # returns 'self' so callers can write: 'async with LLMClient() as client:'.

    async def __aenter__(self) -> "LLMClient":
        # Note 10: httpx.Timeout(seconds) sets the maximum time to wait for the
        # server to respond. LLMs are slow — 120 seconds (2 minutes) is a
        # reasonable default for a local model generating up to 2048 tokens.
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(self.timeout),
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:  # noqa: ANN001
        # Note 11: aclose() gracefully closes the underlying TCP connection pool.
        # Setting self._client = None afterward prevents accidental use of a
        # closed client, which would raise a cryptic RuntimeError.
        if self._client:
            await self._client.aclose()
            self._client = None

    # -- helpers ----------------------------------------------------------------
    # Note 12: _ensure_client() is a guard helper used at the start of every
    # public method. It raises a clear RuntimeError if someone forgets to use
    # the client as a context manager. This prevents confusing AttributeError
    # messages from deep inside the httpx library.

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
        # Note 13: re.DOTALL makes '.' match newlines too, so a <think> block
        # that spans multiple lines is captured and removed in one pass.
        # '.*?' is a non-greedy match — it stops at the FIRST </think>, not
        # the last, which is important if a response contains multiple blocks.
        # Note: <think> tags are used by some reasoning models (e.g., Qwen)
        # as a "scratchpad" before the final answer — they should be stripped
        # before sending the response to the frontend.
        return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)

    # -- public API -------------------------------------------------------------
    # Note 14: stream_chat() uses Server-Sent Events (SSE) — a protocol where
    # the server sends a stream of text lines prefixed with 'data: ', allowing
    # the client to display tokens as they are generated rather than waiting for
    # the entire response. The Angular frontend reads these via the Fetch API.

    async def stream_chat(
        self,
        messages: list[dict],
        max_tokens: int = 1024,
        temperature: float = 0.3,
        # Note 15: temperature controls randomness. Low (0.2-0.4) = more focused
        # and factual, ideal for finance. High (0.8-1.0) = more creative/varied.
        top_p: float = 0.95,
        # Note 16: top_p (nucleus sampling) limits token selection to the smallest
        # set of tokens whose cumulative probability reaches 95%. Together with
        # temperature, it prevents very unlikely (nonsensical) tokens from appearing.
        repeat_penalty: float = 1.1,
        # Note 17: repeat_penalty penalises the model for repeating the same
        # token or phrase. Values slightly above 1.0 (like 1.1) reduce repetitive
        # loops without making the output feel artificially restricted.
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
                # Note 18: aiter_lines() is a non-blocking line iterator. Each
                # SSE message arrives as a 'data: <json>' line, followed by a
                # blank line. We check the 'data: ' prefix and skip blank lines.
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[len("data: "):]
                    # Note 19: '[DONE]' is a sentinel token sent by the llama-cpp
                    # server when token generation is complete. We break out of
                    # the loop here so we do not try to JSON-parse the sentinel.
                    if data.strip() == "[DONE]":
                        break
                    try:
                        chunk_json = json.loads(data)
                        # Note 20: The OpenAI-compatible SSE format nests the
                        # generated token inside choices[0].delta.content.
                        # We safely use .get() at each level to avoid KeyErrors
                        # if a malformed chunk is missing any of these fields.
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
            # Note 21: TimeoutException fires when the model server takes longer
            # than 'self.timeout' seconds. We yield an inline error token so the
            # frontend displays a message instead of spinning indefinitely.
            logger.error("LLM request timed out after %ds", self.timeout)
            yield "[error: LLM request timed out]"
        except httpx.ConnectError as exc:
            # Note 22: ConnectError means the model server is not reachable at
            # all (e.g. llama-cpp-python container is not running or crashed).
            logger.error("Cannot connect to LLM server at %s: %s", self.base_url, exc)
            yield "[error: cannot connect to LLM server]"
        except httpx.HTTPStatusError as exc:
            # Note 23: HTTPStatusError fires when the server returns a non-2xx
            # status code (e.g. 503 Service Unavailable if the model is still
            # loading). We include the status code in the error token.
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
