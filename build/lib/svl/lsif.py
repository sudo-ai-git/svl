# svl/lsif.py
# LSIF (Language Server Index Format) for Code Navigation (H46)
# Emits LSIF data for SVL programs

from typing import Dict, List, Optional, Any, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
import json
import os
from pathlib import Path

from svl.parser_rd import (
    Program, Module, FuncDecl, StructDecl, TypeAlias, ConstDecl, VarDecl,
    Block, LetStmt, IfStmt, WhileStmt, ForStmt, ReturnStmt, AssertStmt,
    BinaryExpr, Ident, Literal, CallExpr, IndexExpr, FieldAccess,
    Param, TypeExpr, NodeType
)


class LsifVertexType(Enum):
    """LSIF vertex types."""
    PROJECT = "project"
    DOCUMENT = "document"
    RANGE = "range"
    HOVER_RESULT = "hoverResult"
    DEFINITION_RESULT = "definitionResult"
    REFERENCE_RESULT = "referenceResult"
    TYPE_DEFINITION_RESULT = "typeDefinitionResult"
    IMPLEMENTATION_RESULT = "implementationResult"
    ITEM = "item"  # Generic item (class, interface, method, etc.)


class LsifEdgeType(Enum):
    """LSIF edge types."""
    CONTAINS = "contains"
    NEXT = "next"
    TEXT_DOCUMENT = "textDocument/definition"
    DEFINITION = "definition"
    REFERENCE = "reference"
    TYPE_DEFINITION = "typeDefinition"
    IMPLEMENTATION = "implementation"
    HOVER = "hover"
    DOCUMENTATION = "documentation"


@dataclass
class LsifVertex:
    """LSIF vertex."""
    id: int
    type: str
    label: Optional[str] = None
    uri: Optional[str] = None
    range: Optional[Dict[str, int]] = None
    document: Optional[int] = None
    tag: Optional[str] = None
    kind: Optional[int] = None  # SymbolKind
    detail: Optional[str] = None
    documentation: Optional[str] = None
    result: Optional[Any] = None

    def to_dict(self) -> Dict[str, Any]:
        d = {'id': self.id, 'type': self.type}
        for k, v in self.__dict__.items():
            if k != 'id' and k != 'type' and v is not None:
                d[k] = v
        return d


@dataclass
class LsifEdge:
    """LSIF edge."""
    id: int
    type: str
    outV: int
    inV: int
    label: Optional[str] = None
    property: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        d = {'id': self.id, 'type': self.type, 'outV': self.outV, 'inV': self.inV}
        if self.label is not None:
            d['label'] = self.label
        if self.property is not None:
            d['property'] = self.property
        return d


class LsifEmitter:
    """Emits LSIF data for SVL programs."""

    def __init__(self, project_root: str):
        self.project_root = Path(project_root).resolve()
        self.vertices: List[LsifVertex] = []
        self.edges: List[LsifEdge] = []
        self._next_id = 1
        self._symbol_ids: Dict[str, int] = {}  # symbol_key -> vertex_id
        self._doc_ids: Dict[str, int] = {}  # file_path -> vertex_id
        self._range_ids: Dict[Tuple[str, int, int, int, int], int] = {}  # (file, sl, sc, el, ec) -> vertex_id

    def _new_id(self) -> int:
        """Generate new vertex/edge ID."""
        id = self._next_id
        self._next_id += 1
        return id

    def _get_range_key(self, file_path: str, start_line: int, start_col: int,
                       end_line: int, end_col: int) -> Tuple:
        return (file_path, start_line, start_col, end_line, end_col)

    def _get_or_create_range(self, file_path: str, start_line: int, start_col: int,
                              end_line: int, end_col: int) -> int:
        """Get or create range vertex."""
        key = self._get_range_key(file_path, start_line, start_col, end_line, end_col)
        if key in self._range_ids:
            return self._range_ids[key]

        range_id = self._new_id()
        self._range_ids[key] = range_id

        vertex = LsifVertex(
            id=range_id,
            type='range',
            range={
                'start': {'line': start_line, 'character': start_col},
                'end': {'line': end_line, 'character': end_col}
            }
        )
        self.vertices.append(vertex)
        return range_id

    def _get_or_create_document(self, file_path: str) -> int:
        """Get or create document vertex."""
        if file_path in self._doc_ids:
            return self._doc_ids[file_path]

        doc_id = self._new_id()
        self._doc_ids[file_path] = doc_id

        # Convert to file:// URI
        abs_path = (self.project_root / file_path).resolve()
        uri = abs_path.as_uri()

        vertex = LsifVertex(
            id=doc_id,
            type='document',
            uri=uri,
            label=file_path
        )
        self.vertices.append(vertex)
        return doc_id

    def emit_program(self, program: Program, file_path: str) -> str:
        """Emit LSIF for entire program."""
        # Create project vertex
        project_id = self._new_id()
        self.vertices.append(LsifVertex(
            id=project_id,
            type='project',
            label='SVL Project'
        ))

        # Create document vertex
        doc_id = self._get_or_create_document(file_path)

        # Project contains document
        self.edges.append(LsifEdge(
            id=self._new_id(),
            type='contains',
            outV=project_id,
            inV=doc_id,
            label='contains'
        ))

        # Process modules
        for module in program.modules:
            self._emit_module(module, doc_id, file_path)

        # Generate LSIF output
        return self._generate_output()

    def _emit_module(self, module: Module, doc_id: int, file_path: str):
        """Emit module and its contents."""
        # Module range
        if module.body.statements:
            first = module.body.statements[0]
            last = module.body.statements[-1]
            module_range = self._get_or_create_range(
                file_path, first.line, first.column, last.line, last.column
            )
        else:
            module_range = self._get_or_create_range(file_path, 1, 1, 1, 1)

        # Module item
        module_id = self._new_id()
        self._symbol_ids[f"{module.name}"] = module_id
        self.vertices.append(LsifVertex(
            id=module_id,
            type='item',
            label=module.name,
            kind=5,  # Module
            detail=f"module {module.name}"
        ))

        # Document contains module range
        self.edges.append(LsifEdge(
            id=self._new_id(),
            type='contains',
            outV=doc_id,
            inV=module_range,
            label='contains'
        ))

        # Module range -> module item
        self.edges.append(LsifEdge(
            id=self._new_id(),
            type='item',
            outV=module_range,
            inV=module_id,
            label='item'
        ))

        # Process module contents
        for item in module.body.statements:
            self._emit_item(item, module_id, doc_id, file_path)

    def _emit_item(self, item: Any, parent_id: int, doc_id: int, file_path: str):
        """Emit a top-level item."""
        if isinstance(item, FuncDecl):
            self._emit_function(item, parent_id, doc_id, file_path)
        elif isinstance(item, StructDecl):
            self._emit_struct(item, parent_id, doc_id, file_path)
        elif isinstance(item, TypeAlias):
            self._emit_type_alias(item, parent_id, doc_id, file_path)
        elif isinstance(item, ConstDecl):
            self._emit_const(item, parent_id, doc_id, file_path)
        elif isinstance(item, VarDecl):
            self._emit_var(item, parent_id, doc_id, file_path)

    def _emit_function(self, func: FuncDecl, parent_id: int, doc_id: int, file_path: str):
        """Emit function."""
        # Function range
        func_range = self._get_or_create_range(
            file_path, func.line, func.column,
            func.body.line if hasattr(func.body, 'line') else func.line + 10,
            func.body.column if hasattr(func.body, 'column') else func.column + 10
        )

        # Function item
        func_id = self._new_id()
        key = f"{func.name}"
        self._symbol_ids[key] = func_id

        params = ', '.join(p.name for p in func.params)
        ret = func.return_type.value if func.return_type and func.return_type.kind == 'prim' else 'void'

        self.vertices.append(LsifVertex(
            id=func_id,
            type='item',
            label=func.name,
            kind=6,  # Function
            detail=f"func {func.name}({params}) -> {ret}"
        ))

        # Edges
        self.edges.append(LsifEdge(
            id=self._new_id(), type='contains', outV=parent_id, inV=func_range, label='contains'
        ))
        self.edges.append(LsifEdge(
            id=self._new_id(), type='item', outV=func_range, inV=func_id, label='item'
        ))

        # Parameters
        for param in func.params:
            self._emit_param(param, func_id, doc_id, file_path)

        # Function body references
        self._emit_block_references(func.body, func_id, doc_id, file_path)

    def _emit_param(self, param: Param, func_id: int, doc_id: int, file_path: str):
        """Emit function parameter."""
        param_id = self._new_id()
        self._symbol_ids[f"{param.name}"] = param_id

        type_str = param.type_ann.value if param.type_ann and param.type_ann.kind == 'prim' else 'any'

        self.vertices.append(LsifVertex(
            id=param_id,
            type='item',
            label=param.name,
            kind=12,  # Variable
            detail=f"param {param.name}: {type_str}"
        ))

        self.edges.append(LsifEdge(
            id=self._new_id(), type='contains', outV=func_id, inV=param_id, label='contains'
        ))

    def _emit_struct(self, struct: StructDecl, parent_id: int, doc_id: int, file_path: str):
        """Emit struct."""
        struct_id = self._new_id()
        self._symbol_ids[struct.name] = struct_id

        self.vertices.append(LsifVertex(
            id=struct_id,
            type='item',
            label=struct.name,
            kind=5,  # Class/Struct
            detail=f"struct {struct.name}"
        ))

        self.edges.append(LsifEdge(
            id=self._new_id(), type='contains', outV=parent_id, inV=struct_id, label='contains'
        ))

        # Fields
        for field in struct.fields:
            field_id = self._new_id()
            type_str = field.type_ann.value if field.type_ann and field.type_ann.kind == 'prim' else 'any'

            self.vertices.append(LsifVertex(
                id=field_id,
                type='item',
                label=field.name,
                kind=7,  # Field
                detail=f"field {field.name}: {type_str}"
            ))

            self.edges.append(LsifEdge(
                id=self._new_id(), type='contains', outV=struct_id, inV=field_id, label='contains'
            ))

    def _emit_type_alias(self, alias: TypeAlias, parent_id: int, doc_id: int, file_path: str):
        """Emit type alias."""
        alias_id = self._new_id()
        self._symbol_ids[alias.name] = alias_id

        self.vertices.append(LsifVertex(
            id=alias_id,
            type='item',
            label=alias.name,
            kind=15,  # TypeParameter
            detail=f"type {alias.name} = ..."
        ))

        self.edges.append(LsifEdge(
            id=self._new_id(), type='contains', outV=parent_id, inV=alias_id, label='contains'
        ))

    def _emit_const(self, const: ConstDecl, parent_id: int, doc_id: int, file_path: str):
        """Emit constant."""
        const_id = self._new_id()
        self._symbol_ids[const.name] = const_id

        type_str = const.type_ann.value if const.type_ann and const.type_ann.kind == 'prim' else 'any'

        self.vertices.append(LsifVertex(
            id=const_id,
            type='item',
            label=const.name,
            kind=13,  # Constant
            detail=f"const {const.name}: {type_str}"
        ))

        self.edges.append(LsifEdge(
            id=self._new_id(), type='contains', outV=parent_id, inV=const_id, label='contains'
        ))

    def _emit_var(self, var: VarDecl, parent_id: int, doc_id: int, file_path: str):
        """Emit variable."""
        var_id = self._new_id()
        self._symbol_ids[var.name] = var_id

        type_str = var.type_ann.value if var.type_ann and var.type_ann.kind == 'prim' else 'any'

        self.vertices.append(LsifVertex(
            id=var_id,
            type='item',
            label=var.name,
            kind=12,  # Variable
            detail=f"var {var.name}: {type_str}"
        ))

        self.edges.append(LsifEdge(
            id=self._new_id(), type='contains', outV=parent_id, inV=var_id, label='contains'
        ))

    def _emit_block_references(self, block: Block, scope_id: int, doc_id: int, file_path: str):
        """Emit references in block."""
        for stmt in block.statements:
            self._emit_stmt_references(stmt, scope_id, doc_id, file_path)

    def _emit_stmt_references(self, stmt: Any, scope_id: int, doc_id: int, file_path: str):
        """Emit references in statement."""
        if isinstance(stmt, LetStmt):
            # Variable declaration reference
            range_id = self._get_or_create_range(file_path, stmt.line, stmt.column, stmt.line, stmt.column + 20)
            self.edges.append(LsifEdge(
                id=self._new_id(), type='definition', outV=range_id, inV=scope_id, label='definition'
            ))

            # Value references
            self._emit_expr_references(stmt.value, scope_id, doc_id, file_path)

        elif isinstance(stmt, CallExpr):
            # Function call reference
            range_id = self._get_or_create_range(file_path, stmt.line, stmt.column, stmt.line, stmt.column + len(stmt.callee))
            if stmt.callee in self._symbol_ids:
                self.edges.append(LsifEdge(
                    id=self._new_id(), type='reference', outV=range_id, inV=self._symbol_ids[stmt.callee], label='reference'
                ))

            for arg in stmt.arguments:
                self._emit_expr_references(arg, scope_id, doc_id, file_path)

        elif isinstance(stmt, Ident):
            # Identifier reference
            range_id = self._get_or_create_range(file_path, stmt.line, stmt.column, stmt.line, stmt.column + len(stmt.name))
            if stmt.name in self._symbol_ids:
                self.edges.append(LsifEdge(
                    id=self._new_id(), type='reference', outV=range_id, inV=self._symbol_ids[stmt.name], label='reference'
                ))

        elif isinstance(stmt, IfStmt):
            self._emit_expr_references(stmt.condition, scope_id, doc_id, file_path)
            self._emit_block_references(stmt.then_branch, scope_id, doc_id, file_path)
            if stmt.else_branch:
                self._emit_block_references(stmt.else_branch, scope_id, doc_id, file_path)

        elif isinstance(stmt, WhileStmt):
            self._emit_expr_references(stmt.condition, scope_id, doc_id, file_path)
            self._emit_block_references(stmt.body, scope_id, doc_id, file_path)

        elif isinstance(stmt, ForStmt):
            self._emit_expr_references(stmt.iter_expr, scope_id, doc_id, file_path)
            self._emit_block_references(stmt.body, scope_id, doc_id, file_path)

        elif isinstance(stmt, ReturnStmt):
            if stmt.value:
                self._emit_expr_references(stmt.value, scope_id, doc_id, file_path)

        elif isinstance(stmt, Block):
            self._emit_block_references(stmt, scope_id, doc_id, file_path)

    def _emit_expr_references(self, expr: Any, scope_id: int, doc_id: int, file_path: str):
        """Emit references in expression."""
        if isinstance(expr, CallExpr):
            range_id = self._get_or_create_range(file_path, expr.line, expr.column, expr.line, expr.column + len(expr.callee))
            if expr.callee in self._symbol_ids:
                self.edges.append(LsifEdge(
                    id=self._new_id(), type='reference', outV=range_id, inV=self._symbol_ids[expr.callee], label='reference'
                ))
            for arg in expr.arguments:
                self._emit_expr_references(arg, scope_id, doc_id, file_path)

        elif isinstance(expr, Ident):
            range_id = self._get_or_create_range(file_path, expr.line, expr.column, expr.line, expr.column + len(expr.name))
            if expr.name in self._symbol_ids:
                self.edges.append(LsifEdge(
                    id=self._new_id(), type='reference', outV=range_id, inV=self._symbol_ids[expr.name], label='reference'
                ))

        elif isinstance(expr, BinaryExpr):
            self._emit_expr_references(expr.left, scope_id, doc_id, file_path)
            self._emit_expr_references(expr.right, scope_id, doc_id, file_path)

        elif isinstance(expr, IndexExpr):
            self._emit_expr_references(expr.left, scope_id, doc_id, file_path)
            self._emit_expr_references(expr.right, scope_id, doc_id, file_path)

        elif isinstance(expr, FieldAccess):
            self._emit_expr_references(expr.left, scope_id, doc_id, file_path)
            # Field access - would need type info to resolve

    def _generate_output(self) -> str:
        """Generate LSIF output as JSON lines."""
        lines = []

        # Header
        lines.append(json.dumps({
            "lsif": "0.6.0",
            "projectRoot": self.project_root.as_uri(),
            "toolInfo": {
                "name": "svl-lsif",
                "version": "0.1.0"
            }
        }))

        # Vertices
        for v in self.vertices:
            lines.append(json.dumps(v.to_dict()))

        # Edges
        for e in self.edges:
            lines.append(json.dumps(e.to_dict()))

        return '\n'.join(lines)

    def write_lsif(self, output_path: str):
        """Write LSIF to file."""
        with open(output_path, 'w') as f:
            f.write(self._generate_output())


def generate_lsif_for_svl(source: str, file_path: str, project_root: str, output_path: str):
    """Generate LSIF for SVL source file."""
    from svl.lexer import tokenize
    from svl.parser_rd import parse

    tokens = tokenize(source)
    ast = parse(tokens)

    emitter = LsifEmitter(project_root)
    emitter.emit_program(ast, file_path)
    emitter.write_lsif(output_path)


def generate_lsif_for_program(program: Program, file_path: str, project_root: str, output_path: str):
    """Generate LSIF for parsed SVL program."""
    emitter = LsifEmitter(project_root)
    emitter.emit_program(program, file_path)
    emitter.write_lsif(output_path)


if __name__ == '__main__':
    print("=== LSIF Generation Test ===")

    from svl.lexer import tokenize
    from svl.parser_rd import parse

    test_source = '''
    module math {
      struct Point { x: int, y: int }

      func add(a: int, b: int) type int { return a + b }
      func make_point(x: int, y: int) type Point { return Point { x: x, y: y } }
      func distance(p1: Point, p2: Point) type float { return 0.0 }
    }
    '''

    tokens = tokenize(test_source)
    ast = parse(tokens)

    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        output = os.path.join(tmpdir, 'output.lsif')
        emitter = LsifEmitter(tmpdir)
        emitter.emit_program(ast, 'math.svl')
        emitter.write_lsif(output)

        # Read and display
        with open(output, 'r') as f:
            lines = f.readlines()

        print(f"Generated {len(lines)} LSIF lines")
        for line in lines[:10]:
            print(line.strip())
        print("...")

        # Count vertices and edges
        vertices = sum(1 for l in lines if '"type":"item"' in l or '"type":"range"' in l or '"type":"document"' in l or '"type":"project"' in l)
        edges = sum(1 for l in lines if '"type":"contains"' in l or '"type":"reference"' in l or '"type":"definition"' in l or '"type":"item"' in l)
        print(f"Vertices: {vertices}, Edges: {edges}")

    print("\n✓ LSIF Generation test complete!")