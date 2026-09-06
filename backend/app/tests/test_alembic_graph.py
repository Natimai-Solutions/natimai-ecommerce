"""The Alembic revision graph must have exactly one head.

Two branches that each add a revision (or each merge the same open heads,
as happened on 2026-09-05) leave two heads once merged; ``alembic upgrade
head`` then refuses to run — in CI, in ``scripts/prestart.sh``, hence in every
deployment. Catching it here means a plain ``pytest`` run, without a
database, reports it with the offending revisions.
"""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _script_directory() -> ScriptDirectory:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "app" / "alembic"))
    return ScriptDirectory.from_config(config)


def test_revision_graph_has_a_single_head() -> None:
    heads = _script_directory().get_heads()
    assert len(heads) == 1, f"several Alembic heads, merge them first: {heads}"


def test_every_revision_is_reachable_from_the_head() -> None:
    """No orphan or dangling ``down_revision`` (a typo would split the graph)."""
    script = _script_directory()
    known = {rev.revision for rev in script.walk_revisions()}
    for rev in script.walk_revisions():
        parents = rev.down_revision
        if parents is None:
            continue
        for parent in parents if isinstance(parents, tuple) else (parents,):
            assert parent in known, f"{rev.revision} revises unknown {parent}"
