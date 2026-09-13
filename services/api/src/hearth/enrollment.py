"""Enrollment envelopes use standard JOSE with a fixed, narrow algorithm policy."""

import json
from datetime import datetime

from joserfc import jwe
from joserfc.jwk import OctKey

from hearth.contracts import EnrollmentEnvelope, EnrollmentPending
from hearth.policy import PolicyDenied

REGISTRY = jwe.JWERegistry(algorithms=["dir", "A256GCM"])


def encrypt_envelope(envelope: EnrollmentEnvelope, secret: bytes) -> str:
    if len(secret) != 32:
        raise ValueError("pairing secret must contain 256 bits")
    return jwe.encrypt_compact({"alg": "dir", "enc": "A256GCM"}, envelope.model_dump_json(),
                               OctKey.import_key(secret), registry=REGISTRY)


def decrypt_envelope(ciphertext: str, secret: bytes, pending: EnrollmentPending,
                     expected_origin: str, now: datetime) -> EnrollmentEnvelope:
    if len(secret) != 32 or len(ciphertext) > 32768:
        raise PolicyDenied("invalid_enrollment_envelope")
    try:
        # Reject security header extensions rather than interpreting attacker-selected behavior.
        from base64 import urlsafe_b64decode
        segment = ciphertext.split(".")[0]
        header = json.loads(urlsafe_b64decode(segment + "=" * (-len(segment) % 4)))
        if header != {"alg": "dir", "enc": "A256GCM"}:
            raise ValueError("unexpected JWE security header")
        result = jwe.decrypt_compact(ciphertext, OctKey.import_key(secret), registry=REGISTRY)
        envelope = EnrollmentEnvelope.model_validate_json(result.plaintext)
    except Exception as exc:
        raise PolicyDenied("invalid_enrollment_envelope") from exc
    if (envelope.node_id != pending.node_id or envelope.attempt_id != pending.attempt_id or
            envelope.nonce != pending.nonce or envelope.public_key_fingerprint != pending.public_key_fingerprint or
            envelope.control_origin != expected_origin or envelope.expires_at <= now or
            (envelope.expires_at - now).total_seconds() > 600):
        raise PolicyDenied("enrollment_binding_mismatch")
    return envelope
