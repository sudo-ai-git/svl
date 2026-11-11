# svl/ast_guard.py
# AST Guard: Forbids builtin `sum()` on iterables (Neumaier summation required)
# Part of Week 7 deliverables

from typing import Any, List, Set
from svl.parser_rd import (
    ASTNode, NodeType,
    CallExpr, Ident, BinaryExpr, LetStmt, FuncDecl,
    Block, ReturnStmt, ConstDecl, VarDecl, IfStmt,
    WhileStmt, ForStmt, AssertStmt, TryStmt, ExprStmt,
    StructLit, ArrayLit, MatchExpr, AwaitExpr, LambdaExpr,
    CaseClause, Pattern, FieldPattern, FieldInit,
    Param, Field, TypeExpr, FuncTypeDetail,
)


class ASTGuardViolation(Exception):
    """Raised when AST contains forbidden patterns."""
    def __init__(self, message: str, node: ASTNode):
        self.message = message
        self.node = node
        super().__init__(f"{message} at line {node.line}, col {node.column}")


class ASTGuard:
    """AST visitor that checks for forbidden patterns."""
    
    FORBIDDEN_FUNCTIONS = {
        'sum',  # Must use neumaier_sum instead
    }
    
    FORBIDDEN_METHODS = {
        'sum',  # list.sum() etc.
    }
    
    def __init__(self):
        self.violations: List[ASTGuardViolation] = []
    
    def check(self, node: ASTNode) -> List[ASTGuardViolation]:
        """Check AST for violations. Returns list of violations."""
        self.violations = []
        self._visit(node)
        return self.violations
    
    def _visit(self, node: ASTNode):
        """Recursively visit AST nodes."""
        if node is None:
            return
        
        # Check for forbidden function calls
        if isinstance(node, CallExpr):
            # callee can be a string (function name) or an Ident node
            callee_name = None
            if isinstance(node.callee, str):
                callee_name = node.callee
            elif isinstance(node.callee, Ident):
                callee_name = node.callee.name
            
            if callee_name in self.FORBIDDEN_FUNCTIONS:
                self.violations.append(ASTGuardViolation(
                    f"Forbidden function '{callee_name}()' - use neumaier_sum() instead",
                    node
                ))
            # Check for method calls like list.sum()
            elif isinstance(node.callee, BinaryExpr) and node.callee.operator == '.':
                if isinstance(node.callee.right, Ident):
                    if node.callee.right.name in self.FORBIDDEN_METHODS:
                        self.violations.append(ASTGuardViolation(
                            f"Forbidden method '.{node.callee.right.name}()' - use neumaier_sum() instead",
                            node
                        ))
        
        # Check for builtin sum in other contexts (list comprehensions, etc.)
        # This is a simplified check - in practice would need more sophisticated analysis
        
        # Recursively visit children
        if hasattr(node, '__dataclass_fields__'):
            for f in node.__dataclass_fields__:
                value = getattr(node, f)
                if isinstance(value, ASTNode):
                    self._visit(value)
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, ASTNode):
                            self._visit(item)
    
    def assert_clean(self, node: ASTNode):
        """Assert that AST has no violations, raising if found."""
        violations = self.check(node)
        if violations:
            raise violations[0]


def neumaier_sum(iterable) -> float:
    """
    Neumaier compensated summation - more accurate than Kahan for arbitrary sequences.
    
    Unlike builtin sum() which can lose precision with large/small values mixed,
    Neumaier summation maintains high accuracy by tracking compensation.
    
    Algorithm:
        sum = 0.0
        c = 0.0
        for x in iterable:
            t = sum + x
            if abs(sum) >= abs(x):
                c += (sum - t) + x
            else:
                c += (x - t) + sum
            sum = t
        return sum + c
    """
    s = 0.0
    c = 0.0
    for x in iterable:
        t = s + x
        if abs(s) >= abs(x):
            c += (s - t) + x
        else:
            c += (x - t) + s
        s = t
    return s + c


# Test Neumaier vs builtin sum
def test_neumaier():
    """Test Neumaier summation against problematic cases."""
    # Classic case: 1e16 + 1 + 1 - 1e16 = 2 (but builtin sum gives 0)
    test_data = [1e16, 1.0, 1.0, -1e16]
    
    builtin_result = sum(test_data)
    neumaier_result = neumaier_sum(test_data)
    exact_result = 2.0
    
    print(f"Test data: {test_data}")
    print(f"  Builtin sum: {builtin_result}")
    print(f"  Neumaier:    {neumaier_result}")
    print(f"  Exact:       {exact_result}")
    print(f"  Builtin error: {abs(builtin_result - exact_result)}")
    print(f"  Neumaier error: {abs(neumaier_result - exact_result)}")
    
    # Additional test: many small numbers
    many_small = [1.0] * 1000000
    builtin_many = sum(many_small)
    neumaier_many = neumaier_sum(many_small)
    print(f"\n1M small numbers:")
    print(f"  Builtin: {builtin_many}")
    print(f"  Neumaier: {neumaier_many}")
    
    return neumaier_result == exact_result


if __name__ == '__main__':
    # Test Neumaier
    test_neumaier()
    
    # Test AST Guard
    from svl.lexer import tokenize
    from svl.parser_rd import parse
    
    # Test case with forbidden sum()
    bad_code = '''
    module test {
      func main() type void {
        let x: float = sum([1.0, 2.0, 3.0])
        return
      }
    }
    '''
    
    print("\n=== AST Guard Test ===")
    tokens = tokenize(bad_code)
    ast = parse(tokens)
    
    guard = ASTGuard()
    violations = guard.check(ast)
    
    if violations:
        print(f"✓ Caught {len(violations)} violation(s):")
        for v in violations:
            print(f"  {v.message} at line {v.node.line}, col {v.node.column}")
    else:
        print("✗ No violations caught!")
    
    # Test case without forbidden patterns
    good_code = '''
    module test {
      func main() type void {
        let x: float = neumaier_sum([1.0, 2.0, 3.0])
        return
      }
    }
    '''
    
    tokens = tokenize(good_code)
    ast = parse(tokens)
    violations = guard.check(ast)
    
    if violations:
        print(f"✗ False positive: {len(violations)} violation(s)")
    else:
        print("✓ Clean AST passes guard")