import os

from alembic import context
from sqlalchemy import create_engine, pool

url = os.environ.get("HEARTH_MIGRATION_DATABASE_URL", "")
if not url.startswith("postgresql+psycopg://"):
    raise RuntimeError("HEARTH_MIGRATION_DATABASE_URL must identify the migration PostgreSQL role")

if context.is_offline_mode():
    context.configure(url=url, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(url, poolclass=pool.NullPool, hide_parameters=True)
    with engine.connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()
