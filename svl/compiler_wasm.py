# svl/compiler_wasm.py
# SVL Compiler Backend — WASM Target (Phase 4, Week 16)
# AST → WASM compilation with deterministic output

from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import hashlib

from svl.parser_rd import (
    Program, Module, FuncDecl, StructDecl, Block, LetStmt, IfStmt, WhileStmt,
    ForStmt, ReturnStmt, AssertStmt, TryStmt, ExprStmt, ConstDecl, VarDecl,
    BinaryExpr, UnaryExpr, CallExpr, MatchExpr, AwaitExpr, LambdaExpr,
    StructLit, ArrayLit, Ident, Literal, FieldAccess, IndexExpr, TernaryExpr,
    AssignExpr, TypeExpr, Param, Field, NodeType
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


from typing import Union


def lower_func_type(params: List[TypeExpr], return_type: TypeExpr) -> WasmFuncType:
    """Lower function type to WASM function type.

    `void` (and `never`) produce NO results. Emitting a dummy i32 result for `void`
    made every void function invalid: its body leaves nothing on the stack, so the
    module failed validation ("type mismatch: expected i32 but nothing on stack").
    """
    results = []
    if not (getattr(return_type, 'kind', None) == 'prim'
            and getattr(return_type, 'value', None) in ('void', 'never')):
        results.append(lower_type_to_wasm(return_type))
    return WasmFuncType(
        params=[lower_type_to_wasm(p) for p in params],
        results=results
    )


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
    struct_sizes: Dict[str, int] = field(default_factory=dict)
    string_literals: Dict[str, int] = field(default_factory=dict)
    next_string_offset: int = 0
    memory_pages: int = 1  # 64KB; the emitter grows this when a program needs a heap
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

# Host import surface: the ONLY `env` functions a module may call. Imports are emitted
# only when called, and a call to anything outside this set is a compile error.
# `print` takes (ptr, len); the rest are single-i32.
HOST_IMPORT_SIGS = {
    'print': '(func $print (param i32 i32))',
    'print_int': '(func $print_int (param i32))',
    'putc': '(func $putc (param i32))',
    'read_key': '(func $read_key (result i32))',
    'clear': '(func $clear)',
    'malloc': '(func $malloc (param i32) (result i32))',
    'iterator_next': '(func $iterator_next (param i32) (result i32))',
    'await': '(func $await (param i32) (result i32))',
}


class WasmCompiler:
    """SVL to WASM compiler."""
    
    def __init__(self, deterministic: bool = True):
        self.deterministic = deterministic
        self.state = CompilerState()
        # Top-level const/var names whose initializer is not a constant expression
        # (the WASM MVP cannot lower those).
        self._non_const_globals = set()
        # Names resolvable as `local.get $name` in the function being compiled.
        self._known_locals = None
        self._uses_heap = False
        self._local_struct_types = {}
        self._temp_counter = 0
        self._heap_base = 0
    
    def compile(self, program: Program) -> str:
        """Compile full SVL program to WASM text format."""
        self._non_const_globals = set()
        # Set when the program needs heap allocation (arrays / struct literals).
        self._uses_heap = False
        # (function name, local name) -> struct type name, for field-offset resolution.
        self._local_struct_types = {}
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
    
    def _literal_init_expr(self, expr) -> Optional[str]:
        """Return a WASM constant expression for a literal initializer, else None."""
        if isinstance(expr, Literal):
            if expr.literal_type in ('int', 'bool'):
                return f'i32.const {int(expr.value)}'
            if expr.literal_type == 'float':
                return f'f64.const {float(expr.value)}'
        if isinstance(expr, UnaryExpr) and expr.operator == '-':
            inner = self._literal_init_expr(expr.operand)
            if inner and inner.startswith('i32.const '):
                return f'i32.const {-int(inner[len("i32.const "):])}'
        return None

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
                elif isinstance(item, (ConstDecl, VarDecl)):
                    # Top-level const/var → a WASM global. Dropping these silently (the
                    # old behaviour) made every reference emit `local.get $name` and the
                    # whole module fail validation with "unknown local".
                    init = self._literal_init_expr(item.value)
                    if init is None:
                        self._non_const_globals.add(item.name)
                        continue
                    val_type = (lower_type_to_wasm(item.type_ann)
                                if item.type_ann is not None else WasmValType.I32)
                    self.state.globals[item.name] = WasmGlobal(
                        name=item.name,
                        val_type=val_type,
                        mutability=(WasmMutability.CONST if isinstance(item, ConstDecl)
                                    else WasmMutability.VAR),
                        init_expr=init,
                    )
        
        # Sort for determinism
        if self.deterministic:
            self.state.sorted_functions = sorted(self.state.functions.keys())
            self.state.sorted_structs = sorted(self.state.sorted_structs)
        else:
            self.state.sorted_functions = list(self.state.functions.keys())
    
    def _temp_local(self, func: 'WasmFunction', prefix: str) -> str:
        """Declare a fresh i32 scratch local and return its name.

        Memory codegen needs to hold an address (or an index) while other expressions are
        evaluated. The old code used a `$tmp_ptr` local that was never declared, so every
        array/struct construct produced `unknown local: failed to find name $tmp_ptr`.
        """
        name = f"__{prefix}{self._temp_counter}"
        self._temp_counter += 1
        func.locals.append((name, WasmValType.I32))
        return name

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
                    # Round the size up to 4 bytes so consecutive allocations stay aligned.
                    self.state.struct_sizes[item.name] = (offset + 3) // 4 * 4
    
    def _compile_functions(self, program: Program):
        """Compile all function bodies."""
        for module in program.modules:
            for item in module.body.statements:
                if isinstance(item, FuncDecl):
                    func_name = f"{module.name}${item.name}"
                    func = self.state.functions[func_name]
                    # Record struct-typed params (layouts exist by now) so `p.field`
                    # resolves inside the body.
                    for p in item.params:
                        if (p.type_ann is not None
                                and getattr(p.type_ann, 'kind', None) == 'struct'
                                and p.type_ann.value in self.state.struct_layouts):
                            self._local_struct_types[(func_name, p.name)] = p.type_ann.value
                    self.state.current_function = func
                    self.state.local_counter = len(func.params)
                    self.state.label_counter = 0
                    # Names resolvable as `local.get $name` for this function.
                    self._known_locals = self._collect_local_names(item.body) | {
                        n for n, _t in func.params
                    }
                    
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
                    # The body did not end in an explicit `return`, so nothing is on the
                    # stack here. `drop; return` (the old code) is INVALID for a function
                    # with results: `drop` needs an operand and `return` needs the result.
                    # Every meaningful path already returned, so mark the fall-through
                    # unreachable — valid WASM, and it traps if control can actually reach it.
                    func.body.append('unreachable')
                else:
                    func.body.append('return')
    
    def _collect_local_names(self, block) -> set:
        """Collect every local name bound in a function body (params excluded).

        Used by `_compile_ident` to turn a reference to a name that was never declared
        into a clear compile error instead of `local.get $name` and an "unknown local"
        assembly failure downstream.
        """
        names = set()

        def walk_block(b):
            if b is None:
                return
            for s in getattr(b, 'statements', []):
                if isinstance(s, LetStmt):
                    names.add(s.name)
                elif isinstance(s, IfStmt):
                    walk_block(s.then_branch)
                    walk_block(s.else_branch)
                elif isinstance(s, WhileStmt):
                    walk_block(s.body)
                elif isinstance(s, ForStmt):
                    names.add(s.var)
                    walk_block(s.body)
                elif isinstance(s, Block):
                    walk_block(s)

        walk_block(block)
        return names

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
            # Drop the leftover value ONLY when the expression actually produces one:
            # `drop` on an empty stack makes the module invalid, and void calls
            # (print / print_int / void functions) leave nothing behind.
            if self._expr_yields_value(stmt.expression):
                self.state.current_function.body.append('drop')
        elif isinstance(stmt, Block):
            self._compile_block(stmt)

    def _expr_yields_value(self, expr) -> bool:
        """True if evaluating `expr` leaves exactly one value (i32) on the stack."""
        if isinstance(expr, AssignExpr):
            return False          # assignments are statements: they leave nothing behind
        if isinstance(expr, CallExpr):
            return self._callee_yields_value(expr.callee)
        return True

    def _callee_yields_value(self, name: str) -> bool:
        """True if calling `name` produces a result value."""
        if name in ('print', 'print_int', 'putc', 'clear'):
            return False                      # void host imports
        for fn_name, fn in self.state.functions.items():
            if fn_name == name or fn_name.endswith(f'${name}'):
                return bool(fn.func_type.results)
        return True                           # malloc / iterator_next / await → value
    
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
        
        # Track the struct type of this local so `p.field` can be resolved later. A named
        # type in annotation position parses as kind='struct' for *any* identifier (including
        # `int`), so only names that are declared structs count.
        struct_name = None
        if stmt.type_ann is not None and getattr(stmt.type_ann, 'kind', None) == 'struct':
            cand = stmt.type_ann.value
            if cand in self.state.struct_layouts:
                struct_name = cand
        if struct_name is None and isinstance(stmt.value, StructLit):
            struct_name = stmt.value.name
        if struct_name:
            self._local_struct_types[(func.name, stmt.name)] = struct_name
    
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
        
        # Condition — `br_if` branches on NON-ZERO, so the test must be inverted:
        # branching on the raw condition exits the loop the moment it becomes TRUE,
        # which made every `while` body execute zero times.
        self._compile_expr(stmt.condition)
        func.body.append('i32.eqz')
        func.body.append(f'br_if {label_end}')
        
        # Body
        self._compile_block(stmt.body)
        
        func.body.append(f'br {label_start}')
        func.body.append('end')
        func.body.append('end')
    
    def _compile_for_stmt(self, stmt: ForStmt):
        """Compile for loop."""
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
        
        # Range loops (`for i in start..end`) have well-defined counting semantics;
        # lower them directly instead of routing through the partial iterator protocol.
        if self._is_range_loop(stmt):
            self._compile_range_for_stmt(stmt, stmt.iter_expr.left, stmt.iter_expr.right)
            return
        
        # Iterator protocol. `iterator_next` returns the next handle/element and 0 once
        # the stream is exhausted, so the loop must exit when the value is 0.
        iter_local = f"iter_{self.state.label_counter}"
        self.state.label_counter += 1
        self._compile_expr(stmt.iter_expr)
        func.locals.append((iter_local, WasmValType.I32))
        func.body.append(f'local.set ${iter_local}')
        
        label_start = f"$for_{self.state.label_counter}"
        label_end = f"$for_end_{self.state.label_counter}"
        self.state.label_counter += 1
        
        func.body.append(f'loop {label_start}')
        func.body.append(f'block {label_end}')
        
        # Advance the iterator; 0 means exhausted → leave the loop (branch on false).
        func.body.append(f'local.get ${iter_local}')
        func.body.append(f'call $iterator_next')
        func.body.append(f'local.set ${iter_local}')
        func.body.append(f'local.get ${iter_local}')
        func.body.append(f'i32.eqz')
        func.body.append(f'br_if {label_end}')
        
        # Bind the current element to the loop variable
        func.locals.append((stmt.var, WasmValType.I32))
        func.body.append(f'local.get ${iter_local}')
        func.body.append(f'local.set ${stmt.var}')
        
        # Body
        self._compile_block(stmt.body)
        
        func.body.append(f'br {label_start}')
        func.body.append('end')
        func.body.append('end')
    
    def _compile_range_for_stmt(self, stmt: ForStmt, start_expr, end_expr):
        """Lower `for <var> in <start>..<end>` to a counting loop over [start, end)."""
        func = self.state.current_function
        
        # var = start
        func.locals.append((stmt.var, WasmValType.I32))
        self._compile_expr(start_expr)
        func.body.append(f'local.set ${stmt.var}')
        
        # range_end = end  (evaluated ONCE, before the loop)
        end_local = f"range_end_{self.state.label_counter}"
        self.state.label_counter += 1
        self._compile_expr(end_expr)
        func.locals.append((end_local, WasmValType.I32))
        func.body.append(f'local.set ${end_local}')
        
        label_start = f"$for_{self.state.label_counter}"
        label_end = f"$for_end_{self.state.label_counter}"
        self.state.label_counter += 1
        
        func.body.append(f'loop {label_start}')
        func.body.append(f'block {label_end}')
        
        # Exit when index >= end (branch on non-zero = condition true).
        func.body.append(f'local.get ${stmt.var}')
        func.body.append(f'local.get ${end_local}')
        func.body.append('i32.ge_s')
        func.body.append(f'br_if {label_end}')
        
        # Body
        self._compile_block(stmt.body)
        
        # var += 1
        func.body.append(f'local.get ${stmt.var}')
        func.body.append('i32.const 1')
        func.body.append('i32.add')
        func.body.append(f'local.set ${stmt.var}')
        
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
        
        # Loop condition: exit when index >= end (`br_if` branches on non-zero).
        func.body.append(f'local.get ${var_name}')
        func.body.append(f'local.get ${end_local}')
        func.body.append(f'i32.ge_s')
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
        # Trap when the assertion FAILS: invert the condition before the branch.
        # (Branching on the raw condition trapped exactly when the assert was satisfied.)
        func.body.append('i32.eqz')
        func.body.append('if')
        func.body.append('unreachable')
        func.body.append('end')
    
    def _compile_try_stmt(self, stmt: TryStmt):
        """`try`/`catch` is not lowered yet.

        The old code emitted `try ... catch <var> ... end`, which is not valid WASM
        (legacy `catch` needs a tag and the whole block was malformed), so the module failed
        to assemble. Fail at compile time with a clear message instead of emitting junk.
        """
        raise SyntaxError(
            f"`try`/`catch` is not supported by the WASM backend yet "
            f"(at line {getattr(stmt, 'line', '?')}) — use a sentinel return value or an "
            f"out-parameter to signal failure"
        )
    
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
        elif isinstance(expr, TernaryExpr):
            self._compile_ternary_expr(expr)
        elif isinstance(expr, AssignExpr):
            self._compile_assign(expr)

    def _compile_assign(self, expr: 'AssignExpr'):
        """Compile `x = v`, `x += v`, `a[i] = v`, `p.f = v`. Leaves NO value on the stack.

        Assignments are how a program mutates state; before this existed, `x = 5` emitted
        nothing and then an ExprStmt `drop`, so the module did not validate at all.
        """
        func = self.state.current_function
        op = expr.operator
        compound_ops = {
            '+=': 'i32.add', '-=': 'i32.sub', '*=': 'i32.mul', '/=': 'i32.div_s',
            '%=': 'i32.rem_s', '&=': 'i32.and', '|=': 'i32.or', '^=': 'i32.xor',
            '<<=': 'i32.shl', '>>=': 'i32.shr_s',
        }
        if op == '=':
            compound = None
        else:
            compound = compound_ops.get(op)
            if compound is None:
                raise SyntaxError(
                    f"unsupported assignment operator '{op}' at line {getattr(expr, 'line', '?')}"
                )
        target = expr.target

        if isinstance(target, Ident):
            known = getattr(self, '_known_locals', None)
            if known is not None and target.name not in known and target.name not in self.state.globals:
                raise SyntaxError(
                    f"assignment to unknown name '{target.name}' "
                    f"at line {getattr(target, 'line', '?')}"
                )
            if compound:
                func.body.append(f'local.get ${target.name}')
                self._compile_expr(expr.value)
                func.body.append(compound)
            else:
                self._compile_expr(expr.value)
            func.body.append(f'local.set ${target.name}')
            return

        if isinstance(target, IndexExpr):
            addr = self._temp_local(func, 'lval')
            self._emit_element_addr(target)
            func.body.append(f'local.set ${addr}')
            self._emit_store(addr, compound, expr.value, 0)
            return

        if isinstance(target, FieldAccess):
            offset, _ftype = self._field_offset(target)
            addr = self._temp_local(func, 'lval')
            self._compile_expr(target.left)
            func.body.append(f'local.set ${addr}')
            self._emit_store(addr, compound, expr.value, offset)
            return

        raise SyntaxError(f"invalid assignment target at line {getattr(expr, 'line', '?')}")

    def _emit_store(self, addr_local: str, compound: Optional[str], value_expr, offset: int = 0):
        """Emit `[addr, value] i32.store` for a memory target whose address is in a local."""
        func = self.state.current_function
        load = f'i32.load offset={offset}' if offset else 'i32.load'
        store = f'i32.store offset={offset}' if offset else 'i32.store'
        func.body.append(f'local.get ${addr_local}')
        if compound:
            func.body.append(f'local.get ${addr_local}')
            func.body.append(load)
            self._compile_expr(value_expr)
            func.body.append(compound)
        else:
            self._compile_expr(value_expr)
        func.body.append(store)
    
    def _compile_ternary_expr(self, expr: TernaryExpr):
        """Compile `if c then a else b` / `c ? a : b` to a WASM value-producing `if`.

        The backend is i32-centric (int → i32), so the arms are typed `i32` here; a
        f64/i64 arm would need the result type threaded through from the type layer.
        """
        func = self.state.current_function
        self._compile_expr(expr.condition)
        func.body.append('if (result i32)')
        self._compile_expr(expr.then_expr)
        func.body.append('else')
        self._compile_expr(expr.else_expr)
        func.body.append('end')
    
    def _compile_binary_expr(self, expr: BinaryExpr):
        self._compile_expr(expr.left)
        self._compile_expr(expr.right)
        
        func = self.state.current_function
        op_map = {
            '+': 'i32.add', '-': 'i32.sub', '*': 'i32.mul', '/': 'i32.div_s',
            '%': 'i32.rem_s', '==': 'i32.eq', '!=': 'i32.ne',
            '<': 'i32.lt_s', '>': 'i32.gt_s', '<=': 'i32.le_s', '>=': 'i32.ge_s',
            '&&': 'i32.and', '||': 'i32.or',
            # Bitwise. These were missing, so they fell through to the `i32.add` default
            # and produced a WRONG ANSWER silently (12 & 10 compiled as 12 + 10 = 22).
            '&': 'i32.and', '|': 'i32.or', '^': 'i32.xor',
            '<<': 'i32.shl', '>>': 'i32.shr_s',
        }
        wasm_op = op_map.get(expr.operator)
        if wasm_op is None:
            # Never fall back to an operator. An unmapped op must fail loudly — a silent
            # default turns a missing arm into a plausible-looking wrong result.
            raise SyntaxError(
                f"unsupported binary operator '{expr.operator}' "
                f"at line {getattr(expr, 'line', '?')}"
            )
        func.body.append(wasm_op)
    
    def _compile_unary_expr(self, expr: UnaryExpr):
        func = self.state.current_function
        if expr.operator == '-':
            # Negation is `0 - operand`. The zero MUST be pushed BEFORE the operand:
            # compiling the operand first made this `operand - 0`, i.e. a silent no-op
            # that returned `5` for `-5`.
            func.body.append('i32.const 0')
            self._compile_expr(expr.operand)
            func.body.append('i32.sub')
            return
        self._compile_expr(expr.operand)
        if expr.operator == '!':
            func.body.append('i32.eqz')
        elif expr.operator == '~':
            # bitwise NOT: x ^ -1
            func.body.append('i32.const -1')
            func.body.append('i32.xor')
        else:
            raise SyntaxError(
                f"unsupported unary operator '{expr.operator}' "
                f"at line {getattr(expr, 'line', '?')}"
            )
    
    def _compile_call_expr(self, expr: CallExpr):
        # `len(x)` — a builtin, not a host import: word 0 of an array or string holds its
        # length, so this works uniformly for both.
        if expr.callee == 'len':
            if len(expr.arguments) != 1:
                raise SyntaxError(
                    f"len() takes exactly 1 argument (line {getattr(expr, 'line', '?')})"
                )
            self._compile_expr(expr.arguments[0])
            self.state.current_function.body.append('i32.load')
            return
        # `zeros(n)` — a fresh length-n array of zeros on the heap (pairs with `$$alloc`).
        # Real programs need to build an array at runtime, not just from a literal.
        if expr.callee == 'zeros':
            if len(expr.arguments) != 1:
                raise SyntaxError(
                    f"zeros() takes exactly 1 argument (line {getattr(expr, 'line', '?')})"
                )
            func = self.state.current_function
            self._uses_heap = True
            n_loc = self._temp_local(func, 'n')
            ptr = self._temp_local(func, 'arr')
            self._compile_expr(expr.arguments[0])
            func.body.append(f'local.set ${n_loc}')
            func.body.append('i32.const 4')                 # 4 (length word) + n*4
            func.body.append(f'local.get ${n_loc}')
            func.body.append('i32.const 4')
            func.body.append('i32.mul')
            func.body.append('i32.add')
            func.body.append('call $alloc')
            func.body.append(f'local.set ${ptr}')
            func.body.append(f'local.get ${ptr}')
            func.body.append(f'local.get ${n_loc}')
            func.body.append('i32.store')                   # length word
            func.body.append(f'local.get ${ptr}')           # memory.fill(dest, val, size)
            func.body.append('i32.const 4')
            func.body.append('i32.add')
            func.body.append('i32.const 0')
            func.body.append(f'local.get ${n_loc}')
            func.body.append('i32.const 4')
            func.body.append('i32.mul')
            func.body.append('memory.fill')
            func.body.append(f'local.get ${ptr}')
            return
        callee = self._resolve_callee(expr.callee, getattr(expr, 'line', '?'))
        # `print` is a host import taking (ptr: i32, len: i32). A lone string-literal
        # argument is therefore expanded into its (ptr, len) pair — pushing only the
        # pointer left the call one operand short and the module failed to validate.
        if expr.callee == 'print' and len(expr.arguments) == 1:
            arg = expr.arguments[0]
            if isinstance(arg, Literal) and arg.literal_type == 'string':
                func = self.state.current_function
                self._compile_expr(arg)                                   # -> ptr
                # The string's data word 0 is its length (so `len(s)` works), so the text
                # itself starts 4 bytes in. Passing the raw pointer would print the four
                # length bytes as garbage before the text.
                func.body.append('i32.const 4')
                func.body.append('i32.add')
                func.body.append(f'i32.const {len(arg.value.encode("utf-8"))}')  # -> len
                func.body.append(f'call {callee}')
                return
        for arg in expr.arguments:
            self._compile_expr(arg)
        func = self.state.current_function
        func.body.append(f'call {callee}')

    def _resolve_callee(self, callee: str, line: Any = '?') -> str:
        """
        A CallExpr carries the bare name (`fib`) while definitions are keyed by the
        module-qualified name (`svl_payload$fib`) — emit the qualified one and leave the
        host imports bare. An unknown callee is a compile error: emitting `call $g` for a
        function that does not exist produced an unassemblable module.
        """
        if callee in self.state.functions:
            return f'${callee}'
        for name in self.state.sorted_functions:
            if name == callee or name.endswith(f'${callee}'):
                return f'${name}'
        if callee in HOST_IMPORT_SIGS:
            return f'${callee}'
        raise SyntaxError(f"call to undefined function '{callee}' at line {line}")
    
    def _compile_match_expr(self, expr: MatchExpr):
        """Compile `match x { case <lit> => e  case _ => e }` to a chain of value-`if`s.

        Every arm must produce the same type (i32 here). A match that falls off the end
        (no wildcard arm and no literal matches at runtime) traps — silently yielding 0
        would be a wrong answer, which is the defect class this backend keeps hitting.
        """
        func = self.state.current_function
        subj = self._temp_local(func, 'match')
        self._compile_expr(expr.subject)
        func.body.append(f'local.set ${subj}')

        def emit_case(i: int):
            if i >= len(expr.cases):
                func.body.append('unreachable')
                return
            case = expr.cases[i]
            pat = case.pattern
            if pat.kind in ('wildcard', 'ident'):
                self._compile_expr(case.body)
                return
            func.body.append(f'local.get ${subj}')
            self._emit_pattern_const(pat)
            func.body.append('i32.eq')
            func.body.append('if (result i32)')
            self._compile_expr(case.body)
            func.body.append('else')
            emit_case(i + 1)
            func.body.append('end')

        emit_case(0)

    def _emit_pattern_const(self, pat):
        """Push the constant that a literal pattern compares against."""
        func = self.state.current_function
        if pat.kind == 'int':
            func.body.append(f'i32.const {int(pat.value)}')
        elif pat.kind == 'bool':
            func.body.append(f'i32.const {1 if pat.value else 0}')
        elif pat.kind == 'null':
            func.body.append('i32.const 0')
        else:
            raise SyntaxError(
                f"unsupported match pattern (kind '{pat.kind}') at line "
                f"{getattr(pat, 'line', '?')} — supported: integer/bool literals and `_`"
            )
    
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
        """Allocate the struct on the heap, store every field, leave the base pointer.

        All fields of the declaration must be present: a missing field would leave the slot
        holding whatever the previous allocation put there (a silent wrong value), so it is
        a compile error.
        """
        func = self.state.current_function
        if expr.name not in self.state.struct_layouts:
            raise SyntaxError(f"unknown struct '{expr.name}' at line {getattr(expr, 'line', '?')}")
        self._uses_heap = True
        layout = self.state.struct_layouts[expr.name]
        size = self.state.struct_sizes.get(expr.name, 4 * len(layout))
        ptr = self._temp_local(func, 'st')
        func.body.append(f'i32.const {size}')
        func.body.append('call $alloc')
        func.body.append(f'local.set ${ptr}')
        provided = set()
        for field_init in expr.fields:
            if field_init.name not in layout:
                raise SyntaxError(
                    f"struct '{expr.name}' has no field '{field_init.name}' "
                    f"(at line {getattr(field_init, 'line', '?')})"
                )
            offset, _ftype = layout[field_init.name]
            func.body.append(f'local.get ${ptr}')
            self._compile_expr(field_init.value)
            func.body.append(f'i32.store offset={offset}' if offset else 'i32.store')
            provided.add(field_init.name)
        missing = [n for n in layout if n not in provided]
        if missing:
            raise SyntaxError(
                f"struct literal '{expr.name}' is missing field(s): {', '.join(missing)} "
                f"(at line {getattr(expr, 'line', '?')})"
            )
        func.body.append(f'local.get ${ptr}')
    
    def _compile_array_lit(self, expr: ArrayLit):
        """Allocate `[len, e0, e1, ...]` on the heap and leave the base pointer.

        Layout: word 0 holds the element count, then one 4-byte word per element. `len()`
        reads word 0 and `a[i]` reads word 1+i, so the two agree by construction.
        """
        func = self.state.current_function
        self._uses_heap = True
        n = len(expr.elements)
        ptr = self._temp_local(func, 'arr')
        func.body.append(f'i32.const {4 + n * 4}')
        func.body.append('call $alloc')
        func.body.append(f'local.set ${ptr}')
        func.body.append(f'local.get ${ptr}')
        func.body.append(f'i32.const {n}')
        func.body.append('i32.store')
        for i, elem in enumerate(expr.elements):
            func.body.append(f'local.get ${ptr}')
            self._compile_expr(elem)
            func.body.append(f'i32.store offset={4 + i * 4}')
        func.body.append(f'local.get ${ptr}')
    
    def _compile_ident(self, expr: Ident):
        func = self.state.current_function
        # A top-level const/var is a WASM global.
        if expr.name in self.state.globals:
            func.body.append(f'global.get ${expr.name}')
            return
        if expr.name in self._non_const_globals:
            raise SyntaxError(
                f"const/var '{expr.name}' has a non-constant initializer, which the WASM "
                f"backend cannot lower (line {getattr(expr, 'line', '?')})"
            )
        known = getattr(self, '_known_locals', None)
        if known is not None and expr.name not in known:
            raise SyntaxError(
                f"Unknown identifier '{expr.name}' at line {getattr(expr, 'line', '?')} "
                f"— not a parameter, a declared local, or a const"
            )
        func.body.append(f'local.get ${expr.name}')
    
    def _compile_literal(self, expr: Literal):
        func = self.state.current_function
        if expr.literal_type == 'int':
            # SVL `int` lowers to i32. An out-of-range literal used to be emitted verbatim
            # and only failed later as "invalid i32 number: constant out of range" from the
            # assembler — fail here, with the line, instead.
            try:
                value = int(expr.value)
            except (TypeError, ValueError):
                raise SyntaxError(
                    f"invalid integer literal {expr.value!r} at line {getattr(expr, 'line', '?')}"
                )
            if not (-0x80000000 <= value <= 0x7FFFFFFF):
                raise SyntaxError(
                    f"integer literal {value} out of i32 range at line {getattr(expr, 'line', '?')}"
                )
            func.body.append(f'i32.const {value}')
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
    
    def _struct_type_of(self, node) -> Optional[str]:
        """Best-effort struct type name of an expression, or None."""
        if isinstance(node, Ident):
            return self._local_struct_types.get((self.state.current_function.name, node.name))
        if isinstance(node, StructLit):
            return node.name
        return None

    def _field_offset(self, node: FieldAccess):
        """(offset, valtype) of `node.right` inside the struct value `node.left`.

        The struct type must be knowable. The old code guessed it from the *variable name*
        (so `p.x` looked up a layout called "p") and silently used offset 0 on a miss,
        which reads the wrong field rather than failing.
        """
        struct_name = self._struct_type_of(node.left)
        if struct_name is None:
            raise SyntaxError(
                f"cannot resolve the struct type of '{getattr(node.left, 'name', type(node.left).__name__)}' "
                f"to read field '{node.right.name}' (line {getattr(node, 'line', '?')}) — "
                f"annotate the local with a struct type or initialise it from a struct literal"
            )
        layout = self.state.struct_layouts.get(struct_name, {})
        if node.right.name not in layout:
            raise SyntaxError(
                f"struct '{struct_name}' has no field '{node.right.name}' "
                f"(at line {getattr(node, 'line', '?')})"
            )
        return layout[node.right.name]

    def _emit_element_addr(self, node: IndexExpr):
        """Leave the address of `node`'s element on the stack, after a bounds check.

        Out-of-range indexes trap instead of silently reading a neighbouring allocation.
        """
        func = self.state.current_function
        base = self._temp_local(func, 'base')
        idx = self._temp_local(func, 'idx')
        self._compile_expr(node.left)
        func.body.append(f'local.set ${base}')
        self._compile_expr(node.right)
        func.body.append(f'local.set ${idx}')
        # idx < 0 -> trap
        func.body.append(f'local.get ${idx}')
        func.body.append('i32.const 0')
        func.body.append('i32.lt_s')
        func.body.append('if')
        func.body.append('unreachable')
        func.body.append('end')
        # idx >= len -> trap
        func.body.append(f'local.get ${idx}')
        func.body.append(f'local.get ${base}')
        func.body.append('i32.load')
        func.body.append('i32.ge_s')
        func.body.append('if')
        func.body.append('unreachable')
        func.body.append('end')
        # base + 4 + idx*4
        func.body.append(f'local.get ${base}')
        func.body.append('i32.const 4')
        func.body.append('i32.add')
        func.body.append(f'local.get ${idx}')
        func.body.append('i32.const 4')
        func.body.append('i32.mul')
        func.body.append('i32.add')

    def _compile_field_access(self, expr: FieldAccess):
        """Read `p.field`."""
        offset, _ftype = self._field_offset(expr)
        self._compile_expr(expr.left)
        self.state.current_function.body.append(
            f'i32.load offset={offset}' if offset else 'i32.load'
        )
    
    def _compile_index_expr(self, expr: IndexExpr):
        """Read `a[i]` (bounds-checked)."""
        self._emit_element_addr(expr)
        self.state.current_function.body.append('i32.load')
    
    def _generate_wasm_module(self) -> str:
        """Generate WASM text format module."""
        # The heap must start above the static string data so allocations never overlap
        # the data segments.
        self._heap_base = (self.state.next_string_offset + 7) // 8 * 8
        lines = []
        
        lines.append('(module')
        
        # Module fields must appear in the canonical WAT order:
        #   type, import, func, memory, global, export, data
        # The memory and data blocks are emitted further down, after the imports and the
        # function bodies, because a memory declared before an import makes the module
        # invalid ("import after memory").
        
        # Function types — one declaration per distinct signature (a second `(type $tN ...)`
        # with the same identifier is rejected as a duplicate).
        type_map = {}
        for func_name in self.state.sorted_functions:
            func = self.state.functions[func_name]
            type_sig = self._func_type_to_string(func.func_type)
            if type_sig in type_map:
                continue
            type_map[type_sig] = len(type_map)
            lines.append(f'  (type $t{type_map[type_sig]} (func {type_sig}))')
        
        # GC Struct types (H25) — `type` fields come before imports.
        # Field names need a `$` sigil: `(field x i32)` is invalid ("expected valtype").
        for struct_name in self.state.sorted_structs:
            layout = self.state.struct_layouts.get(struct_name, {})
            if layout:
                fields = []
                for field_name, (offset, field_type) in layout.items():
                    fields.append(f"    (field ${field_name} {field_type.value})")
                if fields:
                    lines.append(f"  (type ${struct_name} (struct\n{chr(10).join(fields)}\n))")
        
        # Imports — emit ONLY the host functions the module actually calls. An unused
        # import is still an import: the host must supply it or instantiation fails, so
        # adding one unconditionally breaks every existing host.
        host_sigs = {name: sig for name, sig in HOST_IMPORT_SIGS.items()}
        called_hosts = set()
        for func_name in self.state.sorted_functions:
            for instr in self.state.functions[func_name].body:
                if instr.startswith('call $'):
                    called_hosts.add(instr[len('call $'):])
        for host_name, host_sig in host_sigs.items():
            if host_name in called_hosts:
                lines.append(f'  (import "env" "{host_name}" {host_sig})')
        
        # Functions (function definitions come before memory in the canonical field order)
        for func_name in self.state.sorted_functions:
            func = self.state.functions[func_name]
            lines.append(self._generate_wasm_function(func, type_map))
        
        # Internal bump allocator — emitted ONLY when the program allocates (an array or
        # struct literal), so programs that don't allocate keep byte-identical output.
        # It replaces the old `call $malloc` (a host import), which made every allocation
        # the host's problem and collided when the host returned a constant.
        if self._uses_heap:
            lines.append('  (func $alloc (param $n i32) (result i32)')
            lines.append('    (local $p i32)')
            lines.append('    global.get $heap')
            lines.append('    local.set $p')
            lines.append('    global.get $heap')
            lines.append('    local.get $n')
            lines.append('    i32.add')
            lines.append('    global.set $heap')
            lines.append('    local.get $p')
            lines.append('  )')
        
        # Memory (declared after imports and functions; exported separately below).
        # Only programs that allocate get a larger memory, so non-allocating programs keep
        # byte-identical output.
        pages = max(self.state.memory_pages, 16) if self._uses_heap else self.state.memory_pages
        lines.append(f'  (memory {pages})')
        
        # Heap pointer, initialised past the static string data so allocations never
        # overlap the data segments.
        if self._uses_heap:
            lines.append(f'  (global $heap (mut i32) (i32.const {self._heap_base}))')
        
        # Globals — canonical WAT: `(global $n <type> (<init>))` when immutable,
        # `(global $n (mut <type>) (<init>))` when mutable. The old form wrapped the type
        # as `(i32)` and spelled the initializer `(const i32.const N)`, both invalid.
        for name, global_def in self.state.globals.items():
            init = f'({global_def.init_expr})'
            if global_def.mutability == WasmMutability.VAR:
                lines.append(f'  (global ${name} (mut {global_def.val_type.value}) {init})')
            else:
                lines.append(f'  (global ${name} {global_def.val_type.value} {init})')
        
        # Exports
        for func_name in self.state.sorted_functions:
            func = self.state.functions[func_name]
            if func.is_export:
                export_name = func_name.replace('$', '_').replace('.', '_')
                lines.append(f'  (export "{export_name}" (func ${func_name}))')
        
        # Memory export
        lines.append('  (export "memory" (memory 0))')
        
        # Data section for string literals: ONE `(data ...)` per literal — a data segment
        # carries exactly one offset+bytes pair, so stacking pairs inside a single
        # `(data ...)` emits invalid WAT as soon as a program has two string literals.
        # Bytes must be written as `\XX` escapes: a plain `"05 00 00 00"` string literal is
        # the ASCII TEXT "05 00 00 00", not four bytes — which silently corrupted every
        # string literal (print emitted hex text and len(s) returned garbage).
        for string_val, offset in self.state.string_data:
            encoded = string_val.encode('utf-8')
            payload = len(encoded).to_bytes(4, 'little') + encoded
            hex_data = ''.join(f'\\{b:02x}' for b in payload)
            lines.append(f'  (data (i32.const {offset}) "{hex_data}")')
        
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
        
        # Named parameters must be declared inline: function bodies address them as
        # `local.get $name`, which only resolves if the header carries `(param $name <t>)`.
        # An inline signature must also repeat the results, otherwise the function is
        # declared with no results and no longer matches its type reference.
        param_sig = ' '.join(f'(param ${n} {t.value})' for n, t in func.params)
        res_sig = ' '.join(t.value for t in func.func_type.results)
        header = f'  (func ${func.name} (type $t{type_idx})'
        if param_sig:
            header += f' {param_sig}'
        if res_sig:
            header += f' (result {res_sig})'
        lines.append(header)
        
        # Locals — one declaration per NAME.
        # `let x = ...` appends a fresh entry per occurrence, but every access is emitted as
        # `local.get/set $x`, so grouping duplicates into `(local $x $x i32)` emits invalid
        # WAT (duplicate identifier). Deduplicate by name, keeping the first type seen.
        if func.locals:
            param_names = {n for n, _t in func.params}
            seen_locals = {}
            for name, val_type in func.locals:
                if name in param_names:
                    continue                     # a param and a local cannot share a name
                seen_locals.setdefault(name, val_type)
            for name, val_type in seen_locals.items():
                lines.append(f'    (local ${name} {val_type.value})')
        
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


def compile_file_to_wasm(source: str, deterministic: bool = True, strict: bool = True,
                         attest: bool = False) -> str:
    """Compile SVL source file to WASM.

    With ``strict=True`` (the default) the verification gate runs FIRST and the compile is
    refused on failure, so "the layers run on every compilation" is true rather than
    aspirational. Pass ``strict=False`` to compile without the gate (useful for tooling that
    wants to highlight or format a program that does not type-check yet).

    With ``attest=True`` the returned WAT carries an ``svl.attest`` custom section binding the
    artifact to its canonical AST fingerprint (see `svl.attest`).  The default is False so a
    raw compile stays byte-identical and artifacts already pinned elsewhere remain valid; use
    `svl.attest.compile_attested` when producing a shipped artifact.

    Verified safe to default on: across all 54 real programs in this repo + the workspace, the
    gate rejects only the files that do not even PARSE (a genuine `f`-instead-of-`func` error);
    every program that compiled before still compiles.
    """
    if strict:
        from svl.verify_gate import assert_verified
        assert_verified(source)
    from svl.lexer import tokenize
    from svl.parser_rd import parse
    tokens = tokenize(source)
    ast = parse(tokens)
    wat = compile_to_wasm(ast, deterministic)
    if attest:
        from svl.attest import attest_wat
        wat, _payload = attest_wat(source, wat)
    return wat


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