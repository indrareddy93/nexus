"""ORM field descriptors — type-safe, with DB serialisation."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional


class Field:
    """
    Base field descriptor.

    Usage::

        class User(Model):
            id = IntField(primary_key=True)
            name = StrField(max_length=255, nullable=False)
            email = StrField(unique=True)
            created_at = DateTimeField(auto_now_add=True)
    """

    # SQLite type mapping
    db_type: str = "TEXT"

    def __init__(
        self,
        *,
        primary_key: bool = False,
        nullable: bool = True,
        unique: bool = False,
        default: Any = None,
        index: bool = False,
    ) -> None:
        self.primary_key = primary_key
        self.nullable = nullable
        self.unique = unique
        self.default = default
        self.index = index
        self.name: str = ""  # set by ModelMeta

    def __set_name__(self, owner: type, name: str) -> None:
        self.name = name

    def __get__(self, obj: Any, objtype: type | None = None) -> Any:
        if obj is None:
            return self
        return obj.__dict__.get(self.name, self.default)

    def __set__(self, obj: Any, value: Any) -> None:
        obj.__dict__[self.name] = value

    def python_to_db(self, value: Any) -> Any:
        return value

    def db_to_python(self, value: Any) -> Any:
        return value

    def column_ddl(self) -> str:
        parts = [self.name, self.db_type]
        if self.primary_key:
            parts.append("PRIMARY KEY AUTOINCREMENT")
        if not self.nullable and not self.primary_key:
            parts.append("NOT NULL")
        if self.unique:
            parts.append("UNIQUE")
        if self.default is not None and not callable(self.default):
            parts.append(f"DEFAULT {self._sql_default()}")
        return " ".join(parts)

    def _sql_default(self) -> str:
        d = self.default
        if isinstance(d, str):
            return f"'{d}'"
        if isinstance(d, bool):
            return "1" if d else "0"
        return str(d)


class IntField(Field):
    """Integer column (maps to INTEGER in SQLite)."""

    db_type = "INTEGER"

    def __init__(self, *, primary_key: bool = False, **kwargs: Any) -> None:
        super().__init__(primary_key=primary_key, **kwargs)
        if primary_key:
            self.nullable = True  # auto-increment columns can be null before insert

    def python_to_db(self, value: Any) -> Any:
        return int(value) if value is not None else None

    def db_to_python(self, value: Any) -> Any:
        return int(value) if value is not None else None

    def column_ddl(self) -> str:
        parts = [self.name, self.db_type]
        if self.primary_key:
            parts.append("PRIMARY KEY AUTOINCREMENT")
        elif not self.nullable:
            parts.append("NOT NULL")
        if self.unique and not self.primary_key:
            parts.append("UNIQUE")
        return " ".join(parts)


class StrField(Field):
    """VARCHAR / TEXT column."""

    def __init__(self, *, max_length: int | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.max_length = max_length
        self.db_type = f"VARCHAR({max_length})" if max_length else "TEXT"

    def python_to_db(self, value: Any) -> Any:
        return str(value) if value is not None else None

    def db_to_python(self, value: Any) -> Any:
        return str(value) if value is not None else None


class TextField(StrField):
    """Alias for large-text StrField without length limit."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(max_length=None, **kwargs)


class BoolField(Field):
    """Boolean — stored as INTEGER (0/1)."""

    db_type = "INTEGER"

    def python_to_db(self, value: Any) -> Any:
        if value is None:
            return None
        return 1 if value else 0

    def db_to_python(self, value: Any) -> Any:
        if value is None:
            return None
        return bool(value)


class FloatField(Field):
    """Floating-point REAL column."""

    db_type = "REAL"

    def python_to_db(self, value: Any) -> Any:
        return float(value) if value is not None else None

    def db_to_python(self, value: Any) -> Any:
        return float(value) if value is not None else None


class DateTimeField(Field):
    """
    Datetime stored as ISO-8601 TEXT.

    Parameters
    ----------
    auto_now_add:
        Set to ``datetime.utcnow()`` on first INSERT (creation timestamp).
    auto_now:
        Update to ``datetime.utcnow()`` on every SAVE (updated-at timestamp).
    """

    db_type = "TEXT"

    def __init__(
        self,
        *,
        auto_now_add: bool = False,
        auto_now: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.auto_now_add = auto_now_add
        self.auto_now = auto_now
        if auto_now_add or auto_now:
            self.nullable = True  # managed automatically

    def python_to_db(self, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.isoformat()
        return str(value)

    def db_to_python(self, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(str(value))
        except ValueError:
            return value


class JSONField(Field):
    """JSON blob — serialised to TEXT."""

    db_type = "TEXT"

    def python_to_db(self, value: Any) -> Any:
        if value is None:
            return None
        return json.dumps(value, default=str)

    def db_to_python(self, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return value
