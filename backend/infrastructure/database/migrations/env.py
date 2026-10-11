"""Alembic receives an existing connection; no credentials are stored in config."""

from alembic import context

connection = context.config.attributes.get("connection")
if connection is None:
    raise RuntimeError("Use upgrade_database() or python -m scripts.dev_setup bootstrap.")
context.configure(connection=connection, compare_type=True)
with context.begin_transaction():
    context.run_migrations()
