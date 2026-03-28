"""Async Model Manager — CRUD + chainable query builder."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any, TypeVar

from nexus.orm.base import Model
from nexus.orm.fields import DateTimeField

T = TypeVar("T", bound=Model)


class AsyncSQLiteConnection:
    """
    Thin async-compatible wrapper around stdlib sqlite3.

    For production, swap this for aiosqlite or asyncpg by overriding the
    ``AsyncSQLiteConnection`` in the ModelManager.
    """

    def __init__(self, database: str) -> None:
        self.database = database
        self._conn: sqlite3.Connection | None = None

    async def connect(self) -> None:
        self._conn = sqlite3.connect(self.database, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        # Enable WAL mode for better concurrent read performance
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")

    async def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    async def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        assert self._conn is not None, "Not connected — call await db.connect() first"
        cur = self._conn.execute(sql, params)
        self._conn.commit()
        return cur

    async def executemany(self, sql: str, params_list: list[tuple]) -> None:
        assert self._conn is not None
        self._conn.executemany(sql, params_list)
        self._conn.commit()

    async def fetchall(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        cur = await self.execute(sql, params)
        return cur.fetchall()

    async def fetchone(self, sql: str, params: tuple = ()) -> sqlite3.Row | None:
        cur = await self.execute(sql, params)
        return cur.fetchone()

    def is_connected(self) -> bool:
        return self._conn is not None


class QueryBuilder:
    """
    Chainable, lazy query builder for a Model class.

    Example::

        active_admins = await (
            db.query(User)
            .filter(is_active=True, role="admin")
            .order_by("created_at", desc=True)
            .limit(20)
            .offset(0)
            .all()
        )
    """

    def __init__(self, manager: ModelManager, model_cls: type[T]) -> None:
        self._manager = manager
        self._model = model_cls
        self._where: list[str] = []
        self._params: list[Any] = []
        self._order: str | None = None
        self._limit: int | None = None
        self._offset: int | None = None
        self._select: str = "*"

    # ------------------------------------------------------------------
    # Filtering
    # ------------------------------------------------------------------

    def filter(self, **conditions: Any) -> QueryBuilder:
        """
        Filter by keyword conditions.

        Supported operators (via double-underscore suffix)::

            filter(age__gt=18)          # age > 18
            filter(name__like="%Alice%") # name LIKE '%Alice%'
            filter(id__in=[1, 2, 3])    # id IN (1, 2, 3)
            filter(status__ne="banned") # status != 'banned'
        """
        _op_map = {
            "gt": ">",
            "lt": "<",
            "gte": ">=",
            "lte": "<=",
            "ne": "!=",
            "like": "LIKE",
            "ilike": "LIKE",
            "in": "IN",
            "not_in": "NOT IN",
            "is_null": "IS NULL",
            "is_not_null": "IS NOT NULL",
        }

        for col, val in conditions.items():
            op = "="
            if "__" in col:
                col, op_name = col.rsplit("__", 1)
                op = _op_map.get(op_name, "=")

            if op in ("IN", "NOT IN"):
                placeholders = ",".join("?" for _ in val)
                self._where.append(f"{col} {op} ({placeholders})")
                self._params.extend(val)
            elif op in ("IS NULL", "IS NOT NULL"):
                self._where.append(f"{col} {op}")
            else:
                self._where.append(f"{col} {op} ?")
                self._params.append(val)

        return self

    def where(self, condition: str, *params: Any) -> QueryBuilder:
        """Raw SQL WHERE condition — use with care."""
        self._where.append(condition)
        self._params.extend(params)
        return self

    def order_by(self, column: str, *, desc: bool = False) -> QueryBuilder:
        direction = "DESC" if desc else "ASC"
        self._order = f"{column} {direction}"
        return self

    def limit(self, n: int) -> QueryBuilder:
        self._limit = n
        return self

    def offset(self, n: int) -> QueryBuilder:
        self._offset = n
        return self

    # ------------------------------------------------------------------
    # Terminal methods
    # ------------------------------------------------------------------

    def _build_select_sql(self) -> tuple[str, tuple]:
        sql = f"SELECT {self._select} FROM {self._model.__table__}"
        if self._where:
            sql += " WHERE " + " AND ".join(self._where)
        if self._order:
            sql += f" ORDER BY {self._order}"
        if self._limit is not None:
            sql += f" LIMIT {self._limit}"
        if self._offset is not None:
            sql += f" OFFSET {self._offset}"
        return sql, tuple(self._params)

    async def all(self) -> list[T]:
        sql, params = self._build_select_sql()
        rows = await self._manager.db.fetchall(sql, params)
        return [self._manager._row_to_model(self._model, row) for row in rows]

    async def first(self) -> T | None:
        self._limit = 1
        results = await self.all()
        return results[0] if results else None

    async def last(self) -> T | None:
        if not self._order:
            pk = next((n for n, f in self._model._fields.items() if f.primary_key), "id")
            self._order = f"{pk} DESC"
        self._limit = 1
        results = await self.all()
        return results[0] if results else None

    async def count(self) -> int:
        sql = f"SELECT COUNT(*) as cnt FROM {self._model.__table__}"
        if self._where:
            sql += " WHERE " + " AND ".join(self._where)
        row = await self._manager.db.fetchone(sql, tuple(self._params))
        return row["cnt"] if row else 0

    async def exists(self) -> bool:
        return (await self.count()) > 0

    async def delete(self) -> int:
        sql = f"DELETE FROM {self._model.__table__}"
        if self._where:
            sql += " WHERE " + " AND ".join(self._where)
        cur = await self._manager.db.execute(sql, tuple(self._params))
        return cur.rowcount

    async def update(self, **values: Any) -> int:
        set_clauses = [f"{k} = ?" for k in values]
        set_params = list(values.values())
        sql = f"UPDATE {self._model.__table__} SET {', '.join(set_clauses)}"
        if self._where:
            sql += " WHERE " + " AND ".join(self._where)
        cur = await self._manager.db.execute(sql, tuple(set_params) + tuple(self._params))
        return cur.rowcount


class ModelManager:
    """
    Async database manager.

    Usage::

        from nexus.orm import ModelManager, Model, IntField, StrField, DateTimeField

        class User(Model):
            id = IntField(primary_key=True)
            name = StrField(nullable=False)
            email = StrField(unique=True)
            created_at = DateTimeField(auto_now_add=True)

        db = ModelManager("sqlite:///app.db")
        await db.connect()
        await db.create_tables(User)

        user = await db.create(User, name="Alice", email="alice@example.com")
        users = await db.query(User).filter(is_active=True).order_by("name").all()
    """

    def __init__(self, database_url: str = "sqlite:///nexus.db") -> None:
        self.database_url = database_url
        db_path = database_url.replace("sqlite:///", "")
        self.db = AsyncSQLiteConnection(db_path)

    async def connect(self) -> None:
        await self.db.connect()

    async def close(self) -> None:
        await self.db.close()

    async def create_tables(self, *models: type[Model]) -> None:
        for model in models:
            await self.db.execute(model.create_table_sql())
            # Create indexes
            for name, field in model._fields.items():
                if field.index and not field.primary_key:
                    idx_sql = (
                        f"CREATE INDEX IF NOT EXISTS idx_{model.__table__}_{name} "
                        f"ON {model.__table__} ({name})"
                    )
                    await self.db.execute(idx_sql)

    async def drop_tables(self, *models: type[Model]) -> None:
        for model in models:
            await self.db.execute(f"DROP TABLE IF EXISTS {model.__table__}")

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def create(self, model_cls: type[T], **kwargs: Any) -> T:
        """Create and persist a new model instance."""
        instance = model_cls(**kwargs)
        return await self.save(instance)

    async def save(self, instance: Model) -> Model:
        """Insert or replace a model instance (upsert)."""
        fields = instance._fields
        pk_name = next((n for n, f in fields.items() if f.primary_key), None)

        # Handle auto_now fields
        for name, fld in fields.items():
            if isinstance(fld, DateTimeField) and fld.auto_now:
                setattr(instance, name, datetime.utcnow())

        cols: list[str] = []
        vals: list[Any] = []
        for name, fld in fields.items():
            val = getattr(instance, name, None)
            if fld.primary_key and val is None:
                continue  # auto-increment
            cols.append(name)
            vals.append(fld.python_to_db(val))

        placeholders = ",".join("?" for _ in cols)
        sql = (
            f"INSERT OR REPLACE INTO {instance.__table__} "
            f"({','.join(cols)}) VALUES ({placeholders})"
        )
        cur = await self.db.execute(sql, tuple(vals))

        if pk_name and getattr(instance, pk_name, None) is None:
            setattr(instance, pk_name, cur.lastrowid)

        return instance

    async def get(self, model: type[T], pk: Any) -> T | None:
        """Fetch by primary key. Returns None if not found."""
        pk_name = next((n for n, f in model._fields.items() if f.primary_key), "id")
        row = await self.db.fetchone(
            f"SELECT * FROM {model.__table__} WHERE {pk_name} = ?", (pk,)
        )
        return self._row_to_model(model, row) if row else None

    async def get_or_404(self, model: type[T], pk: Any) -> T:
        """Fetch by primary key. Raises ValueError (→ 404) if not found."""
        instance = await self.get(model, pk)
        if instance is None:
            raise ValueError(f"{model.__name__} with pk={pk!r} not found")
        return instance

    async def get_or_create(self, model: type[T], **kwargs: Any) -> tuple[T, bool]:
        """Return (instance, created). Lookup by kwargs, create if missing."""
        qb = self.query(model)
        for k, v in kwargs.items():
            qb = qb.filter(**{k: v})
        existing = await qb.first()
        if existing:
            return existing, False
        new_obj = await self.create(model, **kwargs)
        return new_obj, True

    async def delete(self, instance: Model) -> None:
        """Delete a model instance from the database."""
        pk_name = next((n for n, f in instance._fields.items() if f.primary_key), "id")
        pk_val = getattr(instance, pk_name)
        await self.db.execute(
            f"DELETE FROM {instance.__table__} WHERE {pk_name} = ?", (pk_val,)
        )

    async def bulk_create(self, instances: list[Model]) -> list[Model]:
        """Insert multiple instances efficiently."""
        for instance in instances:
            await self.save(instance)
        return instances

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def query(self, model: type[T]) -> QueryBuilder:
        """Return a QueryBuilder for *model*."""
        return QueryBuilder(self, model)

    # ------------------------------------------------------------------
    # Raw SQL
    # ------------------------------------------------------------------

    async def execute_raw(self, sql: str, params: tuple = ()) -> list[dict]:
        rows = await self.db.fetchall(sql, params)
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_model(model: type[T], row: Any) -> T:
        data = dict(row)
        for name, fld in model._fields.items():
            if name in data:
                data[name] = fld.db_to_python(data[name])
        return model(**data)
