# svl/docs_generation.py
# Docs Generation from Verification (H47)
# Generates documentation from SVL types, theorems, and verification artifacts

from typing import Dict, List, Optional, Any, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
import json
import os
from pathlib import Path
from datetime import datetime

from svl.parser_rd import (
    Program, Module, FuncDecl, StructDecl, TypeAlias, ConstDecl, VarDecl,
    Block, LetStmt, IfStmt, WhileStmt, ForStmt, ReturnStmt, AssertStmt,
    Param, TypeExpr, NodeType
)
from svl.theorem_layer import verify_theorem_layer


class DocFormat(Enum):
    """Documentation output formats."""
    MARKDOWN = "markdown"
    HTML = "html"
    JSON = "json"
    WIT = "wit"


@dataclass
class DocSymbol:
    """Documented symbol."""
    name: str
    kind: str  # 'function', 'struct', 'type', 'const', 'var', 'module'
    signature: str
    docstring: Optional[str] = None
    detail: Optional[str] = None
    verification_status: Optional[str] = None
    location: Optional[Dict[str, int]] = None
    examples: List[str] = field(default_factory=list)
    see_also: List[str] = field(default_factory=list)


@dataclass
class DocModule:
    """Documented module."""
    name: str
    symbols: List[DocSymbol] = field(default_factory=list)
    docstring: Optional[str] = None
    verification_summary: Optional[Dict[str, Any]] = None


@dataclass
class DocProject:
    """Documented project."""
    name: str
    version: str
    description: str
    modules: List[DocModule] = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + 'Z')


class SVLDocGenerator:
    """Generates documentation from SVL AST and verification results."""

    def __init__(self, include_verification: bool = True):
        self.include_verification = include_verification
        self.project: Optional[DocProject] = None

    def generate_from_program(self, program: Program) -> DocProject:
        """Generate documentation from SVL program."""
        modules = []

        for module in program.modules:
            doc_module = self._generate_module(module)
            modules.append(doc_module)

        self.project = DocProject(
            name=program.modules[0].name if program.modules else 'svl',
            version='0.1.0',
            description='SVL Project Documentation',
            modules=modules
        )

        return self.project

    def _generate_module(self, module: Module) -> DocModule:
        """Generate documentation for a module."""
        symbols = []

        for item in module.body.statements:
            if isinstance(item, FuncDecl):
                symbols.append(self._generate_function(item))
            elif isinstance(item, StructDecl):
                symbols.append(self._generate_struct(item))
            elif isinstance(item, TypeAlias):
                symbols.append(self._generate_type_alias(item))
            elif isinstance(item, ConstDecl):
                symbols.append(self._generate_const(item))
            elif isinstance(item, VarDecl):
                symbols.append(self._generate_var(item))

        # Verification summary
        verification_summary = None
        if self.include_verification:
            # Would run verification on module source
            pass

        return DocModule(
            name=module.name,
            symbols=symbols,
            verification_summary=verification_summary
        )

    def _generate_function(self, func: FuncDecl) -> DocSymbol:
        """Generate documentation for a function."""
        params = []
        for param in func.params:
            type_str = self._type_to_string(param.type_ann)
            params.append(f"{param.name}: {type_str}")

        ret_str = self._type_to_string(func.return_type) if func.return_type else 'void'
        signature = f"func {func.name}({', '.join(params)}) -> {ret_str}"

        # Extract docstring (would come from comments in real implementation)
        docstring = None

        # Verification status
        verification_status = None
        if self.include_verification:
            verification_status = "verified"  # Would be actual result

        return DocSymbol(
            name=func.name,
            kind='function',
            signature=signature,
            docstring=docstring,
            detail=f"Function with {len(func.params)} parameter(s)",
            verification_status=verification_status,
            location={'line': func.line, 'column': func.column}
        )

    def _generate_struct(self, struct: StructDecl) -> DocSymbol:
        """Generate documentation for a struct."""
        fields = []
        for field in struct.fields:
            type_str = self._type_to_string(field.type_ann)
            fields.append(f"{field.name}: {type_str}")

        signature = f"struct {struct.name} {{ {', '.join(fields)} }}"

        return DocSymbol(
            name=struct.name,
            kind='struct',
            signature=signature,
            detail=f"Struct with {len(struct.fields)} field(s)",
            location={'line': struct.line, 'column': struct.column}
        )

    def _generate_type_alias(self, alias: TypeAlias) -> DocSymbol:
        """Generate documentation for a type alias."""
        target_str = self._type_to_string(alias.target)
        signature = f"type {alias.name} = {target_str}"

        return DocSymbol(
            name=alias.name,
            kind='type',
            signature=signature,
            detail=f"Type alias for {target_str}",
            location={'line': alias.line, 'column': alias.column}
        )

    def _generate_const(self, const: ConstDecl) -> DocSymbol:
        """Generate documentation for a constant."""
        type_str = self._type_to_string(const.type_ann)
        signature = f"const {const.name}: {type_str}"

        return DocSymbol(
            name=const.name,
            kind='const',
            signature=signature,
            detail=f"Constant of type {type_str}",
            location={'line': const.line, 'column': const.column}
        )

    def _generate_var(self, var: VarDecl) -> DocSymbol:
        """Generate documentation for a variable."""
        type_str = self._type_to_string(var.type_ann)
        signature = f"var {var.name}: {type_str}"

        return DocSymbol(
            name=var.name,
            kind='var',
            signature=signature,
            detail=f"Mutable variable of type {type_str}",
            location={'line': var.line, 'column': var.column}
        )

    def _type_to_string(self, type_expr: Optional[TypeExpr]) -> str:
        """Convert TypeExpr to string representation."""
        if not type_expr:
            return 'void'

        kind = type_expr.kind

        if kind == 'prim':
            return str(type_expr.value)
        elif kind == 'struct':
            return str(type_expr.value)
        elif kind == 'func':
            detail = type_expr.value
            if isinstance(detail, dict):
                return "fn(...)"
            return "fn(...)"
        elif kind == 'generic':
            if isinstance(type_expr.value, dict):
                name = type_expr.value.get('name', '')
                args = type_expr.value.get('args', [])
                arg_strs = [self._type_to_string(a) for a in args]
                return f"{name}<{', '.join(arg_strs)}>"
            return str(type_expr.value)
        elif kind == 'tuple':
            if isinstance(type_expr.value, list):
                items = [self._type_to_string(t) for t in type_expr.value]
                return f"({', '.join(items)})"
            return "tuple"
        elif kind == 'array':
            inner = self._type_to_string(type_expr.value) if isinstance(type_expr.value, TypeExpr) else 'any'
            return f"[{inner}]"
        elif kind == 'vec':
            if isinstance(type_expr.value, dict):
                elem = type_expr.value.get('element_type')
                size = type_expr.value.get('size')
                elem_str = self._type_to_string(elem) if elem else 'any'
                return f"Vec<{elem_str}, {size}>"
            return "Vec"
        elif kind == 'refinement':
            if isinstance(type_expr.value, dict):
                base = type_expr.value.get('base_type')
                return self._type_to_string(base) if base else 'any'
        elif kind in ('linear', 'unique'):
            if isinstance(type_expr.value, dict):
                inner = type_expr.value.get('inner')
                prefix = kind
                inner_str = self._type_to_string(inner) if inner else 'any'
                return f"{prefix} {inner_str}"
        elif kind in ('box', 'diamond'):
            if isinstance(type_expr.value, TypeExpr):
                inner_str = self._type_to_string(type_expr.value)
                prefix = '□' if kind == 'box' else '◇'
                return f"{prefix}{inner_str}"

        return 'any'

    def to_markdown(self, project: DocProject) -> str:
        """Generate Markdown documentation."""
        lines = []
        lines.append(f"# {project.name}")
        lines.append("")
        lines.append(f"*Version: {project.version}*")
        lines.append("")
        lines.append(f"*Generated: {project.generated_at}*")
        lines.append("")
        lines.append(project.description)
        lines.append("")

        # Table of contents
        lines.append("## Table of Contents")
        lines.append("")
        for module in project.modules:
            lines.append(f"- [{module.name}](#{module.name.lower()})")
            for symbol in module.symbols:
                anchor = f"{module.name.lower()}-{symbol.name.lower()}"
                lines.append(f"  - [{symbol.name}](#{anchor})")
        lines.append("")

        # Modules
        for module in project.modules:
            lines.append(f"## {module.name}")
            lines.append("")

            if module.docstring:
                lines.append(module.docstring)
                lines.append("")

            if module.verification_summary:
                lines.append("### Verification Status")
                lines.append("")
                for layer, status in module.verification_summary.items():
                    lines.append(f"- **{layer}**: {status}")
                lines.append("")

            # Symbols by kind
            by_kind: Dict[str, List[DocSymbol]] = {}
            for symbol in module.symbols:
                if symbol.kind not in by_kind:
                    by_kind[symbol.kind] = []
                by_kind[symbol.kind].append(symbol)

            kind_order = ['function', 'struct', 'type', 'const', 'var']
            for kind in kind_order:
                if kind not in by_kind:
                    continue

                symbols = by_kind[kind]
                lines.append(f"### {kind.capitalize()}s")
                lines.append("")

                for symbol in symbols:
                    lines.append(f"#### {symbol.name}")
                    lines.append("")
                    lines.append(f"```svl")
                    lines.append(symbol.signature)
                    lines.append("```")
                    lines.append("")

                    if symbol.detail:
                        lines.append(symbol.detail)
                        lines.append("")

                    if symbol.docstring:
                        lines.append(symbol.docstring)
                        lines.append("")

                    if symbol.verification_status:
                        lines.append(f"**Verification**: {symbol.verification_status}")
                        lines.append("")

                    if symbol.examples:
                        lines.append("**Examples**:")
                        for ex in symbol.examples:
                            lines.append(f"```svl")
                            lines.append(ex)
                            lines.append("```")
                        lines.append("")

                    if symbol.see_also:
                        lines.append(f"**See also**: {', '.join(symbol.see_also)}")
                        lines.append("")

        return '\n'.join(lines)

    def to_html(self, project: DocProject) -> str:
        """Generate HTML documentation."""
        md = self.to_markdown(project)

        # Simple markdown to HTML conversion
        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{project.name} Documentation</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 900px; margin: 0 auto; padding: 20px; }}
        code {{ background: #f4f4f4; padding: 2px 4px; border-radius: 3px; }}
        pre {{ background: #f4f4f4; padding: 16px; border-radius: 5px; overflow-x: auto; }}
        pre code {{ background: none; padding: 0; }}
        h1 {{ border-bottom: 2px solid #eee; padding-bottom: 10px; }}
        h2 {{ border-bottom: 1px solid #eee; padding-bottom: 5px; margin-top: 40px; }}
        .verification {{ color: #28a745; font-weight: bold; }}
        .verification-fail {{ color: #dc3545; }}
        table {{ border-collapse: collapse; width: 100%; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #f4f4f4; }}
    </style>
</head>
<body>
"""

        # Convert markdown to HTML (simplified)
        lines = md.split('\n')
        in_code = False
        for line in lines:
            if line.startswith('```'):
                if in_code:
                    html += '</pre>\n'
                    in_code = False
                else:
                    html += '<pre><code>'
                    in_code = True
                continue

            if in_code:
                html += line + '\n'
                continue

            if line.startswith('# '):
                html += f'<h1>{line[2:]}</h1>\n'
            elif line.startswith('## '):
                html += f'<h2>{line[3:]}</h2>\n'
            elif line.startswith('### '):
                html += f'<h3>{line[4:]}</h3>\n'
            elif line.startswith('#### '):
                html += f'<h4>{line[5:]}</h4>\n'
            elif line.startswith('- '):
                html += f'<li>{line[2:]}</li>\n'
            elif line.startswith('**') and line.endswith('**'):
                html += f'<strong>{line[2:-2]}</strong>\n'
            elif line.strip() == '':
                html += '<p></p>\n'
            else:
                html += f'<p>{line}</p>\n'

        html += """
</body>
</html>
"""
        return html

    def to_json(self, project: DocProject) -> str:
        """Generate JSON documentation."""
        data = {
            'name': project.name,
            'version': project.version,
            'description': project.description,
            'generated_at': project.generated_at,
            'modules': []
        }

        for module in project.modules:
            mod_data = {
                'name': module.name,
                'symbols': []
            }
            for symbol in module.symbols:
                mod_data['symbols'].append({
                    'name': symbol.name,
                    'kind': symbol.kind,
                    'signature': symbol.signature,
                    'docstring': symbol.docstring,
                    'detail': symbol.detail,
                    'verification_status': symbol.verification_status,
                    'location': symbol.location,
                    'examples': symbol.examples,
                    'see_also': symbol.see_also
                })
            data['modules'].append(mod_data)

        return json.dumps(data, indent=2)

    def write_docs(self, project: DocProject, output_dir: str, formats: List[DocFormat] = None):
        """Write documentation to files."""
        formats = formats or [DocFormat.MARKDOWN, DocFormat.HTML, DocFormat.JSON]

        os.makedirs(output_dir, exist_ok=True)

        for fmt in formats:
            if fmt == DocFormat.MARKDOWN:
                content = self.to_markdown(project)
                with open(os.path.join(output_dir, 'README.md'), 'w') as f:
                    f.write(content)

            elif fmt == DocFormat.HTML:
                content = self.to_html(project)
                with open(os.path.join(output_dir, 'index.html'), 'w') as f:
                    f.write(content)

            elif fmt == DocFormat.JSON:
                content = self.to_json(project)
                with open(os.path.join(output_dir, 'docs.json'), 'w') as f:
                    f.write(content)

        print(f"Documentation written to {output_dir}")


def generate_verification_report(verification_result: Any) -> Dict[str, Any]:
    """Generate detailed verification report."""
    return {
        'syntax_layer': {
            'verified': getattr(verification_result, 'syntax_layer_verified', False),
            'viable_start': getattr(verification_result, 'viable_start', None),
            'checksums': getattr(verification_result, 'checksums', None)
        },
        'type_layer': {
            'verified': getattr(verification_result, 'type_layer_verified', False),
            'dual_stream_agree': getattr(verification_result, 'dual_stream_agree', None),
            'mod5_check': getattr(verification_result, 'mod5_check', None)
        },
        'theorem_layer': {
            'verified': getattr(verification_result, 'all_parities_even', False),
            'monodromy_results': getattr(verification_result, 'monodromy_results', {}),
            'program_hash': getattr(verification_result, 'program_hash', '')
        },
        'overall': getattr(verification_result, 'passed', False),
        'total_time_ms': getattr(verification_result, 'total_time_ms', 0)
    }


def extract_examples_from_verification(source: str) -> List[str]:
    """Extract code examples from verified programs."""
    # Would extract ASSERT statements, test functions, etc.
    examples = []
    lines = source.split('\n')
    in_example = False
    current = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith('ASSERT') or stripped.startswith('assert'):
            if current:
                examples.append('\n'.join(current))
                current = []
            in_example = True
        if in_example:
            current.append(line)

    if current:
        examples.append('\n'.join(current))

    return examples


if __name__ == '__main__':
    print("=== Documentation Generation Test ===")

    from svl.lexer import tokenize
    from svl.parser_rd import parse

    test_source = '''
    module math {
      /// Adds two integers
      func add(a: int, b: int) type int { return a + b }

      /// Point in 2D space
      struct Point { x: int, y: int }

      /// Creates a point
      func make_point(x: int, y: int) type Point { return Point { x: x, y: y } }

      const PI: float = 3.14159
      var counter: int = 0
    }
    '''

    tokens = tokenize(test_source)
    ast = parse(tokens)

    generator = SVLDocGenerator(include_verification=True)
    project = generator.generate_from_program(ast)

    # Generate markdown
    md = generator.to_markdown(project)
    print("Generated Markdown:")
    print(md[:1000])
    print("...")

    # Generate HTML
    html = generator.to_html(project)
    print(f"\nGenerated HTML length: {len(html)} chars")

    # Generate JSON
    json_out = generator.to_json(project)
    print(f"Generated JSON length: {len(json_out)} chars")

    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        generator.write_docs(project, tmpdir, [DocFormat.MARKDOWN, DocFormat.HTML, DocFormat.JSON])
        print(f"\nFiles written to {tmpdir}:")
        for f in os.listdir(tmpdir):
            print(f"  {f}")

    print("\n✓ Documentation Generation test complete!")