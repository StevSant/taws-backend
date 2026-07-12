"""Guard: the Alembic migration tree must resolve to exactly one head.

Regression test for the duplicate-revision-id breakage where two feature
migrations independently claimed the same revision number (both "0009" and,
separately, both "0011"), producing multiple heads and an ambiguous
``alembic upgrade head``. The project's "direct-to-main in pairs" workflow
makes this class of collision easy to reintroduce, and backend CI does not
run migrations, so the single-head invariant is asserted here instead.
"""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

_BACKEND_ROOT = Path(__file__).resolve().parent.parent


def _script_directory() -> ScriptDirectory:
    config = Config(str(_BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(_BACKEND_ROOT / "migrations"))
    return ScriptDirectory.from_config(config)


def test_migration_tree_has_single_head() -> None:
    heads = _script_directory().get_heads()

    assert len(heads) == 1, (
        f"Expected exactly one Alembic head, found {len(heads)}: {heads}. "
        "Two migrations likely claimed the same revision id — dedupe them and "
        "re-chain down_revision into a single linear history."
    )


def test_migration_revision_ids_are_unique() -> None:
    revisions = [rev.revision for rev in _script_directory().walk_revisions()]

    duplicates = sorted({rev for rev in revisions if revisions.count(rev) > 1})

    assert not duplicates, (
        f"Duplicate Alembic revision ids found: {duplicates}. Each migration "
        "must declare a unique `revision` string."
    )
