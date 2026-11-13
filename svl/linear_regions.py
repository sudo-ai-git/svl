# svl/linear_regions.py
# Linear Type Inference with Regions (H15)
# Region-based linear type inference similar to Rust's borrow checker

from typing import Dict, List, Optional, Set, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
from svl.parser_rd import (
    TypeExpr, NodeType, FuncDecl, Param, Block,
    LetStmt, ReturnStmt, IfStmt, WhileStmt, ForStmt,
    AssignExpr, ExprStmt, Ident, CallExpr,
)
from svl.lexer import Token, TokenType, tokenize


class RegionKind(Enum):
    """Kind of region."""
    STATIC = "static"      # Global/static region
    STACK = "stack"        # Function-scoped region
    HEAP = "heap"          # Dynamically allocated region
    UNIQUE = "unique"      # Unique ownership region


@dataclass
class Region:
    """A memory region with lifetime."""
    name: str
    kind: RegionKind
    parent: Optional['Region'] = None
    children: List['Region'] = field(default_factory=list)
    variables: Set[str] = field(default_factory=set)
    is_linear: bool = False  # Whether this region enforces linear usage
    
    def add_child(self, child: 'Region'):
        child.parent = self
        self.children.append(child)
        
    def contains_var(self, var: str) -> bool:
        return var in self.variables


@dataclass
class LinearVariable:
    """A variable with linear type and region."""
    name: str
    type: str  # Type expression
    region: Region
    is_moved: bool = False
    is_borrowed: bool = False
    borrow_count: int = 0
    mutable_borrow: bool = False
    # Whether THIS variable carries the linear/unique discipline.  The region is
    # marked linear if any variable in it is, so `region.is_linear` alone cannot
    # answer "is this variable linear?" — every variable in a linear region would
    # otherwise be reported as an unconsumed linear value.
    is_linear: bool = False
    # 'linear' | 'unique' | None.  `linear` must be consumed exactly once;
    # `unique` is affine, so an unconsumed one is not a warning.
    kind: Optional[str] = None


class RegionInferenceEngine:
    """Infers regions and checks linear type usage."""
    
    def __init__(self):
        self.global_region = Region("global", RegionKind.STATIC)
        self.current_region: Region = self.global_region
        self.regions: Dict[str, Region] = {"global": self.global_region}
        self.variables: Dict[str, LinearVariable] = {}
        self.errors: List[str] = []
        self.warnings: List[str] = []
        
    def enter_function(self, func_name: str) -> Region:
        """Create a new stack region for a function."""
        region = Region(f"fn_{func_name}", RegionKind.STACK, parent=self.current_region)
        self.current_region.add_child(region)
        self.regions[region.name] = region
        old_region = self.current_region
        self.current_region = region
        return old_region
        
    def exit_function(self, old_region: Region):
        """Exit function, check for unused linear variables."""
        self._check_unused_linear(self.current_region)
        self.current_region = old_region
        
    def declare_variable(self, name: str, type_expr: str, is_linear: bool = False,
                         kind: Optional[str] = None) -> LinearVariable:
        """Declare a new variable in current region."""
        var = LinearVariable(
            name=name,
            type=type_expr,
            region=self.current_region,
            is_moved=False,
            is_linear=is_linear,
            kind=kind,
        )
        self.variables[name] = var
        self.current_region.variables.add(name)
        
        if is_linear:
            self.current_region.is_linear = True
            
        return var
        
    def move_variable(self, name: str) -> bool:
        """Move a linear variable (consumes it)."""
        if name not in self.variables:
            self.errors.append(f"Variable '{name}' not declared")
            return False
            
        var = self.variables[name]
        if var.is_moved:
            self.errors.append(f"Variable '{name}' already moved")
            return False
            
        if var.is_borrowed:
            self.errors.append(f"Variable '{name}' is borrowed, cannot move")
            return False
            
        var.is_moved = True
        return True
        
    def borrow_variable(self, name: str, mutable: bool = False) -> bool:
        """Borrow a variable (immutable or mutable borrow)."""
        if name not in self.variables:
            self.errors.append(f"Variable '{name}' not declared")
            return False
            
        var = self.variables[name]
        if var.is_moved:
            self.errors.append(f"Variable '{name}' already moved, cannot borrow")
            return False
            
        if mutable:
            if var.borrow_count > 0:
                self.errors.append(f"Variable '{name}' already borrowed, cannot mutably borrow")
                return False
            var.mutable_borrow = True
        else:
            if var.mutable_borrow:
                self.errors.append(f"Variable '{name}' mutably borrowed, cannot immutably borrow")
                return False
                
        var.borrow_count += 1
        var.is_borrowed = True
        return True
        # NOTE: an earlier version of this method had a second, unreachable copy of
        # the mutable/immutable borrow block after `return True`, and two of its
        # branches appended to a non-existent key (`self.errors[...] = ...` on a
        # list).  Dead code that could never run, but which looked like a second
        # implementation — removed.
        
    def return_borrow(self, name: str) -> bool:
        """Return a borrowed variable."""
        if name not in self.variables:
            return False
            
        var = self.variables[name]
        if not var.is_borrowed:
            return False
            
        var.borrow_count -= 1
        if var.borrow_count == 0:
            var.is_borrowed = False
            var.mutable_borrow = False
        return True
        
    def _check_unused_linear(self, region: Region):
        """Warn about linear variables in `region` that were never consumed.

        This used to compute the answer and then `pass  # Could warn here`, so an
        unconsumed linear value was silently accepted — the annotation asserted a
        discipline nothing enforced.  It now records a warning.
        """
        for var_name in region.variables:
            var = self.variables.get(var_name)
            if var is None:
                continue
            # Only the VARIABLE's own annotation matters: the region is marked
            # linear if any member is, so testing `region.is_linear` here reported
            # every unannotated local as an unconsumed linear value.
            if not var.is_linear:
                continue
            # `unique` is affine — an unconsumed one is not a defect.
            if var.kind == 'unique':
                continue
            if var.region == region and not var.is_moved and not var.is_borrowed:
                self.warnings.append(
                    f"linear variable '{var_name}' is never consumed "
                    f"(a linear value must be used exactly once)")
                    
        # Recurse into children
        for child in region.children:
            self._check_unused_linear(child)
            
    def get_stats(self) -> Dict[str, Any]:
        """Get inference statistics."""
        total_vars = len(self.variables)
        linear_vars = sum(1 for v in self.variables.values() if v.is_linear)
        moved = sum(1 for v in self.variables.values() if v.is_moved)
        borrowed = sum(1 for v in self.variables.values() if v.is_borrowed)
        
        return {
            'total_variables': total_vars,
            'linear_variables': linear_vars,
            'moved_variables': moved,
            'borrowed_variables': borrowed,
            'errors': len(self.errors),
            'warnings': len(self.warnings),
            'regions': len(self.regions)
        }


def infer_regions_for_function(func: FuncDecl) -> Dict[str, Any]:
    """Run region inference on a function.

    Kept for compatibility with the original H15 entry point; the enforcement that
    runs on the compile path is `check_linear_usage`, which walks the whole body.
    """
    errors, warnings = check_function(func)
    return {'errors': errors, 'warnings': warnings}


def run_linear_region_analysis(source: str) -> Dict[str, Any]:
    """Run linear region analysis on SVL source."""
    from svl.parser_rd import parse
    from svl.lexer import tokenize

    ast = parse(tokenize(source))
    errors, warnings = check_linear_usage(ast)
    return {'errors': errors, 'warnings': warnings}


# ---------------------------------------------------------------------------
# AST enforcement
# ---------------------------------------------------------------------------
#
# SVL has value semantics — values are i32/f64 in WASM and there is no runtime
# ownership.  `linear`/`unique` are therefore a STATIC discipline over variable
# usage, the same shape as Rust's move checker:
#
#   * a **move** is a bare variable used where ownership transfers — the whole RHS
#     of a `let`/assignment, an argument, or a `return` value;
#   * a **use** is a variable appearing inside a larger expression (`x + 1`,
#     `f(x + 1)`), which borrows it.
#
# Rules enforced:
#   * a moved linear/unique variable may not be used or moved again;
#   * a linear variable that is never consumed is a WARNING (a false positive here
#     would reject a correct program, which is worse than the defect).
#
# `unique` and `linear` share the move rules in this implementation; the difference
# is that an unconsumed `linear` warns and an unconsumed `unique` does not (affine).

LINEAR_KINDS = ('linear', 'unique')


def _annotation_kind(ann: Any) -> Optional[str]:
    """'linear' / 'unique' for a linear/unique annotation, else None.

    Replaces the old `'linear' in str(param.type_ann).lower()` hack, which matched
    any annotation whose string form happened to contain the substring.
    """
    if getattr(ann, 'kind', None) in LINEAR_KINDS:
        return ann.kind
    return None


def _iter_funcs(node, acc=None):
    if acc is None:
        acc = []
    if node is None:
        return acc
    if isinstance(node, FuncDecl):
        acc.append(node)
    if isinstance(node, (list, tuple)):
        for item in node:
            _iter_funcs(item, acc)
    elif hasattr(node, '__dataclass_fields__'):
        for f in node.__dataclass_fields__:
            if f in ('line', 'column', 'offset', 'type'):
                continue
            _iter_funcs(getattr(node, f, None), acc)
    return acc


class _FunctionChecker:
    """Enforce the linear/unique discipline over one function body."""

    def __init__(self, func: FuncDecl):
        self.func = func
        self.engine = RegionInferenceEngine()
        self.state: Dict[str, Dict[str, Any]] = {}   # name -> {'kind','moved'}
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def run(self):
        old = self.engine.enter_function(self.func.name)
        for p in self.func.params:
            kind = _annotation_kind(p.type_ann) if p.type_ann is not None else None
            self.engine.declare_variable(
                p.name,
                str(p.type_ann) if p.type_ann is not None else 'unknown',
                is_linear=(kind is not None),
                kind=kind,
            )
            if kind:
                self.state[p.name] = {'kind': kind, 'moved': False}

        self._block(self.func.body)

        self.engine.exit_function(old)
        # Drop the unused-linear warnings for `unique` (affine): only `linear` must be
        # consumed.
        for w in self.engine.warnings:
            self.warnings.append(w)
        return self.errors, self.warnings

    # -- statements ---------------------------------------------------------

    def _block(self, block) -> None:
        for stmt in getattr(block, 'statements', []) or []:
            self._stmt(stmt)

    def _stmt(self, stmt) -> None:
        from svl.parser_rd import LetStmt, ReturnStmt, IfStmt, WhileStmt, ForStmt

        if isinstance(stmt, LetStmt):
            self._let(stmt)
        elif isinstance(stmt, ReturnStmt):
            if stmt.value is not None:
                self._move_or_use(stmt.value)
        elif isinstance(stmt, IfStmt):
            self._expr(stmt.condition)
            self._block(stmt.then_branch)
            if stmt.else_branch is not None:
                self._block(stmt.else_branch)
        elif isinstance(stmt, WhileStmt):
            self._expr(stmt.condition)
            self._block(stmt.body)
        elif isinstance(stmt, ForStmt):
            self._block(stmt.body)
        elif isinstance(stmt, ExprStmt):
            self._expr(stmt.expression)
        elif isinstance(stmt, AssignExpr):
            self._assign(stmt)
        elif hasattr(stmt, 'expression'):
            self._expr(stmt.expression)

    def _let(self, stmt) -> None:
        from svl.parser_rd import Ident

        kind = _annotation_kind(stmt.type_ann) if stmt.type_ann is not None else None
        moved_from = None
        if isinstance(stmt.value, Ident) and stmt.value.name in self.state:
            moved_from = stmt.value.name
            self._move(stmt.value.name, getattr(stmt, 'line', '?'))
        else:
            self._expr(stmt.value)

        if kind:
            self.engine.declare_variable(
                stmt.name, str(stmt.type_ann),
                is_linear=True, kind=kind)
            self.state[stmt.name] = {'kind': kind, 'moved': False}
        elif moved_from is not None:
            # Ownership transfers: the destination becomes the linear owner.
            inherited = self.state[moved_from]['kind']
            self.engine.declare_variable(
                stmt.name, 'inherited', is_linear=True, kind=inherited)
            self.state[stmt.name] = {'kind': inherited, 'moved': False}

    def _assign(self, stmt) -> None:
        from svl.parser_rd import Ident

        if isinstance(stmt.target, Ident):
            name = stmt.target.name
            if isinstance(stmt.value, Ident) and stmt.value.name in self.state:
                self._move(stmt.value.name, getattr(stmt, 'line', '?'))
            else:
                self._expr(stmt.value)
            # Assigning to an already-moved linear variable is a use after move.
            st = self.state.get(name)
            if st is not None and st['moved'] and stmt.operator != '=':
                self.errors.append(
                    f"line {getattr(stmt, 'line', '?')}: '{name}' is used after being "
                    f"moved (linear/unique values may be moved at most once)")
            return
        self._expr(stmt.value)

    # -- expressions --------------------------------------------------------

    def _move_or_use(self, expr) -> None:
        from svl.parser_rd import Ident

        if isinstance(expr, Ident) and expr.name in self.state:
            self._move(expr.name, getattr(expr, 'line', '?'))
        else:
            self._expr(expr)

    def _move(self, name: str, line) -> None:
        st = self.state.get(name)
        if st is None:
            return
        if st['moved']:
            self.errors.append(
                f"line {line}: '{name}' is moved a second time "
                f"(linear/unique values may be moved at most once)")
            return
        st['moved'] = True
        self.engine.move_variable(name)

    def _use(self, name: str, line) -> None:
        st = self.state.get(name)
        if st is None:
            return
        if st['moved']:
            self.errors.append(
                f"line {line}: '{name}' is used after being moved "
                f"(linear/unique values may be moved at most once)")
            return
        # A use is a borrow that ends immediately in a value-semantics language.
        self.engine.borrow_variable(name)
        self.engine.return_borrow(name)

    def _expr(self, expr) -> None:
        from svl.parser_rd import CallExpr, Ident

        if expr is None:
            return
        if isinstance(expr, Ident):
            self._use(expr.name, getattr(expr, 'line', '?'))
            return
        if isinstance(expr, CallExpr):
            for arg in expr.arguments:
                self._move_or_use(arg)
            return
        if isinstance(expr, (list, tuple)):
            for item in expr:
                self._expr(item)
            return
        if hasattr(expr, '__dataclass_fields__'):
            for f in expr.__dataclass_fields__:
                if f in ('line', 'column', 'offset', 'type'):
                    continue
                self._expr(getattr(expr, f, None))


def check_function(func: FuncDecl):
    """Check one function; returns (errors, warnings)."""
    checker = _FunctionChecker(func)
    return checker.run()


def check_linear_usage(ast) -> Tuple[List[str], List[str]]:
    """Entry point for the compile gate.

    Returns ``(errors, warnings)``.  Errors are HARD violations — a moved value
    used or moved again.  Unconsumed `linear` variables are warnings, not errors:
    a false positive would reject a correct program, which is worse than the defect.
    """
    errors: List[str] = []
    warnings: List[str] = []
    for func in _iter_funcs(ast):
        fn_errors, fn_warnings = check_function(func)
        errors.extend(fn_errors)
        warnings.extend(fn_warnings)
    return errors, warnings


if __name__ == '__main__':
    print("=== Linear Region Inference Test ===")
    
    engine = RegionInferenceEngine()
    
    # Test basic region operations
    old = engine.enter_function("test")
    var = engine.declare_variable("x", "int", is_linear=True)
    print(f"Declared: {var.name}, linear: {engine.current_region.is_linear}")
    
    # Move variable
    engine.move_variable("x")
    print(f"Moved x: {engine.variables['x'].is_moved}")
    
    # Borrow variable
    engine.declare_variable("y", "int", is_linear=True)
    engine.borrow_variable("y", mutable=False)
    print(f"Borrowed y: {engine.variables['y'].is_borrowed}")
    engine.return_borrow("y")
    print(f"Returned y: {engine.variables['y'].is_borrowed}")
    
    engine.exit_function(old)
    
    stats = engine.get_stats()
    print(f"Stats: {stats}")
    print(f"Errors: {engine.errors}")
    
    print("\n✓ Linear Region Inference test complete!")