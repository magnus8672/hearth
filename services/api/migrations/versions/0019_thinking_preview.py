"""Separate, owner-scoped provider thinking previews for private replies."""
from alembic import op

revision = '0019'
down_revision = '0018'


def upgrade():
    # chat_runs already enforces the conversation owner's farm/principal RLS.
    # Separate columns never enter message search, prompt history or vault exports.
    op.execute("""
      ALTER TABLE chat_runs ADD COLUMN reasoning_text text NOT NULL DEFAULT '' CHECK(octet_length(reasoning_text)<=65536);
      ALTER TABLE chat_runs ADD COLUMN reasoning_truncated boolean NOT NULL DEFAULT false;
      ALTER TABLE chat_runs ADD COLUMN stream_phase varchar(12) NOT NULL DEFAULT 'waiting' CHECK(stream_phase IN ('waiting','reasoning','answer'));
    """)


def downgrade():
    raise RuntimeError('Review retained thinking previews before rolling back this migration.')
