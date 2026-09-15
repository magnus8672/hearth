"""Separate image protocol and private, durable generation artifacts."""
from alembic import op

revision = '0006'
down_revision = '0005'


def upgrade():
    op.execute("""
      ALTER TABLE inference_targets ADD COLUMN protocol varchar(40) NOT NULL DEFAULT 'openai.chat.v1';
      ALTER TABLE inference_targets ADD COLUMN profile jsonb NOT NULL DEFAULT '{}';
      ALTER TABLE inference_targets ADD CONSTRAINT target_protocol CHECK(protocol IN ('openai.chat.v1','hearth.image.v1'));
      CREATE TABLE image_jobs (
        id uuid PRIMARY KEY, farm_id uuid NOT NULL, owner_id uuid NOT NULL, workspace_id uuid NOT NULL,
        target_id uuid NOT NULL, request jsonb NOT NULL, status varchar(20) NOT NULL DEFAULT 'running',
        cancel_requested boolean NOT NULL DEFAULT false, progress integer NOT NULL DEFAULT 0,
        session_hash varchar(64) NOT NULL, authorization_version bigint NOT NULL,
        metadata jsonb, image bytea, reason varchar(500),
        created_at timestamptz NOT NULL DEFAULT now(), finished_at timestamptz,
        FOREIGN KEY(workspace_id,farm_id,owner_id) REFERENCES workspaces(id,farm_id,owner_id),
        FOREIGN KEY(target_id,farm_id) REFERENCES inference_targets(id,farm_id),
        CHECK(status IN ('running','completed','cancelled','failed','interrupted')),
        CHECK(image IS NULL OR octet_length(image)<=16777216)
      );
      ALTER TABLE image_jobs ENABLE ROW LEVEL SECURITY;
      ALTER TABLE image_jobs FORCE ROW LEVEL SECURITY;
      CREATE POLICY private_scope ON image_jobs USING (
        owner_id=NULLIF(current_setting('hearth.principal_id',true),'')::uuid AND
        farm_id=NULLIF(current_setting('hearth.farm_id',true),'')::uuid
      ) WITH CHECK (
        owner_id=NULLIF(current_setting('hearth.principal_id',true),'')::uuid AND
        farm_id=NULLIF(current_setting('hearth.farm_id',true),'')::uuid
      );
      GRANT SELECT,INSERT,UPDATE,DELETE ON image_jobs TO hearth_app;
    """)


def downgrade():
    raise RuntimeError('Export private image artifacts before a reviewed rollback.')
