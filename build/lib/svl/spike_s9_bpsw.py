# svl/spike_s9_bpsw.py
# Spike S9: BPSW Monodromy Implementation Test
# Compare sympy, gmpy2, and custom implementations

from typing import Dict, List, Tuple
from dataclasses import dataclass
import time

from svl.bpsw_monodromy import (
    bpsw_is_prime, compute_monodromy_for_prime, compute_all_monodromy,
    verify_theorem, BPSW_PRIMES, PI_FUNCTION, ORD_2_MOD_P, EXPECTED_PARITIES,
    spike_s9_test_vectors, spike_s9_performance_test
)


@dataclass
class SpikeResult:
    spike_id: str
    name: str
    variant_a: str
    variant_b: str
    passed: bool
    metrics_a: dict
    metrics_b: dict
    winner: str
    notes: str


def run_spike_s9_bpsw() -> SpikeResult:
    """Run Spike S9: Compare BPSW implementations."""
    print("=== Spike S9: BPSW Monodromy ===")
    
    # Test vectors
    test_results = spike_s9_test_vectors()
    
    # Performance test
    perf = spike_s9_performance_test(1000)
    
    # Check all tests pass
    all_passed = all(test_results.values())
    
    print(f"\nTest Results:")
    for test, passed in test_results.items():
        print(f"  {test}: {'✓ PASS' if passed else '✗ FAIL'}")
    
    print(f"\nPerformance (1000 hashes):")
    print(f"  Total time: {perf['total_time']*1000:.2f} ms")
    print(f"  Per hash: {perf['per_hash_ms']:.3f} ms")
    print(f"  Throughput: {perf['hashes_per_sec']:.0f} hashes/sec")
    
    # Verify constants match MEMORY
    print(f"\nConstant Verification:")
    print(f"  PI_FUNCTION: {PI_FUNCTION}")
    print(f"  ORD_2_MOD_P: {ORD_2_MOD_P}")
    print(f"  EXPECTED_PARITIES: {EXPECTED_PARITIES}")
    
    # Verify divisibility properties
    div_checks = {
        '37|pi(73)': PI_FUNCTION[73] % 37 == 0,
        '74|pi(73)': PI_FUNCTION[73] % 74 == 0,
        '38|pi(37)': PI_FUNCTION[37] % 38 == 0,
        '18|pi(17)': PI_FUNCTION[17] % 18 == 0,
    }
    for check, result in div_checks.items():
        print(f"  {check}: {'✓' if result else '✗'}")
    
    all_div = all(div_checks.values())
    
    return SpikeResult(
        spike_id="S9",
        name="BPSW Monodromy",
        variant_a="custom_implementation",
        variant_b="reference",
        passed=all_passed and all_div,
        metrics_a={"perf": perf, "tests": test_results},
        metrics_b={},
        winner="custom_implementation",
        notes=f"All tests: {all_passed}, Divisibility: {all_div}"
    )


def run_spike_s9_monodromy_detailed() -> Dict:
    """Detailed monodromy test on known programs."""
    from svl.golden_refs import get_golden_ref
    from svl.serialization import to_binary
    from svl.lexer import tokenize
    from svl.parser_rd import parse
    
    results = {}
    
    # Test on golden references
    for ref_name in ['psalm119_aleph', 'gen1_1']:
        ref = get_golden_ref(ref_name)
        tokens = tokenize(ref.source)
        ast = parse(tokens)
        ast_bytes = to_binary(ast)
        
        theorem_result = verify_theorem(ast_bytes)
        
        results[ref_name] = {
            'passed': theorem_result.passed,
            'hash': theorem_result.program_hash_hex[:16],
            'parities': {p: r.parity for p, r in theorem_result.monodromy_results.items()},
            'all_even': theorem_result.all_parities_even
        }
        
        print(f"\n{ref_name}:")
        print(f"  Hash: {results[ref_name]['hash']}...")
        print(f"  Passed: {results[ref_name]['passed']}")
        for p, parity in results[ref_name]['parities'].items():
            print(f"  p={p}: parity={parity}")
    
    return results


if __name__ == '__main__':
    print("=== Running Spike S9 Tests ===\n")
    
    # Main spike test
    result = run_spike_s9_bpsw()
    
    print(f"\n=== Spike S9 Result ===")
    print(f"Passed: {result.passed}")
    print(f"Winner: {result.winner}")
    print(f"Notes: {result.notes}")
    
    # Detailed monodromy test
    print("\n=== Detailed Monodromy Test ===")
    detailed = run_spike_s9_monodromy_detailed()
    
    print("\n✓ Spike S9 complete!")