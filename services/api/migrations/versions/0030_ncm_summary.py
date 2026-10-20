"""NCM single-document summarization transport; existing capability permission."""
from alembic import op

revision = '0030'
down_revision = '0029'
branch_labels = depends_on = None


def upgrade():
    op.execute("ALTER TABLE inference_targets DROP CONSTRAINT target_protocol")
    op.execute("ALTER TABLE inference_targets ADD CONSTRAINT target_protocol CHECK(protocol IN ('openai.chat.v1','hearth.image.v1','hearth.speech.v1','hearth.transcription.v1','hearth.geometry.v1','hearth.decision.v1','hearth.summary.v1'))")


def downgrade():
    raise RuntimeError('Remove NCM targets deliberately before reverting the protocol migration.')
