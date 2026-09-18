"""Operator-adopted workers and a durable, content-free GPU queue."""
from alembic import op

revision = '0023'
down_revision = '0022'


def upgrade():
    op.execute("""
      CREATE TABLE managed_workers (
        id uuid PRIMARY KEY, farm_id uuid NOT NULL REFERENCES farms(id),
        name text NOT NULL CHECK(length(name) BETWEEN 1 AND 120),
        pool_id uuid NOT NULL UNIQUE REFERENCES provider_pools(id),
        token_hash text NOT NULL CHECK(length(token_hash)=64),
        recipe_digest text NOT NULL CHECK(length(recipe_digest)=64),
        services jsonb NOT NULL CHECK(jsonb_typeof(services)='object'),
        policy text NOT NULL DEFAULT 'resident' CHECK(policy IN ('resident','shared')),
        paused boolean NOT NULL DEFAULT true, revoked boolean NOT NULL DEFAULT false,
        desired_service text, revision bigint NOT NULL DEFAULT 1,
        boot_id uuid, sequence bigint NOT NULL DEFAULT 0, seen_at timestamptz,
        observed_revision bigint NOT NULL DEFAULT 0, ready_service text,
        state text NOT NULL DEFAULT 'offline' CHECK(state IN ('offline','stopped','starting','ready','failed')),
        reason text NOT NULL DEFAULT '', created_at timestamptz NOT NULL DEFAULT now()
      );
      CREATE TABLE image_queue (
        id uuid PRIMARY KEY REFERENCES image_jobs(id), farm_id uuid NOT NULL REFERENCES farms(id),
        owner_id uuid NOT NULL REFERENCES users(id), pool_id uuid NOT NULL REFERENCES provider_pools(id),
        target_id uuid NOT NULL REFERENCES inference_targets(id), target_revision bigint NOT NULL,
        state text NOT NULL DEFAULT 'queued' CHECK(state IN ('queued','starting','dispatched','finished')),
        created_at timestamptz NOT NULL DEFAULT now(), claimed_at timestamptz,
        expires_at timestamptz NOT NULL DEFAULT now()+interval '30 minutes'
      );
      CREATE INDEX image_queue_pending ON image_queue(pool_id,created_at,id) WHERE state='queued';
      ALTER TABLE provider_pools ADD COLUMN last_queue_owner uuid;
    """)
    for table in ('managed_workers', 'image_queue'):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY; ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
        op.execute(f"CREATE POLICY farm_scope ON {table} USING(farm_id=NULLIF(current_setting('hearth.farm_id',true),'')::uuid) WITH CHECK(farm_id=NULLIF(current_setting('hearth.farm_id',true),'')::uuid);")
        op.execute(f'GRANT SELECT,INSERT,UPDATE,DELETE ON {table} TO hearth_app;')


def downgrade():
    raise RuntimeError('Drain managed work before removing worker state.')
