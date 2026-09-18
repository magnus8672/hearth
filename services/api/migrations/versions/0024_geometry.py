"""Private geometry and one fair queue for all managed GPU work."""
from alembic import op

revision = '0024'
down_revision = '0023'


def upgrade():
    op.execute("""
      ALTER TABLE inference_targets DROP CONSTRAINT target_protocol;
      ALTER TABLE inference_targets ADD CONSTRAINT target_protocol CHECK(protocol IN ('openai.chat.v1','hearth.image.v1','hearth.speech.v1','hearth.transcription.v1','hearth.geometry.v1'));
      CREATE TABLE geometry_jobs (
        id uuid PRIMARY KEY, farm_id uuid NOT NULL, owner_id uuid NOT NULL, workspace_id uuid NOT NULL,
        target_id uuid NOT NULL, request jsonb NOT NULL, status text NOT NULL DEFAULT 'queued',
        source_image bytea, artifact bytea, metadata jsonb, reason varchar(500),
        cancel_requested boolean NOT NULL DEFAULT false, progress integer NOT NULL DEFAULT 0,
        session_hash varchar(64) NOT NULL, authorization_version bigint NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(), finished_at timestamptz, deleted_at timestamptz,
        FOREIGN KEY(workspace_id,farm_id,owner_id) REFERENCES workspaces(id,farm_id,owner_id),
        FOREIGN KEY(target_id,farm_id) REFERENCES inference_targets(id,farm_id),
        CHECK(status IN ('queued','running','completed','cancelled','failed','interrupted')),
        CHECK(octet_length(source_image)<=8388608), CHECK(octet_length(artifact)<=67108864)
      );
      ALTER TABLE geometry_jobs ENABLE ROW LEVEL SECURITY;
      ALTER TABLE geometry_jobs FORCE ROW LEVEL SECURITY;
      CREATE POLICY private_scope ON geometry_jobs USING(owner_id=NULLIF(current_setting('hearth.principal_id',true),'')::uuid AND farm_id=NULLIF(current_setting('hearth.farm_id',true),'')::uuid)
      WITH CHECK(owner_id=NULLIF(current_setting('hearth.principal_id',true),'')::uuid AND farm_id=NULLIF(current_setting('hearth.farm_id',true),'')::uuid);
      GRANT SELECT,INSERT,UPDATE,DELETE ON geometry_jobs TO hearth_app;
      ALTER TABLE image_queue RENAME TO capability_queue;
      ALTER TABLE capability_queue DROP CONSTRAINT image_queue_id_fkey;
      ALTER TABLE capability_queue ADD COLUMN kind text NOT NULL DEFAULT 'image' CHECK(kind IN ('image','geometry'));
      ALTER TABLE capability_queue ADD COLUMN image_id uuid GENERATED ALWAYS AS (CASE WHEN kind='image' THEN id END) STORED REFERENCES image_jobs(id);
      ALTER TABLE capability_queue ADD COLUMN geometry_id uuid GENERATED ALWAYS AS (CASE WHEN kind='geometry' THEN id END) STORED REFERENCES geometry_jobs(id);
      ALTER TABLE capability_queue ADD CONSTRAINT queue_job_reference CHECK(
        (kind='image' AND image_id IS NOT NULL AND image_id=id AND geometry_id IS NULL) OR
        (kind='geometry' AND geometry_id IS NOT NULL AND geometry_id=id AND image_id IS NULL));
    """)


def downgrade():
    raise RuntimeError('Export private geometry and drain jobs before a reviewed rollback.')
