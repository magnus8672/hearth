"""Existing inference services and private durable chat turns."""
from alembic import op

revision = '0003'
down_revision = '0002'


def upgrade():
    op.execute("""
      CREATE TABLE provider_pools (
        id uuid PRIMARY KEY, farm_id uuid NOT NULL REFERENCES farms(id),
        name varchar(120) NOT NULL, active_run_id uuid, active_owner_id uuid,
        execution_state varchar(20) NOT NULL DEFAULT 'idle',
        lease_until timestamptz, UNIQUE(id,farm_id), UNIQUE(farm_id,name),
        CHECK(execution_state IN ('idle','running','unknown'))
      );
      CREATE TABLE provider_connections (
        id uuid PRIMARY KEY, farm_id uuid NOT NULL REFERENCES farms(id),
        name varchar(120) NOT NULL, base_url varchar(2048) NOT NULL,
        credential text NOT NULL DEFAULT '',
        created_at timestamptz NOT NULL DEFAULT now(),
        UNIQUE(id,farm_id), UNIQUE(farm_id,base_url)
      );
      CREATE TABLE inference_targets (
        id uuid PRIMARY KEY, farm_id uuid NOT NULL, connection_id uuid NOT NULL,
        resource_pool_id uuid NOT NULL, model_id varchar(200) NOT NULL,
        state varchar(20) NOT NULL DEFAULT 'configured',
        features jsonb NOT NULL DEFAULT '[]', revision bigint NOT NULL DEFAULT 1,
        probed_at timestamptz, verified_until timestamptz, reason varchar(500),
        FOREIGN KEY(connection_id,farm_id) REFERENCES provider_connections(id,farm_id),
        FOREIGN KEY(resource_pool_id,farm_id) REFERENCES provider_pools(id,farm_id),
        UNIQUE(id,farm_id), UNIQUE(connection_id,model_id),
        CHECK(state IN ('configured','ready','failed','disabled'))
      );
      CREATE TABLE capability_bindings (
        farm_id uuid NOT NULL, capability_id varchar(80) NOT NULL REFERENCES capabilities(id),
        target_id uuid NOT NULL, priority integer NOT NULL DEFAULT 0,
        PRIMARY KEY(farm_id,capability_id,target_id),
        FOREIGN KEY(target_id,farm_id) REFERENCES inference_targets(id,farm_id),
        CHECK(priority BETWEEN 0 AND 100)
      );
      ALTER TABLE conversations ADD COLUMN kind varchar(20) NOT NULL DEFAULT 'draft';
      ALTER TABLE conversations ADD CONSTRAINT conversation_kind CHECK(kind IN ('draft','chat'));
      CREATE TABLE chat_runs (
        id uuid PRIMARY KEY, farm_id uuid NOT NULL, owner_id uuid NOT NULL,
        conversation_id uuid NOT NULL, target_id uuid NOT NULL,
        user_message_id uuid NOT NULL REFERENCES messages(id),
        assistant_message_id uuid NOT NULL REFERENCES messages(id),
        status varchar(20) NOT NULL DEFAULT 'running', cancel_requested boolean NOT NULL DEFAULT false,
        authorization_version bigint NOT NULL, session_hash varchar(64) NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(), finished_at timestamptz,
        reason varchar(500), finish_reason varchar(40),
        FOREIGN KEY(conversation_id,farm_id,owner_id) REFERENCES conversations(id,farm_id,owner_id),
        FOREIGN KEY(target_id,farm_id) REFERENCES inference_targets(id,farm_id),
        CHECK(status IN ('running','completed','cancelled','failed','interrupted'))
      );
      CREATE INDEX chat_runs_conversation ON chat_runs(conversation_id,created_at);
      CREATE UNIQUE INDEX one_active_chat_turn ON chat_runs(conversation_id) WHERE status='running';
    """)
    farm_scope = "farm_id = NULLIF(current_setting('hearth.farm_id',true),'')::uuid"
    for table in ('provider_pools', 'provider_connections', 'inference_targets', 'capability_bindings'):
        op.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY')
        op.execute(f'CREATE POLICY farm_scope ON {table} USING ({farm_scope}) WITH CHECK ({farm_scope})')
        op.execute(f'GRANT SELECT,INSERT,UPDATE,DELETE ON {table} TO hearth_app')
    private_scope = farm_scope + " AND owner_id = NULLIF(current_setting('hearth.principal_id',true),'')::uuid"
    op.execute('ALTER TABLE chat_runs ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE chat_runs FORCE ROW LEVEL SECURITY')
    op.execute(f'CREATE POLICY private_scope ON chat_runs USING ({private_scope}) WITH CHECK ({private_scope})')
    op.execute('GRANT SELECT,INSERT,UPDATE,DELETE ON chat_runs TO hearth_app')
    # System catalog copy only; never rewrite user names, drafts or messages.
    op.execute("UPDATE capabilities SET definition=jsonb_set(definition,'{description}',to_jsonb(replace(definition->>'description','Hearth','hearth')))")


def downgrade():
    raise RuntimeError('Export provider and conversation data before a reviewed rollback; chat data is preserved.')
