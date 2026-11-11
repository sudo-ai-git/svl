# svl/tco.py
# Tail Call Optimization (H27)
# Detects and emits return_call for tail calls

from typing import List, Optional, Set
from dataclasses import dataclass
from svl.parser_rd import FuncDecl, CallExpr, ReturnStmt, Block, parse
from svl.lexer import tokenize


@dataclass
class TCOAnalysis:
    """Result of TCO analysis for a function."""
    function_name: str
    tail_calls: List[CallExpr]  # Calls in tail position
    non_tail_calls: List[CallExpr]  # Calls not in tail position
    is_tail_recursive: bool
    optimization_possible: bool


class TCOAnalyzer:
    """Analyzes functions for tail call optimization opportunities."""
    
    def __init__(self):
        self.results: List[TCOAnalysis] = []
        
    def analyze_function(self, func: FuncDecl) -> TCOAnalysis:
        """Analyze a function for tail call optimization."""
        tail_calls = []
        non_tail_calls = []
        
        # Find all calls in the function body
        calls = self._find_calls(func.body)
        
        for call in calls:
            if self._is_in_tail_position(call, func.body):
                tail_calls.append(call)
            else:
                non_tail_calls.append(call)
                
        # Check for tail recursion
        is_tail_recursive = any(
            call.callee == func.name for call in tail_calls
        )
        
        optimization_possible = len(tail_calls) > 0
        
        return TCOAnalysis(
            function_name=func.name,
            tail_calls=tail_calls,
            non_tail_calls=non_tail_calls,
            is_tail_recursive=is_tail_recursive,
            optimization_possible=optimization_possible
        )
    
    def _find_calls(self, node) -> List[CallExpr]:
        """Find all CallExpr nodes in AST."""
        calls = []
        
        def visit(n):
            if n is None:
                return
            if hasattr(n, '__class__') and n.__class__.__name__ == 'CallExpr':
                calls.append(n)
            if hasattr(n, '__dataclass_fields__'):
                for f in n.__dataclass_fields__:
                    value = getattr(n, f)
                    if isinstance(value, list):
                        for item in value:
                            visit(item)
                    elif hasattr(value, '__dataclass_fields__'):
                        visit(value)
                        
        visit(node)
        return calls
    
    def _is_in_tail_position(self, call: CallExpr, body: Block) -> bool:
            """Check if a call is in tail position."""
            # Simplified: check if call is the last expression in a return statement
            # or the last statement in the function body
        
            def check_tail(node, parent=None, is_last=False):
                if node is call:
                    # Check if in return statement or last statement in block
                    if parent and 'ReturnStmt' in parent.__class__.__name__:
                        return True
                    if is_last:
                        return True
                    return False
            
                if node is None:
                    return False
            
                if hasattr(node, '__dataclass_fields__'):
                    for f in node.__dataclass_fields__:
                        if f in ('type', 'line', 'column', 'offset'):
                            continue
                        val = getattr(node, f)
                        if isinstance(val, list):
                            for i, item in enumerate(val):
                                if check_tail(item, node, i == len(val) - 1):
                                    return True
                        elif hasattr(val, '__dataclass_fields__'):
                            # Single AST node child
                            if check_tail(val, node, False):
                                return True
            
                return False
        
            return check_tail(body)
    
    def _find_calls(self, node) -> List[CallExpr]:
        """Find all CallExpr nodes in AST."""
        calls = []
        
        def visit(n):
            if n is None:
                return
            if hasattr(n, '__class__') and n.__class__.__name__ == 'CallExpr':
                calls.append(n)
            if hasattr(n, '__dataclass_fields__'):
                for f in n.__dataclass_fields__:
                    value = getattr(n, f)
                    if isinstance(value, list):
                        for item in value:
                            visit(item)
                    elif hasattr(value, '__dataclass_fields__'):
                        visit(value)
                        
        visit(node)
        return calls


def run_tco_analysis(source: str) -> List[TCOAnalysis]:
    """Run TCO analysis on SVL source."""
    from svl.parser_rd import parse, FuncDecl
    from svl.lexer import tokenize
    
    tokens = tokenize(source)
    ast = parse(tokens)
    
    analyzer = TCOAnalyzer()
    results = []
    
    for item in ast.items:
        if isinstance(item, FuncDecl):
            analysis = analyzer.analyze_function(item)
            results.append(analysis)
            
    return results


if __name__ == '__main__':
    print("=== TCO Analysis Test ===")
    
    # Test tail recursive function
    source = '''
    func fact(n: int, acc: int) type int {
        if n == 0 then { return acc }
        else { return fact(n - 1, n * acc) }
    }
    '''
    
    results = run_tco_analysis(source)
    for r in results:
        print(f"Function: {r.function_name}")
        print(f"  Tail calls: {len(r.tail_calls)}")
        print(f"  Non-tail calls: {len(r.non_tail_calls)}")
        print(f"  Tail recursive: {r.is_tail_recursive}")
        print(f"  Optimization possible: {r.optimization_possible}")
    
    # Test non-tail recursive
    source2 = '''
    func fact(n: int) type int {
        if n == 0 then { return 1 }
        else { return n * fact(n - 1) }
    }
    '''
    
    results2 = run_tco_analysis(source2)
    for r in results2:
        print(f"\nFunction: {r.function_name}")
        print(f"  Tail calls: {len(r.tail_calls)}")
        print(f"  Non-tail calls: {len(r.non_tail_calls)}")
        print(f"  Tail recursive: {r.is_tail_recursive}")
        print(f"  Optimization possible: {r.optimization_possible}")
    
    print("\n✓ TCO Analysis test complete!")