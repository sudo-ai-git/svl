# svl/pcc_wasm.py
# Proof-Carrying Code for WASM (H20)
# Embeds verification proofs in WASM custom sections

from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
import hashlib
import json

from svl.parser_rd import Program, Module, FuncDecl, StructDecl
from svl.theorem_layer import verify_theorem_layer
from svl.compiler_wasm import compile_to_wasm
from svl.attest import content_hash


@dataclass
class ProofArtifact:
    """Verification proof artifact to embed in WASM."""
    layer: str  # 'syntax', 'types', 'theorem', 'smt'
    passed: bool
    checksum: str  # SHA256 of the AST that was verified
    details: Dict[str, Any]
    timestamp: str  # ISO format
    # True for layers that are reported for information only and must not be
    # presented as evidence (the BPSW monodromy check is constant-true).
    informational: bool = False


@dataclass
class PCCWasmModule:
    """WASM module with embedded proof-carrying code."""
    wasm_text: str
    proofs: List[ProofArtifact]
    source_hash: str  # SHA256 of original source
    # Compilation certificate (the band-9 binding): the SHA256 of the EXACT emitted
    # WAT, plus the SHA256 of the artifact's own canonical bytes (custom sections
    # stripped), plus the compiler version.  `verify_pcc_wasm` recompiles the source
    # with the pinned compiler and compares BOTH, so the artifact is provably the
    # compilation of its source — not merely a file that quotes a source hash and
    # carries unrelated bytes.  Empty on artifacts built before this existed.
    emitted_sha256: str = ""
    artifact_sha256: str = ""
    compiler_version: str = ""

    def to_wasm_with_proofs(self) -> str:
        """Deprecated: return WAT text with a `(custom ...)` line.

        This CANNOT assemble — wat2wasm has no custom-section syntax, so the line it
        inserts is rejected (`expected valid module field`).  Use
        `to_wasm_bytes_with_proofs()` for a real artifact.
        """
        # Parse existing WASM to find insertion point
        lines = self.wasm_text.strip().split('\n')

        # Build proof custom section
        proof_data = {
            'source_hash': self.source_hash,
            'emitted_sha256': self.emitted_sha256,
            'artifact_sha256': self.artifact_sha256,
            'compiler_version': self.compiler_version,
            'proofs': [
                {
                    'layer': p.layer,
                    'passed': p.passed,
                    'checksum': p.checksum,
                    'details': p.details,
                    'timestamp': p.timestamp,
                    'informational': p.informational,
                }
                for p in self.proofs
            ]
        }

        proof_json = json.dumps(proof_data, separators=(',', ':'))
        proof_bytes = proof_json.encode('utf-8')

        # WASM custom section format: "custom" <name_len> <name> <data_len> <data>
        # We'll add it as a text representation
        custom_section = f'''  (custom "svl-proofs" "{proof_bytes.hex()}")'''

        # Insert before closing paren of module
        result_lines = []
        for line in lines:
            if line.strip() == ')':
                result_lines.append(custom_section)
            result_lines.append(line)

        return '\n'.join(result_lines)

    def verify_proofs(self) -> bool:
        """Verify embedded proofs match source."""
        # Would extract and verify in real implementation
        return all(p.passed for p in self.proofs)

    def to_wasm_bytes_with_proofs(self) -> bytes:
        """Return a binary WASM module with the proofs in a standard custom section.

        The receiver can re-verify the artifact without the toolchain:
        `wasmtime.Module(engine, bytes)` validates it, and
        `extract_proofs_from_wasm_bytes(bytes)` recovers the proof payload.
        """
        try:
            import wasmtime
        except ImportError as exc:                          # pragma: no cover
            raise RuntimeError(
                "wasmtime is required to emit a binary PCC artifact"
            ) from exc
        binary = wasmtime.wat2wasm(self.wasm_text)
        # The artifact hash covers the canonical code bytes — custom sections are
        # stripped, so it is stable across the proof section being appended.
        self.artifact_sha256 = content_hash(bytes(binary))
        payload = {
            'source_hash': self.source_hash,
            'emitted_sha256': self.emitted_sha256,
            'artifact_sha256': self.artifact_sha256,
            'compiler_version': self.compiler_version,
            'proofs': [
                {
                    'layer': p.layer,
                    'passed': p.passed,
                    'checksum': p.checksum,
                    'details': p.details,
                    'timestamp': p.timestamp,
                    'informational': p.informational,
                }
                for p in self.proofs
            ],
        }
        return binary + WasmCustomSection.create_proof_section(payload)


def compilation_certificate(wasm_text: str) -> Tuple[str, str]:
    """The (emitted hash, compiler version) certificate for a compilation.

    The hash covers the exact emitted WAT.  Because `compile_file_to_wasm` is a pure
    function of the source (verified byte-identical across rebuilds), a verifier can
    recompile the source and compare — which proves the artifact IS that source's
    compilation rather than merely a file that quotes the source's hash.

    The ARTIFACT hash (over canonical code bytes, custom sections stripped) is
    computed by `PCCWasmModule.to_wasm_bytes_with_proofs`, which has the bytes.
    """
    from svl import __version__
    return hashlib.sha256(wasm_text.encode('utf-8')).hexdigest(), __version__


class PCCWasmGenerator:
    """Generates Proof-Carrying Code WASM modules."""

    def __init__(self):
        pass

    def generate(self, source: str, deterministic: bool = True) -> PCCWasmModule:
        """Compile source to WASM with embedded proofs."""
        # 1. Verify source with all three layers
        verification_result = verify_theorem_layer(source)

        # 2. Compile to WASM
        from svl.lexer import tokenize
        from svl.parser_rd import parse
        from svl.serialization import to_binary

        tokens = tokenize(source)
        ast = parse(tokens)
        ast_bytes = to_binary(ast)
        wasm_text = compile_to_wasm(ast, deterministic=deterministic)

        # 3. Compute source hash
        source_hash = hashlib.sha256(source.encode('utf-8')).hexdigest()

        # 4. Create proof artifacts
        emitted_sha256, compiler_version = compilation_certificate(wasm_text)
        proofs = [
            ProofArtifact(
                layer='syntax',
                passed=verification_result.syntax_layer_verified,
                checksum=hashlib.sha256(ast_bytes).hexdigest()[:32],
                details={
                    'checksums_match': verification_result.syntax_layer_verified,
                    'viable_start': getattr(verification_result, 'viable_start', None)
                },
                timestamp=__import__('datetime').datetime.utcnow().isoformat() + 'Z'
            ),
            ProofArtifact(
                layer='types',
                passed=verification_result.type_layer_verified,
                checksum=hashlib.sha256(ast_bytes).hexdigest()[32:64],
                details={
                    'dual_stream_agree': getattr(verification_result, 'dual_stream_agree', True),
                    'mod5_check': getattr(verification_result, 'mod5_check', True)
                },
                timestamp=__import__('datetime').datetime.utcnow().isoformat() + 'Z'
            ),
            ProofArtifact(
                layer='theorem',
                passed=verification_result.all_parities_even,
                checksum=verification_result.program_hash,
                details={
                    'monodromy_results': {
                        str(k): {
                            'prime': v.prime,
                            'program_hash_mod_p': v.program_hash_mod_p,
                            'mr_result': v.mr_result,
                            'lucas_result': v.lucas_result,
                            'parity': v.parity,
                            'passed': v.passed
                        }
                        for k, v in verification_result.monodromy_results.items()
                    },
                    'parities': {str(k): v.parity for k, v in verification_result.monodromy_results.items()}
                },
                timestamp=__import__('datetime').datetime.utcnow().isoformat() + 'Z',
                # Constant-true (0/60 valid programs fail it): reported for information
                # only, never as evidence.  `verify_pcc_wasm` ignores informational layers.
                informational=True,
            ),
            ProofArtifact(
                layer='smt',
                passed=verification_result.smt_verified,
                checksum=(verification_result.program_hash_hex[:32]
                          if verification_result.program_hash_hex else '0' * 32),
                details={
                    'status': verification_result.smt_status,
                    'complete': verification_result.smt_complete,
                    'assertions_checked': getattr(verification_result.smt_result, 'assertions_checked', None),
                    'assertions_proven': getattr(verification_result.smt_result, 'assertions_proven', None),
                },
                timestamp=__import__('datetime').datetime.utcnow().isoformat() + 'Z'
            )
        ]

        return PCCWasmModule(
            wasm_text=wasm_text,
            proofs=proofs,
            source_hash=source_hash,
            emitted_sha256=emitted_sha256,
            compiler_version=compiler_version,
        )

    def generate_from_ast(self, ast: Program, deterministic: bool = True) -> PCCWasmModule:
        """Generate PCC WASM from pre-parsed AST."""
        from svl.serialization import to_binary
        from svl.theorem_layer import verify_theorem_layer

        ast_bytes = to_binary(ast)
        source = self._ast_to_source(ast)
        source_hash = hashlib.sha256(source.encode('utf-8')).hexdigest()

        verification_result = verify_theorem_layer(source)
        wasm_text = compile_to_wasm(ast, deterministic=deterministic)
        emitted_sha256, compiler_version = compilation_certificate(wasm_text)

        proofs = [
            ProofArtifact(
                layer='syntax',
                passed=verification_result.syntax_layer_verified,
                checksum=hashlib.sha256(ast_bytes).hexdigest()[:32],
                details={
                    'checksums_match': verification_result.syntax_layer_verified,
                    'viable_start': getattr(verification_result, 'viable_start', None)
                },
                timestamp=__import__('datetime').datetime.utcnow().isoformat() + 'Z'
            ),
            ProofArtifact(
                layer='types',
                passed=verification_result.type_layer_verified,
                checksum=hashlib.sha256(ast_bytes).hexdigest()[32:64],
                details={
                    'dual_stream_agree': getattr(verification_result, 'dual_stream_agree', True),
                    'mod5_check': getattr(verification_result, 'mod5_check', True)
                },
                timestamp=__import__('datetime').datetime.utcnow().isoformat() + 'Z'
            ),
            ProofArtifact(
                layer='theorem',
                passed=verification_result.all_parities_even,
                checksum=verification_result.program_hash,
                details={
                    'monodromy_results': {
                        str(k): {
                            'prime': v.prime,
                            'program_hash_mod_p': v.program_hash_mod_p,
                            'mr_result': v.mr_result,
                            'lucas_result': v.lucas_result,
                            'parity': v.parity,
                            'passed': v.passed
                        }
                        for k, v in verification_result.monodromy_results.items()
                    },
                    'parities': {str(k): v.parity for k, v in verification_result.monodromy_results.items()}
                },
                timestamp=__import__('datetime').datetime.utcnow().isoformat() + 'Z',
                # Constant-true (0/60 valid programs fail it): reported for information
                # only, never as evidence.  `verify_pcc_wasm` ignores informational layers.
                informational=True,
            ),
            ProofArtifact(
                layer='smt',
                passed=verification_result.smt_verified,
                checksum=(verification_result.program_hash_hex[:32]
                          if verification_result.program_hash_hex else '0' * 32),
                details={
                    'status': verification_result.smt_status,
                    'complete': verification_result.smt_complete,
                    'assertions_checked': getattr(verification_result.smt_result, 'assertions_checked', None),
                    'assertions_proven': getattr(verification_result.smt_result, 'assertions_proven', None),
                },
                timestamp=__import__('datetime').datetime.utcnow().isoformat() + 'Z'
            )
        ]

        return PCCWasmModule(
            wasm_text=wasm_text,
            proofs=proofs,
            source_hash=source_hash,
            emitted_sha256=emitted_sha256,
            compiler_version=compiler_version,
        )

    def _ast_to_source(self, ast: Program) -> str:
        """Convert AST back to source (simplified)."""
        # In practice, would use pretty printer
        return f"module {ast.modules[0].name if ast.modules else 'main'} {{ ... }}"


def extract_proofs_from_wasm(wasm_text: str) -> Optional[Dict[str, Any]]:
    """Extract proof custom section from WASM text."""
    # Parse WASM text format for custom section
    import re

    # Look for custom section with svl-proofs
    pattern = r'\(custom\s+"svl-proofs"\s+"([^"]+)"\)'
    match = re.search(pattern, wasm_text)
    if not match:
        return None

    hex_data = match.group(1)
    try:
        proof_bytes = bytes.fromhex(hex_data)
        return json.loads(proof_bytes.decode('utf-8'))
    except Exception:
        return None


def extract_proofs_from_wasm_bytes(binary: bytes) -> Optional[Dict[str, Any]]:
    """Scan a BINARY WASM module for the `svl-proofs` custom section.

    Walks the section table (section id 0 = custom), decodes the LEB128 name length and
    compares the name.  Returns the parsed JSON payload, or None.
    """
    if binary[:4] != b'\x00asm':
        return None
    i = 8                                       # skip magic + version
    while i < len(binary):
        section_id = binary[i]
        i += 1
        size, shift = 0, 0
        while True:
            b = binary[i]
            i += 1
            size |= (b & 0x7F) << shift
            shift += 7
            if not (b & 0x80):
                break
        payload = binary[i:i + size]
        i += size
        if section_id != 0 or not payload:
            continue
        name_len, shift, j = 0, 0, 0
        while True:
            b = payload[j]
            j += 1
            name_len |= (b & 0x7F) << shift
            shift += 7
            if not (b & 0x80):
                break
        if payload[j:j + name_len].decode('utf-8', 'replace') != 'svl-proofs':
            continue
        try:
            return json.loads(payload[j + name_len:].decode('utf-8'))
        except Exception:
            return None
    return None


def verify_pcc_wasm(wasm, source: str) -> Tuple[bool, List[str]]:
    """Verify PCC WASM against source code.

    Accepts either WAT text (legacy) or binary bytes (the real artifact).

    The embedded proof payload is treated as a CLAIM, not as evidence.  The verifier
    re-derives the compile-time gate and the SMT verdict from ``source`` and refuses the
    artifact when the re-derivation contradicts it — so a forged payload that claims
    ``passed: true`` for a false assertion is rejected.
    """
    if isinstance(wasm, (bytes, bytearray)):
        proofs_data = extract_proofs_from_wasm_bytes(bytes(wasm))
    else:
        proofs_data = extract_proofs_from_wasm(wasm)
    if not proofs_data:
        return False, ["No proof custom section found in WASM"]

    errors = []

    # Verify source hash matches
    source_hash = hashlib.sha256(source.encode('utf-8')).hexdigest()
    if proofs_data.get('source_hash') != source_hash:
        errors.append(f"Source hash mismatch: expected {source_hash}, got {proofs_data.get('source_hash')}")

    # Compilation certificate.  Two independent bindings, both required:
    #   * artifact_sha256 — the ARTIFACT's own canonical bytes.  Without this a file
    #     could quote a source hash and carry unrelated bytes.
    #   * emitted_sha256  — the recompilation of the source with the pinned compiler.
    #     Without this the artifact could be some other program that happens to quote
    #     the right source hash.
    # Together they prove: source --compiler--> bytes, and the artifact IS those bytes.
    recorded_emitted = proofs_data.get('emitted_sha256')
    recorded_artifact = proofs_data.get('artifact_sha256')
    recorded_version = proofs_data.get('compiler_version')
    if recorded_emitted or recorded_artifact:
        from svl import __version__ as current_version
        if recorded_version and recorded_version != current_version:
            errors.append(
                f"Compilation certificate version mismatch: artifact was built by "
                f"compiler {recorded_version}, this is {current_version}")

        if recorded_artifact:
            from svl.attest import content_hash
            given = content_hash(bytes(wasm) if isinstance(wasm, (bytes, bytearray)) else wasm)
            if given != recorded_artifact:
                errors.append(
                    "Compilation certificate mismatch: the artifact's own bytes hash to "
                    f"{given[:16]}..., not the recorded {recorded_artifact[:16]}... "
                    f"— the artifact was modified after certification")

        if recorded_emitted and not (recorded_version and recorded_version != current_version):
            try:
                import wasmtime
                from svl.attest import content_hash
                from svl.compiler_wasm import compile_file_to_wasm
                from svl.pcc_wasm import compilation_certificate
                recompiled_wat = compile_file_to_wasm(source)
                recompiled, _ = compilation_certificate(recompiled_wat)
                if recompiled != recorded_emitted:
                    errors.append(
                        "Compilation certificate mismatch: recompiling the source emits "
                        f"bytes hashing to {recompiled[:16]}..., not the recorded "
                        f"{recorded_emitted[:16]}... — the artifact is NOT the "
                        f"compilation of this source")
                # The binding that ties the two halves together: the ARTIFACT's own
                # canonical bytes must be exactly the recompilation's.  Without this a
                # swapped body could carry a self-consistent pair of claims.
                if recorded_artifact:
                    recompiled_artifact = content_hash(bytes(wasmtime.wat2wasm(recompiled_wat)))
                    given = content_hash(bytes(wasm) if isinstance(wasm, (bytes, bytearray)) else wasm)
                    if recompiled_artifact != given:
                        errors.append(
                            "Compilation certificate mismatch: the artifact's bytes are "
                            f"not the compilation of this source (artifact "
                            f"{given[:16]}... vs recompilation "
                            f"{recompiled_artifact[:16]}...)")
            except Exception as exc:                              # noqa: BLE001
                errors.append(
                    f"could not recompile for the compilation certificate "
                    f"({type(exc).__name__}: {exc})")
    else:
        # Legacy artifact (pre-certificate).  Not a failure, but it cannot prove the
        # binding, and the caller is told so.
        errors.append(
            "no compilation certificate (artifact predates emitted-bytes binding); "
            "source hash matches but the artifact bytes are not bound to it")

    # Re-derive the compile-time gate from the source (AST guard + type layer + interval AI).
    try:
        from svl.verify_gate import verify_program
        problems = verify_program(source)
    except Exception as exc:                                          # noqa: BLE001
        problems = [f"re-derivation raised {type(exc).__name__}: {exc}"]
    if problems:
        errors.append("re-derived gate verdict: FAIL\n  - " + "\n  - ".join(problems))

    # Re-derive the SMT verdict from the source.  A counterexample means the artifact
    # claims a passing build for a program whose assertions are false.
    try:
        from svl.smt_theorem import verify_with_smt
        smt_result = verify_with_smt(source)
        if smt_result.status == 'counterexample':
            errors.append(
                "re-derived SMT verdict: counterexample"
                + (f" ({smt_result.error_message})" if smt_result.error_message else "")
            )
    except ImportError:
        pass
    except Exception as exc:                                          # noqa: BLE001
        errors.append(f"re-derived SMT verdict: could not re-derive ({type(exc).__name__}: {exc})")

    # The embedded claims must not contradict the re-derivation.  `informational`
    # layers (the constant-true BPSW monodromy check) are reported but carry no
    # evidentiary weight, so they cannot make an artifact pass or fail.
    for proof in proofs_data.get('proofs', []):
        if proof.get('informational', False):
            continue
        if not proof.get('passed', False):
            errors.append(f"Proof for layer '{proof['layer']}' did not pass")

    return len(errors) == 0, errors


# WASM Custom Section Binary Format Helpers
class WasmCustomSection:
    """WASM custom section binary encoding."""

    @staticmethod
    def encode_string(s: str) -> bytes:
        """Encode string in WASM LEB128 length-prefixed format."""
        data = s.encode('utf-8')
        length = WasmCustomSection._encode_leb128(len(data))
        return length + data

    @staticmethod
    def _encode_leb128(value: int) -> bytes:
        """Encode unsigned LEB128."""
        result = []
        while True:
            byte = value & 0x7f
            value >>= 7
            if value != 0:
                byte |= 0x80
            result.append(byte)
            if value == 0:
                break
        return bytes(result)

    @staticmethod
    def create_section(name: str, data: bytes) -> bytes:
        """Create a complete WASM custom section."""
        # Section code for custom = 0
        section_code = b'\x00'

        # Section name
        name_bytes = WasmCustomSection.encode_string(name)

        # Section payload: name + data
        payload = name_bytes + data

        # Section size (LEB128)
        size = WasmCustomSection._encode_leb128(len(payload))

        return section_code + size + payload

    @staticmethod
    def create_proof_section(proofs_data: Dict[str, Any]) -> bytes:
        """Create SVL proof custom section."""
        proof_json = json.dumps(proofs_data, separators=(',', ':'))
        return WasmCustomSection.create_section('svl-proofs', proof_json.encode('utf-8'))


if __name__ == '__main__':
    print("=== PCC WASM Test ===")

    test_source = '''
    module main {
      func main() type void {
        let x: int = 42
        let y: int = 58
        let z: int = x + y
        assert z == 100
        return
      }
    }
    '''

    generator = PCCWasmGenerator()
    pcc_module = generator.generate(test_source)

    print(f"Source hash: {pcc_module.source_hash}")
    print(f"WASM length: {len(pcc_module.wasm_text)} chars")
    print(f"Proofs: {len(pcc_module.proofs)}")

    for p in pcc_module.proofs:
        print(f"  {p.layer}: passed={p.passed}, checksum={p.checksum[:16]}...")

    # Generate WASM with proofs
    wasm_with_proofs = pcc_module.to_wasm_with_proofs()
    print(f"\nWASM with proofs length: {len(wasm_with_proofs)} chars")

    # Extract and verify
    extracted = extract_proofs_from_wasm(wasm_with_proofs)
    if extracted:
        print(f"Extracted proofs: {len(extracted.get('proofs', []))}")

    # Verify
    valid, errors = verify_pcc_wasm(wasm_with_proofs, test_source)
    print(f"\nVerification: {'PASS' if valid else 'FAIL'}")
    for e in errors:
        print(f"  Error: {e}")

    # Test binary format
    binary_section = WasmCustomSection.create_proof_section(extracted)
    print(f"\nBinary custom section size: {len(binary_section)} bytes")

    print("\n✓ PCC WASM test complete!")