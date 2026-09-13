import base64
import json
import os
import subprocess
from pathlib import Path

import pytest
from hearth.contracts import CONTRACTS
from hearth.enrollment import decrypt_envelope, encrypt_envelope
from hearth.supply_chain import sign_document
from joserfc.jwk import OKPKey
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[2]


def test_shared_schema_fixtures():
    fixtures = json.loads((ROOT / "tests/fixtures/contracts.json").read_text())
    for fixture in fixtures:
        try:
            CONTRACTS[fixture["contract"]].model_validate(fixture["payload"])
            valid = True
        except ValidationError:
            valid = False
        assert valid == fixture["valid"], fixture["name"]


def test_go_python_enrollment_round_trip(enrollment):
    pending, envelope, key, now = enrollment
    binary = ROOT / ".hearth/bin" / ("hearth-contracts.exe" if os.name == "nt" else "hearth-contracts")
    if not binary.exists():
        pytest.fail("Build native contract probe before Go/Python interoperability test")
    secret = base64.urlsafe_b64encode(key).decode().rstrip("=")

    def call(request):
        result = subprocess.run([str(binary)], input=json.dumps(request), text=True, capture_output=True, check=True)
        return json.loads(result.stdout)

    python_jwe = encrypt_envelope(envelope, key)
    assert call({"action": "decrypt", "secret": secret, "ciphertext": python_jwe}) == envelope.model_dump(mode="json")
    go_jwe = call({"action": "encrypt", "secret": secret, "payload": envelope.model_dump(mode="json")})["ciphertext"]
    assert decrypt_envelope(go_jwe, key, pending, envelope.control_origin, now) == envelope


def test_python_signed_recipe_verified_by_native_go():
    binary = ROOT / ".hearth/bin" / ("hearth-contracts.exe" if os.name == "nt" else "hearth-contracts")
    private = OKPKey.generate_key("Ed25519")
    public = private.as_dict(private=False)["x"]
    typ = "application/hearth.recipe+json"
    payload = b'{"schema_version":1,"recipe_id":"test"}'
    compact = sign_document(payload, private, "approved", typ)
    request = {"action": "verify-signature", "public_key": public, "signer_id": "approved", "content_type": typ, "ciphertext": compact}

    def verify(changes):
        result = subprocess.run([str(binary)], input=json.dumps(request | changes), capture_output=True, text=True, check=True)
        return json.loads(result.stdout)

    result = verify({})
    assert result["valid"] is True
    assert base64.urlsafe_b64decode(result["payload"] + "=" * (-len(result["payload"]) % 4)) == payload
    segments = compact.split(".")
    segments[1] = base64.urlsafe_b64encode(b'{"unapproved":true}').decode().rstrip("=")
    for changes in ({"revoked": True}, {"signer_id": "wrong"}, {"content_type": "application/hearth.node-plan+json"},
                    {"ciphertext": ".".join(segments)}, {"public_key": OKPKey.generate_key("Ed25519").as_dict(private=False)["x"]}):
        assert verify(changes)["valid"] is False
