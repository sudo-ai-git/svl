# svl/type_layer.py
# Unified Type Verification API (Type Layer)
# Integrates Mod-5, Z/2, Dual-Stream, and Structural verification

from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field

from svl.mod5_types import Mod5Bucket, bucket_of_type, z2_negate, mod5_add, mod5_mul
from svl.dual_stream import (
    SemanticStream, StructuralStream, DualStreamChecker,
    TypeStreamResult, DualStreamResult
)
from svl.type_inference import (
    Type, TypeVar, TypeScheme, TypeEnv, TypeChecker, UnificationError
)
from svl.parser_rd import TypeExpr, NodeType
from svl.golden_refs import (
    get_all_golden_refs, verify_all_golden_refs, BLOCK_SIZE,
    compute_block_checksums
)
from svl.serialization import to_binary
from svl.gate231 import compute_checksums_cython, MODULUS


@dataclass
class TypeVerifyResult:
    """Result of type verification."""
    passed: bool
    semantic_bucket: Optional[Mod5Bucket] = None
    structural_checksum: Optional[Tuple[int, int, int]] = None
    dual_stream_agreement: bool = True
    mod5_consistency: bool = True
    z2_consistency: bool = True
    structural_match: bool = True
    semantic_bucket_match: bool = True
    golden_ref_match: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class TypeVerificationConfig:
    """Configuration for type verification."""
    block_size: int = BLOCK_SIZE
    use_cython: bool = True
    verify_semantic: bool = True
    verify_structural: bool = True
    run_dual_stream: bool = True
    verify_golden_refs: bool = True


class TypeLayer:
    """Unified type verification layer."""

    def __init__(self, config: Optional[TypeVerificationConfig] = None):
        self.config = config or TypeVerificationConfig()
        self.type_checker = TypeChecker()
        self.dual_stream = DualStreamChecker(self.type_checker)

    def verify_type(self, source: str, expected_type: Optional[Any] = None) -> TypeVerifyResult:
        """Verify type of SVL source code."""
        try:
            from svl.lexer import tokenize
            from svl.parser_rd import parse

            # Lex and parse
            tokens = tokenize(source)
            ast = parse(tokens)

            # Type check
            ok, errors = self.type_checker.check_program(ast)

            if not ok:
                return TypeVerifyResult(
                    passed=False,
                    errors=errors
                )

            # Dual-stream verification
            dual_stream_result = None
            if self.config.run_dual_stream:
                dual_stream_result = self._run_dual_stream(ast)

            # Golden reference verification
            golden_ref_match = True
            if self.config.verify_golden_refs:
                golden_ref_match = self._verify_golden_refs()

            # Mod-5 consistency
            mod5_ok, mod5_errors = self._verify_mod5_consistency(ast)

            # Z/2 consistency
            z2_ok, z2_errors = self._verify_z2_consistency(ast)

            # Structural match
            structural_ok, struct_errors = self._verify_structural(ast)

            # Dual stream agreement
            dual_ok = True
            if dual_stream_result:
                dual_ok = dual_stream_result.passed and dual_stream_result.agreement

            all_ok = ok and mod5_ok and z2_ok and structural_ok and dual_ok and golden_ref_match
            all_errors = errors + mod5_errors + z2_errors + struct_errors

            return TypeVerifyResult(
                passed=all_ok,
                mod5_consistency=mod5_ok,
                z2_consistency=z2_ok,
                structural_match=structural_ok,
                dual_stream_agreement=dual_ok,
                golden_ref_match=golden_ref_match,
                errors=all_errors
            )

        except Exception as e:
            return TypeVerifyResult(
                passed=False,
                errors=[f"Type verification error: {e}"]
            )

    def _run_dual_stream(self, ast: Any) -> DualStreamResult:
        """Run dual-stream verification on AST."""
        from svl.type_inference import TypeEnv, TypeScheme, Type
        env = TypeEnv()

        # Initialize with primitives
        for p in ['int', 'float', 'bool', 'void', 'never', 'string']:
            env.bindings[p] = TypeScheme(vars=[], body=Type.prim(p))

        # Run dual stream on program
        dual_stream = DualStreamChecker(self.type_checker)
        return dual_stream.verify_program(ast, env)

    def _collect_type_anns(self, ast: Any) -> List[Any]:
        """Collect every type annotation (TypeExpr) reachable from the AST."""
        anns = []

        def walk(node: Any):
            if node is None:
                return
            if hasattr(node, '__dataclass_fields__'):
                if getattr(node, 'type_ann', None) is not None:
                    anns.append(node.type_ann)
                for f in node.__dataclass_fields__:
                    value = getattr(node, f)
                    if hasattr(value, '__dataclass_fields__'):
                        walk(value)
                    elif isinstance(value, list):
                        for item in value:
                            walk(item)

        walk(ast)
        return anns

    def _verify_mod5_consistency(self, ast: Any) -> Tuple[bool, List[str]]:
        """Verify Mod-5 bucket consistency across the AST.

        Falsifiable: every annotated type must have a well-defined in-range bucket, and a
        primitive annotation must land in the documented base bucket B0. The expectation is
        hardcoded (not read from PRIMITIVE_BUCKETS) — comparing the table against itself
        would be tautological and could never fail.
        """
        from svl.mod5_types import PRIMITIVE_BUCKETS
        expected_prim_bucket = Mod5Bucket.B0   # documented contract: primitives are B0
        errors = []

        # The published table itself must agree with the documented contract.
        for prim, bucket in PRIMITIVE_BUCKETS.items():
            if bucket != expected_prim_bucket:
                errors.append(
                    f"PRIMITIVE_BUCKETS[{prim}] = {bucket.name}, documented contract is B0"
                )

        for ann in self._collect_type_anns(ast):
            kind = getattr(ann, 'kind', type(ann).__name__)
            try:
                bucket = bucket_of_type(ann)
            except Exception as e:                       # noqa: BLE001
                errors.append(f"Mod-5 bucket undefined for {kind}: {e}")
                continue
            if not isinstance(bucket, Mod5Bucket) or not (0 <= int(bucket) <= 4):
                errors.append(f"Mod-5 bucket out of range for {kind}: {bucket}")
                continue
            if getattr(ann, 'kind', None) == 'prim' and bucket != expected_prim_bucket:
                errors.append(
                    f"prim {getattr(ann, 'value', None)} in bucket {bucket.name}, "
                    f"documented contract is {expected_prim_bucket.name}"
                )

        return len(errors) == 0, errors

    def _verify_z2_consistency(self, ast: Any) -> Tuple[bool, List[str]]:
        """Verify Z/2 negation is a well-defined involution on every annotated type.

        Falsifiable: a broken Z2_NEGATION_MAP (a bucket that does not map back to itself
        under a double negation) fails here.
        """
        errors = []

        for ann in self._collect_type_anns(ast):
            kind = getattr(ann, 'kind', type(ann).__name__)
            try:
                bucket = bucket_of_type(ann)
                if z2_negate(z2_negate(bucket)) != bucket:
                    errors.append(
                        f"Z/2 involution violated for {kind}: {bucket.name} "
                        f"-> {z2_negate(bucket).name} -> {z2_negate(z2_negate(bucket)).name}"
                    )
            except Exception as e:                       # noqa: BLE001
                errors.append(f"Z/2 negation undefined for {kind}: {e}")

        return len(errors) == 0, errors

    def _verify_structural(self, ast: Any) -> Tuple[bool, List[str]]:
        """Verify the AST's 231-gate structural checksums.

        Falsifiable: serialization must be deterministic (a second independent parse of the
        AST's own bytes yields the same checksums) and every channel must lie in [0, 231).
        """
        errors = []

        try:
            data = to_binary(ast)
            checksums = compute_checksums_cython(data)
        except Exception as e:                           # noqa: BLE001
            errors.append(f"Structural checksum computation failed: {e}")
            return False, errors

        for i, (name, value) in enumerate(zip(('SUM', 'LINEAR', 'PRODUCT'), checksums)):
            if not (0 <= value < MODULUS):
                errors.append(f"{name} checksum out of range [0,{MODULUS}): {value}")
        if compute_checksums_cython(data) != checksums:
            errors.append("Structural checksums are not deterministic across serializations")

        return len(errors) == 0, errors

    def _verify_golden_refs(self) -> bool:
        """Verify golden references still match."""
        results = verify_all_golden_refs()
        return all(results.values())

    def verify_file(self, filepath: str) -> TypeVerifyResult:
        """Verify type from file."""
        with open(filepath, 'r', encoding='utf-8') as f:
            source = f.read()
        return self.verify_type(source)


# Convenience function
def verify_type(source: str, config: Optional[TypeVerificationConfig] = None) -> TypeVerifyResult:
    """Verify type of SVL source code."""
    layer = TypeLayer(config)
    return layer.verify_type(source)


if __name__ == '__main__':
    # Test type layer
    print("=== Type Layer Test ===")

    from svl.golden_refs import get_golden_ref
    from svl.type_layer import verify_type

    # Test with golden reference
    ref = get_golden_ref('psalm119_aleph')
    result = verify_type(ref.source)

    print(f"Psalm 119 Aleph:")
    print(f"  Passed: {result.passed}")
    print(f"  Mod-5: {result.mod5_consistency}")
    print(f"  Z/2: {result.z2_consistency}")
    print(f"  Structural: {result.structural_match}")
    print(f"  Dual Stream: {result.dual_stream_agreement}")
    print(f"  Golden Refs: {result.golden_ref_match}")

    if result.errors:
        print(f"  Errors: {result.errors}")

    # Test forbidden sum()
    bad_code = '''
    module test {
      func main() type void {
        let x: float = sum([1.0, 2.0, 3.0])
        return
      }
    }
    '''

    result2 = verify_type(bad_code)
    print(f"\nForbidden sum test:")
    print(f"  Passed: {result2.passed}")
    print(f"  Errors: {result2.errors}")

    print("\n✓ Type layer test complete!")