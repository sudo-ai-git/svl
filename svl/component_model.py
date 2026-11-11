# svl/component_model.py
# FFI with C/Rust via WASM Component Model (H41)
# Implements WASM Component Model support for SVL

from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import json


class WitType(Enum):
    """WIT (WebAssembly Interface Types) type system."""
    BOOL = "bool"
    U8 = "u8"
    U16 = "u16"
    U32 = "u32"
    U64 = "u64"
    S8 = "s8"
    S16 = "s16"
    S32 = "s32"
    S64 = "s64"
    F32 = "f32"
    F64 = "f64"
    CHAR = "char"
    STRING = "string"
    LIST = "list"
    OPTION = "option"
    RESULT = "result"
    TUPLE = "tuple"
    RECORD = "record"
    VARIANT = "variant"
    ENUM = "enum"
    FLAGS = "flags"
    HANDLE = "handle"
    RESOURCE = "resource"


@dataclass(frozen=True)
class WitTypeRef:
    """Reference to a WIT type."""
    name: str
    module: Optional[str] = None
    params: Tuple['WitTypeRef', ...] = field(default_factory=tuple)

    def __init__(self, name: str, module: Optional[str] = None, params: Optional[List['WitTypeRef']] = None):
        object.__setattr__(self, 'name', name)
        object.__setattr__(self, 'module', module)
        object.__setattr__(self, 'params', tuple(params) if params else tuple())

    def __str__(self):
        if self.module:
            base = f"{self.module}/{self.name}"
        else:
            base = self.name
        if self.params:
            param_strs = ', '.join(str(p) for p in self.params)
            return f"{base}<{param_strs}>"
        return base

    def __hash__(self):
        return hash((self.name, self.module, self.params))

    def __eq__(self, other):
        if not isinstance(other, WitTypeRef):
            return False
        return (self.name == other.name and 
                self.module == other.module and 
                self.params == other.params)


@dataclass
class WitRecord:
    """WIT record type."""
    name: str
    fields: List[Tuple[str, WitTypeRef]]
    docs: Optional[str] = None


@dataclass
class WitVariant:
    """WIT variant type."""
    name: str
    cases: List[Tuple[str, Optional[WitTypeRef]]]
    docs: Optional[str] = None


@dataclass
class WitEnum:
    """WIT enum type."""
    name: str
    cases: List[str]
    docs: Optional[str] = None


@dataclass
class WitFlags:
    """WIT flags type."""
    name: str
    flags: List[str]
    docs: Optional[str] = None


@dataclass
class WitFunction:
    """WIT function signature."""
    name: str
    params: List[Tuple[str, WitTypeRef]]
    results: List[WitTypeRef]
    docs: Optional[str] = None


@dataclass
class WitInterface:
    """WIT interface definition."""
    name: str
    functions: List[WitFunction]
    types: List[Any] = field(default_factory=list)  # Records, variants, etc.
    docs: Optional[str] = None


@dataclass
class WitWorld:
    """WIT world (component interface)."""
    name: str
    imports: List[WitInterface] = field(default_factory=list)
    exports: List[WitInterface] = field(default_factory=list)
    docs: Optional[str] = None


# SVL type to WIT type mapping
SVL_TO_WIT: Dict[str, WitTypeRef] = {
    'bool': WitTypeRef('bool'),
    'int': WitTypeRef('s32'),
    'uint': WitTypeRef('u32'),
    'long': WitTypeRef('s64'),
    'ulong': WitTypeRef('u64'),
    'float': WitTypeRef('f32'),
    'double': WitTypeRef('f64'),
    'string': WitTypeRef('string'),
    'void': WitTypeRef('unit'),  # Unit type
}


class WitGenerator:
    """Generates WIT definitions from SVL modules."""

    def __init__(self):
        self.interfaces: Dict[str, WitInterface] = {}
        self.type_defs: Dict[str, Any] = {}

    def generate_from_module(self, module_name: str, funcs: List[Dict[str, Any]]) -> WitInterface:
        """Generate WIT interface from SVL module functions."""
        functions = []
        for func in funcs:
            wit_func = self._convert_function(func)
            functions.append(wit_func)

        return WitInterface(
            name=module_name,
            functions=functions,
            types=list(self.type_defs.values())
        )

    def _convert_function(self, func: Dict[str, Any]) -> WitFunction:
        """Convert SVL function to WIT function."""
        params = []
        for param in func.get('params', []):
            wit_type = self._convert_type(param['type'])
            params.append((param['name'], wit_type))

        results = []
        for ret_type in func.get('return_types', ['void']):
            wit_type = self._convert_type(ret_type)
            results.append(wit_type)

        return WitFunction(
            name=func['name'],
            params=params,
            results=results,
            docs=func.get('docs')
        )

    def _convert_type(self, svl_type: str) -> WitTypeRef:
        """Convert SVL type to WIT type reference."""
        # Handle generics: List<int> -> list<u32>
        if '<' in svl_type and '>' in svl_type:
            base = svl_type[:svl_type.index('<')]
            inner = svl_type[svl_type.index('<')+1:svl_type.rindex('>')]

            if base == 'List' or base == 'Vec' or base == 'Array':
                inner_ref = self._convert_type(inner)
                return WitTypeRef('list', params=[inner_ref])
            elif base == 'Option' or base == 'Maybe':
                inner_ref = self._convert_type(inner)
                return WitTypeRef('option', params=[inner_ref])
            elif base == 'Result':
                # Result<T, E> - split by comma
                parts = [p.strip() for p in inner.split(',')]
                if len(parts) == 2:
                    ok_ref = self._convert_type(parts[0])
                    err_ref = self._convert_type(parts[1])
                    return WitTypeRef('result', params=[ok_ref, err_ref])

        return SVL_TO_WIT.get(svl_type, WitTypeRef(svl_type))

    def generate_wit_text(self, world: WitWorld) -> str:
        """Generate WIT text format."""
        lines = []
        lines.append(f"package {world.name}")

        if world.docs:
            lines.append(f"@doc(\"{world.docs}\")")

        # Generate type definitions
        all_types = set()
        for iface in world.imports + world.exports:
            for func in iface.functions:
                for _, t in func.params:
                    self._collect_types(t, all_types)
                for t in func.results:
                    self._collect_types(t, all_types)

        # Also include all types defined in the world's interfaces
        for iface in world.imports + world.exports:
            for type_def in iface.types:
                if isinstance(type_def, WitRecord):
                    type_ref = WitTypeRef(type_def.name, module=world.name)
                    all_types.add(type_ref)
                elif isinstance(type_def, WitVariant):
                    type_ref = WitTypeRef(type_def.name, module=world.name)
                    all_types.add(type_ref)
                elif isinstance(type_def, WitEnum):
                    type_ref = WitTypeRef(type_def.name, module=world.name)
                    all_types.add(type_ref)
                elif isinstance(type_def, WitFlags):
                    type_ref = WitTypeRef(type_def.name, module=world.name)
                    all_types.add(type_ref)

        for type_ref in all_types:
            if type_ref.module == world.name:
                type_def = self.type_defs.get(type_ref.name)
                if type_def:
                    lines.append(self._format_type_def(type_def))

        # Generate imports
        for iface in world.imports:
            lines.append(f"interface {iface.name} {{")
            for func in iface.functions:
                lines.append(self._format_function(func, indent=2))
            lines.append("}")

        # Generate exports
        for iface in world.exports:
            lines.append(f"interface {iface.name} {{")
            for func in iface.functions:
                lines.append(self._format_function(func, indent=2))
            lines.append("}")

        # Generate world
        lines.append(f"world {world.name} {{")
        for iface in world.imports:
            lines.append(f"  import {iface.name}")
        for iface in world.exports:
            lines.append(f"  export {iface.name}")
        lines.append("}")

        return '\n'.join(lines)

    def _collect_types(self, type_ref: WitTypeRef, all_types: set):
        """Collect all referenced types."""
        all_types.add(type_ref)
        for param in type_ref.params:
            self._collect_types(param, all_types)

    def _format_type_def(self, type_def: Any) -> str:
        """Format type definition as WIT."""
        if isinstance(type_def, WitRecord):
            lines = [f"record {type_def.name} {{"]
            for field_name, field_type in type_def.fields:
                lines.append(f"  {field_name}: {field_type}")
            lines.append("}")
            return '\n'.join(lines)

        elif isinstance(type_def, WitVariant):
            lines = [f"variant {type_def.name} {{"]
            for case_name, case_type in type_def.cases:
                if case_type:
                    lines.append(f"  {case_name}({case_type})")
                else:
                    lines.append(f"  {case_name}")
            lines.append("}")
            return '\n'.join(lines)

        elif isinstance(type_def, WitEnum):
            cases = ', '.join(type_def.cases)
            return f"enum {type_def.name} {{ {cases} }}"

        elif isinstance(type_def, WitFlags):
            flags = ', '.join(type_def.flags)
            return f"flags {type_def.name} {{ {flags} }}"

        return ""

    def _format_function(self, func: WitFunction, indent: int = 0) -> str:
        """Format function as WIT."""
        prefix = ' ' * indent
        params = ', '.join(f"{name}: {type_ref}" for name, type_ref in func.params)
        results = ', '.join(str(t) for t in func.results)

        if results:
            return f"{prefix}{func.name}: func({params}) -> ({results})"
        return f"{prefix}{func.name}: func({params})"


class ComponentModelFFI:
    """FFI bindings for WASM Component Model."""

    def __init__(self):
        self.bindings: Dict[str, Any] = {}

    def generate_component(self, world: WitWorld) -> str:
        """Generate component WAT (text format)."""
        wit = WitGenerator()
        return wit.generate_wit_text(world)

    def generate_host_bindings(self, world: WitWorld, language: str = 'rust') -> str:
        """Generate host language bindings."""
        if language == 'rust':
            return self._generate_rust_bindings(world)
        elif language == 'c':
            return self._generate_c_bindings(world)
        elif language == 'python':
            return self._generate_python_bindings(world)
        return ""

    def _generate_rust_bindings(self, world: WitWorld) -> str:
        """Generate Rust bindings using wasmtime."""
        lines = []
        lines.append("// Generated Rust bindings for SVL Component Model")
        lines.append("// Requires: wasmtime, wit-bindgen")
        lines.append("")
        lines.append("use wasmtime::*;")
        lines.append("use wasmtime::component::*;")
        lines.append("")

        for iface in world.exports:
            lines.append(f"// Interface: {iface.name}")
            lines.append(f"pub mod {iface.name.lower()} {{")
            lines.append("    use super::*;")
            lines.append("")

            for func in iface.functions:
                lines.append(f"    // {func.name}")
                params = ', '.join(f"{name}: {self._wit_to_rust(type_ref)}"
                                   for name, type_ref in func.params)
                returns = self._wit_to_rust_return(func.results)
                lines.append(f"    pub fn {func.name}({params}) -> {returns} {{")
                lines.append("        // Implementation would call into component")
                lines.append("        unimplemented!()")
                lines.append("    }")
                lines.append("")

            lines.append("}")
            lines.append("")

        return '\n'.join(lines)

    def _generate_c_bindings(self, world: WitWorld) -> str:
        """Generate C bindings."""
        lines = []
        lines.append("/* Generated C bindings for SVL Component Model */")
        lines.append("/* Requires: wasmtime C API */")
        lines.append("")

        for iface in world.exports:
            lines.append(f"// Interface: {iface.name}")
            for func in iface.functions:
                params = ', '.join(f"{self._wit_to_c(type_ref)} {name}"
                                   for name, type_ref in func.params)
                returns = self._wit_to_c_return(func.results)
                lines.append(f"{returns} {iface.name}_{func.name}({params});")
            lines.append("")

        return '\n'.join(lines)

    def _generate_python_bindings(self, world: WitWorld) -> str:
        """Generate Python bindings."""
        lines = []
        lines.append("# Generated Python bindings for SVL Component Model")
        lines.append("# Requires: wasmtime Python package")
        lines.append("")

        for iface in world.exports:
            lines.append(f"class {iface.name.capitalize()}:")
            lines.append("    def __init__(self, component):")
            lines.append("        self.component = component")
            lines.append("")

            for func in iface.functions:
                params = ', '.join(name for name, _ in func.params)
                if params:
                    params = ", " + params
                lines.append(f"    def {func.name}(self{params}):")
                lines.append(f"        # Call {iface.name}.{func.name}")
                lines.append("        pass")
                lines.append("")

        return '\n'.join(lines)

    def _wit_to_rust(self, type_ref: WitTypeRef) -> str:
        """Convert WIT type to Rust type."""
        base_map = {
            'bool': 'bool',
            'u8': 'u8', 'u16': 'u16', 'u32': 'u32', 'u64': 'u64',
            's8': 'i8', 's16': 'i16', 's32': 'i32', 's64': 'i64',
            'f32': 'f32', 'f64': 'f64',
            'char': 'char',
            'string': 'String',
            'unit': '()',
        }

        if type_ref.name in base_map:
            return base_map[type_ref.name]

        if type_ref.name == 'list':
            inner = self._wit_to_rust(type_ref.params[0]) if type_ref.params else 'u8'
            return f"Vec<{inner}>"

        if type_ref.name == 'option':
            inner = self._wit_to_rust(type_ref.params[0]) if type_ref.params else '()'
            return f"Option<{inner}>"

        if type_ref.name == 'result':
            if len(type_ref.params) >= 2:
                ok = self._wit_to_rust(type_ref.params[0])
                err = self._wit_to_rust(type_ref.params[1])
                return f"Result<{ok}, {err}>"
            return "Result<(), ()>"

        return type_ref.name

    def _wit_to_rust_return(self, results: List[WitTypeRef]) -> str:
        """Convert WIT return types to Rust return type."""
        if not results:
            return "()"
        if len(results) == 1:
            return self._wit_to_rust(results[0])
        return f"({', '.join(self._wit_to_rust(r) for r in results)})"

    def _wit_to_c(self, type_ref: WitTypeRef) -> str:
        """Convert WIT type to C type."""
        base_map = {
            'bool': 'bool',
            'u8': 'uint8_t', 'u16': 'uint16_t', 'u32': 'uint32_t', 'u64': 'uint64_t',
            's8': 'int8_t', 's16': 'int16_t', 's32': 'int32_t', 's64': 'int64_t',
            'f32': 'float', 'f64': 'double',
            'char': 'uint32_t',
            'string': 'const char*',
            'unit': 'void',
        }
        return base_map.get(type_ref.name, type_ref.name)

    def _wit_to_c_return(self, results: List[WitTypeRef]) -> str:
        """Convert WIT return types to C return type."""
        if not results:
            return "void"
        if len(results) == 1:
            return self._wit_to_c(results[0])
        return "void /* multiple returns not supported in C */"


def generate_wit_from_svl(module_name: str, functions: List[Dict[str, Any]]) -> str:
    """Convenience function to generate WIT from SVL module."""
    generator = WitGenerator()
    interface = generator.generate_from_module(module_name, functions)

    world = WitWorld(
        name=module_name,
        exports=[interface]
    )

    return generator.generate_wit_text(world)


if __name__ == '__main__':
    print("=== Component Model / WIT Generation Test ===")

    # Test SVL to WIT conversion
    test_functions = [
        {
            'name': 'add',
            'params': [{'name': 'a', 'type': 'int'}, {'name': 'b', 'type': 'int'}],
            'return_types': ['int'],
            'docs': 'Add two integers'
        },
        {
            'name': 'concat',
            'params': [{'name': 'a', 'type': 'string'}, {'name': 'b', 'type': 'string'}],
            'return_types': ['string'],
            'docs': 'Concatenate strings'
        },
        {
            'name': 'process_list',
            'params': [{'name': 'items', 'type': 'List<int>'}],
            'return_types': ['Option<int>'],
            'docs': 'Process list of integers'
        },
    ]

    generator = WitGenerator()
    interface = generator.generate_from_module('math', test_functions)

    world = WitWorld(
        name='math',
        exports=[interface]
    )

    wit_text = generator.generate_wit_text(world)
    print("Generated WIT:")
    print(wit_text)

    print("\n--- Rust Bindings ---")
    ffi = ComponentModelFFI()
    rust_bindings = ffi.generate_host_bindings(world, 'rust')
    print(rust_bindings[:500])
    print("...")

    print("\n--- C Bindings ---")
    c_bindings = ffi.generate_host_bindings(world, 'c')
    print(c_bindings[:500])
    print("...")

    print("\n✓ Component Model / WIT Generation test complete!")