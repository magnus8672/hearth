"""Keep normalized image-edit inputs in the existing owner-scoped job queue."""
from alembic import op

revision = '0028'
down_revision = '0027'


def upgrade():
    op.execute('ALTER TABLE image_jobs ADD COLUMN source_image bytea CHECK(source_image IS NULL OR octet_length(source_image) BETWEEN 1 AND 3145728)')


def downgrade():
    op.execute('ALTER TABLE image_jobs DROP COLUMN source_image')
