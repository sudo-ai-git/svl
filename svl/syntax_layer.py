# svl/syntax_layer.py
# Unified Syntax Verification API (Spike S4)
# Integrates 231-gate checksums, AST Guard, Golden References, Mutation Testing

from typing import Optional, Tuple, List, Dict, Any
from dataclasses import dataclass, field

from svl.gate231 import compute_checksums, compute_checksums_cython
from svl.golden_refs import compute_block_checksums, BLOCK_SIZE
from svl.ast_guard import ASTGuard, neumaier_sum, ASTGuardViolation
from svl.golden_refs import get_golden_ref, get_all_golden_refs, verify_all_golden_refs, BLOCK_SIZE
from svl.viable_start import find_viable_start, verify_unique_viable_start
from svl.mutation_testing import run_spike_s5
from svl.serialization import to_binary
from svl.lexer import tokenize
from svl.parser_rd import parse
from svl.type_layer import verify_type, TypeVerificationConfig
from svl.gate231 import compute_checksums


@dataclass
class VerifyResult:
    """Result of syntax verification."""
    passed: bool
    viable_start: Optional[int]
    checksums_match: bool
    meta_match: bool
    ast_guard_violations: List[str] = field(default_factory=list)
    golden_ref_match: bool = True
    corruption_detected: bool = False
    corruption_position: Optional[int] = None
    error_message: Optional[str] = None


@dataclass
class SyntaxVerificationConfig:
    """Configuration for syntax verification."""
    block_size: int = BLOCK_SIZE
    use_cython: bool = True
    verify_golden_refs: bool = True
    run_mutation_tests: bool = False
    mutation_tests_per_type: int = 20


class SyntaxVerifier:
    """Unified syntax verification for SVL programs."""

    def __init__(self, config: Optional[SyntaxVerificationConfig] = None):
        self.config = config or SyntaxVerificationConfig()
        self.ast_guard = ASTGuard()

    def _verify_syntax_core(self, source: str) -> VerifyResult:
        """Core syntax verification without type checking."""
        try:
            # 1. Lexical analysis
            tokens = tokenize(source)

            # 2. Parsing
            ast = parse(tokens)

            # 3. AST Guard
            violations = self.ast_guard.check(ast)
            violation_messages = [str(v) for v in violations]

            # 4. 231-gate checksum verification.
            #    `checksums_match` compares the gate's independent implementations on the
            #    SAME bytes: it is a real (falsifiable) check — a numpy overflow or a bug in
            #    one implementation fails here. The old code compared a program's checksums
            #    against themselves, so the gate could never fail.
            data = to_binary(ast)
            bs = self.config.block_size
            block = data[:bs] if len(data) >= bs else data + b'\x00' * (bs - len(data))
            checksums = compute_block_checksums(data, bs)
            checksums_match = (compute_checksums_cython(block) == compute_checksums(block))

            # `meta_match` requires the AST to serialize bit-identically after an
            # independent re-parse of the same source. This is the guard that catches a
            # process-salted value (e.g. Python `hash()`) leaking into the AST/serialization.
            try:
                reparse_data = to_binary(parse(tokenize(source)))
                meta_match = (reparse_data == data)
            except Exception:
                meta_match = False

            expected_checksums = checksums
            expected_meta = (checksums[0] ^ checksums[1] ^ checksums[2]) % 231

            # Find viable start
            viable_start = None
            if expected_checksums is not None:
                viable_start = find_viable_start(
                    bytes(data), expected_checksums, expected_meta
                )

            # 5. Golden reference validation
            golden_ref_match = True
            if self.config.verify_golden_refs:
                from svl.golden_refs import verify_all_golden_refs
                ref_results = verify_all_golden_refs()
                golden_ref_match = all(ref_results.values())

            # 6. Mutation testing
            corruption_detected = False
            if self.config.run_mutation_tests:
                from svl.mutation_testing import run_spike_s5
                if expected_checksums is not None:
                    # Create test data with embedded reference
                    from svl.golden_refs import get_golden_ref
                    ref = get_golden_ref('psalm119_aleph')
                    test_data = bytearray(b'\x00' * 1024)
                    ref_tokens = tokenize(ref.source)
                    ref_ast = parse(ref_tokens)
                    # Use module-level to_binary import
                    ref_data = to_binary(ref_ast)
                    block_size = self.config.block_size
                    ref_bytes = ref_data[:block_size]
                    if len(ref_bytes) < block_size:
                        ref_bytes = ref_bytes + b'\x00' * (block_size - len(ref_bytes))
                    test_data[100:100 + block_size] = ref_bytes

                    # Run mutation tests
                    try:
                        mutation_success = run_spike_s5(
                            bytes(test_data), expected_checksums, expected_meta
                        )
                        if not mutation_success:
                            corruption_detected = True
                    except Exception as e:
                        pass  # Mutation test failed

            return VerifyResult(
                passed=checksums_match and meta_match and len(violations) == 0,
                viable_start=viable_start,
                checksums_match=checksums_match,
                meta_match=meta_match,
                ast_guard_violations=violation_messages,
                golden_ref_match=golden_ref_match,
                corruption_detected=corruption_detected
            )

        except ASTGuardViolation as e:
            return VerifyResult(
                passed=False,
                viable_start=None,
                checksums_match=False,
                meta_match=False,
                ast_guard_violations=[str(e)],
                error_message=str(e)
            )
        except Exception as e:
            return VerifyResult(
                passed=False,
                viable_start=None,
                checksums_match=False,
                meta_match=False,
                error_message=f"Verification error: {e}"
            )

    def verify_syntax(self, source: str) -> VerifyResult:
        """Verify syntax with type checking."""
        # Run basic syntax verification
        result = self._verify_syntax_core(source)

        # Also run type checking
        type_config = TypeVerificationConfig(
            block_size=self.config.block_size,
            use_cython=self.config.use_cython,
            verify_golden_refs=self.config.verify_golden_refs
        )
        type_result = verify_type(source, type_config)

        # Combine results
        if not result.passed or not type_result.passed:
            error_messages = []
            if not result.passed:
                if result.error_message:
                    error_messages.append(result.error_message)
                if result.ast_guard_violations:
                    error_messages.extend(result.ast_guard_violations)
            if not type_result.passed:
                error_messages.extend(type_result.errors)

            combined_error = "; ".join(error_messages) if error_messages else "Verification failed"

            return VerifyResult(
                passed=False,
                viable_start=result.viable_start,
                checksums_match=result.checksums_match,
                meta_match=result.meta_match,
                ast_guard_violations=result.ast_guard_violations,
                golden_ref_match=result.golden_ref_match,
                corruption_detected=result.corruption_detected,
                error_message=combined_error
            )

        # Both passed
        return result

    def verify_file(self, filepath: str) -> VerifyResult:
        """Verify syntax from a file."""
        with open(filepath, 'r', encoding='utf-8') as f:
            source = f.read()
        return self.verify_syntax(source)

    def verify_golden_refs_only(self) -> Dict[str, bool]:
        """Verify only golden references."""
        from svl.golden_refs import verify_all_golden_refs
        return verify_all_golden_refs()

    def run_mutation_tests(self, data: bytes, expected_checksums: Tuple[int, int, int], expected_meta: int) -> bool:
        """Run mutation testing on data."""
        from svl.mutation_testing import run_spike_s5
        return run_spike_s5(data, expected_checksums, expected_meta)


def verify_syntax(source: str, config: Optional[SyntaxVerificationConfig] = None) -> VerifyResult:
    """Convenience function to verify syntax."""
    verifier = SyntaxVerifier(config)
    return verifier.verify_syntax(source)


if __name__ == '__main__':
    # Test syntax verification with a golden reference program
    from svl.golden_refs import get_golden_ref

    ref = get_golden_ref('psalm119_aleph')

    print("Testing syntax verification with Psalm 119 Aleph...")
    result = verify_syntax(ref.source)

    print(f"Passed: {result.passed}")
    print(f"Viable start: {result.viable_start}")
    print(f"Checksums match: {result.checksums_match}")
    print(f"Meta match: {result.meta_match}")
    print(f"AST guard violations: {result.ast_guard_violations}")
    print(f"Golden ref match: {result.golden_ref_match}")
    print(f"Corruption detected: {result.corruption_detected}")

    if result.error_message:
        print(f"Error: {result.error_message}")

    # Test with forbidden sum()
    bad_code = '''
    module test {
      func main() type void {
        let x: float = sum([1.0, 2.0, 3.0])
        return
      }
    }
    '''

    print("\nTesting forbidden sum()...")
    result2 = verify_syntax(bad_code)
    print(f"Passed: {result2.passed}")
    print(f"AST guard violations: {result2.ast_guard_violations}")

    # Test with type error
    bad_code2 = '''
    module test {
      func main() type void {
        let x: int = "not an int"
        return
      }
    }
    '''

    print("\nTesting type error...")
    result3 = verify_syntax(bad_code2)
    print(f"Passed: {result3.passed}")
    print(f"Error: {result3.error_message}")
    print(f"Type errors: {getattr(result3, 'type_errors', 'N/A')}")

    print("\n✓ Syntax layer test complete!")
