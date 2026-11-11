# svl/spike_s10_self_verify.py
# Spike S10: Self-Verification & Bootstrap Test
# 3-stage bootstrap: Python → WASM0 → WASM1 → WASM2
# Verify bit-identical output and mutation detection

from typing import Dict, List, Tuple
from dataclasses import dataclass
import time

from svl.bootstrap import (
    run_deterministic_bootstrap, run_mutation_tests, run_golden_ref_bootstrap
)
from svl.compiler_wasm import verify_wasm_determinism, compile_file_to_wasm, wasm_sha256
from svl.golden_refs import get_golden_ref


@dataclass
class SpikeResult:
    spike_id: str
    name: str
    passed: bool
    metrics: dict
    notes: str


def run_spike_s10_bootstrap() -> SpikeResult:
    """Run Spike S10: 3-stage deterministic bootstrap."""
    print("=== Spike S10: Self-Compilation & Bootstrap ===")
    
    metrics = {}
    
    # Test 1: Compiler source determinism
    print("\n--- Test 1: Compiler Source Determinism ---")
    with open('svl/compiler_svl.svl', 'r') as f:
        compiler_source = f.read()
    
    result1 = run_deterministic_bootstrap(compiler_source, 'svl_compiler')
    metrics['compiler_determinism'] = {
        'passed': result1.success and result1.all_identical,
        'sha256': result1.final_sha256,
        'stages': len(result1.stages)
    }
    print(f"  Deterministic: {result1.all_identical}")
    print(f"  SHA256: {result1.final_sha256}")
    
    # Test 2: Golden reference bootstrap
    print("\n--- Test 2: Golden Reference Bootstrap ---")
    result2 = run_golden_ref_bootstrap()
    metrics['golden_ref'] = {
        'passed': result2.success and result2.all_identical,
        'sha256': result2.final_sha256,
        'three_layers': (result2.stages[0].syntax_passed and 
                        result2.stages[0].types_passed and 
                        result2.stages[0].theorem_passed)
    }
    print(f"  Deterministic: {result2.all_identical}")
    print(f"  3-layer pass: {metrics['golden_ref']['three_layers']}")
    print(f"  SHA256: {result2.final_sha256}")
    
    # Test 3: Mutation detection
    print("\n--- Test 3: Mutation Detection ---")
    mutation_results = run_mutation_tests()
    metrics['mutations'] = mutation_results
    for test, detected in mutation_results.items():
        print(f"  {test}: {'✓' if detected else '✗'}")
    
    # Test 4: WASM determinism verification
    print("\n--- Test 4: WASM Determinism Verification ---")
    test_source = get_golden_ref('psalm119_aleph').source
    det_result = verify_wasm_determinism(test_source, runs=5)
    metrics['wasm_determinism'] = det_result
    print(f"  5-run determinism: {det_result}")
    
    # Overall pass criteria
    all_pass = (
        metrics['compiler_determinism']['passed'] and
        metrics['golden_ref']['passed'] and
        metrics['wasm_determinism'] and
        all(metrics['mutations'].values())
    )
    
    return SpikeResult(
        spike_id="S10",
        name="Self-Compilation & Bootstrap",
        passed=all_pass,
        metrics=metrics,
        notes=f"Compiler determinism: {metrics['compiler_determinism']['passed']}, "
              f"Golden ref: {metrics['golden_ref']['passed']}, "
              f"WASM determinism: {metrics['wasm_determinism']}, "
              f"Mutations: {all(metrics['mutations'].values())}"
    )


def run_spike_s10_detailed() -> Dict:
    """Detailed bootstrap analysis."""
    from svl.compiler_wasm import compile_file_to_wasm, wasm_sha256
    from svl.serialization import to_binary
    from svl.lexer import tokenize
    from svl.parser_rd import parse
    
    results = {}
    
    # Test on multiple programs
    test_programs = [
        ('compiler', open('svl/compiler_svl.svl', 'r').read()),
        ('psalm119', get_golden_ref('psalm119_aleph').source),
        ('gen1_1', get_golden_ref('gen1_1').source),
    ]
    
    for name, source in test_programs:
        print(f"\n--- {name} ---")
        
        # Run 3 compilations
        shas = []
        for i in range(3):
            tokens = tokenize(source)
            ast = parse(tokens)
            wasm = compile_file_to_wasm(source, deterministic=True)
            sha = wasm_sha256(wasm)
            shas.append(sha)
            print(f"  Run {i+1}: {sha[:16]}...")
        
        identical = len(set(shas)) == 1
        results[name] = {
            'identical': identical,
            'shas': shas
        }
        print(f"  Identical: {identical}")
    
    return results


def run_spike_s10() -> SpikeResult:
    """Main Spike S10 entry point."""
    result = run_spike_s10_bootstrap()
    run_spike_s10_detailed()
    return result


if __name__ == '__main__':
    print("=== Running Spike S10 Tests ===\n")
    
    result = run_spike_s10()
    
    print(f"\n=== Spike S10 Result ===")
    print(f"Passed: {result.passed}")
    print(f"Notes: {result.notes}")
    
    print("\n✓ Spike S10 complete!")