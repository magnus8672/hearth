"""Private chat image inputs, separate from generated image artifacts."""
from alembic import op

revision = '0015'
down_revision = '0014'


def upgrade():
    op.execute("""
      CREATE TABLE chat_attachments (
        id uuid PRIMARY KEY, farm_id uuid NOT NULL, owner_id uuid NOT NULL,
        conversation_id uuid NOT NULL, image bytea NOT NULL,
        media_type varchar(30) NOT NULL CHECK(media_type='image/jpeg'),
        width integer NOT NULL CHECK(width BETWEEN 1 AND 1600),
        height integer NOT NULL CHECK(height BETWEEN 1 AND 1600),
        created_at timestamptz NOT NULL DEFAULT now(),
        FOREIGN KEY(conversation_id,farm_id,owner_id) REFERENCES conversations(id,farm_id,owner_id),
        CHECK(octet_length(image) BETWEEN 1 AND 3145728)
      );
      ALTER TABLE chat_attachments ENABLE ROW LEVEL SECURITY;
      ALTER TABLE chat_attachments FORCE ROW LEVEL SECURITY;
      CREATE POLICY private_scope ON chat_attachments
        USING (farm_id=NULLIF(current_setting('hearth.farm_id',true),'')::uuid AND owner_id=NULLIF(current_setting('hearth.principal_id',true),'')::uuid)
        WITH CHECK (farm_id=NULLIF(current_setting('hearth.farm_id',true),'')::uuid AND owner_id=NULLIF(current_setting('hearth.principal_id',true),'')::uuid);
      GRANT SELECT,INSERT,UPDATE,DELETE ON chat_attachments TO hearth_app;
      ALTER TABLE messages ADD COLUMN attachment_ids uuid[] NOT NULL DEFAULT '{}';
      ALTER TABLE chat_requests ADD COLUMN attachment_ids uuid[] NOT NULL DEFAULT '{}';
    """)


def downgrade():
    raise RuntimeError('Export private image attachments before a reviewed rollback.')
