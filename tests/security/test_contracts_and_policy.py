from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from hearth.config import Settings
from hearth.contracts import CloudAuthorization, GeometryRequest, Heartbeat, Locality, NodePlan
from hearth.policy import ROLES, PolicyDenied, authorize_cloud, inherited_locality
from pydantic import ValidationError


def test_production_rejects_test_identity_and_http_origins():
    with pytest.raises(ValidationError):
        Settings(mode="production", fixture_identity=True)
    with pytest.raises(ValidationError):
        Settings(mode="production", database_url="postgresql+psycopg://x", session_encryption_key="x", admin_origin="http://localhost")
    with pytest.raises(ValidationError):
        Settings(mode="development", fixture_identity=True)


def test_worker_schema_rejects_injected_authority_unknown_version_and_boolean_epoch():
    body = dict(node_id=str(uuid4()), farm_id=str(uuid4()), node_epoch=1,
                controller_generation=1, sequence=1, observed_plan_revision=0)
    Heartbeat.model_validate(body)
    for mutation in ({"admin": True}, {"schema_version": 2}, {"node_epoch": True}, {"sequence": 0}):
        with pytest.raises(ValidationError):
            Heartbeat.model_validate(body | mutation)


def test_plan_revisions_cannot_skip_or_replay():
    body = dict(farm_id=uuid4(), node_id=uuid4(), controller_generation=1, node_epoch=1,
                expected_revision=3, desired_revision=4, expires_at=datetime.now(UTC) + timedelta(minutes=5))
    NodePlan.model_validate(body)
    for revision in (3, 5):
        with pytest.raises(ValidationError):
            NodePlan.model_validate(body | {"desired_revision": revision})


def test_default_content_and_derived_content_stay_local():
    assert inherited_locality([]) == Locality.LOCAL_ONLY
    assert inherited_locality([Locality.CLOUD_ALLOWED, Locality.LOCAL_ONLY]) == Locality.LOCAL_ONLY


def cloud_request(**changes):
    return CloudAuthorization.model_validate(dict(provider_enabled=True, capability_allowed=True,
        user_opt_in=True, workspace_allowed=True, price_known=True, farm_remaining_minor=100,
        user_remaining_minor=100, requested_reservation_minor=10, input_localities=["cloud_allowed"]) | changes)


@pytest.mark.parametrize("changes,code", [
    ({"provider_enabled": False}, "provider_disabled"),
    ({"user_opt_in": False}, "cloud_not_allowed"),
    ({"workspace_allowed": False}, "workspace_local_only"),
    ({"input_localities": ["cloud_allowed", "local_only"]}, "local_only_context"),
    ({"price_known": False}, "unknown_price"),
    ({"farm_remaining_minor": 0}, "budget_exhausted"),
    ({"user_remaining_minor": 9}, "user_budget_exhausted"),
])
def test_every_cloud_gate_is_required(changes, code):
    with pytest.raises(PolicyDenied, match=code):
        authorize_cloud(cloud_request(**changes))


def test_authorized_cloud_policy_and_geometry_input():
    authorize_cloud(cloud_request())
    with pytest.raises(ValidationError):
        GeometryRequest()
    GeometryRequest(prompt="A small stone arch")
    assert "node.enroll" not in ROLES["Member"]
    assert "role.grant" not in ROLES["FarmAdmin"]
    assert "package.approve" not in ROLES["Operator"]
