"""Tests for nexus/orm — fields, models, manager, query builder."""

import pytest
from nexus.orm import Model, IntField, StrField, BoolField, DateTimeField, JSONField, ModelManager


# ---------------------------------------------------------------------------
# Model definition
# ---------------------------------------------------------------------------

class Article(Model):
    __table__ = "articles"
    id = IntField(primary_key=True)
    title = StrField(max_length=200, nullable=False)
    body = StrField()
    published = BoolField(default=False)
    tags = JSONField()
    created_at = DateTimeField(auto_now_add=True)


class Tag(Model):
    __table__ = "tags"
    id = IntField(primary_key=True)
    name = StrField(unique=True, nullable=False)


# ---------------------------------------------------------------------------
# Field tests
# ---------------------------------------------------------------------------

class TestFields:
    def test_int_field(self):
        a = Article(title="Test")
        a.id = 5
        assert a.id == 5

    def test_str_field_default(self):
        a = Article(title="Hello")
        assert a.title == "Hello"
        assert a.published is False

    def test_bool_field(self):
        a = Article(title="X", published=True)
        assert a.published is True

    def test_json_field(self):
        from nexus.orm.fields import JSONField
        f = JSONField()
        assert f.python_to_db({"k": "v"}) == '{"k": "v"}'
        assert f.db_to_python('{"k": "v"}') == {"k": "v"}
        assert f.db_to_python(None) is None

    def test_datetime_field_auto_now_add(self):
        a = Article(title="Auto")
        assert a.created_at is not None


class TestModelMeta:
    def test_table_name(self):
        assert Article.__table__ == "articles"

    def test_fields_collected(self):
        assert "id" in Article._fields
        assert "title" in Article._fields
        assert "published" in Article._fields

    def test_to_dict(self):
        a = Article(title="Dict Test", published=True)
        d = a.to_dict()
        assert d["title"] == "Dict Test"
        assert d["published"] is True

    def test_create_table_sql(self):
        sql = Article.create_table_sql()
        assert "CREATE TABLE IF NOT EXISTS" in sql
        assert "articles" in sql
        assert "title" in sql

    def test_repr(self):
        a = Article(id=7, title="R")
        assert "7" in repr(a)


# ---------------------------------------------------------------------------
# Manager tests
# ---------------------------------------------------------------------------

@pytest.fixture
async def db():
    manager = ModelManager("sqlite:///:memory:")
    await manager.connect()
    await manager.create_tables(Article, Tag)
    yield manager
    await manager.close()


class TestModelManager:
    @pytest.mark.asyncio
    async def test_create_and_get(self, db):
        a = await db.create(Article, title="First Post", body="Body text")
        assert a.id is not None
        fetched = await db.get(Article, a.id)
        assert fetched is not None
        assert fetched.title == "First Post"

    @pytest.mark.asyncio
    async def test_save_update(self, db):
        a = await db.create(Article, title="Original")
        a.title = "Updated"
        await db.save(a)
        fetched = await db.get(Article, a.id)
        assert fetched.title == "Updated"

    @pytest.mark.asyncio
    async def test_delete(self, db):
        a = await db.create(Article, title="Delete Me")
        pk = a.id
        await db.delete(a)
        assert await db.get(Article, pk) is None

    @pytest.mark.asyncio
    async def test_query_filter(self, db):
        await db.create(Article, title="Draft", published=False)
        await db.create(Article, title="Live", published=True)
        await db.create(Article, title="Also Live", published=True)

        live = await db.query(Article).filter(published=True).all()
        assert len(live) == 2
        assert all(a.published for a in live)

    @pytest.mark.asyncio
    async def test_query_order_and_limit(self, db):
        for i in range(5):
            await db.create(Article, title=f"Article {i}")
        results = await db.query(Article).order_by("id", desc=True).limit(2).all()
        assert len(results) == 2
        assert results[0].id > results[1].id

    @pytest.mark.asyncio
    async def test_count(self, db):
        await db.create(Article, title="A")
        await db.create(Article, title="B")
        n = await db.query(Article).count()
        assert n == 2

    @pytest.mark.asyncio
    async def test_get_or_create(self, db):
        tag, created = await db.get_or_create(Tag, name="python")
        assert created is True
        tag2, created2 = await db.get_or_create(Tag, name="python")
        assert created2 is False
        assert tag.id == tag2.id

    @pytest.mark.asyncio
    async def test_query_first(self, db):
        await db.create(Article, title="Only")
        result = await db.query(Article).first()
        assert result is not None
        assert result.title == "Only"

    @pytest.mark.asyncio
    async def test_bulk_create(self, db):
        articles = [Article(title=f"Bulk {i}") for i in range(3)]
        await db.bulk_create(articles)
        n = await db.query(Article).count()
        assert n == 3

    @pytest.mark.asyncio
    async def test_get_404(self, db):
        with pytest.raises(ValueError, match="not found"):
            await db.get_or_404(Article, 9999)
