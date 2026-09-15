"""Publish generated images into their original conversation scope."""
from alembic import op

revision = '0007'
down_revision = '0006'


def upgrade():
    op.execute("""
      ALTER TABLE image_jobs ADD COLUMN channel_id uuid;
      ALTER TABLE image_jobs ADD FOREIGN KEY(channel_id,farm_id) REFERENCES channels(id,farm_id);
      ALTER TABLE image_jobs ADD UNIQUE(id,farm_id,owner_id);
      ALTER TABLE image_jobs ADD UNIQUE(id,farm_id,owner_id,channel_id);
      ALTER TABLE messages ADD UNIQUE(id,farm_id,owner_id);
      ALTER TABLE channel_messages ADD UNIQUE(id,channel_id,farm_id,author_id);
      CREATE TABLE conversation_images (
        id uuid PRIMARY KEY, farm_id uuid NOT NULL, owner_id uuid NOT NULL,
        message_id uuid, channel_message_id uuid, channel_id uuid,
        request jsonb NOT NULL, status varchar(20) NOT NULL DEFAULT 'running',
        progress integer NOT NULL DEFAULT 0, reason varchar(500), sha256 varchar(64), image bytea,
        FOREIGN KEY(id,farm_id,owner_id) REFERENCES image_jobs(id,farm_id,owner_id),
        FOREIGN KEY(id,farm_id,owner_id,channel_id) REFERENCES image_jobs(id,farm_id,owner_id,channel_id),
        FOREIGN KEY(message_id,farm_id,owner_id) REFERENCES messages(id,farm_id,owner_id),
        FOREIGN KEY(channel_message_id,channel_id,farm_id,owner_id)
          REFERENCES channel_messages(id,channel_id,farm_id,author_id),
        UNIQUE(message_id), UNIQUE(channel_message_id),
        CHECK((message_id IS NOT NULL AND channel_message_id IS NULL AND channel_id IS NULL) OR
              (message_id IS NULL AND channel_message_id IS NOT NULL AND channel_id IS NOT NULL)),
        CHECK(status IN ('running','completed','cancelled','failed','interrupted')),
        CHECK(progress BETWEEN 0 AND 40), CHECK(image IS NULL OR octet_length(image)<=16777216)
      );
      ALTER TABLE conversation_images ENABLE ROW LEVEL SECURITY;
      ALTER TABLE conversation_images FORCE ROW LEVEL SECURITY;
      GRANT SELECT,INSERT,UPDATE,DELETE ON conversation_images TO hearth_app;
    """)
    farm = "farm_id=NULLIF(current_setting('hearth.farm_id',true),'')::uuid"
    owner = "owner_id=NULLIF(current_setting('hearth.principal_id',true),'')::uuid"
    joined = 'EXISTS(SELECT 1 FROM channel_memberships cm WHERE cm.channel_id=conversation_images.channel_id AND cm.farm_id=conversation_images.farm_id)'
    scope = f"{farm} AND ((channel_id IS NULL AND {owner}) OR (channel_id IS NOT NULL AND {joined}))"
    op.execute(f'CREATE POLICY read_scope ON conversation_images FOR SELECT USING ({scope})')
    op.execute(f'CREATE POLICY insert_scope ON conversation_images FOR INSERT WITH CHECK ({scope} AND {owner})')
    # Joined members may reconcile interrupted public jobs; only the executor
    # publishes bytes through the application. This matches channel-message RLS.
    op.execute(f'CREATE POLICY update_scope ON conversation_images FOR UPDATE USING ({scope}) WITH CHECK ({scope})')
    op.execute(f'CREATE POLICY delete_scope ON conversation_images FOR DELETE USING ({scope})')


def downgrade():
    raise RuntimeError('Export conversation images before a reviewed rollback.')
