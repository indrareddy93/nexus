"""Base Model metaclass and Model ABC."""

from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar

from nexus.orm.fields import DateTimeField, Field


class ModelMeta(type):
    """Metaclass that collects Field descriptors into ``_fields``."""

    def __new__(mcs, name: str, bases: tuple, namespace: dict) -> ModelMeta:
        fields: dict[str, Field] = {}

        # Inherit parent fields
        for base in bases:
            if hasattr(base, "_fields"):
                fields.update(base._fields)

        # Collect fields declared on this class
        for attr_name, value in list(namespace.items()):
            if isinstance(value, Field):
                value.name = attr_name
                fields[attr_name] = value

        namespace["_fields"] = fields

        # Default __table__ to snake_case class name
        if "__table__" not in namespace:
            namespace["__table__"] = _to_snake_case(name) + "s"

        cls = super().__new__(mcs, name, bases, namespace)
        return cls


class Model(metaclass=ModelMeta):
    """
    Base class for Nexus ORM models.

    Usage::

        from nexus.orm import Model, IntField, StrField, DateTimeField, BoolField

        class User(Model):
            __table__ = "users"

            id         = IntField(primary_key=True)
            name       = StrField(max_length=128, nullable=False)
            email      = StrField(unique=True, nullable=False)
            is_active  = BoolField(default=True)
            created_at = DateTimeField(auto_now_add=True)
            updated_at = DateTimeField(auto_now=True)
    """

    _fields: ClassVar[dict[str, Field]] = {}
    __table__: ClassVar[str] = ""

    def __init__(self, **kwargs: Any) -> None:
        for name, field in self._fields.items():
            val = kwargs.get(name, field.default)
            if callable(val) and not isinstance(val, type):
                val = val()
            object.__setattr__(self, name, val)

        # Handle auto_now_add — set once on creation
        for name, field in self._fields.items():
            if isinstance(field, DateTimeField) and field.auto_now_add:
                if kwargs.get(name) is None:
                    object.__setattr__(self, name, datetime.utcnow())

    def to_dict(self, *, exclude: set[str] | None = None) -> dict[str, Any]:
        """Serialise the model instance to a plain dict."""
        result: dict[str, Any] = {}
        for name in self._fields:
            if exclude and name in exclude:
                continue
            val = getattr(self, name, None)
            if isinstance(val, datetime):
                val = val.isoformat()
            result[name] = val
        return result

    @classmethod
    def create_table_sql(cls) -> str:
        """Generate CREATE TABLE IF NOT EXISTS SQL."""
        col_defs = [f.column_ddl() for f in cls._fields.values()]
        return f"CREATE TABLE IF NOT EXISTS {cls.__table__} ({', '.join(col_defs)})"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Model:
        return cls(**data)

    def __repr__(self) -> str:
        pk_name = next((n for n, f in self._fields.items() if f.primary_key), None)
        pk_val = getattr(self, pk_name, "?") if pk_name else "?"
        return f"<{self.__class__.__name__} pk={pk_val}>"


def _to_snake_case(name: str) -> str:
    import re
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    s = re.sub(r"([a-z\d])([A-Z])", r"\1_\2", s)
    return s.lower()
