"""Private, durable speech attached to a saved assistant reply."""
from alembic import op

revision = '0016'
down_revision = '0015'


def upgrade():
    op.execute("""
      ALTER TABLE inference_targets DROP CONSTRAINT target_protocol;
      ALTER TABLE inference_targets ADD CONSTRAINT target_protocol CHECK(protocol IN ('openai.chat.v1','hearth.image.v1','hearth.speech.v1'));
      CREATE TABLE speech_jobs (
        id uuid PRIMARY KEY, farm_id uuid NOT NULL, owner_id uuid NOT NULL,
        conversation_id uuid NOT NULL, message_id uuid NOT NULL, target_id uuid NOT NULL,
        request jsonb NOT NULL, route_receipt jsonb NOT NULL,
        status varchar(20) NOT NULL DEFAULT 'running' CHECK(status IN ('running','completed','cancelled','failed','interrupted')),
        cancel_requested boolean NOT NULL DEFAULT false,
        session_hash varchar(64) NOT NULL, authorization_version bigint NOT NULL,
        reason varchar(500), metadata jsonb, audio bytea,
        created_at timestamptz NOT NULL DEFAULT now(), finished_at timestamptz,
        FOREIGN KEY(conversation_id,farm_id,owner_id) REFERENCES conversations(id,farm_id,owner_id),
        FOREIGN KEY(message_id,farm_id,owner_id) REFERENCES messages(id,farm_id,owner_id),
        FOREIGN KEY(target_id,farm_id) REFERENCES inference_targets(id,farm_id),
        CHECK(audio IS NULL OR octet_length(audio) BETWEEN 44 AND 33554432)
      );
      CREATE UNIQUE INDEX speech_message_active ON speech_jobs(message_id) WHERE status IN ('running','completed');
      CREATE UNIQUE INDEX speech_owner_active ON speech_jobs(owner_id) WHERE status='running';
      ALTER TABLE speech_jobs ENABLE ROW LEVEL SECURITY;
      ALTER TABLE speech_jobs FORCE ROW LEVEL SECURITY;
      CREATE POLICY private_scope ON speech_jobs
        USING (farm_id=NULLIF(current_setting('hearth.farm_id',true),'')::uuid AND owner_id=NULLIF(current_setting('hearth.principal_id',true),'')::uuid)
        WITH CHECK (farm_id=NULLIF(current_setting('hearth.farm_id',true),'')::uuid AND owner_id=NULLIF(current_setting('hearth.principal_id',true),'')::uuid);
      GRANT SELECT,INSERT,UPDATE,DELETE ON speech_jobs TO hearth_app;
    """)


def downgrade():
    raise RuntimeError('Export saved speech before a reviewed rollback.')
