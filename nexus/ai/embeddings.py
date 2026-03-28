"""Embedding engine — in-memory vector store with cosine similarity search."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SearchResult:
    """A document retrieved by similarity search."""
    text: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)
    doc_id: str = ""

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "score": round(self.score, 4),
            "metadata": self.metadata,
            "doc_id": self.doc_id,
        }


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Pure-Python cosine similarity — no numpy required."""
    if len(a) != len(b):
        raise ValueError(f"Vector dimension mismatch: {len(a)} vs {len(b)}")
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def _normalize(vec: list[float]) -> list[float]:
    mag = math.sqrt(sum(x * x for x in vec))
    if mag == 0:
        return vec
    return [x / mag for x in vec]


class EmbeddingEngine:
    """
    In-memory vector store with semantic similarity search.

    Can use real embeddings (via httpx to OpenAI/Ollama) or fall back to
    deterministic mock embeddings for testing and offline use.

    Usage::

        engine = EmbeddingEngine()  # uses mock embeddings

        # Or with a real provider:
        engine = EmbeddingEngine(provider="openai", api_key="sk-...", model="text-embedding-3-small")

        # Index documents
        await engine.add_documents([
            {"text": "Python is a high-level programming language", "metadata": {"source": "wiki"}},
            {"text": "Nexus is a fast async Python web framework", "metadata": {"source": "docs"}},
        ])

        # Search
        results = await engine.search("What is Python?", top_k=3)
        for r in results:
            print(f"{r.score:.3f} — {r.text}")
    """

    def __init__(
        self,
        provider: str = "mock",
        model: str = "text-embedding-3-small",
        api_key: str = "",
        embedding_dim: int = 384,
    ) -> None:
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self.embedding_dim = embedding_dim
        self._docs: list[dict[str, Any]] = []        # {"text", "metadata", "doc_id"}
        self._vectors: list[list[float]] = []

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------

    async def add_documents(self, documents: list[dict[str, Any]]) -> int:
        """
        Add documents to the vector store.

        Each document must have a ``"text"`` key. Optional ``"metadata"`` dict
        and ``"doc_id"`` are preserved and returned in search results.

        Returns the number of documents added.
        """
        added = 0
        for doc in documents:
            text = doc.get("text", "")
            if not text:
                continue
            vec = await self._embed(text)
            self._docs.append({
                "text": text,
                "metadata": doc.get("metadata", {}),
                "doc_id": doc.get("doc_id", str(len(self._docs))),
            })
            self._vectors.append(_normalize(vec))
            added += 1
        return added

    async def add_text(self, text: str, *, metadata: dict | None = None, doc_id: str | None = None) -> None:
        """Convenience method to add a single text string."""
        await self.add_documents([{"text": text, "metadata": metadata or {}, "doc_id": doc_id or ""}])

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    async def search(self, query: str, *, top_k: int = 5, threshold: float = 0.0) -> list[SearchResult]:
        """
        Find the *top_k* most similar documents to *query*.

        Parameters
        ----------
        query:     The search query string.
        top_k:     Maximum number of results to return.
        threshold: Minimum cosine similarity score (0.0–1.0).
        """
        if not self._vectors:
            return []

        q_vec = _normalize(await self._embed(query))
        scores = [
            (i, _cosine_similarity(q_vec, doc_vec))
            for i, doc_vec in enumerate(self._vectors)
        ]
        scores.sort(key=lambda x: x[1], reverse=True)

        results: list[SearchResult] = []
        for idx, score in scores[:top_k]:
            if score < threshold:
                continue
            doc = self._docs[idx]
            results.append(
                SearchResult(
                    text=doc["text"],
                    score=score,
                    metadata=doc["metadata"],
                    doc_id=doc["doc_id"],
                )
            )
        return results

    def clear(self) -> None:
        """Remove all indexed documents."""
        self._docs.clear()
        self._vectors.clear()

    def count(self) -> int:
        return len(self._docs)

    def stats(self) -> dict[str, Any]:
        return {
            "documents": len(self._docs),
            "provider": self.provider,
            "model": self.model,
            "embedding_dim": self.embedding_dim,
        }

    # ------------------------------------------------------------------
    # Embedding backend
    # ------------------------------------------------------------------

    async def _embed(self, text: str) -> list[float]:
        if self.provider == "mock" or not self.api_key:
            return self._mock_embedding(text)

        try:
            import httpx
        except ImportError:
            return self._mock_embedding(text)

        if self.provider == "openai":
            url = "https://api.openai.com/v1/embeddings"
            payload = {"input": text, "model": self.model}
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                return resp.json()["data"][0]["embedding"]

        elif self.provider == "ollama":
            url = "http://localhost:11434/api/embeddings"
            payload = {"model": self.model, "prompt": text}
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                return resp.json()["embedding"]

        return self._mock_embedding(text)

    def _mock_embedding(self, text: str) -> list[float]:
        """Deterministic hash-based mock embedding for testing."""
        import hashlib

        h = hashlib.sha256(text.encode()).digest()
        result = []
        for i in range(self.embedding_dim):
            byte_val = h[i % len(h)]
            result.append(math.sin(byte_val + i * 0.1) * 0.5 + math.cos(i * 0.05) * 0.5)
        return result
