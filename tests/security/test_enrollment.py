import base64
import json
import secrets
from datetime import timedelta
from uuid import uuid4

import pytest
from hearth.enrollment import decrypt_envelope, encrypt_envelope
from hearth.policy import PolicyDenied


def test_jwe_interoperable_shape_fresh_iv_and_round_trip(enrollment):
    pending, envelope, key, now = enrollment
    first, second = encrypt_envelope(envelope, key), encrypt_envelope(envelope, key)
    assert first != second
    assert first.split(".")[2] != second.split(".")[2]
    assert decrypt_envelope(first, key, pending, envelope.control_origin, now) == envelope


def test_ciphertext_key_and_binding_tampering_fail(enrollment):
    pending, envelope, key, now = enrollment
    ciphertext = encrypt_envelope(envelope, key)
    pieces = ciphertext.split(".")
    pieces[4] = ("B" if pieces[4][0] == "A" else "A") + pieces[4][1:]
    for altered, altered_key, expectation, origin, at in (
        (".".join(pieces), key, pending, envelope.control_origin, now),
        (ciphertext, secrets.token_bytes(32), pending, envelope.control_origin, now),
        (ciphertext, key, pending.model_copy(update={"node_id": uuid4()}), envelope.control_origin, now),
        (ciphertext, key, pending.model_copy(update={"nonce": secrets.token_urlsafe(32)}), envelope.control_origin, now),
        (ciphertext, key, pending, "https://rogue.invalid", now),
        (ciphertext, key, pending, envelope.control_origin, now + timedelta(minutes=11)),
    ):
        with pytest.raises(PolicyDenied):
            decrypt_envelope(altered, altered_key, expectation, origin, at)


def test_unknown_security_headers_are_rejected(enrollment):
    pending, envelope, key, now = enrollment
    pieces = encrypt_envelope(envelope, key).split(".")
    for extra in ({"zip": "DEF"}, {"jku": "https://rogue.invalid"}, {"alg": "A256KW"}):
        header = {"alg": "dir", "enc": "A256GCM"} | extra
        pieces[0] = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
        with pytest.raises(PolicyDenied):
            decrypt_envelope(".".join(pieces), key, pending, envelope.control_origin, now)
