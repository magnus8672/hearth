from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from hearth.contracts import AdminChangeSet, AdminExecutionGrant, AdminIntent, RevisionPrecondition
from hearth.policy import ROLES, PolicyDenied, Principal, authorize_change, change_digest


@pytest.fixture
def approval():
    now = datetime.now(UTC)
    principal = Principal(uuid4(), uuid4(), ROLES["Owner"], 3)
    target, run = uuid4(), uuid4()
    change = AdminChangeSet(id=uuid4(), farm_id=principal.farm_id, principal_id=principal.id, run_id=run,
        intent=AdminIntent(action="drain_node", target_node_ids=[target]), change_hash="0" * 64,
        preconditions=[RevisionPrecondition(resource_id=target, expected_revision=4)], download_bytes=0,
        disruption="Finish active work and stop taking new jobs.", expires_at=now + timedelta(minutes=5))
    change.change_hash = change_digest(change)
    grant = AdminExecutionGrant(id=uuid4(), farm_id=principal.farm_id, principal_id=principal.id, run_id=run,
        change_hash=change.change_hash, target_node_ids=[target], actions=["drain_node"], maximum_download_bytes=0,
        authorization_version=3, expires_at=now + timedelta(minutes=5))
    return principal, change, grant, {target: 4}, now


def test_approved_exact_change_applies_under_current_permissions(approval):
    authorize_change(*approval)


@pytest.mark.parametrize("mutation,code", [
    ({"run_id": uuid4()}, "grant_scope_mismatch"),
    ({"farm_id": uuid4()}, "grant_scope_mismatch"),
    ({"principal_id": uuid4()}, "grant_scope_mismatch"),
    ({"target_node_ids": [uuid4()]}, "grant_scope_mismatch"),
    ({"actions": ["resume_node"]}, "grant_scope_mismatch"),
    ({"change_hash": "f" * 64}, "change_hash_mismatch"),
    ({"authorization_version": 2}, "authorization_changed"),
    ({"revoked_at": datetime.now(UTC)}, "grant_expired_or_revoked"),
    ({"expires_at": datetime.now(UTC) - timedelta(seconds=1)}, "grant_expired_or_revoked"),
])
def test_grant_cannot_cross_scope_or_outlive_authority(approval, mutation, code):
    principal, change, grant, revisions, now = approval
    with pytest.raises(PolicyDenied, match=code):
        authorize_change(principal, change, grant.model_copy(update=mutation), revisions, now)


def test_plan_tampering_revision_conflict_and_demotion_fail(approval):
    principal, change, grant, revisions, now = approval
    with pytest.raises(PolicyDenied, match="change_content_mismatch"):
        authorize_change(principal, change.model_copy(update={"download_bytes": 100}), grant, revisions, now)
    with pytest.raises(PolicyDenied, match="revision_conflict"):
        authorize_change(principal, change, grant, {key: 5 for key in revisions}, now)
    for role in ("Member", "Auditor"):
        with pytest.raises(PolicyDenied, match="permission_denied"):
            authorize_change(replace(principal, permissions=ROLES[role]), change, grant, revisions, now)
