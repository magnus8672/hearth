"""Erase private generated artifacts while retaining retry and reference identities."""
from alembic import op

revision = '0021'
down_revision = '0020'


def upgrade():
    op.execute("""
      ALTER TABLE image_jobs ADD COLUMN deleted_at timestamptz;
      ALTER TABLE image_jobs ADD CHECK(deleted_at IS NULL OR image IS NULL);
      ALTER TABLE conversation_images DROP CONSTRAINT conversation_images_status_check;
      ALTER TABLE conversation_images ADD CHECK(status IN ('queued','running','completed','cancelled','failed','interrupted','deleted'));
      ALTER TABLE conversation_images ADD CHECK(status <> 'deleted' OR image IS NULL);
    """)


def downgrade():
    raise RuntimeError('Deleted image bytes cannot be recovered by rolling back the schema.')
