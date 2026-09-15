"""Bounded image batches with separate artifacts and one parent execution slot."""
from alembic import op

revision = '0009'
down_revision = '0008'


def upgrade():
    op.execute("""
      ALTER TABLE image_plans ADD UNIQUE(id,farm_id,owner_id);
      ALTER TABLE image_plans ADD COLUMN max_images integer NOT NULL DEFAULT 1 CHECK(max_images BETWEEN 1 AND 4);
      ALTER TABLE image_jobs ADD COLUMN batch_run_id uuid;
      ALTER TABLE image_jobs ADD FOREIGN KEY(batch_run_id,farm_id,owner_id) REFERENCES image_plans(id,farm_id,owner_id);
      ALTER TABLE conversation_images ADD COLUMN batch_run_id uuid;
      ALTER TABLE conversation_images ADD COLUMN batch_index integer NOT NULL DEFAULT 1;
      ALTER TABLE conversation_images ADD COLUMN batch_count integer NOT NULL DEFAULT 1;
      ALTER TABLE conversation_images ADD CHECK(batch_index BETWEEN 1 AND batch_count AND batch_count BETWEEN 1 AND 4);
      ALTER TABLE conversation_images DROP CONSTRAINT conversation_images_message_id_key;
      ALTER TABLE conversation_images DROP CONSTRAINT conversation_images_channel_message_id_key;
      ALTER TABLE conversation_images ADD UNIQUE(message_id,batch_index);
      ALTER TABLE conversation_images ADD UNIQUE(channel_message_id,batch_index);
      ALTER TABLE image_jobs DROP CONSTRAINT image_jobs_status_check;
      ALTER TABLE image_jobs ADD CHECK(status IN ('queued','running','completed','cancelled','failed','interrupted'));
      ALTER TABLE conversation_images DROP CONSTRAINT conversation_images_status_check;
      ALTER TABLE conversation_images ADD CHECK(status IN ('queued','running','completed','cancelled','failed','interrupted'));
    """)


def downgrade():
    raise RuntimeError('Export batch artifacts before a reviewed rollback.')
