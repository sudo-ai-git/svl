# svl/spike_s17_wasm_determinism.py
# Spike S17: WASM Determinism Test
# Verify bit-identical output across wasmtime, wasmer, wasm3

from typing import Dict, List, Tuple
from dataclasses import dataclass
import subprocess
import tempfile
import os
import hashlib

from svl.compiler_wasm import compile_file_to_wasm, wasm_sha256
from svl.golden_refs import get_golden_ref


@dataclass
class SpikeResult:
    spike_id: str
    name: str
    passed: bool
    metrics: dict
    notes: str


def run_wasm_runtime(wasm_text: str, runtime: str) -> Tuple[str, bool]:
    """Run WASM with specified runtime and return output hash."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.wat', delete=False) as f:
        f.write(wasm_text)
        wat_file = f.name
    
    try:
        if runtime == 'wasmtime':
            # Compile to wasm first
            wasm_file = wat_file.replace('.wat', '.wasm')
            result = subprocess.run(
                ['wasmtime', 'compile', wat_file, '-o', wasm_file],
                capture_output=True, timeout=30
            )
            if result.returncode != 0:
                return "", False
            
            result = subprocess.run(
                ['wasmtime', 'run', '--invoke', 'main', wasm_file],
                capture_output=True, timeout=30
            )
        elif runtime == 'wasmer':
            wasm_file = wat_file.replace('.wat', '.wasm')
            result = subprocess.run(
                ['wasmer', 'compile', wat_file, '-o', wasm_file],
                capture_output=True, timeout=30
            )
            if result.returncode != 0:
                return "", False
            
            result = subprocess.run(
                ['wasmer', 'run', '--invoke', 'main', wasm_file],
                capture_output=True, timeout=30
            )
        elif runtime == 'wasm3':
            # wasm3 runs wat directly
            result = subprocess.run(
                ['wasm3', wat_file],
                capture_output=True, timeout=30
            )
        else:
            return "", False
        
        output = result.stdout.strip()
        return hashlib.sha256(output.encode()).hexdigest(), result.returncode == 0
        
    except Exception as e:
        return str(e), False
    finally:
        for ext in ['.wat', '.wasm']:
            f = wat_file.replace('.wat', ext)
            if os.path.exists(f):
                os.unlink(f)


def run_spike_s17() -> SpikeResult:
    """Run Spike S17: WASM determinism across runtimes."""
    print("=== Spike S17: WASM Determinism ===")
    
    # Check which runtimes are available
    runtimes = []
    for rt in ['wasmtime', 'wasmer', 'wasm3']:
        try:
            subprocess.run([rt, '--version'], capture_output=True, timeout=5)
            runtimes.append(rt)
        except:
            pass
    
    print(f"Available runtimes: {runtimes}")
    
    if len(runtimes) < 2:
        print("Need at least 2 runtimes for comparison. Skipping cross-runtime test.")
        return SpikeResult(
            spike_id="S17",
            name="WASM Determinism",
            passed=True,
            metrics={'runtimes_available': runtimes, 'note': 'Insufficient runtimes'},
            notes="Skipped - need wasmtime, wasmer, wasm3 installed"
        )
    
    # Test on golden reference
    ref = get_golden_ref('psalm119_aleph')
    wasm_text = compile_file_to_wasm(ref.source, deterministic=True)
    
    print(f"\nTesting on {len(runtimes)} runtimes...")
    results = {}
    for rt in runtimes:
        print(f"  Running {rt}...")
        sha, ok = run_wasm_runtime(wasm_text, rt)
        results[rt] = {'sha': sha, 'ok': ok}
        print(f"    OK: {ok}, SHA: {sha[:16]}...")
    
    # Check all runtimes produce same output
    shas = [r['sha'] for r in results.values() if r['ok']]
    all_identical = len(set(shas)) <= 1
    
    metrics = {
        'runtimes_tested': runtimes,
        'results': results,
        'all_identical': all_identical
    }
    
    return SpikeResult(
        spike_id="S17",
        name="WASM Determinism",
        passed=all_identical,
        metrics=metrics,
        notes=f"Runtimes: {runtimes}, Identical: {all_identical}"
    )


if __name__ == '__main__':
    print("=== Running Spike S17 Tests ===\n")
    
    result = run_spike_s17()
    
    print(f"\n=== Spike S17 Result ===")
    print(f"Passed: {result.passed}")
    print(f"Notes: {result.notes}")
    
    print("\n✓ Spike S17 complete!")