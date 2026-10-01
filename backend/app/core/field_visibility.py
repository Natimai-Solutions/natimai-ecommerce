"""Fields only the back office may read (cost, supplier price, margins).

Product and order-line schemas are shared by the storefront and the admin. A
serializer on them drops the internal fields unless the request was made by a
superuser: :func:`app.api.deps.get_current_user` calls
:func:`reveal_internal_fields` for one, in the request's own context, and the
response is serialized in that same context. Anything else — anonymous
visitor, customer, background job — gets the redacted form: forgetting to
reveal hides a figure, it never leaks one.
"""

from __future__ import annotations

from collections.abc import Iterable
from contextvars import ContextVar
from typing import Any

_revealed: ContextVar[bool] = ContextVar("reveal_internal_fields", default=False)


def reveal_internal_fields() -> None:
    """Let the current request's responses carry the internal fields."""
    _revealed.set(True)


def internal_fields_revealed() -> bool:
    return _revealed.get()


def redact(data: Any, fields: Iterable[str]) -> Any:
    """Drop ``fields`` from a serialized model unless revealed."""
    if internal_fields_revealed() or not isinstance(data, dict):
        return data
    for name in fields:
        data.pop(name, None)
    return data


__all__ = [
    "internal_fields_revealed",
    "redact",
    "reveal_internal_fields",
]
