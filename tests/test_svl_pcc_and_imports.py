"""Regression tests for the two honesty fixes (2026-11-12).

* The compile gate runs AFTER import linking, so an imported module can no longer
  bypass the AST guard, the type checker and the interval analyser.
* ``verify_pcc_wasm`` re-derives the gate and SMT verdicts from the source instead of
  trusting the embedded ``passed`` booleans, so a forged proof is rejected.
"""
import hashlib

import pytest

from tests.conftest import run_main
from svl.compiler_wasm import compile_file_to_wasm
from svl.verify_gate import SVLVerificationError


# ---------------------------------------------------------------------------
# P0.3 — the import verification bypass
# ---------------------------------------------------------------------------

def test_broken_import_is_refused(tmp_path):
    """A provably-broken imported module must be refused, naming the file."""
    (tmp_path / "evil.svl").write_text(
        "module evil { func main() type int { let a = [1]  let i = 5  return a[i] } }"
    )
    main = 'import "evil.svl"\nmodule m { func main() type int { return 0 } }'
    with pytest.raises(SVLVerificationError, match="evil.svl"):
        compile_file_to_wasm(main, base_dir=str(tmp_path))


def test_correct_import_links_and_runs(tmp_path, wasmtime_module):
    """Negative control: a clean imported module still links and executes."""
    (tmp_path / "lib.svl").write_text(
        "module lib { func answer() type int { return 42 } }"
    )
    main = 'import "lib.svl"\nmodule m { func main() type int { return answer() } }'
    wat = compile_file_to_wasm(main, base_dir=str(tmp_path))
    assert run_main(wasmtime_module, wat) == 42


def test_false_assert_in_import_is_refused_with_prove(tmp_path, z3_module):
    """`prove=True` must cover the linked program, not just the raw source."""
    (tmp_path / "bad.svl").write_text(
        "module bad { func main() type int { assert 1 == 2  return 0 } }"
    )
    main = 'import "bad.svl"\nmodule m { func main() type int { return 0 } }'
    with pytest.raises(SVLVerificationError, match="counterexample"):
        compile_file_to_wasm(main, base_dir=str(tmp_path), prove=True)


# ---------------------------------------------------------------------------
# P0.2 — the forged PCC proof
# ---------------------------------------------------------------------------

def test_forged_pcc_proof_is_refused(wasmtime_module):
    """A payload claiming `passed: true` for a false assertion must be rejected."""
    from svl.pcc_wasm import WasmCustomSection, verify_pcc_wasm

    source = "module t { func main() type int { assert 1 == 2  return 0 } }"
    binary = wasmtime_module.wat2wasm(
        compile_file_to_wasm("module t { func main() type int { return 0 } }")
    )
    payload = {
        "source_hash": hashlib.sha256(source.encode()).hexdigest(),
        "proofs": [{"layer": "smt", "passed": True, "checksum": "0" * 8,
                    "details": "forged", "timestamp": 0}],
    }
    forged = binary + WasmCustomSection.create_proof_section(payload)
    ok, errors = verify_pcc_wasm(forged, source)
    assert ok is False
    assert any("counterexample" in e for e in errors)


def test_valid_pcc_artifact_verifies(wasmtime_module):
    """Negative control: a real artifact from the generator still verifies."""
    from svl.pcc_wasm import PCCWasmGenerator, verify_pcc_wasm

    src = ("module m { func main() type int { let x: int = 42  let y: int = 58"
           "  assert x + y == 100  return 0 } }")
    artifact = PCCWasmGenerator().generate(src).to_wasm_bytes_with_proofs()
    ok, errors = verify_pcc_wasm(artifact, src)
    assert ok is True, errors
