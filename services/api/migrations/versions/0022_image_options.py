"""Bounded 4K artifacts and extended image sampling progress."""
from alembic import op

revision = '0022'
down_revision = '0021'


def upgrade():
    op.execute("""
      ALTER TABLE image_jobs DROP CONSTRAINT image_jobs_image_check;
      ALTER TABLE image_jobs ADD CHECK(image IS NULL OR octet_length(image)<=67108864);
      ALTER TABLE conversation_images DROP CONSTRAINT conversation_images_image_check;
      ALTER TABLE conversation_images ADD CHECK(image IS NULL OR octet_length(image)<=67108864);
      ALTER TABLE conversation_images DROP CONSTRAINT conversation_images_progress_check;
      ALTER TABLE conversation_images ADD CHECK(progress BETWEEN 0 AND 60);
    """)


def downgrade():
    raise RuntimeError('Review stored large images before lowering artifact limits.')
