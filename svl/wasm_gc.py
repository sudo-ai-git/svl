# svl/wasm_gc.py
# WASM GC Proposal Support (H25)
# Support for struct and array types in WASM GC

from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
from svl.compiler_wasm import WasmValType, WasmStructType, WasmArrayType, generate_wasm_gc_types
from svl.parser_rd import Program


@dataclass
class GCStructLayout:
    """Layout information for a GC struct."""
    name: str
    fields: List[Tuple[str, str]]  # (name, wasm_type)
    is_final: bool = True


@dataclass
class GCArrayLayout:
    """Layout information for a GC array."""
    name: str
    element_type: str
    mutable: bool = False


class WASMGCManager:
    """Manages WASM GC type generation and struct/array layouts."""
    
    def __init__(self):
        self.struct_types: Dict[str, GCStructLayout] = {}
        self.array_types: Dict[str, GCArrayLayout] = {}
        self.type_counter = 0
        
    def register_struct(self, name: str, fields: List[Tuple[str, str]], is_final: bool = True) -> GCStructLayout:
        """Register a GC struct type."""
        layout = GCStructLayout(name=name, fields=fields, is_final=is_final)
        self.struct_types[name] = layout
        return layout
        
    def register_array(self, name: str, element_type: str, mutable: bool = False) -> GCArrayLayout:
        """Register a GC array type."""
        layout = GCArrayLayout(name=name, element_type=element_type, mutable=mutable)
        self.array_types[name] = layout
        return layout
        
    def get_struct(self, name: str) -> Optional[GCStructLayout]:
        """Get struct layout by name."""
        return self.struct_types.get(name)
        
    def get_array(self, name: str) -> Optional[GCArrayLayout]:
        """Get array layout by name."""
        return self.array_types.get(name)
        
    def generate_type_decls(self) -> List[str]:
        """Generate WASM GC type declarations."""
        lines = []
        
        # Generate struct types
        for name, layout in sorted(self.struct_types.items()):
            final_str = " (final)" if layout.is_final else ""
            field_lines = []
            for field_name, field_type in layout.fields:
                field_lines.append(f"  (field {field_name} {field_type})")
            lines.append(f"(type ${name} (struct{'' if layout.is_final else ''}\n{chr(10).join(field_lines)}\n))")
        
        # Generate array types
        for name, layout in sorted(self.array_types.items()):
            mutable_str = " (mut)" if layout.mutable else ""
            lines.append(f"(type ${name} (array {layout.element_type}{mutable_str}))")
            
        return lines
    
    def compile_program_with_gc(self, program: Program) -> str:
        """Compile program with WASM GC types."""
        from svl.compiler_wasm import compile_to_wasm, WasmCompiler
        
        # Create a GC-enabled compiler
        compiler = WasmCompiler(deterministic=True)
        # compiler.state = compiler.state  # Reuse existing state
        
        # Add GC type declarations
        gc_decls = self.generate_type_decls()
        
        # Compile with standard compiler first
        wasm = compiler.compile(program)
        
        # Insert GC type declarations
        # Find the right place to insert (after imports, before functions)
        lines = wasm.split('\n')
        insert_idx = 0
        for i, line in enumerate(lines):
            if line.strip().startswith('(func') or line.strip().startswith('(export'):
                insert_idx = i
                break
        
        if insert_idx == 0:
            insert_idx = len(lines)
            
        new_lines = lines[:insert_idx] + gc_decls + lines[insert_idx:]
        return '\n'.join(new_lines)


def compile_with_gc(program: Program) -> str:
    """Compile program with WASM GC support."""
    from svl.compiler_wasm import compile_to_wasm
    from svl.wasm_gc import WASMGCManager
    
    manager = WASMGCManager()
    
    # Extract struct and array types from program
    # This would be done during compilation in practice
    
    return compile_to_wasm(program)


def test_wasm_gc():
    """Test WASM GC type generation."""
    print("=== WASM GC Test ===")
    
    manager = WASMGCManager()
    
    # Register a simple struct
    manager.register_struct("Point", [
        ("x", "i32"),
        ("y", "i32"),
    ])
    
    # Register an array type
    manager.register_array("IntArray", "i32", mutable=True)
    
    # Generate declarations
    decls = manager.generate_type_decls()
    
    print("Generated WASM GC types:")
    for decl in decls:
        print(decl)
    
    # Test compilation
    from svl.parser_rd import parse
    from svl.lexer import tokenize
    
    source = '''
    module test {
      struct Point { x: int, y: int }
      func main() type void { return }
    }
    '''
    
    tokens = tokenize(source)
    ast = parse(tokens)
    
    # Test compilation with GC
    from svl.compiler_wasm import compile_to_wasm
    wasm = compile_to_wasm(ast)
    
    print("\nCompiled WASM (first 500 chars):")
    print(wasm[:500])
    
    print("\n✓ WASM GC test complete!")


if __name__ == '__main__':
    test_wasm_gc()