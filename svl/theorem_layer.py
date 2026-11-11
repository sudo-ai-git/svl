# svl/theorem_layer.py
# Unified Theorem Verification API (Theorem Layer)
# Integrates BPSW Monodromy with Syntax and Type layers
# Extended with SMT-based verification (Z3)

from typing import Optional, Dict, Any
from dataclasses import dataclass, field

from svl.bpsw_monodromy import (
    verify_theorem, TheoremVerifyResult, compute_program_hash,
    compute_program_hash_hex, BPSW_PRIMES, PI_FUNCTION, ORD_2_MOD_P, EXPECTED_PARITIES
)
from svl.serialization import to_binary
from svl.golden_refs import get_all_golden_refs, verify_all_golden_refs, BLOCK_SIZE
from svl.gate231 import compute_checksums_cython

# SMT Integration (H17, H19)
SMT_INTEGRATION = False
Z3_AVAILABLE = False
SMTConfig = None
SMTLogic = None
verify_with_smt = None
try:
    from svl.smt_theorem import (
        verify_with_smt as _verify_with_smt,
        SMTVerifyResult,
        SMTConfig as _SMTConfig,
        SMTLogic as _SMTLogic,
        SMTTheoremLayer,
        Z3_AVAILABLE as _Z3_AVAILABLE
    )
    verify_with_smt = _verify_with_smt
    SMTConfig = _SMTConfig
    SMTLogic = _SMTLogic
    Z3_AVAILABLE = _Z3_AVAILABLE
    SMT_INTEGRATION = True
except ImportError:
    pass


@dataclass
class TheoremVerifyResultWrapper:
    """Wrapper for theorem verification result with additional context."""
    passed: bool
    program_hash: int
    program_hash_hex: str
    monodromy_results: Dict[int, Any]
    all_parities_even: bool
    syntax_layer_verified: bool = False
    type_layer_verified: bool = False
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    # SMT Integration (H17, H19)
    smt_verified: bool = False
    smt_result: Optional[Any] = None
    smt_logic: Optional[str] = None
    smt_solver_time_ms: float = 0.0


@dataclass
class TheoremVerificationConfig:
    """Configuration for theorem verification."""
    block_size: int = BLOCK_SIZE
    use_cython: bool = True
    verify_syntax_first: bool = True
    verify_types_first: bool = True
    verify_golden_refs: bool = True
    # SMT Integration (H17, H19)
    use_smt: bool = True
    smt_logic: Optional[str] = None
    smt_timeout_ms: int = 30000


class TheoremLayer:
    """Unified theorem verification layer."""

    def __init__(self, config: Optional[TheoremVerificationConfig] = None):
        self.config = config or TheoremVerificationConfig()

    def verify_theorem(self, source: str, ast_bytes: Optional[bytes] = None) -> TheoremVerifyResultWrapper:
        """
        Full theorem layer verification:
        1. Optionally verify syntax layer first
        2. Optionally verify type layer first
        3. Compute program hash from AST bytes
        4. Run BPSW Monodromy checks for primes {37, 73, 17}
        5. Verify all parities are even (0)
        """
        errors = []
        warnings = []
        syntax_ok = True
        type_ok = True

        try:
            # 1. Syntax layer verification (optional)
            if self.config.verify_syntax_first:
                from svl.syntax_layer import verify_syntax, SyntaxVerificationConfig
                syntax_config = SyntaxVerificationConfig(
                    block_size=self.config.block_size,
                    use_cython=self.config.use_cython,
                    verify_golden_refs=self.config.verify_golden_refs,
                    run_mutation_tests=False
                )
                syntax_result = verify_syntax(source, syntax_config)
                syntax_ok = syntax_result.passed
                if not syntax_ok:
                    errors.append(f"Syntax verification failed: {syntax_result.error_message}")
                    if syntax_result.ast_guard_violations:
                        errors.extend(syntax_result.ast_guard_violations)

            # 2. Type layer verification (optional)
            if self.config.verify_types_first and syntax_ok:
                from svl.type_layer import verify_type, TypeVerificationConfig
                type_config = TypeVerificationConfig(
                    block_size=self.config.block_size,
                    use_cython=self.config.use_cython,
                    verify_golden_refs=self.config.verify_golden_refs
                )
                type_result = verify_type(source, type_config)
                type_ok = type_result.passed
                if not type_ok:
                    errors.extend(type_result.errors)

            # 3. Theorem verification (BPSW Monodromy + SMT)
            # Get or compute AST bytes
            if ast_bytes is None:
                from svl.lexer import tokenize
                from svl.parser_rd import parse
                tokens = tokenize(source)
                ast = parse(tokens)
                ast_bytes = to_binary(ast)

            theorem_result = verify_theorem(ast_bytes)

            if theorem_result.error_message:
                errors.append(theorem_result.error_message)

            # 3b. SMT-based verification (H17, H19) - if Z3 available and enabled
            smt_verified = False
            smt_result = None
            smt_logic = None
            smt_solver_time_ms = 0.0
            
            if SMT_INTEGRATION and self.config.use_smt and Z3_AVAILABLE and theorem_result.passed:
                try:
                    # These are guaranteed non-None inside this block
                    SMTConfigLocal = SMTConfig
                    SMTLogicLocal = SMTLogic
                    verify_smt_local = verify_with_smt
                    
                    smt_config = SMTConfigLocal(
                        logic=SMTLogicLocal(self.config.smt_logic) if self.config.smt_logic else SMTLogicLocal.QF_LIA,
                        timeout_ms=self.config.smt_timeout_ms,
                        use_bpsw_fallback=True
                    )
                    smt_result = verify_smt_local(source, smt_config)
                    smt_verified = smt_result.passed
                    smt_logic = smt_result.logic.value
                    smt_solver_time_ms = smt_result.solver_time_ms
                    
                    if not smt_verified and smt_result.error_message:
                        warnings.append(f"SMT verification: {smt_result.error_message}")
                        
                except Exception as e:
                    warnings.append(f"SMT verification error: {e}")

            # 4. Golden reference verification
            golden_ref_match = True
            if self.config.verify_golden_refs:
                ref_results = verify_all_golden_refs()
                golden_ref_match = all(ref_results.values())
                if not golden_ref_match:
                    warnings.append("Golden reference verification failed")

            all_passed = syntax_ok and type_ok and theorem_result.passed and golden_ref_match and smt_verified

            return TheoremVerifyResultWrapper(
                passed=all_passed,
                program_hash=theorem_result.program_hash,
                program_hash_hex=theorem_result.program_hash_hex,
                monodromy_results=theorem_result.monodromy_results,
                all_parities_even=theorem_result.all_parities_even,
                syntax_layer_verified=syntax_ok,
                type_layer_verified=type_ok,
                errors=errors,
                warnings=warnings,
                smt_verified=smt_verified,
                smt_result=smt_result,
                smt_logic=smt_logic,
                smt_solver_time_ms=smt_solver_time_ms
            )

        except Exception as e:
            return TheoremVerifyResultWrapper(
                passed=False,
                program_hash=0,
                program_hash_hex="",
                monodromy_results={},
                all_parities_even=False,
                errors=[f"Theorem verification error: {e}"]
            )

    def verify_file(self, filepath: str) -> TheoremVerifyResultWrapper:
        """Verify theorem from file."""
        with open(filepath, 'r', encoding='utf-8') as f:
            source = f.read()
        return self.verify_theorem(source)

    def verify_ast_bytes(self, ast_bytes: bytes) -> TheoremVerifyResultWrapper:
        """Verify theorem directly from AST bytes (bypasses syntax/type layers)."""
        try:
            theorem_result = verify_theorem(ast_bytes)
            return TheoremVerifyResultWrapper(
                passed=theorem_result.passed,
                program_hash=theorem_result.program_hash,
                program_hash_hex=theorem_result.program_hash_hex,
                monodromy_results=theorem_result.monodromy_results,
                all_parities_even=theorem_result.all_parities_even,
                syntax_layer_verified=True,
                type_layer_verified=True,
                errors=[theorem_result.error_message] if theorem_result.error_message else []
            )
        except Exception as e:
            return TheoremVerifyResultWrapper(
                passed=False,
                program_hash=0,
                program_hash_hex="",
                monodromy_results={},
                all_parities_even=False,
                errors=[f"Theorem verification error: {e}"]
            )


# Convenience function
def verify_theorem_layer(source: str, config: Optional[TheoremVerificationConfig] = None) -> TheoremVerifyResultWrapper:
    """Verify theorem layer for SVL source code."""
    layer = TheoremLayer(config)
    return layer.verify_theorem(source)


# VRE Stack Integration
def vre_layer_3_theorem(ast_bytes: bytes) -> TheoremVerifyResultWrapper:
    """
    VRE Layer 3 (Theorem) - Direct integration point for VRE stack.
    Input: AST bytes (canonical serialization)
    Output: TheoremVerifyResultWrapper
    """
    return TheoremLayer().verify_ast_bytes(ast_bytes)


if __name__ == '__main__':
    # Test theorem layer
    print("=== Theorem Layer Test ===")

    from svl.golden_refs import get_golden_ref

    # Test with golden reference
    ref = get_golden_ref('psalm119_aleph')
    result = verify_theorem_layer(ref.source)

    print(f"Psalm 119 Aleph:")
    print(f"  Passed: {result.passed}")
    print(f"  Syntax OK: {result.syntax_layer_verified}")
    print(f"  Type OK: {result.type_layer_verified}")
    print(f"  Hash: {result.program_hash_hex[:16]}...")
    print(f"  All Parities Even: {result.all_parities_even}")

    for p, r in result.monodromy_results.items():
        print(f"  p={p}: hash_mod={r.program_hash_mod_p}, MR={r.mr_result}, Lucas={r.lucas_result}, parity={r.parity}, passed={r.passed}")

    if result.errors:
        print(f"  Errors: {result.errors}")
    if result.warnings:
        print(f"  Warnings: {result.warnings}")

    # Test forbidden sum()
    bad_code = '''
    module test {
      func main() type void {
        let x: float = sum([1.0, 2.0, 3.0])
        return
      }
    }
    '''

    result2 = verify_theorem_layer(bad_code)
    print(f"\nForbidden sum test:")
    print(f"  Passed: {result2.passed}")
    print(f"  Errors: {result2.errors}")

    # Test VRE integration
    print("\n--- VRE Layer 3 Integration Test ---")
    from svl.lexer import tokenize
    from svl.parser_rd import parse
    from svl.serialization import to_binary

    test_source = "module test { func main() type void { return } }"
    tokens = tokenize(test_source)
    ast = parse(tokens)
    ast_bytes = to_binary(ast)

    vre_result = vre_layer_3_theorem(ast_bytes)
    print(f"  VRE Layer 3 Passed: {vre_result.passed}")
    print(f"  Hash: {vre_result.program_hash_hex[:16]}...")
    print(f"  All Parities Even: {vre_result.all_parities_even}")

    print("\n✓ Theorem Layer test complete!")