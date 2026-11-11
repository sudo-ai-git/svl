# svl/escape_analysis.py
# Escape Analysis for Stack Allocation (H28)
# Determines which objects can be allocated on stack vs heap

from typing import Dict, List, Optional, Set, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum

from svl.parser_rd import (
    Program, Module, FuncDecl, Block, LetStmt, VarDecl, StructLit, ArrayLit,
    CallExpr, ReturnStmt, Ident, BinaryExpr, IndexExpr, FieldAccess, LambdaExpr,
    StructDecl, IfStmt, WhileStmt, ForStmt, TryStmt, ExprStmt, NodeType
)


class EscapeState(Enum):
    """Escape state of a variable/allocation."""
    NO_ESCAPE = "no_escape"      # Can be stack allocated
    ARG_ESCAPE = "arg_escape"    # Escapes as function argument
    RETURN_ESCAPE = "return_escape"  # Escapes via return
    GLOBAL_ESCAPE = "global_escape"  # Escapes to global/heap
    UNKNOWN = "unknown"          # Conservative: heap allocate


@dataclass
class AllocationSite:
    """Represents an allocation site in the program."""
    node: Any  # AST node (StructLit, ArrayLit, LambdaExpr)
    func_name: str
    var_name: Optional[str]  # Variable it's assigned to
    escape_state: EscapeState = EscapeState.UNKNOWN
    escaped_to: List[str] = field(default_factory=list)  # Functions it escapes to


@dataclass
class FunctionEscapeInfo:
    """Escape analysis results for a function."""
    func_name: str
    allocations: List[AllocationSite]
    param_escape: Dict[str, EscapeState]  # Parameter -> escape state
    return_escape: EscapeState
    global_vars: Set[str] = field(default_factory=set)


class EscapeAnalyzer:
    """Escape analysis pass for SVL compiler."""

    def __init__(self):
        self.function_infos: Dict[str, FunctionEscapeInfo] = {}
        self.call_graph: Dict[str, Set[str]] = {}  # caller -> callees
        self.global_allocations: Dict[str, AllocationSite] = {}

    def analyze_program(self, program: Program) -> Dict[str, FunctionEscapeInfo]:
        """Run escape analysis on entire program."""
        # Phase 1: Build call graph
        self._build_call_graph(program)

        # Phase 2: Analyze each function
        for module in program.modules:
            for item in module.body.statements:
                if isinstance(item, FuncDecl):
                    self._analyze_function(item)

        # Phase 3: Propagate escapes through call graph
        self._propagate_escapes()

        return self.function_infos

    def _build_call_graph(self, program: Program):
        """Build call graph from program."""
        for module in program.modules:
            for item in module.body.statements:
                if isinstance(item, FuncDecl):
                    self.call_graph[item.name] = set()
                    self._collect_calls(item.body, item.name)

    def _collect_calls(self, block: Block, caller: str):
        """Collect function calls in block."""
        for stmt in block.statements:
            if isinstance(stmt, CallExpr):
                self.call_graph[caller].add(stmt.callee)
            elif isinstance(stmt, LetStmt):
                self._collect_calls_in_expr(stmt.value, caller)
            elif isinstance(stmt, (IfStmt, WhileStmt, ForStmt, TryStmt)):
                self._collect_calls_in_stmt(stmt, caller)
            elif isinstance(stmt, Block):
                self._collect_calls(stmt, caller)

    def _collect_calls_in_stmt(self, stmt: Any, caller: str):
        """Collect calls in a statement."""
        if isinstance(stmt, IfStmt):
            self._collect_calls(stmt.then_branch, caller)
            if stmt.else_branch:
                self._collect_calls(stmt.else_branch, caller)
            self._collect_calls_in_expr(stmt.condition, caller)
        elif isinstance(stmt, WhileStmt):
            self._collect_calls(stmt.body, caller)
            self._collect_calls_in_expr(stmt.condition, caller)
        elif isinstance(stmt, ForStmt):
            self._collect_calls(stmt.body, caller)
            self._collect_calls_in_expr(stmt.iter_expr, caller)
        elif isinstance(stmt, TryStmt):
            self._collect_calls(stmt.try_block, caller)
            self._collect_calls(stmt.catch_block, caller)

    def _collect_calls_in_expr(self, expr: Any, caller: str):
        """Collect calls in an expression."""
        if isinstance(expr, CallExpr):
            self.call_graph[caller].add(expr.callee)
        elif isinstance(expr, BinaryExpr):
            self._collect_calls_in_expr(expr.left, caller)
            self._collect_calls_in_expr(expr.right, caller)
        elif isinstance(expr, (IndexExpr, FieldAccess)):
            self._collect_calls_in_expr(expr.left, caller)
            self._collect_calls_in_expr(expr.right, caller)

    def _analyze_function(self, func: FuncDecl):
        """Analyze escape behavior of a function."""
        allocations: List[AllocationSite] = []
        param_escape: Dict[str, EscapeState] = {}
        return_escape = EscapeState.NO_ESCAPE

        # Initialize parameter escape states
        for param in func.params:
            param_escape[param.name] = EscapeState.NO_ESCAPE

        # Analyze function body
        self._analyze_block(func.body, func.name, allocations, param_escape)

        # Determine return escape
        return_escape = self._analyze_return_escape(func.body)

        # Create function info
        self.function_infos[func.name] = FunctionEscapeInfo(
            func_name=func.name,
            allocations=allocations,
            param_escape=param_escape,
            return_escape=return_escape
        )

    def _analyze_block(self, block: Block, func_name: str,
                       allocations: List[AllocationSite],
                       param_escape: Dict[str, EscapeState]):
        """Analyze a block for allocations and escapes."""
        for stmt in block.statements:
            self._analyze_stmt(stmt, func_name, allocations, param_escape)

    def _analyze_stmt(self, stmt: Any, func_name: str,
                      allocations: List[AllocationSite],
                      param_escape: Dict[str, EscapeState]):
        """Analyze a statement."""
        if isinstance(stmt, LetStmt):
            # Check if RHS is an allocation
            alloc = self._check_allocation(stmt.value, func_name, stmt.name)
            if alloc:
                allocations.append(alloc)
            else:
                # Check for escape through assignment
                self._check_escape_in_expr(stmt.value, func_name, param_escape)

        elif isinstance(stmt, VarDecl):
            alloc = self._check_allocation(stmt.value, func_name, stmt.name)
            if alloc:
                allocations.append(alloc)
            else:
                self._check_escape_in_expr(stmt.value, func_name, param_escape)

        elif isinstance(stmt, ReturnStmt):
            if stmt.value:
                self._check_escape_in_expr(stmt.value, func_name, param_escape)

        elif isinstance(stmt, CallExpr):
            # Arguments may escape
            for arg in stmt.arguments:
                self._check_escape_in_expr(arg, func_name, param_escape)

        elif isinstance(stmt, IfStmt):
            self._check_escape_in_expr(stmt.condition, func_name, param_escape)
            self._analyze_block(stmt.then_branch, func_name, allocations, param_escape)
            if stmt.else_branch:
                self._analyze_block(stmt.else_branch, func_name, allocations, param_escape)

        elif isinstance(stmt, WhileStmt):
            self._check_escape_in_expr(stmt.condition, func_name, param_escape)
            self._analyze_block(stmt.body, func_name, allocations, param_escape)

        elif isinstance(stmt, ForStmt):
            self._check_escape_in_expr(stmt.iter_expr, func_name, param_escape)
            self._analyze_block(stmt.body, func_name, allocations, param_escape)

        elif isinstance(stmt, Block):
            self._analyze_block(stmt, func_name, allocations, param_escape)

    def _check_allocation(self, expr: Any, func_name: str, var_name: Optional[str]) -> Optional[AllocationSite]:
        """Check if expression is an allocation site."""
        if isinstance(expr, (StructLit, ArrayLit, LambdaExpr)):
            return AllocationSite(
                node=expr,
                func_name=func_name,
                var_name=var_name,
                escape_state=EscapeState.NO_ESCAPE
            )
        return None

    def _check_escape_in_expr(self, expr: Any, func_name: str,
                              param_escape: Dict[str, EscapeState]):
        """Check if expression causes variables to escape."""
        if isinstance(expr, Ident):
            # Variable use - check if it's a parameter or local that might escape
            if expr.name in param_escape:
                # Used in context that might escape (argument, return, etc.)
                pass

        elif isinstance(expr, CallExpr):
            # Arguments escape to callee
            for arg in expr.arguments:
                self._mark_escaping(arg, func_name, param_escape, EscapeState.ARG_ESCAPE)

        elif isinstance(expr, ReturnStmt):
            # Return value escapes
            if expr.value:
                self._mark_escaping(expr.value, func_name, param_escape, EscapeState.RETURN_ESCAPE)

        elif isinstance(expr, BinaryExpr):
            self._check_escape_in_expr(expr.left, func_name, param_escape)
            self._check_escape_in_expr(expr.right, func_name, param_escape)

        elif isinstance(expr, (IndexExpr, FieldAccess)):
            self._check_escape_in_expr(expr.left, func_name, param_escape)
            self._check_escape_in_expr(expr.right, func_name, param_escape)

    def _mark_escaping(self, expr: Any, func_name: str,
                       param_escape: Dict[str, EscapeState],
                       escape_state: EscapeState):
        """Mark variables as escaping."""
        if isinstance(expr, Ident) and expr.name in param_escape:
            current = param_escape[expr.name]
            if self._escape_order(current) < self._escape_order(escape_state):
                param_escape[expr.name] = escape_state

    def _escape_order(self, state: EscapeState) -> int:
        """Order of escape states (higher = more escape)."""
        order = {
            EscapeState.NO_ESCAPE: 0,
            EscapeState.ARG_ESCAPE: 1,
            EscapeState.RETURN_ESCAPE: 2,
            EscapeState.GLOBAL_ESCAPE: 3,
            EscapeState.UNKNOWN: 4,
        }
        return order.get(state, 0)

    def _analyze_return_escape(self, block: Block) -> EscapeState:
        """Analyze if function returns allocated objects."""
        for stmt in block.statements:
            if isinstance(stmt, ReturnStmt) and stmt.value:
                if isinstance(stmt.value, (StructLit, ArrayLit, LambdaExpr)):
                    return EscapeState.RETURN_ESCAPE
                if isinstance(stmt.value, Ident):
                    # Could be returning a local allocation
                    return EscapeState.RETURN_ESCAPE
        return EscapeState.NO_ESCAPE

    def _propagate_escapes(self):
        """Propagate escape information through call graph."""
        changed = True
        while changed:
            changed = False
            for caller, callees in self.call_graph.items():
                if caller not in self.function_infos:
                    continue
                caller_info = self.function_infos[caller]

                for callee_name in callees:
                    if callee_name not in self.function_infos:
                        continue
                    callee_info = self.function_infos[callee_name]

                    # Propagate: if callee's param escapes, caller's arg escapes
                    # This is simplified - full implementation would track which arg maps to which param
                    for param, escape_state in callee_info.param_escape.items():
                        if self._escape_order(escape_state) >= self._escape_order(EscapeState.ARG_ESCAPE):
                            # Arguments passed to this callee escape
                            for alloc in caller_info.allocations:
                                if alloc.escape_state == EscapeState.NO_ESCAPE:
                                    alloc.escape_state = EscapeState.ARG_ESCAPE
                                    alloc.escaped_to.append(callee_name)
                                    changed = True

    def get_stack_allocatable(self, func_name: str) -> List[AllocationSite]:
        """Get allocations that can be stack allocated."""
        if func_name not in self.function_infos:
            return []
        return [
            alloc for alloc in self.function_infos[func_name].allocations
            if alloc.escape_state == EscapeState.NO_ESCAPE
        ]

    def get_heap_allocatable(self, func_name: str) -> List[AllocationSite]:
        """Get allocations that must be heap allocated."""
        if func_name not in self.function_infos:
            return []
        return [
            alloc for alloc in self.function_infos[func_name].allocations
            if alloc.escape_state != EscapeState.NO_ESCAPE
        ]


def run_escape_analysis(program: Program) -> Dict[str, FunctionEscapeInfo]:
    """Run escape analysis on program."""
    analyzer = EscapeAnalyzer()
    return analyzer.analyze_program(program)


def can_stack_allocate(program: Program, func_name: str, var_name: str) -> bool:
    """Check if a variable can be stack allocated."""
    analyzer = EscapeAnalyzer()
    infos = analyzer.analyze_program(program)
    if func_name not in infos:
        return False
    for alloc in infos[func_name].allocations:
        if alloc.var_name == var_name and alloc.escape_state == EscapeState.NO_ESCAPE:
            return True
    return False


if __name__ == '__main__':
    print("=== Escape Analysis Test ===")

    from svl.lexer import tokenize
    from svl.parser_rd import parse

    test_source = '''
    module test {
      func helper(x: int) type int { return x + 1 }

      func no_escape() type int {
        let p: Point = Point { x: 1, y: 2 }
        return p.x + p.y
      }

      func escapes_arg() type int {
        let p: Point = Point { x: 1, y: 2 }
        return helper(p.x)
      }

      func escapes_return() type Point {
        let p: Point = Point { x: 1, y: 2 }
        return p
      }

      func main() type void { return }
    }
    '''

    tokens = tokenize(test_source)
    ast = parse(tokens)

    analyzer = EscapeAnalyzer()
    infos = analyzer.analyze_program(ast)

    for func_name, info in infos.items():
        print(f"\nFunction: {func_name}")
        print(f"  Return escape: {info.return_escape}")
        print(f"  Param escapes: {info.param_escape}")
        print(f"  Allocations:")
        for alloc in info.allocations:
            print(f"    {alloc.var_name}: {alloc.escape_state} (escaped to: {alloc.escaped_to})")

        stack_allocs = analyzer.get_stack_allocatable(func_name)
        heap_allocs = analyzer.get_heap_allocatable(func_name)
        print(f"  Stack allocatable: {len(stack_allocs)}")
        print(f"  Heap allocatable: {len(heap_allocs)}")

    print("\n✓ Escape Analysis test complete!")