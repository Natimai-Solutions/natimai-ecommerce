from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from typing import Any, Dict


def _is_crud_instance(obj: Any) -> bool:
    try:
        from app.api.base.crud import CrudBase
        return isinstance(obj, CrudBase)
    except Exception:
        return False


@dataclass
class CrudRegistry:
    """Minimal registry loading CRUD singletons from app.api.crud aggregator.

    Usage:
      env.get("crud_shipping_method") or env["crud_shipping_method"]
      env.get("shipping_method") or env["shipping_method"]
      env.all -> dict of name -> instance
    """

    _registry: Dict[str, Any] = field(default_factory=dict)
    _loaded: bool = False

    def _load(self) -> None:
        if self._loaded:
            return
        mod = importlib.import_module("app.api.crud")
        symbols = getattr(mod, "__all__", None) or [
            name for name in dir(mod) if not name.startswith("__")
        ]
        for name in symbols:
            value = getattr(mod, name, None)
            if value is not None and _is_crud_instance(value):
                # Register original exported name
                self._registry.setdefault(name, value)
                # Also register alias without 'crud_' prefix
                if name.startswith("crud_"):
                    alias = name[len("crud_"):]
                    if alias:
                        self._registry.setdefault(alias, value)
        self._loaded = True

    @property
    def all(self) -> Dict[str, Any]:
        self._load()
        return dict(self._registry)

    def get(self, key: str) -> Any:
        self._load()
        return self._registry.get(key)

    def __getitem__(self, key: str) -> Any:
        self._load()
        value = self._registry.get(key)
        if value is None:
            raise KeyError(key)
        return value
