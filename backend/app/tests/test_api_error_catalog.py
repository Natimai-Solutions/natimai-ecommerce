"""The API is language-agnostic: an error is a code, details and an English
fallback message; the frontends translate the code from the shared catalogue
``shared/utils/src/apiErrors/{en,fr}.json`` (decision of 18/11/2026).

This test keeps it so: every code the backend raises has its English and
French text, the placeholders of a text are details the raise provides, and
no message is written in French any more.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any

import pytest

from app.core.errors import AppError, fill_placeholders

BACKEND = Path(__file__).resolve().parents[2]
APP = BACKEND / "app"
CATALOGUE = BACKEND.parent / "shared" / "utils" / "src" / "apiErrors"
PLACEHOLDER = re.compile(r"\{([a-z_][a-z0-9_]*)\}")
FRENCH = re.compile(r"[éèàçêùâîôûœ«»]")


def _catalogue(lang: str) -> dict[str, str]:
    path = CATALOGUE / f"{lang}.json"
    if not path.exists():  # pragma: no cover - run outside the monorepo
        pytest.skip("shared catalogue not available here")
    data: dict[str, str] = json.loads(path.read_text())
    return data


def _text(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(
            v.value if isinstance(v, ast.Constant) else "{}" for v in node.values
        )
    if isinstance(node, ast.BinOp):
        return (_text(node.left) or "") + (_text(node.right) or "")
    if isinstance(node, ast.IfExp):
        return (_text(node.body) or "") + (_text(node.orelse) or "")
    return None


def _raises() -> list[dict[str, Any]]:
    """Every ``AppError(code=…, message=…, details={…})`` of the backend,
    plus the codes built by the helpers (rate limits, gift card states, the
    ``_invalid`` helpers of the homepage and the media)."""
    found: list[dict[str, Any]] = []
    for path in sorted(APP.rglob("*.py")):
        if "tests" in path.parts or "alembic" in path.parts:
            continue
        tree = ast.parse(path.read_bytes())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            kw = {k.arg: k.value for k in node.keywords}
            if name == "AppError":
                code = kw.get("code")
                details = kw.get("details")
                keys = (
                    {k.value for k in details.keys if isinstance(k, ast.Constant)}
                    if isinstance(details, ast.Dict)
                    else None  # built elsewhere: not checked
                )
                codes: list[str] = []
                if isinstance(code, ast.Constant):
                    codes = [code.value]
                elif isinstance(code, ast.IfExp):
                    codes = [
                        c.value
                        for c in (code.body, code.orelse)
                        if isinstance(c, ast.Constant)
                    ]
                for value in codes:
                    found.append(
                        {
                            "where": f"{path.relative_to(BACKEND)}:{node.lineno}",
                            "code": value,
                            "message": _text(kw.get("message")),
                            "details": keys,
                        }
                    )
            elif name == "rate_limited" and node.args:
                scope = node.args[0]
                if isinstance(scope, ast.Constant):
                    found.append(
                        {
                            "where": f"{path.relative_to(BACKEND)}:{node.lineno}",
                            "code": f"{scope.value}.rate_limited",
                            "message": None,
                            "details": {"scope", "window_seconds"},
                        }
                    )
            elif name == "_invalid":
                code_kw = kw.get("code")
                code_value = (
                    code_kw.value
                    if isinstance(code_kw, ast.Constant)
                    else node.args[1].value
                    if len(node.args) > 1 and isinstance(node.args[1], ast.Constant)
                    else "media.invalid"
                )
                found.append(
                    {
                        "where": f"{path.relative_to(BACKEND)}:{node.lineno}",
                        "code": code_value,
                        "message": _text(node.args[0]) if node.args else None,
                        "details": None,
                    }
                )
    for state in ("redeemed", "expired", "cancelled"):
        found.append(
            {
                "where": "gift_cards.py",
                "code": f"gift_card.{state}",
                "message": None,
                "details": {"state"},
            }
        )
    return found


def test_both_catalogues_have_the_same_codes() -> None:
    en, fr = _catalogue("en"), _catalogue("fr")
    assert set(en) == set(fr)
    for code in en:
        assert set(PLACEHOLDER.findall(en[code])) == set(
            PLACEHOLDER.findall(fr[code])
        ), code


def test_every_raised_code_is_in_the_catalogue() -> None:
    en = _catalogue("en")
    missing = sorted({r["code"] for r in _raises()} - set(en))
    assert missing == [], (
        f"Add these codes to shared/utils/src/apiErrors/en.json and fr.json: {missing}"
    )


def test_placeholders_are_details_the_raise_provides() -> None:
    en = _catalogue("en")
    wrong = [
        (
            r["where"],
            r["code"],
            sorted(set(PLACEHOLDER.findall(en[r["code"]])) - r["details"]),
        )
        for r in _raises()
        if r["code"] in en
        and r["details"] is not None
        and set(PLACEHOLDER.findall(en[r["code"]])) - r["details"]
    ]
    assert wrong == []


def test_no_error_message_is_written_in_french() -> None:
    french = [
        (r["where"], r["code"], r["message"])
        for r in _raises()
        if r["message"] and FRENCH.search(r["message"])
    ]
    assert french == [], "Fallback messages are English (the catalogue's text)"


def test_placeholders_are_filled_from_the_details() -> None:
    error = AppError(
        code="cart.stock.insufficient",
        status_code=409,
        message="“{product_name}”: only {available} left.",
        details={"product_name": "Écran", "available": 2},
    )
    assert error.message == "“Écran”: only 2 left."
    assert fill_placeholders("{missing} stays", {}) == "{missing} stays"


@pytest.mark.asyncio
async def test_the_message_does_not_follow_the_callers_language() -> None:
    from starlette.requests import Request

    from app.core.errors import app_error_handler

    request = Request(
        {
            "type": "http",
            "headers": [(b"accept-language", b"fr-FR,fr;q=0.9")],
            "method": "GET",
            "path": "/",
        }
    )
    response = await app_error_handler(
        request, AppError(code="cart.empty", message="Your cart is empty.")
    )
    body = json.loads(bytes(response.body))
    assert body["error"] == {
        "code": "cart.empty",
        "message": "Your cart is empty.",
        "details": {},
    }
