"""Deterministic authorization used before routing and again at execution boundaries."""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from hearth.contracts import AdminChangeSet, AdminExecutionGrant, CloudAuthorization, Locality

PERMISSIONS = {
    "farm.inspect", "node.enroll", "node.revoke", "node.assign", "node.operate",
    "model.approve", "package.approve", "storage.configure", "tool.approve",
    "provider.configure", "budget.configure", "role.grant", "recovery.configure",
    "audit.read", "conversation.own", "artifact.own", "memory.own", "api_key.own",
    "admin_agent.use", "admin_agent.read_history_own",
}
ROLES = {
    "Owner": frozenset(PERMISSIONS),
    "FarmAdmin": frozenset(PERMISSIONS - {"role.grant", "recovery.configure", "package.approve"}),
    "Operator": frozenset({"farm.inspect", "node.operate", "admin_agent.use", "admin_agent.read_history_own"}),
    "Auditor": frozenset({"farm.inspect", "audit.read", "admin_agent.use", "admin_agent.read_history_own"}),
    "Member": frozenset({"conversation.own", "artifact.own", "memory.own", "api_key.own"}),
}
ACTION_PERMISSIONS = {
    "assign_capability": "node.assign", "configure_service": "node.assign",
    "drain_node": "node.operate", "resume_node": "node.operate", "retry_service": "node.operate",
}


class PolicyDenied(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class Principal:
    id: UUID
    farm_id: UUID
    permissions: frozenset[str]
    authorization_version: int

    def require(self, permission: str):
        if permission not in self.permissions:
            raise PolicyDenied("permission_denied")


def inherited_locality(labels: list[Locality]) -> Locality:
    if not labels or Locality.LOCAL_ONLY in labels:
        return Locality.LOCAL_ONLY
    return Locality.CLOUD_ALLOWED


def authorize_cloud(request: CloudAuthorization):
    for allowed, code in (
        (request.provider_enabled, "provider_disabled"),
        (request.capability_allowed, "capability_forbidden"),
        (request.user_opt_in, "cloud_not_allowed"),
        (request.workspace_allowed, "workspace_local_only"),
        (inherited_locality(request.input_localities) == Locality.CLOUD_ALLOWED, "local_only_context"),
        (request.price_known, "unknown_price"),
        (request.requested_reservation_minor <= request.farm_remaining_minor, "budget_exhausted"),
        (request.requested_reservation_minor <= request.user_remaining_minor, "user_budget_exhausted"),
    ):
        if not allowed:
            raise PolicyDenied(code)


def authorize_change(principal: Principal, change: AdminChangeSet, grant: AdminExecutionGrant,
                     revisions: dict[UUID, int], now: datetime):
    principal.require("admin_agent.use")
    principal.require(ACTION_PERMISSIONS[change.intent.action])
    if change.change_hash != change_digest(change):
        raise PolicyDenied("change_content_mismatch")
    if not (principal.id == change.principal_id == grant.principal_id and
            principal.farm_id == change.farm_id == grant.farm_id and change.run_id == grant.run_id):
        raise PolicyDenied("grant_scope_mismatch")
    if grant.revoked_at is not None or min(grant.expires_at, change.expires_at) <= now:
        raise PolicyDenied("grant_expired_or_revoked")
    if grant.authorization_version != principal.authorization_version:
        raise PolicyDenied("authorization_changed")
    if grant.change_hash is not None and grant.change_hash != change.change_hash:
        raise PolicyDenied("change_hash_mismatch")
    if change.intent.action not in grant.actions or not set(change.intent.target_node_ids) <= set(grant.target_node_ids):
        raise PolicyDenied("grant_scope_mismatch")
    if change.download_bytes > grant.maximum_download_bytes:
        raise PolicyDenied("grant_resource_limit")
    if any(revisions.get(item.resource_id) != item.expected_revision for item in change.preconditions):
        raise PolicyDenied("revision_conflict")


def change_digest(change: AdminChangeSet) -> str:
    """Server-normalized content digest. A caller cannot preserve a hash while changing the approved plan."""
    try:
        payload = json.dumps(change.model_dump(mode="json", exclude={"change_hash"}), sort_keys=True,
                             separators=(",", ":"), ensure_ascii=False, allow_nan=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
    except (TypeError, ValueError) as exc:
        raise PolicyDenied("invalid_change_content") from exc
