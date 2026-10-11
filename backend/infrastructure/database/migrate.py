"""Initialize an empty database and apply repeatable schema upgrades."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text

HEAD = "20261011_baseline"


class MigrationError(ValueError):
    """Safe schema diagnostics without a connection URL or provider response."""


def migration_config(connection):
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).with_name("migrations")))
    config.attributes["connection"] = connection
    return config


def upgrade_database(engine, target="head"):
    """Startup never resets data or adopts a schema from removed migrations."""
    with engine.connect() as connection:
        lock_name = None
        if connection.dialect.name == "mysql":
            lock_name = "mmrag:schema:" + (engine.url.database or "")[:48]
            if connection.scalar(text("SELECT GET_LOCK(:name, 30)"), {"name": lock_name}) != 1:
                raise MigrationError("Another schema upgrade is running; retry later.")
            connection.commit()
        try:
            config = migration_config(connection)
            tables = set(inspect(connection).get_table_names())
            revisions = []
            if "alembic_version" in tables:
                revisions = list(connection.scalars(text("SELECT version_num FROM alembic_version")))
            if not revisions and tables - {"alembic_version"}:
                raise MigrationError("Unversioned nonempty database; recreate the project database before initialization.")
            known = {revision.revision for revision in ScriptDirectory.from_config(config).walk_revisions()}
            if any(revision not in known for revision in revisions):
                raise MigrationError("Database references removed migrations; recreate the project database before initialization.")
            connection.commit()
            command.upgrade(config, target)
            connection.commit()
        finally:
            if lock_name is not None:
                connection.rollback()
                connection.execute(text("SELECT RELEASE_LOCK(:name)"), {"name": lock_name})
                connection.commit()
