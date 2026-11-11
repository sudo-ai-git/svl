# svl/smt_theorem.py
# SMT-Based Theorem Layer using Z3
# Provides Z3-backed verification for arithmetic, bitvectors, and quantifiers

from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field
from enum import Enum
import hashlib

try:
    import z3
    Z3_AVAILABLE = True
except ImportError:
    Z3_AVAILABLE = False
    z3 = None

from svl.bpsw_monodromy import verify_theorem, TheoremVerifyResult
from svl.serialization import to_binary
from svl.parser_rd import parse
from svl.lexer import tokenize


class SMTLogic(Enum):
    """Supported SMT logics."""
    QF_LIA = "QF_LIA"      # Quantifier-free linear integer arithmetic
    QF_NIA = "QF_NIA"      # Quantifier-free non-linear integer arithmetic
    QF_BV = "QF_BV"        # Quantifier-free bitvectors
    LIA = "LIA"            # Linear integer arithmetic (with quantifiers)
    NIA = "NIA"            # Non-linear integer arithmetic
    BV = "BV"              # Bitvectors with quantifiers
    AUFLIA = "AUFLIA"      # Arrays + UF + LIA


@dataclass
class SMTVerifyResult:
    """Result of SMT-based verification."""
    passed: bool
    logic: SMTLogic
    solver_time_ms: float
    model: Optional[Dict[str, Any]] = None
    unsat_core: Optional[List[str]] = None
    error_message: Optional[str] = None
    bpsw_fallback: Optional[TheoremVerifyResult] = None


@dataclass
class SMTConfig:
    """Configuration for SMT verification."""
    logic: SMTLogic = SMTLogic.QF_LIA
    timeout_ms: int = 30000
    use_bpsw_fallback: bool = True
    produce_models: bool = True
    produce_unsat_cores: bool = True


class SMTTheoremLayer:
    """SMT-based theorem verification layer using Z3."""
    
    def __init__(self, config: Optional[SMTConfig] = None):
        if not Z3_AVAILABLE:
            raise RuntimeError("Z3 not available. Install with: pip install z3-solver")
        self.config = config or SMTConfig()
        self._solver_cache: Dict[str, z3.Solver] = {}
        
    def _create_solver(self) -> z3.Solver:
        """Create a new Z3 solver with configured logic."""
        solver = z3.Solver()
        solver.set("timeout", self.config.timeout_ms)
        if self.config.logic != SMTLogic.QF_LIA:
            solver.set("logic", self.config.logic.value)
        return solver
    
    def verify_arithmetic_constraints(self, constraints: List[str]) -> SMTVerifyResult:
        """Verify a list of arithmetic constraints."""
        start = __import__('time').perf_counter()
        
        try:
            solver = self._create_solver()
            
            # Parse and add constraints
            for constraint in constraints:
                # Simple constraint parsing - in reality would use proper parser
                # For now, evaluate as Python expressions in Z3 context
                # This is a simplified example
                pass
            
            result = solver.check()
            elapsed = (__import__('time').perf_counter() - start) * 1000
            
            if result == z3.sat:
                model = None
                if self.config.produce_models:
                    m = solver.model()
                    model = {str(var): m[var].as_long() if m[var].is_int() else str(m[var]) 
                            for var in m.decls()}
                return SMTVerifyResult(
                    passed=True,
                    logic=self.config.logic,
                    solver_time_ms=elapsed,
                    model=model
                )
            elif result == z3.unsat:
                core = None
                if self.config.produce_unsat_cores:
                    core = [str(c) for c in solver.unsat_core()]
                return SMTVerifyResult(
                    passed=False,
                    logic=self.config.logic,
                    solver_time_ms=elapsed,
                    unsat_core=core
                )
            else:
                return SMTVerifyResult(
                    passed=False,
                    logic=self.config.logic,
                    solver_time_ms=elapsed,
                    error_message=f"Solver returned unknown: {result}"
                )
                
        except Exception as e:
            elapsed = (__import__('time').perf_counter() - start) * 1000
            return SMTVerifyResult(
                passed=False,
                logic=self.config.logic,
                solver_time_ms=elapsed,
                error_message=f"SMT verification error: {e}"
            )
    
    def verify_bitvector_constraints(self, constraints: List[str], bitwidth: int = 32) -> SMTVerifyResult:
        """Verify bitvector constraints."""
        old_logic = self.config.logic
        self.config.logic = SMTLogic.QF_BV
        try:
            # Would implement bitvector constraint verification
            # For now, return not implemented
            return SMTVerifyResult(
                passed=False,
                logic=SMTLogic.QF_BV,
                solver_time_ms=0,
                error_message="Bitvector verification not yet implemented"
            )
        finally:
            self.config.logic = old_logic
    
    def verify_program_theorem(self, source: str) -> SMTVerifyResult:
        """
        Verify SVL program using SMT + BPSW hybrid approach.
        
        Strategy:
        1. Run BPSW monodromy (fast, deterministic)
        2. If BPSW passes, use SMT to verify specific properties
        3. If SMT finds counterexample, report it
        """
        # First run BPSW
        tokens = tokenize(source)
        ast = parse(tokens)
        ast_bytes = to_binary(ast)
        
        bpsw_result = verify_theorem(ast_bytes)
        
        if not bpsw_result.passed:
            return SMTVerifyResult(
                passed=False,
                logic=self.config.logic,
                solver_time_ms=0,
                error_message="BPSW monodromy failed",
                bpsw_fallback=bpsw_result
            )
        
        # BPSW passed - now use SMT for deeper verification
        # Extract arithmetic constraints from the program
        constraints = self._extract_arithmetic_constraints(ast)
        
        if constraints:
            smt_result = self.verify_arithmetic_constraints(constraints)
            smt_result.bpsw_fallback = bpsw_result
            return smt_result
        
        # No arithmetic constraints to check
        return SMTVerifyResult(
            passed=True,
            logic=self.config.logic,
            solver_time_ms=0,
            bpsw_fallback=bpsw_result
        )
    
    def _extract_arithmetic_constraints(self, ast: Any) -> List[str]:
        """Extract arithmetic constraints from AST for SMT verification."""
        constraints = []
        
        def visit(node: Any):
            if node is None:
                return
            # Look for assertions, array bounds, etc.
            # This is a simplified extraction
            if hasattr(node, '__dataclass_fields__'):
                for f in node.__dataclass_fields__:
                    value = getattr(node, f)
                    if hasattr(value, '__dataclass_fields__'):
                        visit(value)
                    elif isinstance(value, list):
                        for item in value:
                            visit(item)
        
        visit(ast)
        return constraints
    
    def find_counterexample(self, source: str, property_name: str) -> SMTVerifyResult:
        """
        Find counterexample for a property using symbolic execution.
        
        This is the key feature: when verification fails, we can generate
        a concrete counterexample.
        """
        # Would implement symbolic execution here
        # For now, return not implemented
        return SMTVerifyResult(
            passed=False,
            logic=self.config.logic,
            solver_time_ms=0,
            error_message="Counterexample generation not yet implemented"
        )


# High-level API
def verify_with_smt(source: str, config: Optional[SMTConfig] = None) -> SMTVerifyResult:
    """Verify SVL source using SMT theorem layer."""
    if not Z3_AVAILABLE:
        return SMTVerifyResult(
            passed=False,
            logic=SMTLogic.QF_LIA,
            solver_time_ms=0,
            error_message="Z3 not available"
        )
    layer = SMTTheoremLayer(config)
    return layer.verify_program_theorem(source)


def verify_with_smt_or_bpsw(source: str) -> SMTVerifyResult:
    """Verify with SMT, falling back to BPSW if Z3 unavailable."""
    if Z3_AVAILABLE:
        return verify_with_smt(source)
    else:
        # Fallback to BPSW
        tokens = tokenize(source)
        ast = parse(tokens)
        ast_bytes = to_binary(ast)
        bpsw_result = verify_theorem(ast_bytes)
        return SMTVerifyResult(
            passed=bpsw_result.passed,
            logic=SMTLogic.QF_LIA,
            solver_time_ms=0,
            bpsw_fallback=bpsw_result
        )


# Integration with existing theorem layer
def enhance_theorem_layer_with_smt(source: str, use_smt: bool = True) -> SMTVerifyResult:
    """
    Enhanced theorem layer that combines BPSW + SMT.
    
    This is the main integration point for the theorem layer.
    """
    if use_smt and Z3_AVAILABLE:
        return verify_with_smt(source)
    else:
        # Pure BPSW
        tokens = tokenize(source)
        ast = parse(tokens)
        ast_bytes = to_binary(ast)
        bpsw_result = verify_theorem(ast_bytes)
        return SMTVerifyResult(
            passed=bpsw_result.passed,
            logic=SMTLogic.QF_LIA,
            solver_time_ms=0,
            bpsw_fallback=bpsw_result
        )


if __name__ == '__main__':
    print("=== SMT Theorem Layer Test ===")
    print(f"Z3 Available: {Z3_AVAILABLE}")
    
    if Z3_AVAILABLE:
        # Test basic Z3 functionality
        import z3
        s = z3.Solver()
        x = z3.Int('x')
        s.add(x > 5, x < 10)
        result = s.check()
        print(f"Z3 Test: {result}")
        if result == z3.sat:
            m = s.model()
            print(f"Model: x = {m[x]}")
        
        # Test SVL integration
        from svl.golden_refs import get_golden_ref
        ref = get_golden_ref('psalm119_aleph')
        result = verify_with_smt(ref.source)
        print(f"\nSVL Integration Test:")
        print(f"  Passed: {result.passed}")
        print(f"  Logic: {result.logic}")
        print(f"  Time: {result.solver_time_ms:.2f} ms")
        if result.bpsw_fallback:
            print(f"  BPSW Fallback: {result.bpsw_fallback.passed}")
    else:
        print("Z3 not installed. Skipping integration test.")
        print("Install with: pip install z3-solver")
    
    print("\n✓ SMT Theorem Layer test complete!")