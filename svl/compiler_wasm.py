# svl/compiler_wasm.py
# SVL Compiler Backend — WASM Target (Phase 4, Week 16)
# AST → WASM compilation with deterministic output

from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import hashlib

from svl.parser_rd import (
    Program, Module, FuncDecl, StructDecl, Block, LetStmt, IfStmt, WhileStmt,
    ForStmt, ReturnStmt, AssertStmt, TryStmt, ExprStmt,
    BinaryExpr, UnaryExpr, CallExpr, MatchExpr, AwaitExpr, LambdaExpr,
    StructLit, ArrayLit, Ident, Literal, FieldAccess, IndexExpr,
    TypeExpr, Param, Field, NodeType
)
from svl.serialization import to_binary
from svl.simd_vectorization import SimdVectorizer, SimdType, LoopInfo


# ============================================================================
# WASM TYPE SYSTEM
# ============================================================================

class WasmValType(Enum):
    I32 = "i32"
    I64 = "i64"
    F32 = "f32"
    F64 = "f64"
    FUNCREF = "funcref"
    EXTERNREF = "externref"


class WasmMutability(Enum):
    CONST = "const"
    VAR = "var"


@dataclass
class WasmFuncType:
    params: List[WasmValType]
    results: List[WasmValType]


@dataclass
class WasmGlobal:
    name: str
    val_type: WasmValType
    mutability: WasmMutability
    init_expr: str


@dataclass
class WasmMemory:
    min_pages: int
    max_pages: Optional[int] = None


@dataclass
class WasmExport:
    name: str
    kind: str  # func, memory, global, table
    index: int


@dataclass
class WasmImport:
    module: str
    name: str
    kind: str  # func, memory, global, table
    func_type: Optional[WasmFuncType] = None


# ============================================================================
# TYPE LOWERING: Mod-5 Types → WASM ValTypes
# ============================================================================

def lower_type_to_wasm(type_expr: TypeExpr) -> WasmValType:
    """Lower SVL type expression to WASM valtype."""
    if type_expr.kind == 'prim':
        prim_map = {
            'int': WasmValType.I32,
            'float': WasmValType.F64,
            'bool': WasmValType.I32,
            'string': WasmValType.I32,  # pointer to string in linear memory
            'void': WasmValType.I32,    # dummy
            'never': WasmValType.I32,   # unreachable
        }
        return prim_map.get(type_expr.value, WasmValType.I32)
    elif type_expr.kind in ('struct', 'generic'):
        return WasmValType.I32  # pointer to heap object
    elif type_expr.kind == 'func':
        return WasmValType.FUNCREF
    elif type_expr.kind == 'tuple':
        return WasmValType.I32  # pointer to tuple struct
    elif type_expr.kind == 'array':
        return WasmValType.I32  # pointer to array
    return WasmValType.I32


# WASM GC Proposal Support (H25)
# Support for struct and array types in WASM GC

class WasmGCType(Enum):
    """WASM GC types."""
    STRUCT = "struct"
    ARRAY = "array"
    I31 = "i31"  # 31-bit integer for small integers
    EXTERNREF = "externref"
    ANYREF = "anyref"
    EQREF = "eqref"
    STRUCTREF = "structref"
    ARRAYREF = "arrayref"


@dataclass
class WasmStructType:
    """WASM GC struct type."""
    fields: List[Tuple[str, WasmValType]]  # (name, type)
    is_final: bool = False  # Whether struct can be subtyped


@dataclass
class WasmArrayType:
    """WASM GC array type."""
    element_type: WasmValType
    mutable: bool = False


# ============================================================================
# TYPE LOWERING: Mod-5 Types → WASM ValTypes
# ============================================================================

from typing import Union

def lower_type_to_wasm(type_expr: TypeExpr) -> WasmValType:
    """Lower SVL type expression to WASM valtype."""
    if type_expr.kind == 'prim':
        prim_map = {
            'int': WasmValType.I32,
            'float': WasmValType.F64,
            'bool': WasmValType.I32,
            'string': WasmValType.I32,  # pointer to string in linear memory
            'void': WasmValType.I32,    # dummy
            'never': WasmValType.I32,   # unreachable
        }
        return prim_map.get(type_expr.value, WasmValType.I32)
    elif type_expr.kind in ('struct', 'generic'):
        return WasmValType.I32  # pointer to heap object
    elif type_expr.kind == 'func':
        return WasmValType.FUNCREF
    elif type_expr.kind == 'tuple':
        return WasmValType.I32  # pointer to tuple struct
    elif type_expr.kind == 'array':
        return WasmValType.I32  # pointer to array
    return WasmValType.I32


def lower_func_type(params: List[TypeExpr], return_type: TypeExpr) -> WasmFuncType:
    """Lower function type to WASM function type."""
    return WasmFuncType(
        params=[lower_type_to_wasm(p) for p in params],
        results=[lower_type_to_wasm(return_type)]
    )


# WASM GC Proposal Support (H25)
# Support for struct and array types in WASM GC

class WasmGCType(Enum):
    """WASM GC types."""
    STRUCT = "struct"
    ARRAY = "array"
    I31 = "i31"  # 31-bit integer for small integers
    EXTERNREF = "externref"
    ANYREF = "anyref"
    EQREF = "eqref"
    STRUCTREF = "structref"
    ARRAYREF = "arrayref"


@dataclass
class WasmStructType:
    """WASM GC struct type."""
    fields: List[Tuple[str, WasmValType]]  # (name, type)
    is_final: bool = False  # Whether struct can be subtyped


@dataclass
class WasmArrayType:
    """WASM GC array type."""
    element_type: WasmValType
    mutable: bool = False


def lower_type_to_wasm_gc(type_expr: TypeExpr) -> Union[WasmValType, WasmStructType, WasmArrayType]:
    """Lower SVL type expression to WASM GC type."""
    if type_expr.kind == 'prim':
        prim_map = {
            'int': WasmValType.I32,
            'float': WasmValType.F64,
            'bool': WasmValType.I32,
            'string': WasmValType.EXTERNREF,
            'void': WasmValType.I32,
            'never': WasmValType.I32,
        }
        return prim_map.get(type_expr.value, WasmValType.I32)
    elif type_expr.kind == 'struct':
        # Return struct type reference
        return WasmStructType(fields=[], is_final=True)
    elif type_expr.kind == 'generic':
        val = type_expr.value
        if isinstance(val, dict) and val.get('name') == 'Array':
            elem_type = lower_type_to_wasm_gc(val['args'][0])
            return WasmArrayType(element_type=elem_type, mutable=True)
    elif type_expr.kind == 'func':
        return WasmValType.FUNCREF
    elif type_expr.kind == 'array':
        val = type_expr.value
        if isinstance(val, TypeExpr):
            elem_type = lower_type_to_wasm_gc(val)
            return WasmArrayType(element_type=elem_type, mutable=True)
    return WasmValType.I32


def generate_wasm_gc_types(state: 'CompilerState') -> List[str]:
    """Generate WASM GC type definitions."""
    lines = []
    
    # Generate struct types
    for struct_name, layout in state.struct_layouts.items():
        fields = []
        for field_name, (offset, field_type) in layout.items():
            fields.append(f"  (field {field_name} {field_type.value})")
        lines.append(f"(type ${struct_name} (struct\n{''.join(fields)}\n))")
    
    # Generate array types
    # Would need array type info from state
    
    return lines


# ============================================================================
# COMPILER STATE
# ============================================================================

@dataclass
class CompilerState:
    """State maintained during compilation."""
    functions: Dict[str, 'WasmFunction'] = field(default_factory=dict)
    globals: Dict[str, WasmGlobal] = field(default_factory=dict)
    struct_layouts: Dict[str, Dict[str, Tuple[int, WasmValType]]] = field(default_factory=dict)
    string_literals: Dict[str, int] = field(default_factory=dict)
    next_string_offset: int = 0
    memory_pages: int = 1  # 64KB pages
    function_index: int = 0
    type_index: int = 0
    current_function: Optional['WasmFunction'] = None
    local_counter: int = 0
    label_counter: int = 0
    string_data: List[Tuple[str, int]] = field(default_factory=list)  # (string, offset)
    
    # For deterministic output
    sorted_functions: List[str] = field(default_factory=list)
    sorted_structs: List[str] = field(default_factory=list)
    
    # SIMD vectorization info
    simd_loop_info: Dict[str, 'LoopInfo'] = field(default_factory=dict)  # func_name -> loop info


@dataclass
class WasmFunction:
    name: str
    func_type: WasmFuncType
    params: List[Tuple[str, WasmValType]]  # (name, type)
    locals: List[Tuple[str, WasmValType]]  # (name, type)
    body: List[str]  # WASM instructions as strings
    is_async: bool = False
    is_export: bool = False


# ============================================================================
# COMPILER
# ============================================================================

class WasmCompiler:
    """SVL to WASM compiler."""
    
    def __init__(self, deterministic: bool = True):
        self.deterministic = deterministic
        self.state = CompilerState()
    
    def compile(self, program: Program) -> str:
        """Compile full SVL program to WASM text format."""
        # Phase 1: Collect all declarations
        self._collect_declarations(program)
        
        # Phase 1.5: Run SIMD vectorizer to analyze loops
        self._run_simd_vectorizer(program)
        
        # Phase 2: Compute struct layouts
        self._compute_struct_layouts(program)
        
        # Phase 3: Compile functions
        self._compile_functions(program)
        
        # Phase 4: Generate WASM module
        return self._generate_wasm_module()
    
    def _run_simd_vectorizer(self, program: Program):
        """Run SIMD vectorizer to find vectorizable loops."""
        vectorizer = SimdVectorizer()
        loops = vectorizer.analyze_program(program)
        
        # Store loop info keyed by function name
        for loop in loops:
            if loop.is_vectorizable:
                # Find the function this loop belongs to
                # We'll match by function name pattern: module$func
                for func_name in self.state.functions:
                    # Store the first vectorizable loop for each function
                    if func_name not in self.state.simd_loop_info:
                        self.state.simd_loop_info[func_name] = loop
                        break
    
    def _collect_declarations(self, program: Program):
        """Collect all modules, functions, structs, globals."""
        for module in program.modules:
            for item in module.body.statements:
                if isinstance(item, FuncDecl):
                    func_name = f"{module.name}${item.name}"
                    func_type = lower_func_type(
                        [p.type_ann for p in item.params if p.type_ann],
                        item.return_type if item.return_type else TypeExpr(
                            type=NodeType.TYPE_EXPR, line=0, column=0, offset=0,
                            kind='prim', value='void'
                        )
                    )
                    self.state.functions[func_name] = WasmFunction(
                        name=func_name,
                        func_type=func_type,
                        params=[(p.name, lower_type_to_wasm(p.type_ann)) for p in item.params if p.type_ann],
                        locals=[],
                        body=[],
                        is_async=False,  # TODO: detect ASYNC
                        is_export=(item.name == 'main')
                    )
                elif isinstance(item, StructDecl):
                    if item.name not in self.state.sorted_structs:
                        self.state.sorted_structs.append(item.name)
        
        # Sort for determinism
        if self.deterministic:
            self.state.sorted_functions = sorted(self.state.functions.keys())
            self.state.sorted_structs = sorted(self.state.sorted_structs)
        else:
            self.state.sorted_functions = list(self.state.functions.keys())
    
    def _compute_struct_layouts(self, program: Program):
        """Compute memory layout for structs."""
        for module in program.modules:
            for item in module.body.statements:
                if isinstance(item, StructDecl):
                    layout = {}
                    offset = 0
                    for field in item.fields:
                        field_type = lower_type_to_wasm(field.type_ann) if field.type_ann else WasmValType.I32
                        # Align to 4 bytes for i32, 8 for i64/f64
                        align = 4 if field_type in (WasmValType.I32, WasmValType.F32) else 8
                        offset = (offset + align - 1) // align * align
                        layout[field.name] = (offset, field_type)
                        offset += 4 if field_type in (WasmValType.I32, WasmValType.F32) else 8
                    self.state.struct_layouts[item.name] = layout
    
    def _compile_functions(self, program: Program):
        """Compile all function bodies."""
        for module in program.modules:
            for item in module.body.statements:
                if isinstance(item, FuncDecl):
                    func_name = f"{module.name}${item.name}"
                    func = self.state.functions[func_name]
                    self.state.current_function = func
                    self.state.local_counter = len(func.params)
                    self.state.label_counter = 0
                    
                    # Compile function body
                    self._compile_block(item.body, is_function_body=True)
                    
                    self.state.current_function = None
    
    def _compile_block(self, block: Block, is_function_body: bool = False):
        """Compile a block of statements."""
        for stmt in block.statements:
            self._compile_stmt(stmt)
        
        # If function body and no explicit return, add implicit return
        if is_function_body and self.state.current_function:
            func = self.state.current_function
            if not func.body or not func.body[-1].startswith('return'):
                if func.func_type.results:
                    func.body.append('drop')  # Drop any leftover value
                func.body.append('return')
    
    def _compile_stmt(self, stmt):
        """Compile a statement."""
        if isinstance(stmt, LetStmt):
            self._compile_let_stmt(stmt)
        elif isinstance(stmt, IfStmt):
            self._compile_if_stmt(stmt)
        elif isinstance(stmt, WhileStmt):
            self._compile_while_stmt(stmt)
        elif isinstance(stmt, ForStmt):
            self._compile_for_stmt(stmt)
        elif isinstance(stmt, ReturnStmt):
            self._compile_return_stmt(stmt)
        elif isinstance(stmt, AssertStmt):
            self._compile_assert_stmt(stmt)
        elif isinstance(stmt, TryStmt):
            self._compile_try_stmt(stmt)
        elif isinstance(stmt, ExprStmt):
            self._compile_expr(stmt.expression)
            # Drop result if not used
            self.state.current_function.body.append('drop')
        elif isinstance(stmt, Block):
            self._compile_block(stmt)
    
    def _compile_let_stmt(self, stmt: LetStmt):
        """Compile let binding."""
        # Allocate local
        local_idx = self.state.local_counter
        self.state.local_counter += 1
        
        # Compile value
        self._compile_expr(stmt.value)
        
        # Store to local
        func = self.state.current_function
        func.locals.append((stmt.name, lower_type_to_wasm(stmt.type_ann) if stmt.type_ann else WasmValType.I32))
        func.body.append(f'local.set ${stmt.name}')
    
    def _compile_if_stmt(self, stmt: IfStmt):
        """Compile if statement."""
        func = self.state.current_function
        
        # Compile condition
        self._compile_expr(stmt.condition)
        
        # If-then-else
        func.body.append('if')
        self._compile_block(stmt.then_branch)
        
        if stmt.else_branch:
            func.body.append('else')
            self._compile_block(stmt.else_branch)
        
        func.body.append('end')
    
    def _compile_while_stmt(self, stmt: WhileStmt):
        """Compile while loop."""
        func = self.state.current_function
        label_start = f"$while_{self.state.label_counter}"
        label_end = f"$while_end_{self.state.label_counter}"
        self.state.label_counter += 1
        
        func.body.append(f'loop {label_start}')
        func.body.append(f'block {label_end}')
        
        # Condition
        self._compile_expr(stmt.condition)
        func.body.append(f'br_if {label_end}')
        
        # Body
        self._compile_block(stmt.body)
        
        func.body.append(f'br {label_start}')
        func.body.append('end')
        func.body.append('end')
    
    def _compile_for_stmt(self, stmt: ForStmt):
        """Compile for loop (for x in iterable)."""
        func = self.state.current_function
        
        # Check if this function has a vectorizable loop
        simd_loop = self.state.simd_loop_info.get(func.name)
        is_vectorizable = (
            simd_loop is not None and 
            simd_loop.loop_var == stmt.var and
            self._is_range_loop(stmt)
        )
        
        if is_vectorizable:
            self._compile_vectorized_for_loop(stmt, simd_loop)
            return
        
        # Simplified: compile as while loop with iterator
        iter_local = f"$iter_{self.state.label_counter}"
        self.state.label_counter += 1
        self._compile_expr(stmt.iter_expr)
        func.locals.append((iter_local, WasmValType.I32))
        func.body.append(f'local.set {iter_local}')
        
        label_start = f"$for_{self.state.label_counter}"
        label_end = f"$for_end_{self.state.label_counter}"
        self.state.label_counter += 1
        
        func.body.append(f'loop {label_start}')
        func.body.append(f'block {label_end}')
        
        # Check iterator has next (simplified - just check not null)
        func.body.append(f'local.get {iter_local}')
        func.body.append(f'i32.const 0')
        func.body.append(f'i32.ne')
        func.body.append(f'br_if {label_end}')
        
        # Get next element and bind to loop variable
        func.body.append(f'local.get {iter_local}')
        # Simplified: assume iterator has 'next' method
        func.body.append(f'call $iterator_next')
        func.locals.append((stmt.var, WasmValType.I32))
        func.body.append(f'local.set {stmt.var}')
        
        # Body
        self._compile_block(stmt.body)
        
        func.body.append(f'br {label_start}')
        func.body.append('end')
        func.body.append('end')
    
    def _is_range_loop(self, stmt: ForStmt) -> bool:
        """Check if for loop is a simple range loop: for i in start..end"""
        if not isinstance(stmt.iter_expr, BinaryExpr):
            return False
        return stmt.iter_expr.operator == '..'
    
    def _compile_vectorized_for_loop(self, stmt: ForStmt, loop_info: LoopInfo):
        """Compile a vectorized for loop using SIMD instructions."""
        func = self.state.current_function
        vt = loop_info.simd_type
        width = loop_info.vector_width
        var_name = stmt.var
        
        # Extract range bounds (simplified)
        start_expr = stmt.iter_expr.left
        end_expr = stmt.iter_expr.right
        
        # Initialize loop variable
        func.locals.append((var_name, WasmValType.I32))
        self._compile_expr(start_expr)
        func.body.append(f'local.set ${var_name}')
        
        # Compile end bound and store in local
        end_local = f"{var_name}_end"
        func.locals.append((end_local, WasmValType.I32))
        self._compile_expr(end_expr)
        func.body.append(f'local.set ${end_local}')
        
        # The accumulator variable (sum) should already be declared by the let statement
        sum_local = "sum"
        
        # Create vectorized loop
        label_start = f"$vec_loop_{self.state.label_counter}"
        label_end = f"$vec_loop_end_{self.state.label_counter}"
        self.state.label_counter += 1
        
        func.body.append(f'loop {label_start}')
        func.body.append(f'block {label_end}')
        
        # Loop condition: index < end
        func.body.append(f'local.get ${var_name}')
        func.body.append(f'local.get ${end_local}')
        func.body.append(f'i32.lt_s')
        func.body.append(f'br_if {label_end}')
        
        # Process array accesses with SIMD loads
        for array_name, index_var in loop_info.array_accesses:
            # Load vector from memory: v128.load (local.get $array_name + index * 4)
            func.body.append(f'local.get ${array_name}')
            func.body.append(f'local.get ${var_name}')
            func.body.append(f'i32.const 4')
            func.body.append(f'i32.mul')
            func.body.append(f'i32.add')
            func.body.append(f'v128.load')
            vec_local = f"{array_name}_vec"
            func.locals.append((vec_local, WasmValType.I32))  # v128 is represented as i32 in WASM text
            func.body.append(f'local.set ${vec_local}')
        
        # Process computations with SIMD ops
        # For dot product: multiply vectors, then horizontal add
        # Only process multiplication operations (the vector computation)
        result_vec_local = f"{var_name}_result_vec"
        func.locals.append((result_vec_local, WasmValType.I32))
        
        for comp in loop_info.computations:
            # Only handle multiplication for SIMD (the actual vector computation)
            if comp.operator != '*':
                continue
            simd_op = self._get_simd_op(comp, vt)
            if simd_op:
                # Get vector operands
                for array_name, _ in loop_info.array_accesses:
                    vec_local = f"{array_name}_vec"
                    func.body.append(f'local.get ${vec_local}')
                func.body.append(simd_op.op)
                func.body.append(f'local.set ${result_vec_local}')
        
        # Horizontal reduction to scalar and accumulate into sum
        if vt == SimdType.I32X4:
            func.body.append(f'local.get ${result_vec_local}')
            func.body.append('i32x4.extract_lane 0')
            func.body.append(f'local.get ${result_vec_local}')
            func.body.append('i32x4.extract_lane 1')
            func.body.append('i32.add')
            func.body.append(f'local.get ${result_vec_local}')
            func.body.append('i32x4.extract_lane 2')
            func.body.append('i32.add')
            func.body.append(f'local.get ${result_vec_local}')
            func.body.append('i32x4.extract_lane 3')
            func.body.append('i32.add')
        elif vt == SimdType.F32X4:
            func.body.append(f'local.get ${result_vec_local}')
            func.body.append('f32x4.extract_lane 0')
            func.body.append(f'local.get ${result_vec_local}')
            func.body.append('f32x4.extract_lane 1')
            func.body.append('f32.add')
            func.body.append(f'local.get ${result_vec_local}')
            func.body.append('f32x4.extract_lane 2')
            func.body.append('f32.add')
            func.body.append(f'local.get ${result_vec_local}')
            func.body.append('f32x4.extract_lane 3')
            func.body.append('f32.add')
        
        # Add to accumulator (sum)
        func.body.append(f'local.get ${sum_local}')
        func.body.append('i32.add')
        func.body.append(f'local.set ${sum_local}')
        
        # Increment loop index by vector width
        func.body.append(f'local.get ${var_name}')
        func.body.append(f'i32.const {width}')
        func.body.append(f'i32.add')
        func.body.append(f'local.set ${var_name}')
        
        func.body.append(f'br {label_start}')
        func.body.append('end')
        func.body.append('end')
    
    def _get_simd_op(self, comp: BinaryExpr, vt: SimdType) -> Optional[object]:
        """Get SIMD operation for binary expression."""
        element_type = 'i32'  # Would infer from type checker
        
        # Map parser operators to SIMD operator names
        op_map = {
            '+': 'add',
            '-': 'sub',
            '*': 'mul',
            '/': 'div',
            '%': 'rem',
        }
        simd_op_name = op_map.get(comp.operator, comp.operator)
        key = (element_type, simd_op_name)
        
        # Map from simd_vectorization.py
        SCALAR_TO_SIMD = {
            ('i32', 'add'): type('SimdOp', (), {'op': 'i32x4.add'})(),
            ('i32', 'sub'): type('SimdOp', (), {'op': 'i32x4.sub'})(),
            ('i32', 'mul'): type('SimdOp', (), {'op': 'i32x4.mul'})(),
            ('i64', 'add'): type('SimdOp', (), {'op': 'i64x2.add'})(),
            ('i64', 'sub'): type('SimdOp', (), {'op': 'i64x2.sub'})(),
            ('i64', 'mul'): type('SimdOp', (), {'op': 'i64x2.mul'})(),
            ('f32', 'add'): type('SimdOp', (), {'op': 'f32x4.add'})(),
            ('f32', 'sub'): type('SimdOp', (), {'op': 'f32x4.sub'})(),
            ('f32', 'mul'): type('SimdOp', (), {'op': 'f32x4.mul'})(),
            ('f64', 'add'): type('SimdOp', (), {'op': 'f64x2.add'})(),
            ('f64', 'sub'): type('SimdOp', (), {'op': 'f64x2.sub'})(),
            ('f64', 'mul'): type('SimdOp', (), {'op': 'f64x2.mul'})(),
        }
        return SCALAR_TO_SIMD.get(key)
    
    def _compile_return_stmt(self, stmt: ReturnStmt):
        """Compile return statement."""
        func = self.state.current_function
        if stmt.value:
            self._compile_expr(stmt.value)
        func.body.append('return')
    
    def _compile_assert_stmt(self, stmt: AssertStmt):
        """Compile assert statement."""
        func = self.state.current_function
        self._compile_expr(stmt.condition)
        # If false, trap (unreachable)
        func.body.append('if')
        func.body.append('unreachable')
        func.body.append('end')
    
    def _compile_try_stmt(self, stmt: TryStmt):
        """Compile try-catch (using WASM exception handling proposal)."""
        func = self.state.current_function
        
        # Try block
        func.body.append('try')
        self._compile_block(stmt.try_block)
        
        # Catch
        func.body.append(f'catch {stmt.catch_var}')
        self._compile_block(stmt.catch_block)
        
        func.body.append('end')
    
    def _compile_expr(self, expr) -> None:
        """Compile expression."""
        if isinstance(expr, BinaryExpr):
            self._compile_binary_expr(expr)
        elif isinstance(expr, UnaryExpr):
            self._compile_unary_expr(expr)
        elif isinstance(expr, CallExpr):
            self._compile_call_expr(expr)
        elif isinstance(expr, MatchExpr):
            self._compile_match_expr(expr)
        elif isinstance(expr, AwaitExpr):
            self._compile_await_expr(expr)
        elif isinstance(expr, LambdaExpr):
            self._compile_lambda_expr(expr)
        elif isinstance(expr, StructLit):
            self._compile_struct_lit(expr)
        elif isinstance(expr, ArrayLit):
            self._compile_array_lit(expr)
        elif isinstance(expr, Ident):
            self._compile_ident(expr)
        elif isinstance(expr, Literal):
            self._compile_literal(expr)
        elif isinstance(expr, FieldAccess):
            self._compile_field_access(expr)
        elif isinstance(expr, IndexExpr):
            self._compile_index_expr(expr)
    
    def _compile_binary_expr(self, expr: BinaryExpr):
        self._compile_expr(expr.left)
        self._compile_expr(expr.right)
        
        func = self.state.current_function
        op_map = {
            '+': 'i32.add', '-': 'i32.sub', '*': 'i32.mul', '/': 'i32.div_s',
            '%': 'i32.rem_s', '==': 'i32.eq', '!=': 'i32.ne',
            '<': 'i32.lt_s', '>': 'i32.gt_s', '<=': 'i32.le_s', '>=': 'i32.ge_s',
            '&&': 'i32.and', '||': 'i32.or',
        }
        wasm_op = op_map.get(expr.operator, 'i32.add')
        func.body.append(wasm_op)
    
    def _compile_unary_expr(self, expr: UnaryExpr):
        self._compile_expr(expr.operand)
        func = self.state.current_function
        if expr.operator == '-':
            func.body.append('i32.const 0')
            func.body.append('i32.sub')
        elif expr.operator == '!':
            func.body.append('i32.eqz')
    
    def _compile_call_expr(self, expr: CallExpr):
        for arg in expr.arguments:
            self._compile_expr(arg)
        func = self.state.current_function
        func.body.append(f'call ${expr.callee}')
    
    def _compile_match_expr(self, expr: MatchExpr):
        # Simplified: compile as if-else chain
        func = self.state.current_function
        self._compile_expr(expr.subject)
        
        for i, case in enumerate(expr.cases):
            # This is a simplified pattern match - real implementation would be more complex
            func.body.append(f'local.set $match_subject_{i}')
            func.body.append(f'if')
            # Pattern matching logic would go here
            func.body.append(f'local.get $match_subject_{i}')
            self._compile_expr(case.body)
            func.body.append('end')
    
    def _compile_await_expr(self, expr: AwaitExpr):
        self._compile_expr(expr.expression)
        func = self.state.current_function
        func.body.append('call $await')
    
    def _compile_lambda_expr(self, expr: LambdaExpr):
        # Allocate closure struct: { func_ptr, env_ptr }
        func = self.state.current_function
        # This is a placeholder - full closure compilation is complex
        func.body.append('i32.const 0')  # placeholder
    
    def _compile_struct_lit(self, expr: StructLit):
        func = self.state.current_function
        # Allocate struct in linear memory
        struct_size = sum(
            4 if ft in (WasmValType.I32, WasmValType.F32) else 8
            for _, ft in self.state.struct_layouts.get(expr.name, {}).values()
        )
        func.body.append(f'i32.const {struct_size}')
        func.body.append('call $malloc')
        
        # Initialize fields
        layout = self.state.struct_layouts.get(expr.name, {})
        for field_init in expr.fields:
            func.body.append('local.set $tmp_ptr')  # Save pointer
            self._compile_expr(field_init.value)
            offset, field_type = layout.get(field_init.name, (0, WasmValType.I32))
            func.body.append('local.get $tmp_ptr')
            func.body.append(f'i32.const {offset}')
            func.body.append('i32.add')
            if field_type == WasmValType.I32:
                func.body.append('i32.store')
            elif field_type == WasmValType.F64:
                func.body.append('f64.store')
        func.body.append('local.get $tmp_ptr')
    
    def _compile_array_lit(self, expr: ArrayLit):
        func = self.state.current_function
        # Allocate array: header (length) + elements
        elem_count = len(expr.elements)
        func.body.append(f'i32.const {4 + elem_count * 4}')  # header + elements
        func.body.append('call $malloc')
        func.body.append('local.set $tmp_ptr')
        
        # Store length
        func.body.append('local.get $tmp_ptr')
        func.body.append(f'i32.const {elem_count}')
        func.body.append('i32.store')
        
        # Store elements
        for i, elem in enumerate(expr.elements):
            func.body.append('local.get $tmp_ptr')
            func.body.append(f'i32.const {4 + i * 4}')
            func.body.append('i32.add')
            self._compile_expr(elem)
            func.body.append('i32.store')
        
        func.body.append('local.get $tmp_ptr')
    
    def _compile_ident(self, expr: Ident):
        func = self.state.current_function
        func.body.append(f'local.get ${expr.name}')
    
    def _compile_literal(self, expr: Literal):
        func = self.state.current_function
        if expr.literal_type == 'int':
            func.body.append(f'i32.const {expr.value}')
        elif expr.literal_type == 'float':
            func.body.append(f'f64.const {expr.value}')
        elif expr.literal_type == 'bool':
            func.body.append(f'i32.const {1 if expr.value else 0}')
        elif expr.literal_type == 'string':
            # Store string in data section, return pointer
            if expr.value not in self.state.string_literals:
                self.state.string_literals[expr.value] = self.state.next_string_offset
                self.state.next_string_offset += len(expr.value.encode('utf-8')) + 4
                self.state.string_data.append((expr.value, self.state.string_literals[expr.value]))
            offset = self.state.string_literals[expr.value]
            func.body.append(f'i32.const {offset}')
        elif expr.literal_type == 'null':
            func.body.append('i32.const 0')
    
    def _compile_field_access(self, expr: FieldAccess):
        self._compile_expr(expr.left)
        func = self.state.current_function
        func.body.append('local.set $tmp_ptr')
        
        # Get struct name from left expression (simplified)
        # In real implementation, would need type info
        struct_name = 'Unknown'
        if isinstance(expr.left, Ident):
            struct_name = expr.left.name
        
        layout = self.state.struct_layouts.get(struct_name, {})
        offset, field_type = layout.get(expr.right.name, (0, WasmValType.I32))
        
        func.body.append('local.get $tmp_ptr')
        func.body.append(f'i32.const {offset}')
        func.body.append('i32.add')
        if field_type == WasmValType.I32:
            func.body.append('i32.load')
        elif field_type == WasmValType.F64:
            func.body.append('f64.load')
    
    def _compile_index_expr(self, expr: IndexExpr):
        self._compile_expr(expr.left)
        self._compile_expr(expr.right)
        func = self.state.current_function
        
        # Array access: base + 4 (header) + index * 4
        func.body.append('i32.const 4')
        func.body.append('i32.add')
        func.body.append('i32.const 4')
        func.body.append('i32.mul')
        func.body.append('i32.add')
        func.body.append('i32.load')
    
    def _generate_wasm_module(self) -> str:
        """Generate WASM text format module."""
        lines = []
        
        lines.append('(module')
        
        # Memory
        lines.append(f'  (memory (export "memory") {self.state.memory_pages})')
        
        # Data section for string literals
        if self.state.string_data:
            lines.append('  (data')
            for string_val, offset in self.state.string_data:
                # Length-prefixed UTF-8
                encoded = string_val.encode('utf-8')
                length = len(encoded)
                # Write length as 4-byte little-endian
                length_bytes = length.to_bytes(4, 'little')
                data = length_bytes + encoded
                hex_data = ' '.join(f'{b:02x}' for b in data)
                lines.append(f'    (i32.const {offset})')
                lines.append(f'    "{hex_data}"')
            lines.append('  )')
        
        # Function types
        type_map = {}
        for func_name in self.state.sorted_functions:
            func = self.state.functions[func_name]
            type_sig = self._func_type_to_string(func.func_type)
            if type_sig not in type_map:
                type_map[type_sig] = len(type_map)
            lines.append(f'  (type $t{type_map[type_sig]} (func {type_sig}))')
        
        # Imports
        lines.append('  (import "env" "print" (func $print (param i32 i32)))')
        lines.append('  (import "env" "malloc" (func $malloc (param i32) (result i32)))')
        lines.append('  (import "env" "iterator_next" (func $iterator_next (param i32) (result i32)))')
        lines.append('  (import "env" "await" (func $await (param i32) (result i32)))')
        
        # GC Struct types (H25)
        for struct_name in self.state.sorted_structs:
            layout = self.state.struct_layouts.get(struct_name, {})
            if layout:
                fields = []
                for field_name, (offset, field_type) in layout.items():
                    fields.append(f"  (field {field_name} {field_type.value})")
                if fields:
                    lines.append(f"  (type ${struct_name} (struct\n{chr(10).join(fields)}\n))")
        
        # Globals
        for name, global_def in self.state.globals.items():
            lines.append(f'  (global ${name} ({global_def.val_type.value}) ({global_def.mutability.value} {global_def.init_expr}))')
        
        # Functions
        for func_name in self.state.sorted_functions:
            func = self.state.functions[func_name]
            lines.append(self._generate_wasm_function(func, type_map))
        
        # Exports
        for func_name in self.state.sorted_functions:
            func = self.state.functions[func_name]
            if func.is_export:
                export_name = func_name.replace('$', '_').replace('.', '_')
                lines.append(f'  (export "{export_name}" (func ${func_name}))')
        
        # Memory export
        lines.append('  (export "memory" (memory 0))')
        
        lines.append(')')
        return '\n'.join(lines)
    
    def _func_type_to_string(self, func_type: WasmFuncType) -> str:
        params = ' '.join(t.value for t in func_type.params)
        results = ' '.join(t.value for t in func_type.results)
        if results:
            return f'(param {params}) (result {results})'
        return f'(param {params})'
    
    def _generate_wasm_function(self, func: WasmFunction, type_map: Dict[str, int]) -> str:
        lines = []
        type_sig = self._func_type_to_string(func.func_type)
        type_idx = type_map[type_sig]
        
        lines.append(f'  (func ${func.name} (type $t{type_idx})')
        
        # Locals
        if func.locals:
            local_decls = {}
            for name, val_type in func.locals:
                if val_type not in local_decls:
                    local_decls[val_type] = []
                local_decls[val_type].append(name)
            
            for val_type, names in local_decls.items():
                lines.append(f'    (local {" ".join(f"${n}" for n in names)} {val_type.value})')
        
        # Body
        for instr in func.body:
            lines.append(f'    {instr}')
        
        lines.append('  )')
        return '\n'.join(lines)


# ============================================================================
# HIGH-LEVEL API
# ============================================================================

def compile_to_wasm(ast: Program, deterministic: bool = True) -> str:
    """Compile SVL AST to WASM text format."""
    compiler = WasmCompiler(deterministic=deterministic)
    return compiler.compile(ast)


def compile_file_to_wasm(source: str, deterministic: bool = True) -> str:
    """Compile SVL source file to WASM."""
    from svl.lexer import tokenize
    from svl.parser_rd import parse
    tokens = tokenize(source)
    ast = parse(tokens)
    return compile_to_wasm(ast, deterministic)


def verify_wasm_determinism(source: str, runs: int = 3) -> bool:
    """Verify that compilation produces bit-identical output."""
    outputs = []
    for _ in range(runs):
        wasm = compile_file_to_wasm(source, deterministic=True)
        outputs.append(wasm)
    
    first = outputs[0]
    return all(out == first for out in outputs)


def wasm_sha256(wasm_text: str) -> str:
    """Compute SHA256 of WASM output."""
    return hashlib.sha256(wasm_text.encode('utf-8')).hexdigest()


if __name__ == '__main__':
    # Test compiler
    test_source = '''
    module main {
      func main() type void {
        let x: int = 42
        let y: int = 58
        let z: int = x + y
        assert z == 100
        return
      }
    }
    '''
    
    print("=== WASM Compiler Test ===")
    wasm_output = compile_file_to_wasm(test_source)
    print(wasm_output[:2000])
    print("...")
    print(f"\nFull output length: {len(wasm_output)} chars")
    print(f"SHA256: {wasm_sha256(wasm_output)}")
    
    # Test determinism
    print("\n--- Determinism Test ---")
    if verify_wasm_determinism(test_source):
        print("✓ Deterministic compilation verified")
    else:
        print("✗ Non-deterministic output!")
    
    # Test with golden reference
    from svl.golden_refs import get_golden_ref
    ref = get_golden_ref('psalm119_aleph')
    wasm_ref = compile_file_to_wasm(ref.source)
    print(f"\nPsalm 119 Aleph WASM SHA256: {wasm_sha256(wasm_ref)}")
    
    print("\n✓ WASM Compiler test complete!")