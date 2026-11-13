"""Attestation soundness for the package registry.

`PackageRegistry.add_verification` used to compare only the caller-supplied
`public_key` bytes against the registered key and then write `status=VERIFIED`
without ever calling `verify()`.  Anyone who knew a registered public key could
therefore attest arbitrary content, **and** pin its hash as the record's
`verified_content_hash` — the hash `verify_package` later compares real bytes
against.  Every test here is built to fail if that behaviour comes back.
"""
import hashlib
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from svl.package_registry import (
    PackageMetadata,
    PackageRegistry,
    VerificationStatus,
    verify_attestation_signature,
)


def _keypair():
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub_pem = priv.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return priv, pub_pem


def _pss():
    return padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
                       salt_length=padding.PSS.MAX_LENGTH)


def _sign(priv, name, version, content_hash):
    return priv.sign(
        f"{name}:{version}:{content_hash}".encode(), _pss(), hashes.SHA256()
    )


def _pem(priv):
    return priv.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def _register(tmp_path, verifier="alice"):
    """Register `verifier` and return (registry, its private key).

    `publish_package` self-attests under `metadata.author` and signs with the key it is
    handed, so the signer MUST be the registered verifier's key — that is the whole
    point of the registry.
    """
    reg = PackageRegistry(str(tmp_path / "registry"))
    signer, pub_pem = _keypair()
    assert reg.register_verifier(verifier, pub_pem), "verifier registration failed"
    return reg, signer


def _publish(tmp_path, reg, signer, name="pkg", version="1.0.0", body=None):
    """Publish `body` as `name@version` signed by `signer`; return (hash, body, signer)."""
    body = body if body is not None else b"module m { func f() type void { return } }"
    path = tmp_path / f"{name}-{version}.bin"
    path.write_bytes(body)
    content_hash = hashlib.sha256(body).hexdigest()
    meta = PackageMetadata(name=name, version=version, description="t",
                           author="alice", license="MIT")
    assert reg.publish_package(str(path), meta, content_hash, _pem(signer))
    return content_hash, body, signer


def _record(reg, name):
    rec = reg.get_package(name)
    assert rec is not None, f"package {name!r} not in the registry"
    return rec


class TestAddVerificationSoundness:
    def test_forged_signature_is_refused(self, tmp_path):
        """Registered key, garbage signature -> REFUSED, and nothing is pinned."""
        reg, signer = _register(tmp_path)
        _publish(tmp_path, reg, signer)
        pk = reg.verifiers["alice"]

        before = _record(reg, "pkg").verified_content_hash
        ok = reg.add_verification(
            "pkg", "1.0.0", "0" * 64, "alice", b"not-a-signature", pk
        )
        assert ok is False, "a garbage signature must not be accepted"
        assert _record(reg, "pkg").verified_content_hash == before, \
            "a refused attestation must not pin the verified content hash"

    def test_signature_by_an_unregistered_key_is_refused(self, tmp_path):
        """Signed by a real key that is NOT the registered one -> refused."""
        reg, signer = _register(tmp_path)
        _publish(tmp_path, reg, signer)
        intruder, _ = _keypair()
        pk = reg.verifiers["alice"]

        sig = _sign(intruder, "pkg", "1.0.0", "0" * 64)
        assert reg.add_verification("pkg", "1.0.0", "0" * 64, "alice", sig, pk) is False

    def test_wrong_payload_is_refused(self, tmp_path):
        """Signed over a DIFFERENT content hash than the one submitted."""
        reg, signer = _register(tmp_path)
        real_hash, _, signer = _publish(tmp_path, reg, signer)
        pk = reg.verifiers["alice"]

        sig = _sign(signer, "pkg", "1.0.0", "f" * 64)
        assert reg.add_verification("pkg", "1.0.0", real_hash, "alice", sig, pk) is False

    def test_valid_signature_is_accepted(self, tmp_path):
        """The legitimate path still works: sign, submit, accepted."""
        reg, signer = _register(tmp_path)
        content_hash, _, signer = _publish(tmp_path, reg, signer)
        pk = reg.verifiers["alice"]

        sig = _sign(signer, "pkg", "1.0.0", content_hash)
        assert reg.add_verification("pkg", "1.0.0", content_hash, "alice", sig, pk) is True
        rec = _record(reg, "pkg")
        assert rec.is_verified
        assert rec.verified_content_hash == content_hash

    def test_unknown_verifier_is_refused(self, tmp_path):
        reg, signer = _register(tmp_path)
        _publish(tmp_path, reg, signer)
        _, pub_pem = _keypair()
        pk = serialization.load_pem_public_key(pub_pem).public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        assert reg.add_verification("pkg", "1.0.0", "0" * 64, "mallory", b"x", pk) is False


class TestSignatureHelper:
    def test_tampered_signature_bytes_fail(self):
        priv, _ = _keypair()
        pk = priv.public_key().public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        sig = bytearray(_sign(priv, "a", "1.0.0", "h"))
        assert verify_attestation_signature(bytes(sig), pk, "a", "1.0.0", "h") is True
        sig[0] ^= 0xFF
        assert verify_attestation_signature(bytes(sig), pk, "a", "1.0.0", "h") is False

    def test_non_rsa_key_is_refused(self):
        """An EC key is not an RSA key; the helper must decline, not crash."""
        from cryptography.hazmat.primitives.asymmetric import ec
        ec_priv = ec.generate_private_key(ec.SECP256R1())
        ec_der = ec_priv.public_key().public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        assert verify_attestation_signature(b"sig", ec_der, "a", "1.0.0", "h") is False


class TestPublishVerifyStillAgree:
    """The refactor to a shared payload constructor must not break the working path."""

    def test_publish_then_verify_roundtrip(self, tmp_path):
        reg, signer = _register(tmp_path)
        _, body, _ = _publish(tmp_path, reg, signer)
        assert reg.verify_package("pkg", "1.0.0", body, "alice") is True

    def test_verify_rejects_tampered_content(self, tmp_path):
        reg, signer = _register(tmp_path)
        _publish(tmp_path, reg, signer)
        assert reg.verify_package("pkg", "1.0.0", b"tampered", "alice") is False

    def test_self_attesting_artifact_is_verified(self, tmp_path):
        """A compiled SVL artifact with a valid svl.attest section -> VERIFIED."""
        from svl.attest import attest
        from svl.compiler_wasm import compile_file_to_wasm

        src = "module m { func add(a: int, b: int) type int { return a + b } }"
        binary, _payload = attest(src, compile_file_to_wasm(src))

        signer, _ = _keypair()
        reg = PackageRegistry(str(tmp_path / "r2"))
        assert reg.register_verifier("alice", _pem_pub(signer))

        path = tmp_path / "attested.wasm"
        path.write_bytes(binary)
        content_hash = hashlib.sha256(binary).hexdigest()
        meta = PackageMetadata(name="att", version="1.0.0", description="t",
                               author="alice", license="MIT")
        assert reg.publish_package(str(path), meta, content_hash, _pem(signer)) is True

        rec = _record(reg, "att")
        assert rec.attestations[0].status is VerificationStatus.VERIFIED
        assert reg.verify_package("att", "1.0.0", binary, "alice") is True


def _pem_pub(priv):
    return priv.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
