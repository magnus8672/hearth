"""Core catalog, private content, scoped grants and durable outbox.

Revision ID: 0001
"""
import json
from pathlib import Path

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0001"
down_revision = None


def upgrade():
    op.create_table("farms", sa.Column("id", UUID, primary_key=True), sa.Column("name", sa.String(120), nullable=False),
                    sa.Column("controller_generation", sa.BigInteger, nullable=False, server_default="1"),
                    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_table("capabilities", sa.Column("id", sa.String(80), primary_key=True),
                    sa.Column("revision", sa.BigInteger, nullable=False), sa.Column("definition", JSONB, nullable=False))
    op.create_table("permission_catalog", sa.Column("id", sa.String(80), primary_key=True))
    op.create_table("users", sa.Column("id", UUID, primary_key=True),
                    sa.Column("farm_id", UUID, sa.ForeignKey("farms.id"), nullable=False),
                    sa.Column("issuer", sa.String(500), nullable=False), sa.Column("subject", sa.String(200), nullable=False),
                    sa.Column("display_name", sa.String(120), nullable=False),
                    sa.Column("state", sa.String(20), nullable=False, server_default="active"),
                    sa.Column("authorization_version", sa.BigInteger, nullable=False, server_default="1"),
                    sa.UniqueConstraint("issuer", "subject"), sa.UniqueConstraint("id", "farm_id"))
    op.create_table("role_grants", sa.Column("id", UUID, primary_key=True),
                    sa.Column("user_id", UUID, nullable=False), sa.Column("farm_id", UUID, nullable=False),
                    sa.Column("role", sa.String(60), nullable=False),
                    sa.ForeignKeyConstraint(["user_id", "farm_id"], ["users.id", "users.farm_id"]),
                    sa.UniqueConstraint("user_id", "farm_id", "role"))
    op.create_table("workspaces", sa.Column("id", UUID, primary_key=True),
                    sa.Column("farm_id", UUID, nullable=False), sa.Column("owner_id", UUID, nullable=False),
                    sa.Column("name", sa.String(120), nullable=False),
                    sa.Column("locality", sa.String(20), nullable=False, server_default="local_only"),
                    sa.ForeignKeyConstraint(["owner_id", "farm_id"], ["users.id", "users.farm_id"]),
                    sa.UniqueConstraint("id", "farm_id", "owner_id"),
                    sa.CheckConstraint("locality IN ('local_only','cloud_allowed')"))
    op.create_table("conversations", sa.Column("id", UUID, primary_key=True),
                    sa.Column("farm_id", UUID, nullable=False), sa.Column("owner_id", UUID, nullable=False),
                    sa.Column("workspace_id", UUID, nullable=False), sa.Column("title", sa.String(200), nullable=False),
                    sa.Column("revision", sa.BigInteger, nullable=False, server_default="1"),
                    sa.Column("deleted_at", sa.DateTime(timezone=True)),
                    sa.ForeignKeyConstraint(["workspace_id", "farm_id", "owner_id"], ["workspaces.id", "workspaces.farm_id", "workspaces.owner_id"]),
                    sa.UniqueConstraint("id", "farm_id", "owner_id"))
    op.create_table("messages", sa.Column("id", UUID, primary_key=True),
                    sa.Column("conversation_id", UUID, nullable=False), sa.Column("farm_id", UUID, nullable=False),
                    sa.Column("owner_id", UUID, nullable=False), sa.Column("sequence", sa.BigInteger, nullable=False),
                    sa.Column("role", sa.String(20), nullable=False), sa.Column("content", sa.Text, nullable=False),
                    sa.Column("locality", sa.String(20), nullable=False, server_default="local_only"),
                    sa.Column("status", sa.String(20), nullable=False, server_default="completed"),
                    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
                    sa.ForeignKeyConstraint(["conversation_id", "farm_id", "owner_id"], ["conversations.id", "conversations.farm_id", "conversations.owner_id"]),
                    sa.UniqueConstraint("conversation_id", "sequence"),
                    sa.CheckConstraint("locality IN ('local_only','cloud_allowed')"))
    op.create_table("outbox", sa.Column("id", UUID, primary_key=True), sa.Column("farm_id", UUID, nullable=False),
                    sa.Column("owner_id", UUID, nullable=False), sa.Column("aggregate_id", UUID, nullable=False),
                    sa.Column("aggregate_version", sa.BigInteger, nullable=False), sa.Column("event_type", sa.String(80), nullable=False),
                    sa.Column("payload", JSONB, nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
                    sa.Column("delivered_at", sa.DateTime(timezone=True)),
                    sa.UniqueConstraint("aggregate_id", "aggregate_version", "event_type"))
    op.create_table("audit_events", sa.Column("id", UUID, primary_key=True), sa.Column("farm_id", UUID, nullable=False),
                    sa.Column("actor_id", UUID), sa.Column("action", sa.String(80), nullable=False),
                    sa.Column("safe_metadata", JSONB, nullable=False), sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    for table in ("workspaces", "conversations", "messages", "outbox"):
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        clause = "owner_id = NULLIF(current_setting('hearth.principal_id', true), '')::uuid AND farm_id = NULLIF(current_setting('hearth.farm_id', true), '')::uuid"
        op.execute(f'CREATE POLICY private_scope ON "{table}" USING ({clause}) WITH CHECK ({clause})')
    for table in ("farms", "users", "role_grants"):
        op.execute(f'GRANT SELECT ON "{table}" TO hearth_app')
    for table in ("workspaces", "conversations", "messages", "outbox"):
        op.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON "{table}" TO hearth_app')
    op.execute("GRANT SELECT ON capabilities, permission_catalog TO hearth_app")
    op.execute("GRANT INSERT ON audit_events TO hearth_app")
    seeds = json.loads((Path(__file__).resolve().parents[1] / "seeds/0001.json").read_text())
    capabilities = sa.table("capabilities", sa.column("id"), sa.column("revision"), sa.column("definition", JSONB))
    op.bulk_insert(capabilities, [{"id": c["capability_id"], "revision": c["revision"], "definition": c} for c in seeds["capabilities"]])
    permissions = sa.table("permission_catalog", sa.column("id"))
    op.bulk_insert(permissions, [{"id": p} for p in seeds["permissions"]])


def downgrade():
    for table in ("audit_events", "outbox", "messages", "conversations", "workspaces", "role_grants", "users", "permission_catalog", "capabilities", "farms"):
        op.drop_table(table)
