# svl/wit_generation.py
# WIT Generation from SVL Modules (H42)
# Generates WebAssembly Interface Types (WIT) from SVL type definitions

from typing import Dict, List, Optional, Any, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum

from svl.parser_rd import (
    Program, Module, FuncDecl, StructDecl, TypeAlias, Param,
    TypeExpr, FuncTypeDetail, NodeType
)
from svl.component_model import (
    WitTypeRef, WitRecord, WitVariant, WitEnum, WitFlags,
    WitFunction, WitInterface, WitWorld, WitGenerator, WitType
)


class SVLWitGenerator:
    """Generates WIT from SVL AST directly."""

    def __init__(self):
        self.type_defs: Dict[str, Any] = {}
        self.generated_types: Set[str] = set()

    def generate_from_program(self, program: Program) -> tuple[WitWorld, Dict[str, Any]]:
        """Generate WIT world from entire SVL program. Returns (world, type_defs)."""
        exports = []
        imports = []
        all_type_defs = {}

        for module in program.modules:
            interface, type_defs = self._generate_module_interface(module)
            exports.append(interface)
            all_type_defs.update(type_defs)

        world = WitWorld(
            name=program.modules[0].name if program.modules else 'svl',
            imports=imports,
            exports=exports
        )

        return world, all_type_defs

    def _generate_module_interface(self, module: Module) -> tuple[WitInterface, Dict[str, Any]]:
        """Generate WIT interface from SVL module."""
        functions = []
        types = []
        type_defs = {}

        for item in module.body.statements:
            if isinstance(item, FuncDecl):
                functions.append(self._convert_function(item, module.name))
            elif isinstance(item, StructDecl):
                record = self._convert_struct(item)
                types.append(record)
                type_defs[record.name] = record
            elif isinstance(item, TypeAlias):
                # Type aliases - could generate variant/enum/record
                pass

        interface = WitInterface(
            name=module.name,
            functions=functions,
            types=types
        )

        return interface, type_defs

    def _convert_function(self, func: FuncDecl, module_name: str) -> WitFunction:
        """Convert SVL function to WIT function."""
        params = []
        for param in func.params:
            wit_type = self._convert_type_expr(param.type_ann, module_name)
            params.append((param.name, wit_type))

        results = []
        if func.return_type:
            wit_type = self._convert_type_expr(func.return_type, module_name)
            results.append(wit_type)
        else:
            results.append(WitTypeRef('unit'))

        return WitFunction(
            name=func.name,
            params=params,
            results=results,
            docs=None
        )

    def _convert_struct(self, struct: StructDecl) -> WitRecord:
        """Convert SVL struct to WIT record."""
        fields = []
        for field in struct.fields:
            wit_type = self._convert_type_expr(field.type_ann, '')
            fields.append((field.name, wit_type))

        return WitRecord(
            name=struct.name,
            fields=fields,
            docs=None
        )

    def _convert_type_expr(self, type_expr: Optional[TypeExpr], module_name: str) -> WitTypeRef:
        """Convert SVL TypeExpr to WIT type reference."""
        if not type_expr:
            return WitTypeRef('unit')

        kind = type_expr.kind

        if kind == 'prim':
            return self._prim_to_wit(type_expr.value)

        elif kind == 'struct':
            # User-defined struct
            return WitTypeRef(type_expr.value, module=module_name if module_name else None)

        elif kind == 'func':
            # Function types become resources/handles in WIT
            return WitTypeRef('handle', module='wasi:cli/cli')

        elif kind == 'generic':
            if isinstance(type_expr.value, dict):
                name = type_expr.value.get('name', '')
                args = type_expr.value.get('args', [])

                if name in ('List', 'Vec', 'Array'):
                    if args:
                        inner = self._convert_type_expr(args[0], module_name)
                        return WitTypeRef('list', params=[inner])
                elif name in ('Option', 'Maybe'):
                    if args:
                        inner = self._convert_type_expr(args[0], module_name)
                        return WitTypeRef('option', params=[inner])
                elif name in ('Result', 'Either'):
                    if len(args) >= 2:
                        ok = self._convert_type_expr(args[0], module_name)
                        err = self._convert_type_expr(args[1], module_name)
                        return WitTypeRef('result', params=[ok, err])
                elif name in ('Dict', 'Map'):
                    if len(args) >= 2:
                        # Dict<K,V> -> list<tuple<K,V>> or map type
                        key = self._convert_type_expr(args[0], module_name)
                        val = self._convert_type_expr(args[1], module_name)
                        return WitTypeRef('list', params=[WitTypeRef('tuple', params=[key, val])])

                return WitTypeRef(name, module=module_name)

        elif kind == 'tuple':
            if isinstance(type_expr.value, list):
                params = [self._convert_type_expr(t, module_name) for t in type_expr.value]
                return WitTypeRef('tuple', params=params)

        elif kind == 'array':
            if isinstance(type_expr.value, TypeExpr):
                inner = self._convert_type_expr(type_expr.value, module_name)
                return WitTypeRef('list', params=[inner])

        elif kind == 'vec':
            # Dependent types
            if isinstance(type_expr.value, dict):
                elem_type = type_expr.value.get('element_type')
                if elem_type:
                    inner = self._convert_type_expr(elem_type, module_name)
                    return WitTypeRef('list', params=[inner])

        elif kind == 'refinement':
            # Refinement types map to base type
            if isinstance(type_expr.value, dict):
                base_type = type_expr.value.get('base_type')
                if base_type:
                    return self._convert_type_expr(base_type, module_name)

        elif kind in ('linear', 'unique'):
            # Linear/unique qualifiers don't affect WIT representation
            if isinstance(type_expr.value, dict):
                inner = type_expr.value.get('inner')
                if inner:
                    return self._convert_type_expr(inner, module_name)

        elif kind in ('box', 'diamond'):
            # Modal types
            if isinstance(type_expr.value, TypeExpr):
                return self._convert_type_expr(type_expr.value, module_name)

        return WitTypeRef('unit')

    def _prim_to_wit(self, prim: str) -> WitTypeRef:
        """Map primitive types to WIT."""
        mapping = {
            'bool': WitTypeRef('bool'),
            'int': WitTypeRef('s32'),
            'uint': WitTypeRef('u32'),
            'long': WitTypeRef('s64'),
            'ulong': WitTypeRef('u64'),
            'float': WitTypeRef('f32'),
            'double': WitTypeRef('f64'),
            'string': WitTypeRef('string'),
            'void': WitTypeRef('unit'),
            'never': WitTypeRef('unit'),
        }
        return mapping.get(prim, WitTypeRef('s32'))


def generate_wit_file(program: Program, output_path: str) -> str:
    """Generate WIT file from SVL program."""
    generator = SVLWitGenerator()
    world, type_defs = generator.generate_from_program(program)

    wit_gen = WitGenerator()
    wit_gen.type_defs.update(type_defs)
    wit_text = wit_gen.generate_wit_text(world)

    with open(output_path, 'w') as f:
        f.write(wit_text)

    return wit_text


def generate_wit_from_svl_source(source: str, output_path: str) -> str:
    """Generate WIT from SVL source code."""
    from svl.lexer import tokenize
    from svl.parser_rd import parse

    tokens = tokenize(source)
    ast = parse(tokens)
    return generate_wit_file(ast, output_path)


# WIT Package Generation
@dataclass
class WitPackage:
    """WIT package metadata."""
    name: str
    version: str
    description: str = ""
    license: str = "MIT"
    repository: str = ""
    homepage: str = ""
    keywords: List[str] = field(default_factory=list)


def generate_wit_package(package: WitPackage, wit_files: List[str], output_dir: str):
    """Generate WIT package directory structure."""
    import os

    os.makedirs(output_dir, exist_ok=True)

    # Generate wit.toml
    wit_toml = f'''[package]
name = "{package.name}"
version = "{package.version}"
description = "{package.description}"
license = "{package.license}"
repository = "{package.repository}"
homepage = "{package.homepage}"
keywords = {package.keywords}

[dependencies]
'''
    with open(os.path.join(output_dir, 'wit.toml'), 'w') as f:
        f.write(wit_toml)

    # Copy/create WIT files
    wit_dir = os.path.join(output_dir, 'wit')
    os.makedirs(wit_dir, exist_ok=True)

    for i, wit_content in enumerate(wit_files):
        wit_file = os.path.join(wit_dir, f'{package.name}_{i}.wit')
        with open(wit_file, 'w') as f:
            f.write(wit_content)


# WIT Validation
def validate_wit_syntax(wit_text: str) -> Tuple[bool, List[str]]:
    """Validate WIT syntax (basic validation)."""
    errors = []
    lines = wit_text.split('\n')

    in_interface = False
    in_world = False
    brace_count = 0

    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        if stripped.startswith('interface ') and '{' in line:
            in_interface = True
            brace_count += line.count('{') - line.count('}')

        elif stripped.startswith('world ') and '{' in line:
            in_world = True
            brace_count += line.count('{') - line.count('}')

        elif in_interface or in_world:
            brace_count += line.count('{') - line.count('}')
            if brace_count <= 0:
                in_interface = False
                in_world = False

        # Check for basic syntax issues
        if 'func(' in stripped and ')' not in stripped:
            errors.append(f"Line {i}: Unclosed function signature")

        if stripped.startswith('record ') and '{' in line:
            if '}' not in wit_text[wit_text.index(line):]:
                errors.append(f"Line {i}: Unclosed record definition")

    if brace_count != 0:
        errors.append(f"Mismatched braces: {brace_count}")

    return len(errors) == 0, errors


if __name__ == '__main__':
    print("=== WIT Generation Test ===")

    from svl.lexer import tokenize
    from svl.parser_rd import parse

    test_source = '''
    module math {
      struct Point { x: int, y: int }
      struct Rect { top_left: Point, bottom_right: Point }

      func add(a: int, b: int) type int { return a + b }
      func make_point(x: int, y: int) type Point { return Point { x: x, y: y } }
      func distance(p1: Point, p2: Point) type float { return 0.0 }
      func process_points(pts: List<Point>) type Option<Point> { return None }
    }
    '''

    tokens = tokenize(test_source)
    ast = parse(tokens)

    generator = SVLWitGenerator()
    world = generator.generate_from_program(ast)

    print(f"World: {world.name}")
    print(f"Exports: {len(world.exports)}")
    for iface in world.exports:
        print(f"  Interface: {iface.name}")
        print(f"    Functions: {len(iface.functions)}")
        for func in iface.functions:
            params = ', '.join(f"{n}: {t}" for n, t in func.params)
            results = ', '.join(str(t) for t in func.results)
            print(f"      {func.name}({params}) -> ({results})")
        print(f"    Types: {len(iface.types)}")
        for t in iface.types:
            print(f"      {type(t).__name__}: {t.name}")

    # Generate WIT text
    wit_gen = WitGenerator()
    wit_text = wit_gen.generate_wit_text(world)
    print("\nGenerated WIT:")
    print(wit_text)

    # Validate
    valid, errors = validate_wit_syntax(wit_text)
    print(f"\nValidation: {'PASS' if valid else 'FAIL'}")
    for e in errors:
        print(f"  Error: {e}")

    print("\n✓ WIT Generation test complete!")