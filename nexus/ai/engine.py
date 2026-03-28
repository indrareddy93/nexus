"""AI Engine — unified multi-provider LLM interface."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AIMessage:
    """A single chat message."""
    role: str  # "system" | "user" | "assistant"
    content: str

    def to_dict(self) -> dict:
        return {"role": self.role, "content": self.content}


@dataclass
class AIResponse:
    """Response from the LLM."""
    content: str
    model: str
    usage: dict[str, int] = field(default_factory=dict)
    raw: Any = None

    @property
    def prompt_tokens(self) -> int:
        return self.usage.get("prompt_tokens", self.usage.get("input_tokens", 0))

    @property
    def completion_tokens(self) -> int:
        return self.usage.get("completion_tokens", self.usage.get("output_tokens", 0))

    @property
    def total_tokens(self) -> int:
        return self.usage.get("total_tokens", self.prompt_tokens + self.completion_tokens)


class AIEngine:
    """
    Unified AI generation interface supporting multiple providers.

    Supported providers:
    - ``openai``   — OpenAI GPT-4o, GPT-4o-mini, etc.
    - ``anthropic`` — Anthropic Claude models
    - ``ollama``   — Local Ollama models (llama3, mistral, etc.)
    - ``openai_compatible`` — Any OpenAI-compatible API (Groq, Together, etc.)

    Usage::

        # OpenAI
        ai = AIEngine(provider="openai", model="gpt-4o-mini", api_key="sk-...")
        response = await ai.generate("Explain async Python in one paragraph")
        print(response.content)

        # Anthropic
        ai = AIEngine(provider="anthropic", model="claude-3-haiku-20240307", api_key="sk-ant-...")

        # Local Ollama
        ai = AIEngine(provider="ollama", model="llama3")

        # Multi-turn conversation
        history = [
            AIMessage("user", "What is Nexus?"),
            AIMessage("assistant", "Nexus is a Python ASGI framework..."),
        ]
        response = await ai.generate("Can you give an example?", messages=history)
    """

    PROVIDER_URLS: dict[str, str] = {
        "openai": "https://api.openai.com/v1/chat/completions",
        "anthropic": "https://api.anthropic.com/v1/messages",
        "ollama": "http://localhost:11434/api/chat",
        "groq": "https://api.groq.com/openai/v1/chat/completions",
        "together": "https://api.together.xyz/v1/chat/completions",
    }

    def __init__(
        self,
        provider: str = "openai",
        model: str = "gpt-4o-mini",
        api_key: str = "",
        base_url: str | None = None,
        system_prompt: str = "",
        temperature: float = 0.7,
        max_tokens: int = 2048,
        timeout: float = 120.0,
    ) -> None:
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self.base_url = base_url or self.PROVIDER_URLS.get(provider, "")
        self.system_prompt = system_prompt
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def generate(
        self,
        prompt: str,
        *,
        messages: list[AIMessage] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> AIResponse:
        """Generate a single completion."""
        msgs = self._build_messages(prompt, messages)
        payload = self._build_payload(
            msgs,
            temperature=temperature or self.temperature,
            max_tokens=max_tokens or self.max_tokens,
            **kwargs,
        )
        return await self._call_api(payload)

    async def chat(
        self,
        messages: list[AIMessage],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AIResponse:
        """Multi-turn chat completion without a new user prompt."""
        msgs = []
        if self.system_prompt:
            msgs.append({"role": "system", "content": self.system_prompt})
        msgs.extend(m.to_dict() for m in messages)
        payload = self._build_payload(
            msgs,
            temperature=temperature or self.temperature,
            max_tokens=max_tokens or self.max_tokens,
        )
        return await self._call_api(payload)

    async def generate_stream(
        self,
        prompt: str,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """
        Stream tokens from the LLM as they arrive.

        Usage::

            async for token in ai.generate_stream("Tell me a story"):
                print(token, end="", flush=True)
        """
        try:
            import httpx
        except ImportError as e:
            raise ImportError("Install httpx: pip install httpx") from e

        msgs = self._build_messages(prompt)
        payload = {
            **self._build_payload(msgs, temperature=self.temperature, max_tokens=self.max_tokens, **kwargs),
            "stream": True,
        }
        headers = self._build_headers()

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream("POST", self.base_url, json=payload, headers=headers) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line or line == "data: [DONE]":
                        continue
                    if line.startswith("data: "):
                        try:
                            chunk = json.loads(line[6:])
                            content = (
                                chunk.get("choices", [{}])[0]
                                .get("delta", {})
                                .get("content", "")
                            )
                            if content:
                                yield content
                        except json.JSONDecodeError:
                            continue

    async def embed(self, text: str) -> list[float]:
        """
        Get embeddings from the provider's embedding endpoint.

        Falls back to a simple hash-based mock if httpx is unavailable.
        """
        try:
            import httpx
        except ImportError:
            return self._mock_embedding(text)

        if self.provider == "openai":
            url = "https://api.openai.com/v1/embeddings"
            payload = {"input": text, "model": "text-embedding-3-small"}
        elif self.provider == "ollama":
            url = "http://localhost:11434/api/embeddings"
            payload = {"model": self.model, "prompt": text}
        else:
            return self._mock_embedding(text)

        headers = self._build_headers()
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        if self.provider == "ollama":
            return data.get("embedding", [])
        return data.get("data", [{}])[0].get("embedding", [])

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build_messages(
        self, prompt: str, extra: list[AIMessage] | None = None
    ) -> list[dict]:
        msgs: list[dict] = []
        if self.system_prompt:
            msgs.append({"role": "system", "content": self.system_prompt})
        if extra:
            msgs.extend(m.to_dict() for m in extra)
        msgs.append({"role": "user", "content": prompt})
        return msgs

    def _build_payload(
        self, messages: list[dict], *, temperature: float, max_tokens: int, **kwargs: Any
    ) -> dict:
        if self.provider == "anthropic":
            system_msgs = [m for m in messages if m["role"] == "system"]
            non_system = [m for m in messages if m["role"] != "system"]
            payload: dict[str, Any] = {
                "model": self.model,
                "max_tokens": max_tokens,
                "messages": non_system,
            }
            if system_msgs:
                payload["system"] = system_msgs[0]["content"]
            return payload
        return {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            **kwargs,
        }

    async def _call_api(self, payload: dict) -> AIResponse:
        try:
            import httpx
        except ImportError as e:
            raise ImportError("Install httpx for AI features: pip install httpx") from e

        headers = self._build_headers()
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(self.base_url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        return self._parse_response(data)

    def _parse_response(self, data: dict) -> AIResponse:
        if self.provider == "anthropic":
            content = data.get("content", [{}])[0].get("text", "")
            usage = {
                "prompt_tokens": data.get("usage", {}).get("input_tokens", 0),
                "completion_tokens": data.get("usage", {}).get("output_tokens", 0),
            }
        else:
            content = (
                data.get("choices", [{}])[0].get("message", {}).get("content", "")
            )
            usage = data.get("usage", {})

        return AIResponse(content=content, model=self.model, usage=usage, raw=data)

    def _build_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.provider == "anthropic":
            headers["x-api-key"] = self.api_key
            headers["anthropic-version"] = "2023-06-01"
        elif self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    @staticmethod
    def _mock_embedding(text: str, dim: int = 384) -> list[float]:
        """Deterministic mock embedding for testing without an API key."""
        import hashlib
        import math
        h = hashlib.sha256(text.encode()).digest()
        result = []
        for i in range(dim):
            byte_val = h[i % len(h)]
            result.append(math.sin(byte_val + i) * 0.1)
        mag = math.sqrt(sum(x * x for x in result))
        return [x / mag for x in result] if mag > 0 else result
