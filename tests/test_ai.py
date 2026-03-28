"""Tests for nexus/ai — embeddings, RAG (using mock provider)."""

import pytest
from nexus.ai.engine import AIEngine, AIMessage
from nexus.ai.embeddings import EmbeddingEngine, _cosine_similarity
from nexus.ai.rag import RAGPipeline


class TestEmbeddingEngine:
    @pytest.mark.asyncio
    async def test_add_and_search(self):
        engine = EmbeddingEngine()  # uses mock embeddings
        await engine.add_documents([
            {"text": "Python is a programming language", "metadata": {"src": "wiki"}},
            {"text": "Nexus is a web framework", "metadata": {"src": "docs"}},
            {"text": "The sky is blue", "metadata": {"src": "nature"}},
        ])
        assert engine.count() == 3
        results = await engine.search("Python programming", top_k=2)
        assert len(results) <= 2
        for r in results:
            assert 0.0 <= r.score <= 1.0

    @pytest.mark.asyncio
    async def test_search_empty(self):
        engine = EmbeddingEngine()
        results = await engine.search("anything")
        assert results == []

    @pytest.mark.asyncio
    async def test_clear(self):
        engine = EmbeddingEngine()
        await engine.add_text("test doc")
        engine.clear()
        assert engine.count() == 0

    @pytest.mark.asyncio
    async def test_add_text_shortcut(self):
        engine = EmbeddingEngine()
        await engine.add_text("short text", metadata={"source": "test"})
        assert engine.count() == 1

    def test_cosine_similarity_identical(self):
        v = [1.0, 0.0, 0.0]
        assert abs(_cosine_similarity(v, v) - 1.0) < 1e-9

    def test_cosine_similarity_orthogonal(self):
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert abs(_cosine_similarity(a, b)) < 1e-9

    def test_stats(self):
        engine = EmbeddingEngine(provider="mock", model="test-model")
        s = engine.stats()
        assert s["provider"] == "mock"
        assert s["documents"] == 0


class TestAIEngine:
    def test_init_defaults(self):
        ai = AIEngine()
        assert ai.provider == "openai"
        assert ai.model == "gpt-4o-mini"
        assert ai.temperature == 0.7

    def test_build_headers_openai(self):
        ai = AIEngine(api_key="test-key")
        headers = ai._build_headers()
        assert headers["Authorization"] == "Bearer test-key"

    def test_build_headers_anthropic(self):
        ai = AIEngine(provider="anthropic", api_key="ant-key")
        headers = ai._build_headers()
        assert headers["x-api-key"] == "ant-key"
        assert "anthropic-version" in headers

    def test_mock_embedding_deterministic(self):
        ai = AIEngine()
        e1 = ai._mock_embedding("hello")
        e2 = ai._mock_embedding("hello")
        assert e1 == e2

    def test_mock_embedding_different_inputs(self):
        ai = AIEngine()
        e1 = ai._mock_embedding("hello")
        e2 = ai._mock_embedding("world")
        assert e1 != e2

    def test_ai_message(self):
        msg = AIMessage(role="user", content="Hi")
        d = msg.to_dict()
        assert d["role"] == "user"
        assert d["content"] == "Hi"


class TestRAGPipeline:
    @pytest.mark.asyncio
    async def test_ingest_and_stats(self):
        ai = AIEngine()
        embeddings = EmbeddingEngine()
        rag = RAGPipeline(ai=ai, embeddings=embeddings, top_k=2)

        n = await rag.ingest([
            {"text": "Nexus has a built-in ORM"},
            {"text": "Nexus supports JWT authentication"},
        ])
        assert n == 2
        s = rag.stats()
        assert s["documents"] == 2

    @pytest.mark.asyncio
    async def test_clear_knowledge_base(self):
        ai = AIEngine()
        embeddings = EmbeddingEngine()
        rag = RAGPipeline(ai=ai, embeddings=embeddings)
        await rag.ingest([{"text": "Test doc"}])
        rag.clear_knowledge_base()
        assert rag.stats()["documents"] == 0

    @pytest.mark.asyncio
    async def test_ingest_text(self):
        ai = AIEngine()
        embeddings = EmbeddingEngine()
        rag = RAGPipeline(ai=ai, embeddings=embeddings)
        await rag.ingest_text("Single text doc", metadata={"type": "note"})
        assert rag.stats()["documents"] == 1
