"""Private upload drafts become shared images only when posted to a joined channel."""
from alembic import op

revision = '0027'
down_revision = '0026'


def upgrade():
    op.execute("""
      CREATE TABLE channel_attachments (
        id uuid PRIMARY KEY, farm_id uuid NOT NULL, channel_id uuid NOT NULL,
        owner_id uuid NOT NULL, message_id uuid, position integer,
        image bytea NOT NULL CHECK(octet_length(image) BETWEEN 1 AND 3145728),
        media_type varchar(30) NOT NULL DEFAULT 'image/jpeg' CHECK(media_type='image/jpeg'),
        width integer NOT NULL CHECK(width BETWEEN 1 AND 1600),
        height integer NOT NULL CHECK(height BETWEEN 1 AND 1600),
        created_at timestamptz NOT NULL DEFAULT now(),
        FOREIGN KEY(channel_id,farm_id) REFERENCES channels(id,farm_id) ON DELETE CASCADE,
        FOREIGN KEY(message_id,channel_id,farm_id,owner_id) REFERENCES channel_messages(id,channel_id,farm_id,author_id) ON DELETE CASCADE,
        CHECK((message_id IS NULL AND position IS NULL) OR (message_id IS NOT NULL AND position BETWEEN 0 AND 3)),
        UNIQUE(message_id,position)
      );
      CREATE INDEX channel_attachments_room ON channel_attachments(channel_id,message_id);
      ALTER TABLE channel_attachments ENABLE ROW LEVEL SECURITY;
      ALTER TABLE channel_attachments FORCE ROW LEVEL SECURITY;
    """)
    scope = "farm_id=NULLIF(current_setting('hearth.farm_id',true),'')::uuid AND EXISTS(SELECT 1 FROM channel_memberships m WHERE m.channel_id=channel_attachments.channel_id AND m.farm_id=channel_attachments.farm_id)"
    own = "owner_id=NULLIF(current_setting('hearth.principal_id',true),'')::uuid"
    op.execute(f'CREATE POLICY attachment_read ON channel_attachments FOR SELECT USING ({scope} AND ({own} OR message_id IS NOT NULL))')
    op.execute(f'CREATE POLICY attachment_insert ON channel_attachments FOR INSERT WITH CHECK ({scope} AND {own} AND message_id IS NULL)')
    op.execute(f'CREATE POLICY attachment_update ON channel_attachments FOR UPDATE USING ({scope} AND {own} AND message_id IS NULL) WITH CHECK ({scope} AND {own})')
    op.execute(f'CREATE POLICY attachment_delete ON channel_attachments FOR DELETE USING ({scope} AND {own} AND message_id IS NULL)')
    op.execute('GRANT SELECT,INSERT,UPDATE,DELETE ON channel_attachments TO hearth_app')


def downgrade():
    raise RuntimeError('Export shared channel images before a reviewed rollback.')
