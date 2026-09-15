"""Explicitly joined farm channels, separate from private conversations."""
from alembic import op

revision = '0005'
down_revision = '0004'


def upgrade():
    op.execute("""
      CREATE TABLE channels (
        id uuid PRIMARY KEY, farm_id uuid NOT NULL REFERENCES farms(id),
        creator_id uuid NOT NULL, name varchar(80) NOT NULL, revision bigint NOT NULL DEFAULT 1,
        created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(id,farm_id), UNIQUE(farm_id,name)
      );
      CREATE TABLE channel_memberships (
        channel_id uuid NOT NULL, farm_id uuid NOT NULL, owner_id uuid NOT NULL,
        joined_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(channel_id,owner_id),
        FOREIGN KEY(channel_id,farm_id) REFERENCES channels(id,farm_id)
      );
      CREATE TABLE channel_messages (
        id uuid PRIMARY KEY, channel_id uuid NOT NULL, farm_id uuid NOT NULL,
        author_id uuid NOT NULL, display_name varchar(200) NOT NULL,
        sequence bigint NOT NULL, role varchar(20) NOT NULL, content text NOT NULL,
        status varchar(20) NOT NULL, request_id uuid NOT NULL, target_id uuid,
        reason varchar(500), created_at timestamptz NOT NULL DEFAULT now(),
        FOREIGN KEY(channel_id,farm_id) REFERENCES channels(id,farm_id),
        FOREIGN KEY(target_id,farm_id) REFERENCES inference_targets(id,farm_id),
        UNIQUE(channel_id,sequence), UNIQUE(channel_id,request_id,role), UNIQUE(id,farm_id),
        CHECK(role IN ('user','assistant')),
        CHECK(status IN ('completed','running','cancelled','failed','interrupted'))
      );
      CREATE TABLE channel_runs (
        id uuid PRIMARY KEY, farm_id uuid NOT NULL, owner_id uuid NOT NULL,
        channel_id uuid NOT NULL, assistant_message_id uuid NOT NULL,
        target_id uuid NOT NULL, session_hash varchar(64) NOT NULL,
        authorization_version bigint NOT NULL, status varchar(20) NOT NULL DEFAULT 'running',
        created_at timestamptz NOT NULL DEFAULT now(), finished_at timestamptz,
        FOREIGN KEY(channel_id,farm_id) REFERENCES channels(id,farm_id),
        FOREIGN KEY(assistant_message_id,farm_id) REFERENCES channel_messages(id,farm_id),
        FOREIGN KEY(target_id,farm_id) REFERENCES inference_targets(id,farm_id),
        CHECK(status IN ('completed','running','cancelled','failed','interrupted'))
      );
    """)
    farm = "farm_id = NULLIF(current_setting('hearth.farm_id',true),'')::uuid"
    owner = "owner_id = NULLIF(current_setting('hearth.principal_id',true),'')::uuid"
    for table, scope in [('channels', farm), ('channel_memberships', farm + ' AND ' + owner),
                         ('channel_runs', farm + ' AND ' + owner),
                         ('channel_messages', farm + ' AND EXISTS(SELECT 1 FROM channel_memberships cm WHERE cm.channel_id=channel_messages.channel_id AND cm.farm_id=channel_messages.farm_id)')]:
        op.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY')
        op.execute(f'CREATE POLICY channel_scope ON {table} USING ({scope}) WITH CHECK ({scope})')
        op.execute(f'GRANT SELECT,INSERT,UPDATE,DELETE ON {table} TO hearth_app')


def downgrade():
    raise RuntimeError('Export channel history before a reviewed rollback.')
