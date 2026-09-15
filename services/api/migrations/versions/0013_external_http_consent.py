"""Explicit administrator approval for plaintext external LAN connections."""
from alembic import op

revision = '0013'
down_revision = '0012'


def upgrade():
    op.execute("ALTER TABLE provider_connections ADD COLUMN allow_insecure_http boolean NOT NULL DEFAULT false CHECK (NOT allow_insecure_http OR base_url LIKE 'http://%')")


def downgrade():
    raise RuntimeError('Connection trust changes require an explicit reviewed rollback.')
