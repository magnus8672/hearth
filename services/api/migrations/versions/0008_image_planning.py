"""Durable local prompt planning and a fenced handoff to image execution."""
from alembic import op

revision = '0008'
down_revision = '0007'


def upgrade():
    for table in ('messages', 'channel_messages'):
        op.execute(f"ALTER TABLE {table} ADD COLUMN generation_phase varchar(30) NOT NULL DEFAULT 'text'")
        op.execute(f"ALTER TABLE {table} ADD COLUMN phase_changed_at timestamptz NOT NULL DEFAULT now()")
        op.execute(f"ALTER TABLE {table} ADD CHECK(generation_phase IN ('text','image_planning','image_handoff','image_rendering','image_finished'))")
    op.execute("""
      CREATE TABLE image_plans (
        id uuid PRIMARY KEY, farm_id uuid NOT NULL, owner_id uuid NOT NULL,
        conversation_id uuid, channel_id uuid, message_id uuid NOT NULL,
        planning_target_id uuid NOT NULL, planning_revision bigint NOT NULL,
        image_target_id uuid NOT NULL, image_revision bigint NOT NULL,
        source_image_id uuid REFERENCES conversation_images(id),
        input jsonb NOT NULL, proposal jsonb, session_hash varchar(64) NOT NULL,
        status varchar(20) NOT NULL DEFAULT 'planning', reason varchar(500),
        created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(), started_at timestamptz,
        FOREIGN KEY(conversation_id,farm_id,owner_id) REFERENCES conversations(id,farm_id,owner_id),
        FOREIGN KEY(channel_id,farm_id) REFERENCES channels(id,farm_id),
        FOREIGN KEY(planning_target_id,farm_id) REFERENCES inference_targets(id,farm_id),
        FOREIGN KEY(image_target_id,farm_id) REFERENCES inference_targets(id,farm_id),
        CHECK((conversation_id IS NOT NULL) <> (channel_id IS NOT NULL)),
        CHECK(status IN ('planning','handoff','rendering','completed','clarification','cancelled','failed','interrupted'))
      );
      ALTER TABLE image_plans ENABLE ROW LEVEL SECURITY;
      ALTER TABLE image_plans FORCE ROW LEVEL SECURITY;
      CREATE POLICY private_scope ON image_plans USING (
        owner_id=NULLIF(current_setting('hearth.principal_id',true),'')::uuid AND
        farm_id=NULLIF(current_setting('hearth.farm_id',true),'')::uuid
      ) WITH CHECK (
        owner_id=NULLIF(current_setting('hearth.principal_id',true),'')::uuid AND
        farm_id=NULLIF(current_setting('hearth.farm_id',true),'')::uuid
      );
      GRANT SELECT,INSERT,UPDATE,DELETE ON image_plans TO hearth_app;
      ALTER TABLE conversation_images ADD COLUMN planning_model varchar(200);
      ALTER TABLE conversation_images ADD COLUMN source_image_id uuid REFERENCES conversation_images(id);
      ALTER TABLE conversation_images ADD COLUMN variation boolean NOT NULL DEFAULT false;
    """)


def downgrade():
    raise RuntimeError('Export image planning provenance before a reviewed rollback.')
