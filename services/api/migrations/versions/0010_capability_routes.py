"""Revisioned capability assignments, route provenance and per-connection TLS trust."""
from alembic import op

revision = '0010'
down_revision = '0009'


def upgrade():
    op.execute("""
      ALTER TABLE provider_connections ADD COLUMN tls_ca_pem text NOT NULL DEFAULT '';
      CREATE TABLE capability_routes (
        farm_id uuid NOT NULL REFERENCES farms(id),
        capability_id varchar(80) NOT NULL REFERENCES capabilities(id),
        revision bigint NOT NULL DEFAULT 1 CHECK(revision > 0),
        PRIMARY KEY(farm_id,capability_id)
      );
      ALTER TABLE capability_routes ENABLE ROW LEVEL SECURITY;
      ALTER TABLE capability_routes FORCE ROW LEVEL SECURITY;
      CREATE POLICY farm_scope ON capability_routes
        USING (farm_id = NULLIF(current_setting('hearth.farm_id',true),'')::uuid)
        WITH CHECK (farm_id = NULLIF(current_setting('hearth.farm_id',true),'')::uuid);
      GRANT SELECT,INSERT,UPDATE,DELETE ON capability_routes TO hearth_app;
      ALTER TABLE chat_runs ADD COLUMN capability_id varchar(80) NOT NULL DEFAULT 'chat.general' REFERENCES capabilities(id);
      ALTER TABLE chat_runs ADD COLUMN requested_capability varchar(80) NOT NULL DEFAULT 'auto';
      ALTER TABLE chat_requests ADD COLUMN requested_capability varchar(80) NOT NULL DEFAULT 'auto';
      ALTER TABLE channel_runs ADD COLUMN capability_id varchar(80) NOT NULL DEFAULT 'chat.general' REFERENCES capabilities(id);
      ALTER TABLE channel_runs ADD COLUMN requested_capability varchar(80) NOT NULL DEFAULT 'auto';
    """)


def downgrade():
    raise RuntimeError('Export route and execution provenance before a reviewed rollback.')
