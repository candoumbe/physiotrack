"""Use only the already-validated connection supplied by the runner."""

from alembic import context

from physiotrack_migrator.models import Base

connection = context.config.attributes["connection"]
context.configure(
    connection=connection,
    target_metadata=Base.metadata,
    version_table_schema="public",
    transactional_ddl=True,
)
with context.begin_transaction():
    context.run_migrations()
