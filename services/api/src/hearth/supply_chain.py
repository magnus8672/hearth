"""Verify signed immutable content before an installer can stage it for use."""

import hashlib
import json
from base64 import urlsafe_b64decode
from collections.abc import Mapping
from pathlib import Path

from joserfc import jws
from joserfc.jwk import OKPKey

from hearth.policy import PolicyDenied

REGISTRY = jws.JWSRegistry(algorithms=["Ed25519"])
CONTENT_TYPES = {"application/hearth.recipe+json", "application/hearth.package+json", "application/hearth.node-plan+json"}


def sign_document(payload: bytes, key: OKPKey, key_id: str, content_type: str) -> str:
    if content_type not in CONTENT_TYPES or len(payload) > 128_000:
        raise ValueError("unsupported or oversized signed document")
    return jws.serialize_compact({"alg": "Ed25519", "kid": key_id, "typ": content_type}, payload, key, registry=REGISTRY)


def verify_document(compact: str, trusted_keys: Mapping[str, OKPKey], revoked_ids: set[str], content_type: str) -> bytes:
    """Key IDs select only a locally approved public key. Headers never supply keys or URLs."""
    try:
        if content_type not in CONTENT_TYPES or len(compact) > 175_000 or compact.count(".") != 2:
            raise ValueError("invalid signed content")
        encoded = compact.split(".", 1)[0]
        if len(encoded) > 1024:
            raise ValueError("oversized header")
        header = json.loads(urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        if set(header) != {"alg", "kid", "typ"} or header["alg"] != "Ed25519" or header["typ"] != content_type:
            raise ValueError("unexpected signature header")
        key_id = header["kid"]
        if not isinstance(key_id, str) or key_id in revoked_ids or key_id not in trusted_keys:
            raise ValueError("untrusted signer")
        return jws.deserialize_compact(compact, trusted_keys[key_id], registry=REGISTRY).payload
    except Exception as exc:
        raise PolicyDenied("untrusted_signed_content") from exc


def verify_file(path: Path, expected_digest: str, expected_bytes: int) -> None:
    if expected_bytes < 0 or len(expected_digest) != 64 or path.is_symlink() or not path.is_file():
        raise PolicyDenied("package_integrity_failed")
    digest, measured = hashlib.sha256(), 0
    with path.open("rb") as source:
        while chunk := source.read(1 << 20):
            measured += len(chunk)
            if measured > expected_bytes:
                raise PolicyDenied("package_integrity_failed")
            digest.update(chunk)
    if measured != expected_bytes or digest.hexdigest() != expected_digest:
        raise PolicyDenied("package_integrity_failed")
