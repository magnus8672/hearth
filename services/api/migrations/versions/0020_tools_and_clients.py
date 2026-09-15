"""Shared MCP catalog, private credentials/invocations and capability client keys."""
from alembic import op

revision = '0020'
down_revision = '0019'


def upgrade():
    op.execute("""
      CREATE TABLE client_keys (
        id uuid PRIMARY KEY, farm_id uuid NOT NULL, owner_id uuid NOT NULL,
        name varchar(120) NOT NULL, token_hash varchar(64) NOT NULL UNIQUE,
        capabilities jsonb NOT NULL, allow_tools boolean NOT NULL DEFAULT false,
        authorization_version bigint NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(), expires_at timestamptz NOT NULL,
        revoked_at timestamptz, last_used_at timestamptz,
        FOREIGN KEY(owner_id,farm_id) REFERENCES users(id,farm_id), UNIQUE(id,farm_id,owner_id)
      );
      CREATE TABLE client_runs (
        id uuid PRIMARY KEY, farm_id uuid NOT NULL, owner_id uuid NOT NULL, key_id uuid NOT NULL,
        target_id uuid NOT NULL, route_receipt jsonb NOT NULL,
        state varchar(20) NOT NULL DEFAULT 'running' CHECK(state IN ('running','completed','failed','interrupted')),
        created_at timestamptz NOT NULL DEFAULT now(), finished_at timestamptz,
        FOREIGN KEY(key_id,farm_id,owner_id) REFERENCES client_keys(id,farm_id,owner_id) ON DELETE CASCADE,
        FOREIGN KEY(target_id,farm_id) REFERENCES inference_targets(id,farm_id)
      );
      CREATE TABLE mcp_servers (
        id uuid PRIMARY KEY, farm_id uuid NOT NULL REFERENCES farms(id), owner_id uuid NOT NULL,
        name varchar(120) NOT NULL, base_url varchar(2048) NOT NULL,
        tls_ca_pem text NOT NULL DEFAULT '', allow_insecure_http boolean NOT NULL DEFAULT false,
        requires_credential boolean NOT NULL DEFAULT false, enabled boolean NOT NULL DEFAULT true,
        revision bigint NOT NULL DEFAULT 1, catalog_revision bigint NOT NULL DEFAULT 1, connection_revision bigint NOT NULL DEFAULT 1,
        created_at timestamptz NOT NULL DEFAULT now(), checked_at timestamptz, reason varchar(500),
        FOREIGN KEY(owner_id,farm_id) REFERENCES users(id,farm_id), UNIQUE(id,farm_id), UNIQUE(farm_id,base_url)
      );
      CREATE TABLE mcp_tools (
        id uuid PRIMARY KEY, farm_id uuid NOT NULL, server_id uuid NOT NULL,
        name varchar(128) NOT NULL, definition jsonb NOT NULL, schema_hash varchar(64) NOT NULL,
        enabled boolean NOT NULL DEFAULT false, access varchar(12) NOT NULL DEFAULT 'owner' CHECK(access IN ('owner','members')),
        effect varchar(12) NOT NULL DEFAULT 'write' CHECK(effect IN ('read','write')),
        capabilities jsonb NOT NULL DEFAULT '[]', revision bigint NOT NULL DEFAULT 1,
        FOREIGN KEY(server_id,farm_id) REFERENCES mcp_servers(id,farm_id) ON DELETE CASCADE,
        UNIQUE(id,farm_id), UNIQUE(server_id,name)
      );
      CREATE TABLE mcp_credentials (
        server_id uuid NOT NULL, farm_id uuid NOT NULL, owner_id uuid NOT NULL, credential text NOT NULL, connection_revision bigint NOT NULL DEFAULT 1,
        PRIMARY KEY(server_id,owner_id),
        FOREIGN KEY(server_id,farm_id) REFERENCES mcp_servers(id,farm_id) ON DELETE CASCADE,
        FOREIGN KEY(owner_id,farm_id) REFERENCES users(id,farm_id)
      );
      CREATE TABLE tool_invocations (
        id uuid PRIMARY KEY, farm_id uuid NOT NULL, owner_id uuid NOT NULL, tool_id uuid NOT NULL,
        tool_revision bigint NOT NULL, server_revision bigint NOT NULL, request_hash varchar(64) NOT NULL,
        arguments jsonb NOT NULL, result jsonb, capability_id varchar(80), chat_run_id uuid,
        state varchar(20) NOT NULL CHECK(state IN ('awaiting_approval','approved','running','completed','failed','uncertain','denied')),
        created_at timestamptz NOT NULL DEFAULT now(), expires_at timestamptz NOT NULL DEFAULT now()+interval '15 minutes',
        finished_at timestamptz,
        FOREIGN KEY(tool_id,farm_id) REFERENCES mcp_tools(id,farm_id),
        FOREIGN KEY(owner_id,farm_id) REFERENCES users(id,farm_id)
      );
      CREATE INDEX tool_invocations_owner ON tool_invocations(farm_id,owner_id,created_at DESC);
      ALTER TABLE chat_runs ADD COLUMN tool_phase boolean NOT NULL DEFAULT false;
      ALTER TABLE chat_runs ADD COLUMN tool_phase_at timestamptz;
    """)
    farm = "farm_id=NULLIF(current_setting('hearth.farm_id',true),'')::uuid"
    private = farm + " AND owner_id=NULLIF(current_setting('hearth.principal_id',true),'')::uuid"
    for table in ('client_keys', 'client_runs', 'mcp_servers', 'mcp_tools', 'mcp_credentials', 'tool_invocations'):
        scope = farm if table in ('mcp_servers', 'mcp_tools') else private
        op.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY')
        op.execute(f'CREATE POLICY scope ON {table} USING ({scope}) WITH CHECK ({scope})')
        op.execute(f'GRANT SELECT,INSERT,UPDATE,DELETE ON {table} TO hearth_app')


def downgrade():
    raise RuntimeError('Review retained client keys, tool approvals and invocation receipts before rollback.')
