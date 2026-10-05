from alembic.config import Config
from alembic.script import ScriptDirectory


def test_migration_history_has_one_linear_head():
    scripts = ScriptDirectory.from_config(Config("alembic.ini"))

    revisions = list(scripts.walk_revisions())

    assert scripts.get_heads() == ["a04d79012711"]
    assert [revision.revision for revision in revisions] == [
        "a04d79012711",
        "dba4f311e944",
        "11d1f79aef4d",
    ]
    assert revisions[-1].down_revision is None
