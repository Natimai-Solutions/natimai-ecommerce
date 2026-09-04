"""The batch enrichment must look a product up on the same keys as the single one.

The single-product task passed the UPC, the batch did not. The same product
therefore matched when an admin enriched it by hand and missed in the hourly
run that actually processes the catalogue — a silently lower match rate, and
the match rate decides how much of the catalogue is sellable at all.
"""

from __future__ import annotations

import ast
import pathlib

_SOURCE = pathlib.Path(__file__).resolve().parents[1] / "tasks" / "icecat_tasks.py"


def _lookup_keyword_sets() -> list[set[str]]:
    """Keyword names of every enrich_product_with_icecat call in the module."""
    tree = ast.parse(_SOURCE.read_text())
    calls: list[set[str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if name == "enrich_product_with_icecat":
            calls.append({kw.arg for kw in node.keywords if kw.arg})
    return calls


def test_every_lookup_passes_the_same_identifiers() -> None:
    calls = _lookup_keyword_sets()
    assert len(calls) >= 2, "expected the single and batch lookups"
    assert len({frozenset(call) for call in calls}) == 1, (
        "the Icecat lookups disagree on which identifiers they send: "
        f"{[sorted(call) for call in calls]}"
    )


def test_the_upc_is_among_them() -> None:
    for call in _lookup_keyword_sets():
        assert "upc" in call
        assert "ean" in call
