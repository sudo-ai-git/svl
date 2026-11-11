# svl/incremental.py
# Incremental Compilation with Salsa (H44)
# Provides incremental compilation infrastructure using Salsa

from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
import hashlib
import time
import os
from functools import lru_cache


try:
    import salsa
    SALSA_AVAILABLE = True
except ImportError:
    SALSA_AVAILABLE = False
    salsa = None


class CompilationQuery:
    """Base class for compilation queries."""
    pass


class SourceFileQuery(CompilationQuery):
    """Query for source file content."""
    def __init__(self, path: str):
        self.path = path


class ParsedASTQuery(CompilationQuery):
    """Query for parsed AST."""
    def __init__(self, path: str):
        self.path = path


class TypeCheckedQuery(CompilationQuery):
    """Query for type-checked AST."""
    def __init__(self, path: str):
        self.path = path


class VerifiedQuery(CompilationQuery):
    """Query for verified AST."""
    def __init__(self, path: str):
        self.path = path


class CompiledWASMQuery(CompilationQuery):
    """Query for compiled WASM."""
    def __init__(self, path: str):
        self.path = path


class IncrementalCompiler:
    """Incremental compiler using Salsa for incremental computation."""
    
    def __init__(self):
        if not SALSA_AVAILABLE:
            raise RuntimeError("Salsa not available. Install with: pip install salsa")
        
        # Salsa database
        self.db = salsa.Database()
        self._setup_queries()
        
    def _setup_queries(self):
        """Set up Salsa queries for incremental compilation."""
        
        @salsa.tracked
        def source_file(db: salsa.Database, path: str) -> str:
            """Get source file content."""
            with open(path, 'r') as f:
                return f.read()
        
        @salsa.tracked
        def parsed_ast(db: salsa.Database, path: str) -> Any:
            """Parse source file to AST."""
            from svl.lexer import tokenize
            from svl.parser_rd import parse
            source = source_file(db, path)
            tokens = tokenize(source)
            return parse(tokens)
        
        @salsa.tracked
        def verified_ast(db: salsa.Database, path: str) -> Any:
            """Verify AST through all layers."""
            from svl.syntax_layer import verify_syntax
            from svl.type_layer import verify_type
            from svl.theorem_layer import verify_theorem_layer
            
            ast = parsed_ast(db, path)
            
            syntax_result = verify_syntax(ast)
            if not syntax_result.passed:
                raise Exception(f"Syntax errors: {syntax_result.errors}")
            
            type_result = verify_type(ast)
            if not type_result.passed:
                raise Exception(f"Type errors: {type_result.errors}")
            
            theorem_result = verify_theorem_layer(ast)
            if not theorem_result.passed:
                raise Exception(f"Verification failed: {theorem_result.errors}")
            
            return ast
        
        @salsa.tracked
        def compiled_wasm(db: salsa.Database, path: str) -> str:
            """Compile verified AST to WASM."""
            from svl.compiler_wasm import compile_to_wasm
            ast = verified_ast(db, path)
            return compile_to_wasm(ast)
        
        # Store query functions
        self.source_file = source_file
        self.parsed_ast = parsed_ast
        self.verified_ast = verified_ast
        self.compiled_wasm = compiled_wasm
        
    def get_source(self, path: str) -> str:
        """Get source file content."""
        return self.source_file(self.db, path)
    
    def get_ast(self, path: str) -> Any:
        """Get parsed AST."""
        return self.parsed_ast(self.db, path)
    
    def get_verified_ast(self, path: str) -> Any:
        """Get verified AST."""
        return self.verified_ast(self.db, path)
    
    def get_wasm(self, path: str) -> str:
        """Get compiled WASM."""
        return self.compiled_wasm(self.db, path)
    
    def invalidate_file(self, path: str):
        """Invalidate cached results for a file."""
        # Salsa automatically handles invalidation through revision tracking
        # We just need to update the source file
        self.source_file.set(self.db, path, self._read_file(path))
        self.db.sweep()
    
    def _read_file(self, path: str) -> str:
        with open(path, 'r') as f:
            return f.read()


# Fallback implementation without Salsa
class FallbackIncrementalCompiler:
    """Fallback incremental compiler without Salsa."""
    
    def __init__(self):
        self.cache: Dict[str, Any] = {}
        self.timestamps: Dict[str, float] = {}
        
    def get_ast(self, path: str) -> Any:
        """Get AST with caching."""
        mtime = os.path.getmtime(path)
        if path in self.cache and self.timestamps.get(path, 0) >= mtime:
            return self.cache[path]
        
        from svl.lexer import tokenize
        from svl.parser_rd import parse
        with open(path, 'r') as f:
            source = f.read()
        tokens = tokenize(source)
        ast = parse(tokens)
        self.cache[path] = ast
        self.timestamps[path] = mtime
        return ast
    
    def get_verified_ast(self, path: str) -> Any:
        """Get verified AST with caching."""
        # Simplified - no incremental verification
        ast = self.get_ast(path)
        
        from svl.syntax_layer import verify_syntax
        from svl.type_layer import verify_type
        from svl.theorem_layer import verify_theorem_layer
        
        syntax_result = verify_syntax(ast)
        if not syntax_result.passed:
            raise Exception(f"Syntax errors: {syntax_result.errors}")
        
        type_result = verify_type(ast)
        if not type_result.passed:
            raise Exception(f"Type errors: {type_result.errors}")
        
        theorem_result = verify_theorem_layer(ast)
        if not theorem_result.passed:
            raise Exception(f"Verification failed: {theorem_result.errors}")
        
        return ast
    
    def invalidate_file(self, path: str):
        """Invalidate cache for a file."""
        if path in self.cache:
            del self.cache[path]
            del self.timestamps[path]


def create_incremental_compiler() -> Any:
    """Create an incremental compiler (with or without Salsa)."""
    if SALSA_AVAILABLE:
        return IncrementalCompiler()
    else:
        return FallbackIncrementalCompiler()


def test_incremental_compilation():
    """Test incremental compilation."""
    print("=== Incremental Compilation Test ===")
    
    compiler = create_incremental_compiler()
    
    # Test with a sample file
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.svl', delete=False) as f:
        f.write('''
module test {
    func fact(n: int, acc: int) type int {
        if n == 0 then { return acc }
        else { return fact(n - 1, n * acc) }
    }
    func main() type void { return }
}
''')
        test_file = f.name
    
    try:
        # First compilation
        start = time.time()
        ast = compiler.get_ast(test_file)
        time1 = time.time() - start
        print(f"First AST parse: {time1:.4f}s")
        
        # Second compilation (should be cached)
        start = time.time()
        ast2 = compiler.get_ast(test_file)
        time2 = time.time() - start
        print(f"Second AST parse: {time2:.4f}s")
        
        # Modify file
        with open(test_file, 'w') as f:
            f.write('''
module test {
    func fact(n: int, acc: int) type int {
        if n == 0 then { return acc }
        else { return fact(n - 1, n * acc) }
    }
    func main() type void { return }
}
''')
        
        # Third compilation (after modification)
        start = time.time()
        ast3 = compiler.get_ast(test_file)
        time3 = time.time() - start
        print(f"Third AST parse (after modify): {time3:.4f}s")
        
        print("✓ Incremental compilation test complete!")
        
    except Exception as e:
        print(f"Test failed: {e}")
    finally:
        os.unlink(test_file)


if __name__ == '__main__':
    test_incremental_compilation()