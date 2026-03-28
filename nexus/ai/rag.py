"""RAG Pipeline — Retrieval-Augmented Generation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from nexus.ai.embeddings import EmbeddingEngine, SearchResult
from nexus.ai.engine import AIEngine


@dataclass
class RAGResponse:
    """Result of a RAG query."""
    answer: str
    sources: list[SearchResult]
    model: str
    usage: dict[str, int]
    query: str = ""

    def to_dict(self) -> dict:
        return {
            "answer": self.answer,
            "query": self.query,
            "model": self.model,
            "usage": self.usage,
            "sources": [s.to_dict() for s in self.sources],
        }


class RAGPipeline:
    """
    End-to-end Retrieval-Augmented Generation pipeline.

    Embeds documents into a vector store, retrieves the most relevant
    ones for each query, and uses an LLM to generate a grounded answer.

    Usage::

        ai = AIEngine(provider="openai", api_key="sk-...")
        embeddings = EmbeddingEngine()  # mock or real

        rag = RAGPipeline(ai=ai, embeddings=embeddings, top_k=3)

        # Index knowledge base
        await rag.ingest([
            {"text": "Nexus supports async routing via ASGI.", "metadata": {"source": "docs"}},
            {"text": "JWT authentication is built into Nexus auth module.", "metadata": {"source": "docs"}},
        ])

        # Query
        result = await rag.query("How does Nexus handle authentication?")
        print(result.answer)
        for source in result.sources:
            print(f"  [{source.score:.2f}] {source.text[:80]}")
    """

    DEFAULT_TEMPLATE = (
        "You are a helpful assistant. Answer the question based ONLY on the provided context.\n"
        "If the context doesn't contain enough information to answer, say so clearly.\n\n"
        "Context:\n{context}\n\n"
        "Question: {question}\n\n"
        "Answer:"
    )

    def __init__(
        self,
        ai: AIEngine,
        embeddings: EmbeddingEngine,
        *,
        prompt_template: str | None = None,
        top_k: int = 5,
        score_threshold: float = 0.0,
    ) -> None:
        self.ai = ai
        self.embeddings = embeddings
        self.template = prompt_template or self.DEFAULT_TEMPLATE
        self.top_k = top_k
        self.score_threshold = score_threshold

    async def ingest(self, documents: list[dict[str, Any]]) -> int:
        """Add documents to the knowledge base. Returns count ingested."""
        return await self.embeddings.add_documents(documents)

    async def ingest_text(self, text: str, *, metadata: dict | None = None) -> None:
        """Add a single text chunk to the knowledge base."""
        await self.embeddings.add_text(text, metadata=metadata)

    async def query(self, question: str, *, top_k: int | None = None) -> RAGResponse:
        """
        Retrieve relevant context and generate a grounded answer.

        Parameters
        ----------
        question:  The natural-language question.
        top_k:     Override the default number of retrieved documents.
        """
        k = top_k if top_k is not None else self.top_k
        sources = await self.embeddings.search(
            question, top_k=k, threshold=self.score_threshold
        )

        if not sources:
            context = "No relevant context found."
        else:
            context = "\n\n".join(
                f"[Source {i + 1}] {s.text}" for i, s in enumerate(sources)
            )

        prompt = self.template.format(context=context, question=question)
        response = await self.ai.generate(prompt)

        return RAGResponse(
            answer=response.content,
            sources=sources,
            model=response.model,
            usage=response.usage,
            query=question,
        )

    async def batch_query(self, questions: list[str]) -> list[RAGResponse]:
        """Run multiple queries sequentially."""
        return [await self.query(q) for q in questions]

    def clear_knowledge_base(self) -> None:
        """Remove all documents from the vector store."""
        self.embeddings.clear()

    def stats(self) -> dict[str, Any]:
        return {
            "documents": self.embeddings.count(),
            "top_k": self.top_k,
            "ai_model": self.ai.model,
            "embedding_provider": self.embeddings.provider,
        }
