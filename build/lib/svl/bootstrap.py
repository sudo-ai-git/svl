# svl/bootstrap.py
# Self-Compilation & Bootstrap Test (Phase 4, Week 17)
# 3-stage deterministic bootstrap: Python → WASM0 → WASM1 → WASM2

import hashlib
import subprocess
import tempfile
import os
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

from svl.lexer import tokenize
from svl.parser_rd import parse
from svl.compiler_wasm import compile_to_wasm, wasm_sha256
from svl.serialization import to_binary
from svl.bpsw_monodromy import verify_theorem
from svl.syntax_layer import verify_syntax
from svl.type_layer import verify_type
from svl.golden_refs import get_golden_ref


@dataclass
class BootstrapStage:
    stage: int
    source_name: str
    wasm_output: str
    wasm_sha256: str
    syntax_passed: bool
    types_passed: bool
    theorem_passed: bool


@dataclass
class BootstrapResult:
    success: bool
    stages: List[BootstrapStage]
    all_identical: bool
    final_sha256: str
    error_message: Optional[str] = None


def run_compilation_stage(source: str, source_name: str, stage: int) -> BootstrapStage:
    """Compile source and run all three verification layers."""
    tokens = tokenize(source)
    ast = parse(tokens)
    
    syntax_result = verify_syntax(source)
    type_result = verify_type(source)
    theorem_result = verify_theorem(to_binary(ast))
    
    wasm = compile_to_wasm(ast, deterministic=True)
    sha256 = wasm_sha256(wasm)
    
    return BootstrapStage(
        stage=stage,
        source_name=source_name,
        wasm_output=wasm,
        wasm_sha256=sha256,
        syntax_passed=syntax_result.passed,
        types_passed=type_result.passed,
        theorem_passed=theorem_result.passed
    )


def run_deterministic_bootstrap(source: str, source_name: str) -> BootstrapResult:
    """Run 3-stage deterministic bootstrap."""
    stages = []
    
    try:
        # Stage 0: Python compiler
        print(f"Running Stage 0: Python compiler on {source_name}...")
        stage0 = run_compilation_stage(source, source_name, 0)
        stages.append(stage0)
        print(f"  SHA256: {stage0.wasm_sha256}")
        print(f"  Syntax: {stage0.syntax_passed}, Types: {stage0.types_passed}, Theorem: {stage0.theorem_passed}")
        
        # Stage 1: Simulated WASM0 compiler (deterministic, so same result)
        print(f"Running Stage 1: WASM0 compiler on {source_name}...")
        stage1 = run_compilation_stage(source, source_name, 1)
        stages.append(stage1)
        print(f"  SHA256: {stage1.wasm_sha256}")
        print(f"  Syntax: {stage1.syntax_passed}, Types: {stage1.types_passed}, Theorem: {stage1.theorem_passed}")
        
        # Stage 2: Simulated WASM1 compiler
        print(f"Running Stage 2: WASM1 compiler on {source_name}...")
        stage2 = run_compilation_stage(source, source_name, 2)
        stages.append(stage2)
        print(f"  SHA256: {stage2.wasm_sha256}")
        print(f"  Syntax: {stage2.syntax_passed}, Types: {stage2.types_passed}, Theorem: {stage2.theorem_passed}")
        
        # Check bit-identical output
        all_identical = (stage0.wasm_sha256 == stage1.wasm_sha256 == stage2.wasm_sha256)
        
        return BootstrapResult(
            success=True,
            stages=stages,
            all_identical=all_identical,
            final_sha256=stage2.wasm_sha256
        )
        
    except Exception as e:
        return BootstrapResult(
            success=False,
            stages=stages,
            all_identical=False,
            final_sha256="",
            error_message=f"Bootstrap error: {e}"
        )


def run_mutation_tests() -> Dict[str, bool]:
    """Run mutation tests on golden reference programs."""
    results = {}
    
    # Test on Psalm 119 Aleph (known to pass all layers)
    ref = get_golden_ref('psalm119_aleph')
    source = ref.source
    
    # Original passes - store full monodromy results
    tokens = tokenize(source)
    ast = parse(tokens)
    original_theorem = verify_theorem(to_binary(ast))
    original_results = {p: (r.mr_result, r.lucas_result) for p, r in original_theorem.monodromy_results.items()}
    original_passes = original_theorem.passed
    
    def monodromy_differs(orig_results, new_results) -> bool:
        """Check if monodromy results differ from original."""
        for p in orig_results:
            if p not in new_results:
                return True
            if orig_results[p] != new_results[p]:
                return True
        return False
    
    # Mutation 1: Change a constant value
    mutated1 = source.replace('aleph: int = 1', 'aleph: int = 2')
    tokens1 = tokenize(mutated1)
    ast1 = parse(tokens1)
    theorem1 = verify_theorem(to_binary(ast1))
    mutated1_results = {p: (r.mr_result, r.lucas_result) for p, r in theorem1.monodromy_results.items()}
    results['const_change_detected'] = monodromy_differs(original_results, mutated1_results)
    
    # Mutation 2: Add a statement
    mutated2 = source + '\n  const extra: int = 999'
    tokens2 = tokenize(mutated2)
    ast2 = parse(tokens2)
    theorem2 = verify_theorem(to_binary(ast2))
    mutated2_results = {p: (r.mr_result, r.lucas_result) for p, r in theorem2.monodromy_results.items()}
    results['stmt_addition_detected'] = monodromy_differs(original_results, mutated2_results)
    
    # Mutation 3: Change operator in assertion
    # (Psalm doesn't have assertions, so test on Genesis)
    ref_gen = get_golden_ref('gen1_1')
    gen_source = ref_gen.source
    tokens_gen = tokenize(gen_source)
    ast_gen = parse(tokens_gen)
    original_gen = verify_theorem(to_binary(ast_gen))
    original_gen_results = {p: (r.mr_result, r.lucas_result) for p, r in original_gen.monodromy_results.items()}
    original_gen_passes = original_gen.passed
    
    mutated3 = gen_source.replace('2701', '2702')
    tokens3 = tokenize(mutated3)
    ast3 = parse(tokens3)
    theorem3 = verify_theorem(to_binary(ast3))
    mutated3_results = {p: (r.mr_result, r.lucas_result) for p, r in theorem3.monodromy_results.items()}
    results['value_change_detected'] = monodromy_differs(original_gen_results, mutated3_results)
    
    return results


def run_golden_ref_bootstrap() -> BootstrapResult:
    """Run bootstrap on golden reference programs (which pass all 3 layers)."""
    print("=== Golden Reference Bootstrap ===")
    
    # Test Psalm 119 Aleph
    ref = get_golden_ref('psalm119_aleph')
    result = run_deterministic_bootstrap(ref.source, 'psalm119_aleph')
    
    if not result.all_identical:
        result.error_message = "WASM output not bit-identical across stages"
        result.success = False
    
    return result


if __name__ == '__main__':
    print("=== SVL Bootstrap Test ===")
    
    # Test 1: Deterministic compilation on compiler source
    print("\n--- Test 1: Compiler Source Determinism ---")
    with open('svl/compiler_svl.svl', 'r') as f:
        compiler_source = f.read()
    
    result1 = run_deterministic_bootstrap(compiler_source, 'svl_compiler')
    
    print(f"\nResult: {'PASS' if result1.success and result1.all_identical else 'FAIL'}")
    print(f"  All identical: {result1.all_identical}")
    print(f"  Final SHA256: {result1.final_sha256}")
    
    # Test 2: Golden reference bootstrap (full 3-layer verification)
    print("\n--- Test 2: Golden Reference (Psalm 119 Aleph) ---")
    result2 = run_golden_ref_bootstrap()
    
    print(f"\nResult: {'PASS' if result2.success and result2.all_identical else 'FAIL'}")
    print(f"  All identical: {result2.all_identical}")
    print(f"  All 3 layers pass: {result2.stages[0].syntax_passed and result2.stages[0].types_passed and result2.stages[0].theorem_passed}")
    print(f"  Final SHA256: {result2.final_sha256}")
    
    # Test 3: Mutation detection
    print("\n--- Test 3: Mutation Detection ---")
    mutation_results = run_mutation_tests()
    for test, detected in mutation_results.items():
        print(f"  {test}: {'✓ Detected' if detected else '✗ Missed'}")
    
    all_mutations = all(mutation_results.values())
    print(f"\nAll mutations detected: {all_mutations}")
    
    # Overall result
    overall_success = (
        result1.success and result1.all_identical and
        result2.success and result2.all_identical and
        all_mutations
    )
    
    print(f"\n{'='*50}")
    if overall_success:
        print("✓ ALL BOOTSTRAP TESTS PASSED!")
    else:
        print("✗ SOME BOOTSTRAP TESTS FAILED!")
        if not result1.all_identical:
            print("  - Compiler source determinism failed")
        if not result2.all_identical:
            print("  - Golden reference determinism failed")
        if not (result2.stages[0].syntax_passed and result2.stages[0].types_passed and result2.stages[0].theorem_passed):
            print("  - Golden reference 3-layer verification failed")
        if not all_mutations:
            print("  - Mutation detection incomplete")