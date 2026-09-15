"""Share reply model identity with channel participants without exposing run secrets."""
from alembic import op

revision = '0014'
down_revision = '0013'


def upgrade():
    op.execute('ALTER TABLE channel_messages ADD COLUMN model_id varchar(200)')
    # The migrator can read historical receipts for every author. Normal channel
    # readers still cannot inspect another member's private execution records.
    op.execute("UPDATE channel_messages m SET model_id=r.route_receipt->>'model_id' FROM channel_runs r WHERE r.assistant_message_id=m.id AND m.role='assistant'")


def downgrade():
    raise RuntimeError('Preserve reply provenance before a reviewed rollback.')
