# svl/package_registry.py
# Package Registry with Verification Attestation (H43)
# Provides a package registry with cryptographic verification attestations

from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import time
from pathlib import Path
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.exceptions import InvalidSignature


class PackageType(Enum):
    """Type of package."""
    LIBRARY = "library"
    EXECUTABLE = "executable"
    TEMPLATE = "template"


class VerificationStatus(Enum):
    """Verification status of a package."""
    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    FAILED = "failed"
    REVOKED = "revoked"


@dataclass
class PackageMetadata:
    """Metadata for a package."""
    name: str
    version: str
    description: str
    author: str
    license: str
    homepage: Optional[str] = None
    repository: Optional[str] = None
    dependencies: Dict[str, str] = field(default_factory=dict)  # name -> version constraint
    keywords: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    package_type: PackageType = PackageType.LIBRARY
    entry_point: Optional[str] = None  # For executables


@dataclass
class VerificationAttestation:
    """Cryptographic verification attestation for a package."""
    package_name: str
    package_version: str
    content_hash: str  # SHA256 of package contents
    verifier_id: str  # Who verified it
    signature: bytes  # Signature of the attestation
    public_key: bytes  # Public key of verifier
    timestamp: float = field(default_factory=time.time)
    status: VerificationStatus = VerificationStatus.UNVERIFIED
    attestation_id: str = field(default_factory=lambda: hashlib.sha256(str(time.time()).encode()).hexdigest()[:16])
    # Reproducible-build identity, copied from the artifact's own `svl.attest` section when
    # there is one.  `content_hash` binds the exact bytes; these bind the PROGRAM, so two
    # builds of the same source from different layouts still compare equal.
    ast_sha256: Optional[str] = None
    gate231: Optional[List[int]] = None


@dataclass
class PackageRecord:
    """Complete package record with metadata and verification."""
    metadata: PackageMetadata
    attestations: List[VerificationAttestation] = field(default_factory=list)
    verified_content_hash: Optional[str] = None  # Hash of verified package content

    @property
    def is_verified(self) -> bool:
        """Check if package has at least one valid verification."""
        return any(a.status == VerificationStatus.VERIFIED for a in self.attestations)

    @property
    def latest_attestation(self) -> Optional[VerificationAttestation]:
        """Get the most recent attestation."""
        if not self.attestations:
            return None
        return max(self.attestations, key=lambda a: a.timestamp)


class PackageRegistry:
    """Package registry with cryptographic verification."""

    def __init__(self, storage_path: str = "./package_registry"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.packages: Dict[str, PackageRecord] = {}  # name -> PackageRecord
        self.verifiers: Dict[str, bytes] = {}  # verifier_id -> public_key
        self._load_registry()

    def _load_registry(self):
        """Load registry from disk."""
        index_file = self.storage_path / "index.json"
        if index_file.exists():
            with open(index_file, 'r') as f:
                data = json.load(f)
                for pkg_data in data.get("packages", []):
                    metadata = PackageMetadata(**pkg_data["metadata"])
                    attestations = []
                    for a in pkg_data.get("attestations", []):
                        a = dict(a)
                        # signature/public_key are persisted as hex; without decoding them the
                        # reloaded attestation can never verify (verification silently broke
                        # for any registry that was saved and loaded again).
                        for field in ("signature", "public_key"):
                            value = a.get(field)
                            if isinstance(value, str):
                                try:
                                    a[field] = bytes.fromhex(value)
                                except ValueError:
                                    a[field] = value.encode("utf-8", "replace")
                        attestations.append(VerificationAttestation(**a))
                    record = PackageRecord(
                        metadata=metadata,
                        attestations=attestations,
                        verified_content_hash=pkg_data.get("verified_content_hash")
                    )
                    self.packages[metadata.name] = record

        # Load verifiers
        verifiers_file = self.storage_path / "verifiers.json"
        if verifiers_file.exists():
            with open(verifiers_file, 'r') as f:
                data = json.load(f)
                self.verifiers = {k: bytes.fromhex(v) for k, v in data.items()}

    def _save_registry(self):
        """Save registry to disk."""
        # Save packages
        package_list = []
        for r in self.packages.values():
            attestation_list = []
            for a in r.attestations:
                attestation_list.append({
                    "package_name": a.package_name,
                    "package_version": a.package_version,
                    "content_hash": a.content_hash,
                    "verifier_id": a.verifier_id,
                    "signature": a.signature.hex(),
                    "public_key": a.public_key.hex(),
                    "timestamp": a.timestamp,
                    "status": a.status.value,
                    "attestation_id": a.attestation_id,
                    "ast_sha256": a.ast_sha256,
                    "gate231": a.gate231
                })
            package_list.append({
                "metadata": {
                    "name": r.metadata.name,
                    "version": r.metadata.version,
                    "description": r.metadata.description,
                    "author": r.metadata.author,
                    "license": r.metadata.license,
                    "homepage": r.metadata.homepage,
                    "repository": r.metadata.repository,
                    "dependencies": r.metadata.dependencies,
                    "keywords": r.metadata.keywords,
                    "created_at": r.metadata.created_at,
                    "updated_at": r.metadata.updated_at,
                    "package_type": r.metadata.package_type.value,
                    "entry_point": r.metadata.entry_point
                },
                "attestations": attestation_list,
                "verified_content_hash": r.verified_content_hash
            })

        packages_data = {
            "packages": package_list
        }

        index_file = self.storage_path / "index.json"
        with open(index_file, 'w') as f:
            json.dump(packages_data, f, indent=2)

        # Save verifiers
        verifiers_data = {k: v.hex() for k, v in self.verifiers.items()}
        verifiers_file = self.storage_path / "verifiers.json"
        with open(verifiers_file, 'w') as f:
            json.dump(verifiers_data, f, indent=2)

    def register_verifier(self, verifier_id: str, public_key_pem: bytes) -> bool:
        """Register a verifier's public key."""
        try:
            public_key = serialization.load_pem_public_key(public_key_pem)
            # Verify it's an RSA key
            if not isinstance(public_key, rsa.RSAPublicKey):
                return False
            self.verifiers[verifier_id] = public_key.public_bytes(
                encoding=serialization.Encoding.DER,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            )
            self._save_registry()
            return True
        except Exception:
            return False

    def publish_package(self, package_path: str, metadata: PackageMetadata,
                        content_hash: str, signer_key_pem: bytes) -> bool:
        """Publish a package with self-attestation.

        The attestation is marked VERIFIED only when there is something to check: a compiled
        SVL artifact (wasm magic) must carry a valid `svl.attest` section whose canonical hash
        matches the bytes it is handed.  Any other content is still published and still
        signed, but recorded as UNVERIFIED -- previously EVERY publish was marked VERIFIED
        unconditionally, which made the status meaningless.

        For a self-attesting artifact the canonical AST fingerprint (`ast_sha256`, `gate231`)
        is copied off the artifact's own section onto the attestation, so the registry exposes
        the reproducible-build identity and not only the byte hash.
        """
        # Compute content hash
        with open(package_path, 'rb') as f:
            content = f.read()
            computed_hash = hashlib.sha256(content).hexdigest()
            if computed_hash != content_hash:
                return False

        # Decide the honest status, and harvest the artifact's own self-attestation.
        ast_sha256: Optional[str] = None
        gate231: Optional[List[int]] = None
        status = VerificationStatus.UNVERIFIED
        if content[:4] == b"\x00asm":
            try:
                from svl.attest import verify_attestation, extract_attestation
                attested_ok, _details = verify_attestation(content)
                payload = extract_attestation(content) or {}
                if isinstance(payload.get("ast_sha256"), str):
                    ast_sha256 = payload["ast_sha256"]
                if isinstance(payload.get("gate231"), list):
                    gate231 = [int(x) for x in payload["gate231"]]
                if attested_ok:
                    status = VerificationStatus.VERIFIED
            except Exception:                                      # noqa: BLE001
                status = VerificationStatus.UNVERIFIED

        # Sign the attestation
        try:
            private_key = serialization.load_pem_private_key(signer_key_pem, password=None)
            if not isinstance(private_key, rsa.RSAPrivateKey):
                return False
        except Exception:
            return False

        # Create attestation
        attestation_data = f"{metadata.name}:{metadata.version}:{content_hash}".encode()
        signature = private_key.sign(
            attestation_data,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )

        public_key = private_key.public_key()
        public_key_der = public_key.public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )

        attestation = VerificationAttestation(
            package_name=metadata.name,
            package_version=metadata.version,
            content_hash=content_hash,
            verifier_id=metadata.author,  # Self-attestation by author
            signature=signature,
            public_key=public_key_der,
            status=status,
            ast_sha256=ast_sha256,
            gate231=gate231
        )

        # Create or update package record.  `verified_content_hash` is a claim that something
        # checked the bytes, so it is only set for an attestation that actually verified.
        if metadata.name in self.packages:
            record = self.packages[metadata.name]
            record.metadata = metadata
            record.attestations.append(attestation)
            if status == VerificationStatus.VERIFIED:
                record.verified_content_hash = content_hash
        else:
            record = PackageRecord(
                metadata=metadata,
                attestations=[attestation],
                verified_content_hash=content_hash if status == VerificationStatus.VERIFIED else None
            )
            self.packages[metadata.name] = record

        self._save_registry()
        return True

    def verify_package(self, package_name: str, package_version: str,
                       content: bytes, verifier_id: str) -> bool:
        """Verify a package with a registered verifier."""
        if package_name not in self.packages:
            return False

        if verifier_id not in self.verifiers:
            return False

        record = self.packages[package_name]

        # Find matching package version
        # For simplicity, we assume latest version
        # In practice, would check version constraints

        # Compute content hash
        content_hash = hashlib.sha256(content).hexdigest()

        # Verify against attested hash
        if record.verified_content_hash and record.verified_content_hash != content_hash:
            return False

        # Verify signature
        public_key_der = self.verifiers[verifier_id]
        public_key = serialization.load_der_public_key(public_key_der)

        attestation_data = f"{package_name}:{package_version}:{content_hash}".encode()

        # Find attestation by this verifier
        attestation = None
        for a in record.attestations:
            if a.verifier_id == verifier_id and a.package_version == package_version:
                attestation = a
                break

        if not attestation:
            return False

        # If the package content is a compiled SVL artifact, require its self-attestation to
        # check out. That is the only check that binds the verification to the actual code
        # bytes (see svl/attest.py) rather than to a signed claim about a hash.
        if content[:4] == b"\x00asm":
            try:
                from svl.attest import verify_attestation
                attested_ok, _details = verify_attestation(content)
            except Exception:                                      # noqa: BLE001
                attested_ok = False
            if not attested_ok:
                return False

        try:
            # SECURITY: verify against the REGISTERED key only. This previously reassigned
            # `public_key` from `attestation.public_key` — i.e. from the party being verified —
            # which made the check attacker-controlled: any package could self-sign and be
            # reported VERIFIED under a trusted verifier's name.
            public_key.verify(
                attestation.signature,
                f"{package_name}:{package_version}:{content_hash}".encode(),
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )
            return True
        except (InvalidSignature, Exception):
            return False

    def add_verification(self, package_name: str, package_version: str,
                         content_hash: str, verifier_id: str,
                         signature: bytes, public_key: bytes) -> bool:
        """Add a verification attestation from a registered verifier."""
        if package_name not in self.packages:
            return False

        if verifier_id not in self.verifiers:
            return False

        # Verify the signature matches the registered verifier
        verifier_pk_der = self.verifiers[verifier_id]
        if public_key != verifier_pk_der:
            return False

        attestation = VerificationAttestation(
            package_name=package_name,
            package_version=package_version,
            content_hash=content_hash,
            verifier_id=verifier_id,
            signature=signature,
            public_key=public_key,
            status=VerificationStatus.VERIFIED
        )

        record = self.packages[package_name]
        record.attestations.append(attestation)
        record.verified_content_hash = content_hash
        self._save_registry()
        return True

    def get_package(self, name: str) -> Optional[PackageRecord]:
        """Get package record by name."""
        return self.packages.get(name)

    def list_packages(self, query: Optional[str] = None) -> List[PackageMetadata]:
        """List packages, optionally filtered by query."""
        results = []
        for record in self.packages.values():
            if query is None or query.lower() in record.metadata.name.lower() or \
               query.lower() in record.metadata.description.lower():
                results.append(record.metadata)
        return results

    def revoke_verification(self, package_name: str, attestation_id: str) -> bool:
        """Revoke a verification attestation."""
        if package_name not in self.packages:
            return False

        record = self.packages[package_name]
        for attestation in record.attestations:
            if attestation.attestation_id == attestation_id:
                attestation.status = VerificationStatus.REVOKED
                self._save_registry()
                return True
        return False


# CLI interface
class PackageRegistryCLI:
    """Command-line interface for package registry."""

    def __init__(self, registry: PackageRegistry):
        self.registry = registry

    def publish(self, package_path: str, metadata_json: str, signer_key: str) -> bool:
        """Publish a package."""
        with open(metadata_json, 'r') as f:
            metadata_dict = json.load(f)
        metadata = PackageMetadata(**metadata_dict)

        with open(signer_key, 'rb') as f:
            signer_key_pem = f.read()

        # Compute content hash
        with open(package_path, 'rb') as f:
            content = f.read()
            content_hash = hashlib.sha256(content).hexdigest()

        return self.registry.publish_package(package_path, metadata, content_hash, signer_key_pem)

    def verify(self, package_name: str, package_version: str,
               package_path: str, verifier_id: str) -> bool:
        """Verify a package."""
        with open(package_path, 'rb') as f:
            content = f.read()
        return self.registry.verify_package(package_name, package_version, content, verifier_id)


if __name__ == '__main__':
    # Test the package registry
    print("=== Package Registry Test ===")

    registry = PackageRegistry("./test_registry")

    # Test registering a verifier
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization

    # Generate test keys
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()

    public_key_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    private_key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )

    # Register verifier
    success = registry.register_verifier("test_verifier", public_key_pem)
    print(f"Registered verifier: {success}")

    # Create test package metadata
    metadata = PackageMetadata(
        name="test_package",
        version="1.0.0",
        description="A test package",
        author="test_verifier",
        license="MIT",
        dependencies={"dep1": ">=1.0.0"},
        keywords=["test", "example"]
    )

    # Create a dummy package file
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.svl') as f:
        f.write('module test { func main() type void { return } }')
        package_path = f.name

    # Publish package
    with open(package_path, 'rb') as f:
        content = f.read()
    content_hash = hashlib.sha256(content).hexdigest()

    success = registry.publish_package(package_path, metadata, content_hash, private_key_pem)
    print(f"Published package: {success}")

    # Verify package
    with open(package_path, 'rb') as f:
        content = f.read()
    verified = registry.verify_package("test_package", "1.0.0", content, "test_verifier")
    print(f"Verified: {verified}")

    # List packages
    packages = registry.list_packages()
    print(f"Packages: {[p.name for p in packages]}")

    print("\n✓ Package Registry test complete!")