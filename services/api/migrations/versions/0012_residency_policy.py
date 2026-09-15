"""Preserve existing providers; opt in to loaded-model checks per target."""
from alembic import op

revision = '0012'
down_revision = '0011'


def upgrade():
    op.execute("ALTER TABLE inference_targets ADD COLUMN residency_policy varchar(32) NOT NULL DEFAULT 'unknown' CHECK (residency_policy IN ('unknown','lmstudio_loaded'))")
    op.execute("ALTER TABLE inference_targets ADD CONSTRAINT residency_protocol CHECK (residency_policy='unknown' OR protocol='openai.chat.v1')")


def downgrade():
    raise RuntimeError('Residency policy requires an explicit reviewed rollback.')
