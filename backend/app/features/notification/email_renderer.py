"""Central renderer for transactional email templates.

Templates live under ``app/templates/email/<lang>/<name>.{subject.txt,txt,html}``
so they can be edited without touching Python and translated per language later.
HTML templates are auto-escaped (``{{ value }}`` interpolations are XSS-safe);
text and subject templates are not.

Usage:
    email = render_email("order_created", full_name="...", order_id="...")
    email.subject, email.text, email.html
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
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


def _render_part(name: str, suffix: str, lang: str, context: dict[str, Any]) -> str:
    """Render ``<lang>/<name>.<suffix>``, falling back to the default language."""
    for candidate in dict.fromkeys((lang, DEFAULT_LANG)):
        try:
            template = _env.get_template(f"{candidate}/{name}.{suffix}")
        except TemplateNotFound:
            continue
        return template.render(**context)
    raise TemplateNotFound(f"{lang}/{name}.{suffix}")


def render_email(
    name: str, *, lang: str = DEFAULT_LANG, **context: Any
) -> RenderedEmail:
    """Render the subject/text/html parts of email template ``name``."""
    return RenderedEmail(
        subject=_render_part(name, "subject.txt", lang, context).strip(),
        text=_render_part(name, "txt", lang, context),
        html=_render_part(name, "html", lang, context),
    )
