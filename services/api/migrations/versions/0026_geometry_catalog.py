"""Private model names and bounded reference thumbnails, including legacy models."""
from alembic import op

revision = '0026'
down_revision = '0025'


def upgrade():
    # NULL names preserve legacy rows without rewriting private content or RLS.
    # The API supplies a distinct ID-based title until their owner renames them.
    op.execute("ALTER TABLE geometry_jobs ADD COLUMN name varchar(120) CHECK (name IS NULL OR length(btrim(name)) > 0)")
    op.execute('ALTER TABLE geometry_jobs ADD COLUMN thumbnail bytea CHECK (octet_length(thumbnail) <= 524288)')


def downgrade():
    op.execute('ALTER TABLE geometry_jobs DROP COLUMN thumbnail, DROP COLUMN name')
