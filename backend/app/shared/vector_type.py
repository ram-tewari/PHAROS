"""Portable embedding column type.

On PostgreSQL the column is a native pgvector ``vector(N)`` so it can be
HNSW-indexed and queried with ``<=>``. On SQLite (unit tests) it is stored
as JSON text and similarity is computed in Python by the retriever.

Values cross the driver boundary as text (``'[0.1,0.2,…]'``) wrapped in an
explicit ``CAST(… AS vector(N))``. That works identically with psycopg2 and
asyncpg and needs neither the ``pgvector`` Python package nor numpy. (A bare
``:param::vector`` cast silently matches zero rows under asyncpg — the bug
recorded in the project history — so the cast is always generated here
rather than hand-written in SQL strings.)
"""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from typing import Any

from sqlalchemy import Text, cast, type_coerce
from sqlalchemy.types import TypeDecorator, UserDefinedType

EMBEDDING_DIM = 768


class _PgVector(UserDefinedType):
    cache_ok = True

    def __init__(self, dim: int) -> None:
        self.dim = dim

    def get_col_spec(self, **_: Any) -> str:
        return f"vector({self.dim})"


def to_vector_literal(values: Sequence[float]) -> str:
    """Serialise floats to pgvector's text format, rejecting NaN/inf."""
    out = []
    for v in values:
        f = float(v)
        if not math.isfinite(f):
            raise ValueError("embedding contains a non-finite value")
        out.append(repr(f))
    return "[" + ",".join(out) + "]"


def parse_vector_literal(value: str | None) -> list[float] | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    return [float(x) for x in json.loads(text)]


class _VectorText(TypeDecorator):
    """Text-typed bind parameter that serialises a float list."""

    impl = Text
    cache_ok = True

    def __init__(self, dim: int) -> None:
        super().__init__()
        self.dim = dim

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, str):
            value = parse_vector_literal(value)
        if len(value) != self.dim:
            raise ValueError(
                f"embedding has {len(value)} dimensions, column expects {self.dim}"
            )
        return to_vector_literal(value)


class EmbeddingVector(TypeDecorator):
    """``vector(dim)`` on PostgreSQL, JSON-encoded ``TEXT`` elsewhere."""

    impl = Text
    cache_ok = True

    def __init__(self, dim: int = EMBEDDING_DIM) -> None:
        super().__init__()
        self.dim = dim

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(_PgVector(self.dim))
        return dialect.type_descriptor(Text())

    def bind_expression(self, bindvalue):
        # The parameter travels as serialised text; the server-side CAST
        # targets this type, which compiles to vector(dim) on PostgreSQL and
        # TEXT elsewhere.
        return cast(type_coerce(bindvalue, _VectorText(self.dim)), self)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, (list, tuple)):
            return [float(x) for x in value]
        return parse_vector_literal(value)
