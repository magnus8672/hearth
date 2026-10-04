"""Private typed decisions and independently revisioned routing policy."""
import json

from alembic import op
from sqlalchemy import text

revision = '0029'
down_revision = '0028'


def upgrade():
    # Freeze this definition independently of future catalog edits.
    definition = {'schema_version': 1, 'capability_id': 'decision.evaluate', 'revision': 1,
                  'display_name': 'Decisions', 'description': 'Typed local decisions without executing actions.',
                  'icon': 'reasoning', 'input_modalities': ['text'], 'output_modalities': ['text'],
                  'quality_suite': 'decision.evaluate.v1', 'deadline_seconds': 30, 'cloud_eligible': False}
    op.get_bind().execute(text("INSERT INTO capabilities(id,revision,definition) VALUES('decision.evaluate',1,CAST(:definition AS jsonb))"), {'definition': json.dumps(definition)})
    op.execute("INSERT INTO permission_catalog(id) VALUES('capability.decision.evaluate')")
    op.execute("""
      ALTER TABLE inference_targets DROP CONSTRAINT target_protocol;
      ALTER TABLE inference_targets ADD CONSTRAINT target_protocol CHECK(protocol IN
        ('openai.chat.v1','hearth.image.v1','hearth.speech.v1','hearth.transcription.v1','hearth.geometry.v1','hearth.decision.v1'));
      ALTER TABLE capability_routes ADD COLUMN selection_policy text NOT NULL DEFAULT 'ordered'
        CHECK(selection_policy IN ('ordered','balanced'));
      CREATE TABLE decision_settings (
        farm_id uuid PRIMARY KEY REFERENCES farms(id), revision bigint NOT NULL DEFAULT 1 CHECK(revision>0),
        mode text NOT NULL DEFAULT 'legacy' CHECK(mode IN ('legacy','shadow','semantic')),
        source text NOT NULL DEFAULT 'builtin' CHECK(source IN ('builtin','dedicated')),
        target_id uuid, fallback_builtin boolean NOT NULL DEFAULT true,
        member_builtin boolean NOT NULL DEFAULT true,
        threshold double precision NOT NULL DEFAULT 0.85 CHECK(threshold>=0 AND threshold<=1),
        deadline_ms integer NOT NULL DEFAULT 5000 CHECK(deadline_ms BETWEEN 100 AND 10000),
        shadow_sample integer NOT NULL DEFAULT 0 CHECK(shadow_sample BETWEEN 0 AND 100),
        CHECK(source='builtin' OR target_id IS NOT NULL)
      );
      CREATE TABLE decision_runs (
        id uuid PRIMARY KEY, farm_id uuid NOT NULL, owner_id uuid NOT NULL,
        target_id uuid, request jsonb NOT NULL, request_hash text NOT NULL,
        state text NOT NULL DEFAULT 'running' CHECK(state IN ('running','completed','failed','cancelled')),
        result jsonb, receipt jsonb NOT NULL, reason text, cancel_requested boolean NOT NULL DEFAULT false,
        created_at timestamptz NOT NULL DEFAULT now(), finished_at timestamptz,
        FOREIGN KEY(owner_id,farm_id) REFERENCES users(id,farm_id)
      );
      CREATE INDEX decision_runs_owner ON decision_runs(farm_id,owner_id,created_at DESC);
      CREATE TABLE route_affinity (
        farm_id uuid NOT NULL, owner_id uuid NOT NULL, scope text NOT NULL, capability_id text NOT NULL,
        candidate_hash text NOT NULL, target_id uuid NOT NULL, expires_at timestamptz NOT NULL,
        PRIMARY KEY(farm_id,owner_id,scope,capability_id),
        FOREIGN KEY(owner_id,farm_id) REFERENCES users(id,farm_id)
      );
      CREATE TABLE decision_observations (
        id uuid PRIMARY KEY, farm_id uuid NOT NULL, owner_id uuid NOT NULL,
        metadata jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
        FOREIGN KEY(owner_id,farm_id) REFERENCES users(id,farm_id)
      );
    """)
    for table in ('decision_settings', 'decision_runs', 'route_affinity', 'decision_observations'):
        op.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY')
        scope = "farm_id=NULLIF(current_setting('hearth.farm_id',true),'')::uuid"
        if table != 'decision_settings':
            scope += " AND owner_id=NULLIF(current_setting('hearth.principal_id',true),'')::uuid"
        op.execute(f'CREATE POLICY scoped ON {table} USING ({scope}) WITH CHECK ({scope})')
        op.execute(f'GRANT SELECT,INSERT,UPDATE,DELETE ON {table} TO hearth_app')


def downgrade():
    raise RuntimeError('Export decision history and restore a reviewed backup before rollback.')
