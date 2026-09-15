"""Private side notes and durable, explicitly requested steering."""
from alembic import op

revision = '0004'
down_revision = '0003'


def upgrade():
    op.execute("""
      CREATE TABLE side_notes (
        id uuid PRIMARY KEY, farm_id uuid NOT NULL, owner_id uuid NOT NULL,
        workspace_id uuid NOT NULL, content varchar(4000) NOT NULL,
        revision bigint NOT NULL DEFAULT 1, created_at timestamptz NOT NULL DEFAULT now(),
        dismissed_at timestamptz,
        FOREIGN KEY(workspace_id,farm_id,owner_id) REFERENCES workspaces(id,farm_id,owner_id)
      );
      CREATE TABLE chat_requests (
        id uuid PRIMARY KEY, farm_id uuid NOT NULL, owner_id uuid NOT NULL,
        conversation_id uuid NOT NULL, content varchar(4000) NOT NULL,
        interrupt_run_id uuid NOT NULL REFERENCES chat_runs(id),
        authorization_version bigint NOT NULL, session_hash varchar(64) NOT NULL,
        state varchar(20) NOT NULL DEFAULT 'queued', reason varchar(500),
        created_at timestamptz NOT NULL DEFAULT now(),
        FOREIGN KEY(conversation_id,farm_id,owner_id) REFERENCES conversations(id,farm_id,owner_id),
        CHECK(state IN ('queued','dispatched','blocked','cancelled'))
      );
      CREATE UNIQUE INDEX one_pending_steer ON chat_requests(conversation_id) WHERE state IN ('queued','blocked');
    """)
    scope = "owner_id = NULLIF(current_setting('hearth.principal_id',true),'')::uuid AND farm_id = NULLIF(current_setting('hearth.farm_id',true),'')::uuid"
    for table in ('side_notes', 'chat_requests'):
        op.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY')
        op.execute(f'CREATE POLICY private_scope ON {table} USING ({scope}) WITH CHECK ({scope})')
        op.execute(f'GRANT SELECT,INSERT,UPDATE,DELETE ON {table} TO hearth_app')


def downgrade():
    raise RuntimeError('Export private notes and queued requests before a reviewed rollback.')
