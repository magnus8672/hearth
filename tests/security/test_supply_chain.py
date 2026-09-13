import hashlib
import json
from base64 import urlsafe_b64encode

import pytest
from hearth.policy import PolicyDenied
from hearth.supply_chain import sign_document, verify_document, verify_file
from joserfc.jwk import OKPKey


def test_signed_recipe_rejects_tampering_revocation_and_type_confusion():
    private = OKPKey.generate_key("Ed25519")
    public = OKPKey.import_key(private.as_dict(private=False))
    content_type = "application/hearth.recipe+json"
    payload = b'{"schema_version":1,"recipe_id":"fixture"}'
    compact = sign_document(payload, private, "test-key", content_type)
    assert verify_document(compact, {"test-key": public}, set(), content_type) == payload
    segments = compact.split(".")
    segments[1] = urlsafe_b64encode(b'{"command":"unapproved"}').decode().rstrip("=")
    for token, keys, revoked, typ in (
        (".".join(segments), {"test-key": public}, set(), content_type),
        (compact, {}, set(), content_type),
        (compact, {"test-key": public}, {"test-key"}, content_type),
        (compact, {"test-key": public}, set(), "application/hearth.node-plan+json"),
    ):
        with pytest.raises(PolicyDenied):
            verify_document(token, keys, revoked, typ)
    segments = compact.split(".")
    segments[0] = urlsafe_b64encode(json.dumps({"alg": "Ed25519", "kid": "test-key", "typ": content_type,
                                               "jku": "https://untrusted.invalid"}).encode()).decode().rstrip("=")
    with pytest.raises(PolicyDenied):
        verify_document(".".join(segments), {"test-key": public}, set(), content_type)


def test_package_digest_and_exact_size_are_both_required(tmp_path):
    artifact = tmp_path / "fixture.bin"
    artifact.write_bytes(b"immutable package fixture")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    verify_file(artifact, digest, artifact.stat().st_size)
    for expected_digest, size in (("f" * 64, artifact.stat().st_size), (digest, 1), (digest, 100)):
        with pytest.raises(PolicyDenied):
            verify_file(artifact, expected_digest, size)
