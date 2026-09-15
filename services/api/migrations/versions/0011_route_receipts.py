"""Keep original execution identity when an assigned target moves to a new host."""
from alembic import op

revision = '0011'
down_revision = '0010'


def upgrade():
    op.execute("ALTER TABLE chat_runs ADD COLUMN route_receipt jsonb NOT NULL DEFAULT '{}'")
    op.execute("ALTER TABLE channel_runs ADD COLUMN route_receipt jsonb NOT NULL DEFAULT '{}'")
    # Old runs have no trustworthy historical target revision. Preserve only
    # what the current record provides, with that limitation made explicit.
    for table in ('chat_runs', 'channel_runs'):
        op.execute(f"UPDATE {table} r SET route_receipt=jsonb_build_object('model_id',t.model_id,'protocol',t.protocol,'target_id',t.id,'provenance','legacy_current_target') FROM inference_targets t WHERE t.id=r.target_id")


def downgrade():
    raise RuntimeError('Execution provenance must be exported before a reviewed rollback.')
