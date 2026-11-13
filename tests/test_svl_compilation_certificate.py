"""The compilation certificate: artifact ↔ source ↔ compiler.

Before this, `verify_pcc_wasm` re-derived the gate and SMT verdict from the source and
compared a `source_hash` the artifact *quoted*.  Nothing bound the artifact's own BYTES:
a file could quote a source hash and carry unrelated code.

`PCCWasmModule` now carries a compilation certificate — the emitted WAT hash, the
artifact's canonical byte hash (custom sections stripped), and the compiler version —
and `verify_pcc_wasm` checks three bindings:

  1. the artifact's own bytes hash to the recorded value;
  2. recompiling the source emits the recorded WAT hash;
  3. the artifact's canonical bytes ARE the recompilation's.

(3) is the one that ties the halves together; without it a swapped body can carry a
self-consistent pair of claims.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from svl.pcc_wasm import (
    PCCWasmGenerator,
    compilation_certificate,
    extract_proofs_from_wasm_bytes,
    verify_pcc_wasm,
)

SRC = 'module m { func add(a: int, b: int) type int { return a + b } }'
OTHER = 'module m { func add(a: int, b: int) type int { return a - b } }'


def _artifact(source=SRC):
    return PCCWasmGenerator().generate(source).to_wasm_bytes_with_proofs()


def _resign(module):
    """Serialise a module whose fields have been edited after generation."""
    return module.to_wasm_bytes_with_proofs()


def _legacy_artifact(source=SRC):
    """An artifact whose proof payload predates the compilation certificate.

    `to_wasm_bytes_with_proofs` always recomputes the certificate, so clearing the
    fields is not enough — the payload has to be built without them.
    """
    import hashlib
    import wasmtime
    from svl.compiler_wasm import compile_file_to_wasm
    from svl.pcc_wasm import WasmCustomSection
    binary = wasmtime.wat2wasm(compile_file_to_wasm(source))
    payload = {
        'source_hash': hashlib.sha256(source.encode('utf-8')).hexdigest(),
        'proofs': [],
    }
    return binary + WasmCustomSection.create_proof_section(payload)


class TestCertificatePresent:
    def test_payload_carries_all_three_fields(self):
        payload = extract_proofs_from_wasm_bytes(_artifact())
        assert payload['source_hash']
        assert payload['emitted_sha256']
        assert payload['artifact_sha256']
        assert payload['compiler_version']

    def test_emitted_hash_is_the_wat_hash(self):
        from svl.compiler_wasm import compile_file_to_wasm
        import hashlib
        expected = hashlib.sha256(compile_file_to_wasm(SRC).encode()).hexdigest()
        assert extract_proofs_from_wasm_bytes(_artifact())['emitted_sha256'] == expected

    def test_artifact_hash_is_the_canonical_code_hash(self):
        from svl.attest import content_hash
        blob = _artifact()
        # The canonical hash is over the code bytes; appending a different custom
        # section must not change it.
        assert extract_proofs_from_wasm_bytes(blob)['artifact_sha256'] == content_hash(blob)

    def test_compilation_certificate_shape(self):
        emitted, version = compilation_certificate('(module)')
        assert len(emitted) == 64
        assert version


class TestValidArtifact:
    def test_verifies(self):
        ok, errors = verify_pcc_wasm(_artifact(), SRC)
        assert ok, errors

    def test_reproducible_across_generations(self):
        a = _artifact()
        b = _artifact()
        assert extract_proofs_from_wasm_bytes(a)['emitted_sha256'] == \
               extract_proofs_from_wasm_bytes(b)['emitted_sha256']


class TestTamperRefused:
    def test_swapped_body_is_refused(self):
        """The key case: a different compilation carrying a forged-but-consistent pair
        of claims.  Only the artifact-vs-recompilation binding catches it."""
        gen = PCCWasmGenerator()
        module = gen.generate(SRC)
        module.wasm_text = gen.generate(OTHER).wasm_text
        module.emitted_sha256 = gen.generate(SRC).emitted_sha256   # forged claim
        ok, errors = verify_pcc_wasm(_resign(module), SRC)
        assert not ok
        assert any('not the compilation of this source' in e for e in errors)

    def test_flipped_body_byte_is_refused(self):
        blob = bytearray(_artifact())
        blob[20] ^= 0x01                       # inside the code section
        ok, errors = verify_pcc_wasm(bytes(blob), SRC)
        assert not ok
        assert any('modified after certification' in e for e in errors)

    def test_forged_emitted_hash_is_refused(self):
        gen = PCCWasmGenerator()
        module = gen.generate(SRC)
        module.emitted_sha256 = '0' * 64
        ok, errors = verify_pcc_wasm(_resign(module), SRC)
        assert not ok
        assert any('recompiling the source emits' in e for e in errors)

    def test_forged_compiler_version_is_refused(self):
        gen = PCCWasmGenerator()
        module = gen.generate(SRC)
        module.compiler_version = '0.0.0-fake'
        ok, errors = verify_pcc_wasm(_resign(module), SRC)
        assert not ok
        assert any('version mismatch' in e for e in errors)

    def test_wrong_source_is_refused(self):
        ok, errors = verify_pcc_wasm(_artifact(), OTHER)
        assert not ok

    def test_artifact_for_another_program_is_refused_against_this_source(self):
        ok, errors = verify_pcc_wasm(_artifact(OTHER), SRC)
        assert not ok
        assert any('not the compilation of this source' in e or
                   'Source hash mismatch' in e for e in errors)


class TestLegacyArtifact:
    def test_an_artifact_without_a_certificate_is_reported(self):
        """Pre-certificate artifacts cannot prove the binding; say so, don't pass silently."""
        ok, errors = verify_pcc_wasm(_legacy_artifact(), SRC)
        assert not ok
        assert any('no compilation certificate' in e for e in errors)
