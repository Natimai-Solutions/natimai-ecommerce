"""Central renderer for transactional email templates.

Templates live under ``app/templates/email/<lang>/<name>.{subject.txt,txt,html}``
(``fr`` and ``en``, R7 / L3), with a fallback to French for a template not yet
translated. Every template receives ``lang`` and the filters ``money`` and
``date`` that format in that language.
HTML templates are auto-escaped (``{{ value }}`` interpolations are XSS-safe);
text and subject templates are not.

Usage:
    email = render_email("order_created", full_name="...", order_id="...")
    email.subject, email.text, email.html
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, TemplateNotFound, select_autoescape

# app/features/notification/email_renderer.py → app/templates/email
_TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates" / "email"

DEFAULT_LANG = "fr"


def short_ref(value: Any) -> str:
    """Human-friendly reference for a UUID: ``#e090fee1`` (first 8 hex chars).

    Non-UUID values (already-short refs, "n/a", empty) pass through unchanged
    so templates can apply the filter unconditionally.
    """
    raw = str(value or "").strip()
    try:
        parsed = uuid.UUID(raw)
    except ValueError:
        return raw
    return f"#{parsed.hex[:8]}"


_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html"]),
)
_env.filters["short_ref"] = short_ref


@dataclass(slots=True)
class RenderedEmail:
    """A rendered email — subject line + plain-text and HTML bodies."""

    subject: str
    text: str
    html: str


def _money(amount: Any, currency: str | None = None, *, lang: str) -> str:
    from app.core.i18n import format_money

    return format_money(amount, currency, lang)


def _render_part(name: str, suffix: str, lang: str, context: dict[str, Any]) -> str:
    """Render ``<lang>/<name>.<suffix>``, falling back to the default language."""
    from app.core.i18n import format_date

    for candidate in dict.fromkeys((lang, DEFAULT_LANG)):
        try:
            template = _env.get_template(f"{candidate}/{name}.{suffix}")
        except TemplateNotFound:
            continue
        return template.render(
            **{
                "lang": candidate,
                "money": partial(_money, lang=candidate),
                "date": partial(format_date, locale=candidate),
                **context,
            }
        )
    raise TemplateNotFound(f"{lang}/{name}.{suffix}")


def render_email(
    name: str, *, lang: str | None = None, **context: Any
) -> RenderedEmail:
    """Render the subject/text/html parts of email template ``name``.

    ``lang``: the customer's language (order, preference); defaults to the
    language of the current request, else the shop's.
    """
    from app.core import runtime_settings
    from app.core.i18n import request_locale, resolve_locale

    lang = resolve_locale(lang, request_locale())
    context.setdefault("shop_name", runtime_settings.peek("shop_name"))
    # The logo chosen in the back-office (R9 / T9); None keeps the text header.
    from app.features.media.branding import logo_url_from_settings

    context.setdefault("shop_logo_url", logo_url_from_settings())
    return RenderedEmail(
        subject=_render_part(name, "subject.txt", lang, context).strip(),
        text=_render_part(name, "txt", lang, context),
        html=_render_part(name, "html", lang, context),
    )
