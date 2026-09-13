import secrets
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from hearth.contracts import EnrollmentEnvelope, EnrollmentPending


@pytest.fixture
def enrollment():
    now = datetime.now(UTC)
    pending = EnrollmentPending(attempt_id=uuid4(), node_id=uuid4(), nonce=secrets.token_urlsafe(32),
                                 public_key_fingerprint="a" * 64, display_name="Test member")
    envelope = EnrollmentEnvelope(farm_id=uuid4(), node_id=pending.node_id, attempt_id=pending.attempt_id,
        nonce=pending.nonce, public_key_fingerprint=pending.public_key_fingerprint,
        farm_ca_pem="FIXTURE ONLY: " + "x" * 120, control_origin="https://127.0.0.1:8443",
        enrollment_token=secrets.token_urlsafe(32), expires_at=now + timedelta(minutes=5))
    return pending, envelope, secrets.token_bytes(32), now
