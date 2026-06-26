"""Guard against route-ordering bugs.

FastAPI path params compile to Starlette `str` convertors, so a parametrized
route declared before a literal sibling greedily captures it
(e.g. ``/me/{payment_id}`` swallows ``/me/methods`` → 422 on the UUID parse).

For each route+method we build a concrete example path and find the first route
that matches it in registration order; if that route isn't the one we started
from, it is shadowed and the test fails.
"""

import uuid

from starlette.routing import Match, Route

from app.main import app


def _example_path(route: Route) -> str:
    result = route.path
    for name, conv in route.param_convertors.items():
        cname = type(conv).__name__.lower()
        if "int" in cname:
            val = "1"
        elif "float" in cname:
            val = "1.0"
        elif "path" in cname:
            val = "x/y"
        else:  # str (FastAPI typed params too) / uuid
            val = str(uuid.uuid4())
        result = result.replace("{" + name + "}", val)
    return result


def test_no_shadowed_routes() -> None:
    routes = [r for r in app.routes if isinstance(r, Route)]
    shadowed: list[str] = []
    for b in routes:
        for method in sorted((b.methods or set()) - {"HEAD", "OPTIONS"}):
            scope = {"type": "http", "method": method, "path": _example_path(b)}
            for a in routes:
                match, _ = a.matches(scope)
                if match == Match.FULL:
                    if a is not b:
                        shadowed.append(f"{method} {b.path}  <-  {a.path}")
                    break
    assert not shadowed, (
        "Route(s) shadowed by an earlier parametrized route:\n" + "\n".join(shadowed)
    )
