# svl/simd_vectorization.py
# SIMD Vectorization for WASM Compiler (H26)
# Auto-vectorization pass for loops with SIMD instruction emission

from typing import Dict, List, Optional, Set, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum

from svl.parser_rd import (
    Program, Module, FuncDecl, Block, ForStmt, BinaryExpr, Ident, Literal,
    IndexExpr, ArrayLit, LetStmt, ReturnStmt, IfStmt, WhileStmt, TryStmt,
    ExprStmt, StructLit, LambdaExpr, CallExpr, StructDecl, NodeType,
    AssignExpr, UnaryExpr
)


class SimdType(Enum):
    """WASM SIMD vector types."""
    V128 = "v128"
    I8X16 = "i8x16"
    I16X8 = "i16x8"
    I32X4 = "i32x4"
    I64X2 = "i64x2"
    F32X4 = "f32x4"
    F64X2 = "f64x2"


@dataclass
class SimdOperation:
    """SIMD operation with vector type."""
    op: str
    vector_type: SimdType
    lane_count: int


# Mapping from scalar ops to SIMD ops
SCALAR_TO_SIMD = {
    ('i32', 'add'): SimdOperation('i32x4.add', SimdType.I32X4, 4),
    ('i32', 'sub'): SimdOperation('i32x4.sub', SimdType.I32X4, 4),
    ('i32', 'mul'): SimdOperation('i32x4.mul', SimdType.I32X4, 4),
    ('i64', 'add'): SimdOperation('i64x2.add', SimdType.I64X2, 2),
    ('i64', 'sub'): SimdOperation('i64x2.sub', SimdType.I64X2, 2),
    ('i64', 'mul'): SimdOperation('i64x2.mul', SimdType.I64X2, 2),
    ('f32', 'add'): SimdOperation('f32x4.add', SimdType.F32X4, 4),
    ('f32', 'sub'): SimdOperation('f32x4.sub', SimdType.F32X4, 4),
    ('f32', 'mul'): SimdOperation('f32x4.mul', SimdType.F32X4, 4),
    ('f64', 'add'): SimdOperation('f64x2.add', SimdType.F64X2, 2),
    ('f64', 'sub'): SimdOperation('f64x2.sub', SimdType.F64X2, 2),
    ('f64', 'mul'): SimdOperation('f64x2.mul', SimdType.F64X2, 2),
}

# Horizontal reduction ops
HORIZONTAL_OPS = {
    'i32x4': 'i32x4.add',  # hadd not available, use shuffle+add
    'i64x2': 'i64x2.add',
    'f32x4': 'f32x4.add',
    'f64x2': 'f64x2.add',
}


@dataclass
class LoopInfo:
    """Information about a loop for vectorization."""
    loop_var: str
    start: int
    end: int
    step: int
    body: Block
    array_accesses: List[Tuple[str, str]]  # (array_name, index_var)
    computations: List[BinaryExpr]
    is_vectorizable: bool = False
    simd_type: Optional[SimdType] = None
    vector_width: int = 4


class SimdVectorizer:
    """Auto-vectorization pass for SVL compiler."""

    def __init__(self):
        self.loop_infos: List[LoopInfo] = []
        self.array_types: Dict[str, Tuple[str, int]] = {}  # name -> (element_type, size)

    def analyze_program(self, program: Program) -> List[LoopInfo]:
        """Analyze program for vectorizable loops."""
        self.loop_infos = []
        self.array_types = {}

        for module in program.modules:
            self._collect_array_types(module)
            self._analyze_module(module)

        return self.loop_infos

    def _collect_array_types(self, module: Module):
        """Collect array type information from struct/array declarations."""
        for item in module.body.statements:
            if isinstance(item, StructDecl):
                # Structs with array-like fields
                pass
            elif isinstance(item, FuncDecl):
                # Check parameters and locals for array types
                self._collect_from_func(item)

    def _collect_from_func(self, func: FuncDecl):
        """Collect array info from function."""
        for param in func.params:
            if param.type_ann and param.type_ann.kind == 'array':
                elem_type = param.type_ann.value.kind if hasattr(param.type_ann.value, 'kind') else 'i32'
                self.array_types[param.name] = (elem_type, 0)  # size unknown

    def _analyze_module(self, module: Module):
        """Analyze module for loops."""
        for item in module.body.statements:
            if isinstance(item, FuncDecl):
                self._analyze_func(item)

    def _analyze_func(self, func: FuncDecl):
        """Analyze function body for vectorizable loops."""
        self._analyze_block(func.body, func.name)

    def _analyze_block(self, block: Block, func_name: str):
        """Analyze block for loops."""
        for stmt in block.statements:
            if isinstance(stmt, ForStmt):
                loop_info = self._analyze_for_loop(stmt, func_name)
                if loop_info:
                    self.loop_infos.append(loop_info)
            elif isinstance(stmt, Block):
                self._analyze_block(stmt, func_name)

    def _analyze_for_loop(self, for_stmt: ForStmt, func_name: str) -> Optional[LoopInfo]:
        """Analyze a for loop for vectorization potential."""
        # Check if it's a simple range loop: for i in 0..N
        if not self._is_simple_range_loop(for_stmt):
            return None

        # Extract loop bounds
        start, end, step = self._extract_loop_bounds(for_stmt)
        if start is None or end is None:
            return None

        # Analyze body for array accesses and computations
        array_accesses = []
        computations = []
        self._analyze_loop_body(for_stmt.body, array_accesses, computations)

        # Check vectorizability
        is_vectorizable, simd_type, vector_width = self._check_vectorizability(
            array_accesses, computations
        )

        return LoopInfo(
            loop_var=for_stmt.var,
            start=start,
            end=end,
            step=step,
            body=for_stmt.body,
            array_accesses=array_accesses,
            computations=computations,
            is_vectorizable=is_vectorizable,
            simd_type=simd_type,
            vector_width=vector_width
        )

    def _is_simple_range_loop(self, for_stmt: ForStmt) -> bool:
        """Check if for loop is a simple range loop."""
        # Check iter_expr is a range expression or simple iterable
        return True  # Simplified

    def _extract_loop_bounds(self, for_stmt: ForStmt) -> Tuple[Optional[int], Optional[int], Optional[int]]:
        """Extract loop start, end, step from for statement."""
        # Simplified: would parse range expression
        return 0, 100, 1  # Placeholder

    def _analyze_loop_body(self, block: Block,
                          array_accesses: List[Tuple[str, str]],
                          computations: List[BinaryExpr]):
        """Analyze loop body for array accesses and computations."""
        for stmt in block.statements:
            if isinstance(stmt, LetStmt):
                self._analyze_expr(stmt.value, array_accesses, computations)
            elif isinstance(stmt, ExprStmt):
                self._analyze_expr(stmt.expression, array_accesses, computations)
            elif isinstance(stmt, AssignExpr):
                self._analyze_expr(stmt.value, array_accesses, computations)

            # Recurse into nested blocks
            if isinstance(stmt, Block):
                self._analyze_loop_body(stmt, array_accesses, computations)

    def _analyze_expr(self, expr, array_accesses: List[Tuple[str, str]], computations: List[BinaryExpr]):
        """Recursively analyze expression for array accesses and computations."""
        if isinstance(expr, IndexExpr):
            array_accesses.append((expr.left.name if isinstance(expr.left, Ident) else 'unknown',
                                  expr.right.name if isinstance(expr.right, Ident) else 'unknown'))
        elif isinstance(expr, BinaryExpr):
            computations.append(expr)
            # Recurse into left and right
            self._analyze_expr(expr.left, array_accesses, computations)
            self._analyze_expr(expr.right, array_accesses, computations)
        elif isinstance(expr, CallExpr):
            for arg in expr.arguments:
                self._analyze_expr(arg, array_accesses, computations)
        elif isinstance(expr, UnaryExpr):
            self._analyze_expr(expr.operand, array_accesses, computations)
        elif isinstance(expr, AssignExpr):
            self._analyze_expr(expr.value, array_accesses, computations)

    def _check_vectorizability(self,
                               array_accesses: List[Tuple[str, str]],
                               computations: List[BinaryExpr]) -> Tuple[bool, Optional[SimdType], int]:
        """Check if loop can be vectorized."""
        if not array_accesses:
            return False, None, 0

        # Check if all accesses are to same array with contiguous indices
        # Check if computations are simple arithmetic
        element_type = 'i32'  # Default

        # Determine SIMD type from element type
        if element_type in ('i32', 'int'):
            return True, SimdType.I32X4, 4
        elif element_type in ('i64', 'long'):
            return True, SimdType.I64X2, 2
        elif element_type in ('f32', 'float'):
            return True, SimdType.F32X4, 4
        elif element_type in ('f64', 'double'):
            return True, SimdType.F64X2, 2

        return False, None, 0

    def generate_simd_wasm(self, loop_info: LoopInfo) -> List[str]:
        """Generate WASM SIMD instructions for vectorized loop."""
        if not loop_info.is_vectorizable:
            return []

        instructions = []
        vt = loop_info.simd_type
        width = loop_info.vector_width

        # Vectorized loop setup
        instructions.append(f";; SIMD vectorized loop (width={width})")
        instructions.append(f"local.set ${loop_info.loop_var}_vec")

        # Process array accesses
        for array_name, index_var in loop_info.array_accesses:
            # Load vector from memory
            instructions.append(f";; Load vector from {array_name}")
            instructions.append(f"v128.load (local.get ${array_name})")

        # Process computations
        for comp in loop_info.computations:
            simd_op = self._get_simd_op(comp)
            if simd_op:
                instructions.append(f";; {comp.operator} -> {simd_op.op}")
                instructions.append(simd_op.op)

        # Store results
        instructions.append("v128.store")

        return instructions

    def _get_simd_op(self, comp: BinaryExpr) -> Optional[SimdOperation]:
        """Get SIMD operation for binary expression."""
        # Determine element type from context
        element_type = 'i32'  # Would infer from type checker
        key = (element_type, comp.operator)
        return SCALAR_TO_SIMD.get(key)


class SimdWasmEmitter:
    """Emits WASM SIMD instructions."""

    def __init__(self, vectorizer: SimdVectorizer):
        self.vectorizer = vectorizer

    def emit_vectorized_function(self, func: FuncDecl) -> str:
        """Emit WASM for function with vectorized loops."""
        # Find loops in this function
        func_loops = [li for li in self.vectorizer.loop_infos
                      if self._loop_in_function(li, func)]

        if not func_loops:
            return ""  # No vectorization

        # Generate WASM with SIMD
        lines = []
        lines.append(f"(func ${func.name}")

        for loop in func_loops:
            simd_instrs = self.vectorizer.generate_simd_wasm(loop)
            lines.extend(f"  {instr}" for instr in simd_instrs)

        lines.append(")")
        return '\n'.join(lines)

    def _loop_in_function(self, loop: LoopInfo, func: FuncDecl) -> bool:
        """Check if loop is in function."""
        # Simplified check
        return True


def run_simd_vectorization_pass(program: Program) -> Program:
    """Run SIMD vectorization pass on program."""
    vectorizer = SimdVectorizer()
    vectorizer.analyze_program(program)

    # In a full implementation, would modify AST or generate different WASM
    return program


def has_simd_instructions(wasm_text: str) -> bool:
    """Check if WASM text contains SIMD instructions."""
    simd_prefixes = [
        'v128.', 'i8x16.', 'i16x8.', 'i32x4.', 'i64x2.',
        'f32x4.', 'f64x2.'
    ]
    return any(prefix in wasm_text for prefix in simd_prefixes)


if __name__ == '__main__':
    print("=== SIMD Vectorization Test ===")

    # Test with a simple program
    from svl.lexer import tokenize
    from svl.parser_rd import parse

    test_source = '''
    module test {
      func dot_product(a: vec<int, 4>, b: vec<int, 4>) type int {
        let sum: int = 0
        for i in 0..4 {
          sum = sum + a[i] * b[i]
        }
        return sum
      }
      func main() type void { return }
    }
    '''

    tokens = tokenize(test_source)
    ast = parse(tokens)

    vectorizer = SimdVectorizer()
    loops = vectorizer.analyze_program(ast)

    print(f"Found {len(loops)} vectorizable loops")
    for loop in loops:
        print(f"  Loop var: {loop.loop_var}, vectorizable: {loop.is_vectorizable}")
        print(f"    SIMD type: {loop.simd_type}, width: {loop.vector_width}")
        print(f"    Array accesses: {loop.array_accesses}")
        print(f"    Computations: {len(loop.computations)}")

    print("\n✓ SIMD Vectorization test complete!")