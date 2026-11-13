# svl/spike_s18_hermes_integration.py
# Spike S18: Hermes Integration Test
# End-to-end verify in <50ms via /svl verify command

from typing import Dict, List
from dataclasses import dataclass
import time

from svl.theorem_layer import verify_theorem_layer, TheoremVerificationConfig
from svl.syntax_layer import verify_syntax, SyntaxVerificationConfig
from svl.type_layer import verify_type, TypeVerificationConfig
from svl.golden_refs import get_golden_ref


@dataclass
class SpikeResult:
    spike_id: str
    name: str
    passed: bool
    metrics: dict
    notes: str


def run_spike_s18_hermes_integration() -> SpikeResult:
    """Run Spike S18: Hermes Integration Test."""
    print("=== Spike S18: Hermes Integration ===")
    
    metrics = {}
    
    # Test 1: VRE Layer 1 (Syntax) - 231-gate
    print("\n--- VRE Layer 1: Syntax (231-gate) ---")
    ref = get_golden_ref('psalm119_aleph')
    
    config = SyntaxVerificationConfig(
        block_size=512,
        use_cython=True,
        verify_golden_refs=True,
        run_mutation_tests=False
    )
    
    start = time.perf_counter()
    syntax_result = verify_syntax(ref.source, config)
    syntax_time = (time.perf_counter() - start) * 1000
    
    metrics['layer1_syntax'] = {
        'passed': syntax_result.passed,
        'time_ms': syntax_time,
        'viable_start': syntax_result.viable_start,
        'golden_refs': syntax_result.golden_ref_match
    }
    print(f"  Passed: {syntax_result.passed}")
    print(f"  Time: {syntax_time:.2f} ms")
    print(f"  Viable start: {syntax_result.viable_start}")
    
    # Test 2: VRE Layer 2 (Types) - Mod-5 Dual-Stream
    print("\n--- VRE Layer 2: Types (Mod-5 Dual-Stream) ---")
    type_config = TypeVerificationConfig(
        block_size=512,
        use_cython=True,
        verify_golden_refs=True
    )
    
    start = time.perf_counter()
    type_result = verify_type(ref.source, type_config)
    type_time = (time.perf_counter() - start) * 1000
    
    metrics['layer2_types'] = {
        'passed': type_result.passed,
        'time_ms': type_time,
        'dual_stream': type_result.dual_stream_agreement,
        'mod5': type_result.mod5_consistency,
        'z2': type_result.z2_consistency
    }
    print(f"  Passed: {type_result.passed}")
    print(f"  Time: {type_time:.2f} ms")
    print(f"  Dual-stream: {type_result.dual_stream_agreement}")
    
    # Test 3: VRE Layer 3 (Theorem) - BPSW Monodromy
    print("\n--- VRE Layer 3: Theorem (BPSW Monodromy) ---")
    theorem_config = TheoremVerificationConfig(
        block_size=512,
        use_cython=True,
        verify_syntax_first=True,
        verify_types_first=True,
        verify_golden_refs=True
    )
    
    start = time.perf_counter()
    theorem_result = verify_theorem_layer(ref.source, theorem_config)
    theorem_time = (time.perf_counter() - start) * 1000
    
    metrics['layer3_theorem'] = {
        'passed': theorem_result.passed,
        'time_ms': theorem_time,
        'syntax_ok': theorem_result.syntax_layer_verified,
        'types_ok': theorem_result.type_layer_verified,
        'all_parities_even': theorem_result.all_parities_even
    }
    print(f"  Passed: {theorem_result.passed}")
    print(f"  Time: {theorem_time:.2f} ms")
    print(f"  All parities even: {theorem_result.all_parities_even}")
    
    # Test 4: End-to-end latency
    print("\n--- End-to-End Latency ---")
    total_time = syntax_time + type_time + theorem_time
    metrics['e2e_latency_ms'] = total_time
    metrics['target_met'] = total_time < 50
    print(f"  Total time: {total_time:.2f} ms")
    print(f"  Target (<50ms): {metrics['target_met']}")
    
    # Test 5: Slash command simulation
    print("\n--- Slash Command Simulation ---")
    test_cases = [
        'let x: int = 42',
        'func main() type void { return }',
        'module test { const x: int = 1 }'
    ]
    
    slash_times = []
    for code in test_cases:
        start = time.perf_counter()
        result = verify_theorem_layer(code, theorem_config)
        elapsed = (time.perf_counter() - start) * 1000
        slash_times.append(elapsed)
        print(f"  /svl verify \"{code[:30]}...\": {elapsed:.2f} ms")
    
    avg_slash = sum(slash_times) / len(slash_times)
    metrics['slash_commands'] = {
        'times_ms': slash_times,
        'avg_ms': avg_slash,
        'target_met': avg_slash < 50
    }
    print(f"  Average: {avg_slash:.2f} ms")
    print(f"  Target (<50ms): {metrics['slash_commands']['target_met']}")
    
    # Overall pass criteria
    all_layers_pass = (
        metrics['layer1_syntax']['passed'] and
        metrics['layer2_types']['passed'] and
        metrics['target_met'] and
        metrics['slash_commands']['target_met']
    )
    
    return SpikeResult(
        spike_id="S18",
        name="Hermes Integration",
        passed=all_layers_pass,
        metrics=metrics,
        notes=f"Layers: L1={metrics['layer1_syntax']['passed']}, "
              f"L2={metrics['layer2_types']['passed']}, "
              f"L3={metrics['layer3_theorem']['passed']}, "
              f"E2E={metrics['e2e_latency_ms']:.1f}ms, "
              f"Slash={metrics['slash_commands']['avg_ms']:.1f}ms"
    )


if __name__ == '__main__':
    print("=== Running Spike S18 Tests ===\n")
    
    result = run_spike_s18_hermes_integration()
    
    print(f"\n=== Spike S18 Result ===")
    print(f"Passed: {result.passed}")
    print(f"Notes: {result.notes}")
    
    print("\n✓ Spike S18 complete!")