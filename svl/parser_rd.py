# svl/parser_rd.py
# Recursive Descent Parser for SVL (Spike S2-A)
# Based on the grammar in BUILD_PLAN_2_SELF_VERIFYING_LANGUAGE.md

from typing import List, Optional, Union, Dict, Any
from dataclasses import dataclass, field
from enum import Enum

from svl.lexer import Token, TokenType, tokenize


# AST Node Types
class NodeType(Enum):
    PROGRAM = "Program"
    MODULE = "Module"
    IMPORT = "Import"
    EXPORT = "Export"
    FUNC_DECL = "FuncDecl"
    STRUCT_DECL = "StructDecl"
    TYPE_ALIAS = "TypeAlias"
    CONST_DECL = "ConstDecl"
    VAR_DECL = "VarDecl"
    BLOCK = "Block"
    LET_STMT = "LetStmt"
    IF_STMT = "IfStmt"
    WHILE_STMT = "WhileStmt"
    FOR_STMT = "ForStmt"
    RETURN_STMT = "ReturnStmt"
    ASSERT_STMT = "AssertStmt"
    TRY_STMT = "TryStmt"
    EXPR_STMT = "ExprStmt"
    BINARY_EXPR = "BinaryExpr"
    UNARY_EXPR = "UnaryExpr"
    CALL_EXPR = "CallExpr"
    MATCH_EXPR = "MatchExpr"
    AWAIT_EXPR = "AwaitExpr"
    LAMBDA_EXPR = "LambdaExpr"
    STRUCT_LIT = "StructLit"
    ARRAY_LIT = "ArrayLit"
    IDENT = "Ident"
    LITERAL = "Literal"
    # Effect nodes (H2: Effect System)
    EFFECT_ROW = "EffectRow"
    EFFECT_DECL = "EffectDecl"
    HANDLE_EXPR = "HandleExpr"
    # Linear/Uniqueness type qualifiers (H3: Linear Types)
    LINEAR_TYPE = "LinearType"
    UNIQUE_TYPE = "UniqueType"
    # Dependent type nodes (H4: Dependent Types)
    VEC_TYPE = "VecType"
    # Gradual typing nodes (H5: Gradual Typing)
    DYNAMIC_TYPE = "DynamicType"
    CAST_EXPR = "CastExpr"
    # Macro system nodes (H6: Macro System)
    MACRO_DECL = "MacroDecl"
    MACRO_RULE = "MacroRule"
    # Module functor nodes (H7: Module Functors)
    MODULE_TYPE_DECL = "ModuleTypeDecl"
    MODULE_FUNCTOR_DECL = "ModuleFunctorDecl"
    # Algebraic effects nodes (H8: Algebraic Effects)
    EFFECT_OPERATION = "EffectOperation"
    HANDLE_CASE = "HandleCase"
    # Type class nodes (H9: Type Classes)
    CLASS_DECL = "ClassDecl"
    INSTANCE_DECL = "InstanceDecl"
    CLASS_METHOD = "ClassMethod"
    # Higher-kinded type nodes (H10: HKT)
    KIND_STAR_TYPE = "KindStar"
    KIND_ARROW_TYPE = "KindArrow"
    HKT_APPLICATION = "HKTApplication"
    # Modal type nodes (H16: Modal Types)
    BOX_TYPE = "BoxType"
    DIAMOND_TYPE = "DiamondType"
    # Refinement type nodes (H11: Refinement Types)
    REFINEMENT_TYPE = "RefinementType"
    # Quantified constraint nodes (H13: Quantified Constraints)
    FORALL_CONSTRAINT = "ForallConstraint"
    IMPLIES_CONSTRAINT = "ImpliesConstraint"
    CASE_CLAUSE = "CaseClause"
    PATTERN = "Pattern"
    FIELD_INIT = "FieldInit"
    PARAM = "Param"
    FIELD = "Field"
    TYPE_EXPR = "TypeExpr"
    PRIM_TYPE = "PrimType"
    STRUCT_TYPE = "StructType"
    FUNC_TYPE = "FuncType"
    GENERIC_TYPE = "GenericType"
    TUPLE_TYPE = "TupleType"
    ARRAY_TYPE = "ArrayType"
    TERNARY_EXPR = "TernaryExpr"
    # Version nodes (H1: Semantic Versioning)
    VERSION = "Version"
    VERSION_CONSTRAINT = "VersionConstraint"


@dataclass
class ASTNode:
    type: NodeType
    line: int
    column: int
    offset: int

    def to_dict(self):
        return {k: v for k, v in self.__dict__.items() if not k.startswith('_')}


@dataclass
class Program(ASTNode):
    modules: List['Module']
    imports: List['Import']
    exports: List['Export']
    items: List['TopLevelItem']


@dataclass
class Version(ASTNode):
    major: int
    minor: int
    patch: int
    pre_release: Optional[str] = None
    build: Optional[str] = None


@dataclass
class VersionConstraint(ASTNode):
    operator: str  # ^, ~, >=, <=, >, <, =
    version: 'Version'


@dataclass
class Module(ASTNode):
    name: str
    body: 'Block'
    version: Optional['Version'] = None


@dataclass
class Import(ASTNode):
    path: str
    version_constraint: Optional['VersionConstraint'] = None


@dataclass
class Export(ASTNode):
    name: str


@dataclass
class FuncDecl(ASTNode):
    name: str
    params: List['Param']
    return_type: Optional['TypeExpr']
    body: 'Block'
    effects: Optional['EffectRow'] = None


@dataclass
class StructDecl(ASTNode):
    name: str
    fields: List['Field']


@dataclass
class TypeAlias(ASTNode):
    name: str
    type_params: List[str]
    target: 'TypeExpr'


@dataclass
class ConstDecl(ASTNode):
    name: str
    type_ann: Optional['TypeExpr']
    value: 'Expr'


@dataclass
class VarDecl(ASTNode):
    name: str
    type_ann: Optional['TypeExpr']
    value: 'Expr'


@dataclass
class Block(ASTNode):
    statements: List['Stmt']


TopLevelItem = Union['FuncDecl', 'StructDecl', 'ConstDecl', 'VarDecl', 'TypeAlias', 'MacroDecl', 'ModuleTypeDecl', 'ModuleFunctorDecl', 'EffectDecl', 'ClassDecl', 'InstanceDecl']
Stmt = Union['LetStmt', 'IfStmt', 'WhileStmt', 'ForStmt', 'ReturnStmt',
             'AssertStmt', 'TryStmt', 'ExprStmt', 'Block']
Expr = Union['BinaryExpr', 'UnaryExpr', 'CallExpr', 'MatchExpr', 'AwaitExpr',
             'LambdaExpr', 'StructLit', 'ArrayLit', 'Ident', 'Literal',
             'FieldAccess', 'IndexExpr', 'AssignExpr', 'TernaryExpr']


@dataclass
class LetStmt(ASTNode):
    name: str
    type_ann: Optional['TypeExpr']
    value: Expr


@dataclass
class IfStmt(ASTNode):
    condition: Expr
    then_branch: Block
    else_branch: Optional[Block]


@dataclass
class WhileStmt(ASTNode):
    condition: Expr
    body: Block


@dataclass
class ForStmt(ASTNode):
    var: str
    iter_expr: Expr
    body: Block


@dataclass
class ReturnStmt(ASTNode):
    value: Optional[Expr]


@dataclass
class AssertStmt(ASTNode):
    condition: Expr


@dataclass
class TryStmt(ASTNode):
    try_block: Block
    catch_var: str
    catch_type: Optional['TypeExpr']
    catch_block: Block


@dataclass
class ExprStmt(ASTNode):
    expression: Expr


@dataclass
class BinaryExpr(ASTNode):
    left: Expr
    operator: str  # +, -, *, /, %, ==, !=, <, >, <=, >=, &&, ||
    right: Expr


@dataclass
class UnaryExpr(ASTNode):
    operator: str  # -, !, ~
    operand: Expr


@dataclass
class AssignExpr(ASTNode):
    target: 'Ident'
    operator: str  # =, +=, -=, *=, /=, %=, &=, |=, ^=, <<=, >>=
    value: Expr


@dataclass
class TernaryExpr(ASTNode):
    condition: Expr
    then_expr: Expr
    else_expr: Expr


@dataclass
class CallExpr(ASTNode):
    callee: str
    arguments: List[Expr]


@dataclass
class MatchExpr(ASTNode):
    subject: Expr
    cases: List['CaseClause']


@dataclass
class AwaitExpr(ASTNode):
    expression: Expr


@dataclass
class LambdaExpr(ASTNode):
    params: List['Param']
    return_type: Optional['TypeExpr']
    body: Expr


@dataclass
class StructLit(ASTNode):
    name: str
    fields: List['FieldInit']


@dataclass
class ArrayLit(ASTNode):
    elements: List[Expr]


@dataclass
class EffectRow(ASTNode):
    effects: List[str]  # List of effect names


@dataclass
class EffectDecl(ASTNode):
    name: str
    operations: List['EffectOperation']


@dataclass
class EffectOperation(ASTNode):
    name: str
    params: List['Param']
    return_type: Optional['TypeExpr']


@dataclass
class HandleExpr(ASTNode):
    expr: Expr
    handlers: List['EffectHandler']


@dataclass
class EffectHandler(ASTNode):
    effect_name: str
    operation: str
    params: List['Param']
    body: Expr


@dataclass
class LinearType(ASTNode):
    inner_type: 'TypeExpr'


@dataclass
class UniqueType(ASTNode):
    inner_type: 'TypeExpr'


@dataclass
class VecType(ASTNode):
    element_type: 'TypeExpr'
    size: 'Expr'  # Size expression (Nat)


@dataclass
class DynamicType(ASTNode):
    pass


@dataclass
class CastExpr(ASTNode):
    expr: 'Expr'
    target_type: 'TypeExpr'


@dataclass
class MacroDecl(ASTNode):
    name: str
    rules: List['MacroRule']


@dataclass
class MacroRule(ASTNode):
    pattern: List['Token']
    body: 'Expr'


@dataclass
class ModuleTypeDecl(ASTNode):
    name: str
    body: 'Block'


@dataclass
class ModuleFunctorDecl(ASTNode):
    name: str
    param_name: str
    param_type: 'ModuleTypeDecl'
    body: 'Block'


@dataclass
class EffectDecl(ASTNode):
    name: str
    operations: List['EffectOperation']


@dataclass
class EffectOperation(ASTNode):
    name: str
    params: List['Param']
    return_type: Optional['TypeExpr']


@dataclass
class HandleExpr(ASTNode):
    expr: 'Expr'
    cases: List['HandleCase']


@dataclass
class HandleCase(ASTNode):
    effect_name: str
    operation: str
    params: List['Param']
    body: 'Expr'


@dataclass
class ClassDecl(ASTNode):
    name: str
    type_params: List[str]
    constraints: List['TypeExpr']  # superclass constraints
    methods: List['ClassMethod']


@dataclass
class ClassMethod(ASTNode):
    name: str
    params: List['Param']
    return_type: Optional['TypeExpr']


@dataclass
class InstanceDecl(ASTNode):
    class_name: str
    type_args: List['TypeExpr']
    methods: List['FuncDecl']


@dataclass
class KindStar(ASTNode):
    pass


@dataclass
class RefinementType(ASTNode):
    variable: str
    base_type: 'TypeExpr'
    predicate: 'Expr'


@dataclass
class BoxType(ASTNode):
    inner_type: 'TypeExpr'


@dataclass
class DiamondType(ASTNode):
    inner_type: 'TypeExpr'


@dataclass
class IntersectionType(ASTNode):
    types: List['TypeExpr']


@dataclass
class UnionType(ASTNode):
    types: List['TypeExpr']


@dataclass
class ForallConstraint(ASTNode):
    type_vars: List[str]
    constraints: List['TypeExpr']
    body: 'TypeExpr'


@dataclass
class ImpliesConstraint(ASTNode):
    antecedent: 'TypeExpr'
    consequent: 'TypeExpr'


@dataclass
class KindArrow(ASTNode):
    from_kind: 'Kind'
    to_kind: 'Kind'


@dataclass
class HKTApplication(ASTNode):
    constructor: 'TypeExpr'
    args: List['TypeExpr']


@dataclass
class Ident(ASTNode):
    name: str


@dataclass
class Literal(ASTNode):
    value: Union[int, float, str, bool, None]
    literal_type: str  # int, float, string, bool, null


@dataclass
class CaseClause(ASTNode):
    pattern: 'Pattern'
    body: Expr


@dataclass
class Pattern(ASTNode):
    kind: str  # literal, ident, wildcard, struct
    value: Optional[Union[str, 'Pattern', List['FieldPattern']]] = None


@dataclass
class FieldPattern(ASTNode):
    name: str
    pattern: Optional['Pattern'] = None


@dataclass
class FieldInit(ASTNode):
    name: str
    value: Expr


@dataclass
class Param(ASTNode):
    name: str
    type_ann: Optional['TypeExpr']


@dataclass
class Field(ASTNode):
    name: str
    type_ann: Optional['TypeExpr']


@dataclass
class TypeExpr(ASTNode):
    kind: str  # prim, struct, func, generic, tuple, array, linear, unique
    value: Union[str, List['TypeExpr'], 'FuncTypeDetail', 'TypeExpr', Dict[str, Any]]


@dataclass
class FuncTypeDetail:
    params: List['TypeExpr']
    return_type: 'TypeExpr'


class Parser:
    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.pos = 0
        self.current = tokens[0] if tokens else None

    def advance(self):
        self.pos += 1
        if self.pos < len(self.tokens):
            self.current = self.tokens[self.pos]
        return self.current

    def peek(self, offset=1):
        if self.pos + offset < len(self.tokens):
            return self.tokens[self.pos + offset]
        return None

    def match(self, *types: TokenType) -> bool:
        if self.current and self.current.type in types:
            self.advance()
            return True
        return False

    def expect(self, *types: TokenType) -> Token:
        if self.current and self.current.type in types:
            tok = self.current
            self.advance()
            return tok
        raise SyntaxError(f"Expected {types}, got {self.current}")

    def at_end(self) -> bool:
        return self.current is None or self.current.type == TokenType.EOF

    def make_node(self, node_type: NodeType) -> ASTNode:
        return ASTNode(
            type=node_type,
            line=self.current.line if self.current else 0,
            column=self.current.column if self.current else 0,
            offset=self.current.offset if self.current else 0
        )

    # Entry point
    def parse(self) -> Program:
        from svl.parser_rd import ModuleTypeDecl, ModuleFunctorDecl
        modules = []
        imports = []
        exports = []
        items = []

        while not self.at_end():
            # Check for module type / module functor (multi-token lookahead)
            if self.current and self.current.type == TokenType.MODULE:
                # Look ahead to see if next token is TYPE or FUNCTOR
                if self.pos + 1 < len(self.tokens):
                    next_tok = self.tokens[self.pos + 1]
                    if next_tok.type == TokenType.TYPE:
                        # module type Name { ... }
                        self.advance()  # consume MODULE
                        self.advance()  # consume TYPE
                        name_tok = self.expect(TokenType.IDENT)
                        name = name_tok.value
                        body = self.parse_block()
                        items.append(ModuleTypeDecl(
                            type=NodeType.MODULE_TYPE_DECL,
                            line=name_tok.line, column=name_tok.column, offset=name_tok.offset,
                            name=name, body=body
                        ))
                        continue
                    elif next_tok.type == TokenType.MODULE_FUNCTOR:
                        # module functor Name(Param: ModuleType) { ... }
                        self.advance()  # consume MODULE
                        self.advance()  # consume MODULE_FUNCTOR
                        name_tok = self.expect(TokenType.IDENT)
                        name = name_tok.value
                        self.expect(TokenType.LPAREN)
                        param_name_tok = self.expect(TokenType.IDENT)
                        param_name = param_name_tok.value
                        self.expect(TokenType.COLON)
                        # Parse module type reference (just an identifier for now)
                        param_type_ref_tok = self.expect(TokenType.IDENT)
                        param_type = ModuleTypeDecl(
                            type=NodeType.MODULE_TYPE_DECL,
                            line=0, column=0, offset=0,
                            name=param_type_ref_tok.value, body=Block(
                                type=NodeType.BLOCK,
                                line=0, column=0, offset=0,
                                statements=[]
                            )
                        )
                        self.expect(TokenType.RPAREN)
                        body = self.parse_block()
                        items.append(ModuleFunctorDecl(
                            type=NodeType.MODULE_FUNCTOR_DECL,
                            line=name_tok.line, column=name_tok.column, offset=name_tok.offset,
                            name=name, param_name=param_name, param_type=param_type, body=body
                        ))
                        continue
            if self.match(TokenType.MODULE):
                modules.append(self.parse_module())
            elif self.match(TokenType.IMPORT):
                imports.append(self.parse_import())
            elif self.match(TokenType.EXPORT):
                exports.append(self.parse_export())
            else:
                items.append(self.parse_top_level())

        return Program(
            type=NodeType.PROGRAM,
            line=1, column=1, offset=0,
            modules=modules, imports=imports, exports=exports, items=items
        )

    def parse_module(self) -> Module:
        name_tok = self.expect(TokenType.IDENT)
        name = name_tok.value
        version = None
        if self.match(TokenType.AT):
            version = self.parse_version()
        body = self.parse_block()
        return Module(
            type=NodeType.MODULE,
            line=name_tok.line, column=name_tok.column, offset=name_tok.offset,
            name=name, version=version, body=body
        )

    def parse_version(self) -> 'Version':
        # Expect VERSION token (e.g., 1.2.3)
        version_tok = self.expect(TokenType.VERSION)
        parts = version_tok.value.split('.')
        major = int(parts[0]) if len(parts) > 0 else 0
        minor = int(parts[1]) if len(parts) > 1 else 0
        patch = int(parts[2]) if len(parts) > 2 else 0
        pre_release = None
        build = None
        # Check for pre-release (e.g., -beta.1) or build (e.g., +build.123)
        # For simplicity, just store the full string
        return Version(
            type=NodeType.VERSION,
            line=version_tok.line, column=version_tok.column, offset=version_tok.offset,
            major=major, minor=minor, patch=patch,
            pre_release=pre_release, build=build
        )

    def parse_import(self) -> Import:
        path_tok = self.expect(TokenType.STRING)
        path = path_tok.value
        version_constraint = None
        if self.match(TokenType.AT):
            version_constraint = self.parse_version_constraint()
        return Import(
            type=NodeType.IMPORT,
            line=path_tok.line, column=path_tok.column, offset=path_tok.offset,
            path=path, version_constraint=version_constraint
        )

    def parse_version_constraint(self) -> 'VersionConstraint':
        # Expect version constraint operator (^, ~, >=, <=, >, <, =)
        # The lexer emits VERSION_CONSTRAINT for >=, <=, !=
        # But ^ and ~ are tokenized as BITWISE_XOR and BITWISE_NOT
        # And >=, <= are tokenized as GE, LE
        # Accept all of these in version constraint context
        op_tok = None
        if self.current and self.current.type in (TokenType.VERSION_CONSTRAINT, 
                                                  TokenType.BITWISE_XOR,  # ^
                                                  TokenType.BITWISE_NOT,  # ~
                                                  TokenType.GE,           # >=
                                                  TokenType.LE,           # <=
                                                  TokenType.GT,           # >
                                                  TokenType.LT):          # <
            op_tok = self.current
            self.advance()
        else:
            # Fallback: could be bare version (treated as =)
            version_tok = self.expect(TokenType.VERSION)
            parts = version_tok.value.split('.')
            major = int(parts[0]) if len(parts) > 0 else 0
            minor = int(parts[1]) if len(parts) > 1 else 0
            patch = int(parts[2]) if len(parts) > 2 else 0
            version = Version(
                type=NodeType.VERSION,
                line=version_tok.line, column=version_tok.column, offset=version_tok.offset,
                major=major, minor=minor, patch=patch
            )
            return VersionConstraint(
                type=NodeType.VERSION_CONSTRAINT,
                line=version_tok.line, column=version_tok.column, offset=version_tok.offset,
                operator='=', version=version
            )
        
        # Expect version
        version_tok = self.expect(TokenType.VERSION)
        parts = version_tok.value.split('.')
        major = int(parts[0]) if len(parts) > 0 else 0
        minor = int(parts[1]) if len(parts) > 1 else 0
        patch = int(parts[2]) if len(parts) > 2 else 0
        version = Version(
            type=NodeType.VERSION,
            line=version_tok.line, column=version_tok.column, offset=version_tok.offset,
            major=major, minor=minor, patch=patch
        )
        return VersionConstraint(
            type=NodeType.VERSION_CONSTRAINT,
            line=op_tok.line, column=op_tok.column, offset=op_tok.offset,
            operator=op_tok.value, version=version
        )

    def parse_export(self) -> Export:
        name_tok = self.expect(TokenType.IDENT)
        return Export(
            type=NodeType.EXPORT,
            line=name_tok.line, column=name_tok.column, offset=name_tok.offset,
            name=name_tok.value
        )

    def parse_macro_decl(self) -> MacroDecl:
        # Parse: macro name { rule1; rule2; ... } or macro_rules! name { ... }
        name_tok = self.expect(TokenType.IDENT)
        name = name_tok.value
        self.expect(TokenType.LBRACE)
        rules = []
        while not self.match(TokenType.RBRACE) and not self.at_end():
            # Parse macro rule: pattern => body
            # For simplicity, just parse as expression
            pattern_start = self.pos
            pattern_tokens = []
            while self.current and self.current.type not in (TokenType.FAT_ARROW, TokenType.RBRACE, TokenType.SEMICOLON):
                pattern_tokens.append(self.current)
                self.advance()
            if self.match(TokenType.FAT_ARROW):
                body = self.parse_expr()
            else:
                body = Literal(
                    type=NodeType.LITERAL,
                    line=self.current.line, column=self.current.column, offset=self.current.offset,
                    value=None, literal_type='null'
                )
            rules.append(MacroRule(
                type=NodeType.MACRO_RULE,
                line=self.current.line, column=self.current.column, offset=self.current.offset,
                pattern=pattern_tokens, body=body
            ))
            self.match(TokenType.SEMICOLON)
        return MacroDecl(
            type=NodeType.MACRO_DECL,
            line=name_tok.line, column=name_tok.column, offset=name_tok.offset,
            name=name, rules=rules
        )

    def parse_module_type_or_functor(self) -> TopLevelItem:
        """Parse module type or module functor declaration."""
        if self.current and self.current.type == TokenType.MODULE_TYPE:
            # module type Name { ... }
            self.advance()
            name_tok = self.expect(TokenType.IDENT)
            name = name_tok.value
            body = self.parse_block()
            return ModuleTypeDecl(
                type=NodeType.MODULE_TYPE_DECL,
                line=name_tok.line, column=name_tok.column, offset=name_tok.offset,
                name=name, body=body
            )
        elif self.current and self.current.type == TokenType.MODULE_FUNCTOR:
            # module functor Name(Param: ModuleType) { ... }
            self.advance()
            name_tok = self.expect(TokenType.IDENT)
            name = name_tok.value
            self.expect(TokenType.LPAREN)
            param_name_tok = self.expect(TokenType.IDENT)
            param_name = param_name_tok.value
            self.expect(TokenType.COLON)
            param_type = ModuleTypeDecl(
                type=NodeType.MODULE_TYPE_DECL,
                line=param_name_tok.line, column=param_name_tok.column, offset=param_name_tok.offset,
                name=param_name, body=Block(
                    type=NodeType.BLOCK,
                    line=0, column=0, offset=0,
                    statements=[]
                )
            )
            self.expect(TokenType.RPAREN)
            body = self.parse_block()
            return ModuleFunctorDecl(
                type=NodeType.MODULE_FUNCTOR_DECL,
                line=name_tok.line, column=name_tok.column, offset=name_tok.offset,
                name=name, param_name=param_name, param_type=param_type, body=body
            )
        else:
            raise SyntaxError(f"Expected module_type or module_functor, got {self.current}")

    def parse_effect_decl(self) -> EffectDecl:
        """Parse effect declaration: effect Name { operation1(...); operation2(...); ... }"""
        # EFFECT_KW already consumed by match_any
        name_tok = self.expect(TokenType.IDENT)
        name = name_tok.value
        self.expect(TokenType.LBRACE)
        operations = []
        while not self.match(TokenType.RBRACE) and not self.at_end():
            # Parse effect operation: name(params) -> return_type
            op_name_tok = self.expect(TokenType.IDENT)
            op_name = op_name_tok.value
            self.expect(TokenType.LPAREN)
            params = self.parse_params()
            return_type = None
            if self.match(TokenType.ARROW):
                return_type = self.parse_type_expr()
            # Semicolon is optional before closing brace
            self.match(TokenType.SEMICOLON)
            operations.append(EffectOperation(
                type=NodeType.EFFECT_OPERATION,
                line=op_name_tok.line, column=op_name_tok.column, offset=op_name_tok.offset,
                name=op_name, params=params, return_type=return_type
            ))
        return EffectDecl(
            type=NodeType.EFFECT_DECL,
            line=name_tok.line, column=name_tok.column, offset=name_tok.offset,
            name=name, operations=operations
        )

    def parse_class_decl(self) -> ClassDecl:
        """Parse class declaration: class Name<params> where constraints { method1; method2; ... }"""
        self.advance()  # consume CLASS_KW
        name_tok = self.expect(TokenType.IDENT)
        name = name_tok.value
        type_params = []
        if self.match(TokenType.LT):
            while True:
                param_tok = self.expect(TokenType.IDENT)
                type_params.append(param_tok.value)
                if not self.match(TokenType.COMMA):
                    break
            self.expect(TokenType.GT)
        constraints = []
        # Check if there's a where clause before the body
        if self.match(TokenType.WHERE_KW):
            # Check if next token is LBRACE (body) or a type expression
            if self.current and self.current.type != TokenType.LBRACE:
                while True:
                    constraints.append(self.parse_type_expr())
                    if not self.match(TokenType.COMMA):
                        break
        self.expect(TokenType.LBRACE)
        methods = []
        while not self.match(TokenType.RBRACE) and not self.at_end():
            # Parse class method: name(params) -> return_type
            method_name_tok = self.expect(TokenType.IDENT)
            method_name = method_name_tok.value
            self.expect(TokenType.LPAREN)
            params = self.parse_params()
            return_type = None
            if self.match(TokenType.ARROW):
                return_type = self.parse_type_expr()
            self.match(TokenType.SEMICOLON)
            methods.append(ClassMethod(
                type=NodeType.CLASS_METHOD,
                line=method_name_tok.line, column=method_name_tok.column, offset=method_name_tok.offset,
                name=method_name, params=params, return_type=return_type
            ))
        return ClassDecl(
            type=NodeType.CLASS_DECL,
            line=name_tok.line, column=name_tok.column, offset=name_tok.offset,
            name=name, type_params=type_params, constraints=constraints, methods=methods
        )

    def parse_instance_decl(self) -> InstanceDecl:
        """Parse instance declaration: instance ClassName<types> { method1; method2; ... }"""
        self.advance()  # consume INSTANCE_KW
        class_name_tok = self.expect(TokenType.IDENT)
        class_name = class_name_tok.value
        type_args = []
        if self.match(TokenType.LT):
            while True:
                type_args.append(self.parse_type_expr())
                if not self.match(TokenType.COMMA):
                    break
            self.expect(TokenType.GT)
        self.expect(TokenType.LBRACE)
        methods = []
        while not self.match(TokenType.RBRACE) and not self.at_end():
            # Parse instance method signature: name(params) -> return_type { body }
            # This is similar to a function declaration but without 'func' keyword
            method_name_tok = self.expect(TokenType.IDENT)
            method_name = method_name_tok.value
            self.expect(TokenType.LPAREN)
            params = self.parse_params()
            return_type = None
            if self.match(TokenType.ARROW):
                return_type = self.parse_type_expr()
            body = self.parse_block()
            methods.append(FuncDecl(
                type=NodeType.FUNC_DECL,
                line=method_name_tok.line, column=method_name_tok.column, offset=method_name_tok.offset,
                name=method_name, params=params, return_type=return_type, body=body, effects=None
            ))
            self.match(TokenType.SEMICOLON)
        return InstanceDecl(
            type=NodeType.INSTANCE_DECL,
            line=self.current.line if self.current else 0,
            column=self.current.column if self.current else 0,
            offset=self.current.offset if self.current else 0,
            class_name=class_name, type_args=type_args, methods=methods
        )

    def match_any(self, *types: TokenType) -> bool:
        """Match current token against any of the given types."""
        if self.current and self.current.type in types:
            self.advance()
            return True
        return False

    def parse_top_level(self) -> TopLevelItem:
        if self.match_any(TokenType.FUNC, TokenType.FUNC):
            return self.parse_func_decl()
        elif self.match_any(TokenType.STRUCT, TokenType.STRUCT):
            return self.parse_struct_decl()
        elif self.match_any(TokenType.TYPE, TokenType.TYPE):
            if self.current and self.current.type == TokenType.IDENT:
                return self.parse_type_alias()
            else:
                raise SyntaxError("Expected identifier after 'type'")
        elif self.match_any(TokenType.CONST, TokenType.CONST):
            return self.parse_const_decl()
        elif self.match_any(TokenType.VAR, TokenType.VAR):
            return self.parse_var_decl()
        elif self.match_any(TokenType.MACRO, TokenType.MACRO_RULES):
            return self.parse_macro_decl()
        elif self.match_any(TokenType.MODULE_TYPE, TokenType.MODULE_FUNCTOR):
            return self.parse_module_type_or_functor()
        elif self.match_any(TokenType.EFFECT_KW):
            return self.parse_effect_decl()
        elif self.match_any(TokenType.CLASS_KW):
            return self.parse_class_decl()
        elif self.match_any(TokenType.INSTANCE_KW):
            return self.parse_instance_decl()
        else:
            raise SyntaxError(f"Unexpected token at top level: {self.current}")

    def parse_func_decl(self) -> FuncDecl:
        name_tok = self.expect(TokenType.IDENT)
        name = name_tok.value
        self.expect(TokenType.LPAREN)
        params = self.parse_params()
        return_type = None
        if self.match(TokenType.TYPE):
            return_type = self.parse_type_expr()
        effects = None
        if self.match(TokenType.EXCLAMATION):
            effects = self.parse_effect_row()
        body = self.parse_block()
        return FuncDecl(
            type=NodeType.FUNC_DECL,
            line=name_tok.line, column=name_tok.column, offset=name_tok.offset,
            name=name, params=params, return_type=return_type, body=body, effects=effects
        )

    def parse_effect_row(self) -> 'EffectRow':
        """Parse effect row: !Effect or !{Effect1, Effect2, ...}"""
        effects = []
        if self.match(TokenType.LBRACE):
            # Effect row with braces: !{IO, State, Exception}
            while True:
                effect_tok = self.expect(TokenType.IDENT)
                effects.append(effect_tok.value)
                if not self.match(TokenType.COMMA):
                    break
            self.expect(TokenType.RBRACE)
        else:
            # Single effect: !IO
            effect_tok = self.expect(TokenType.IDENT)
            effects.append(effect_tok.value)
        return EffectRow(
            type=NodeType.EFFECT_ROW,
            line=self.current.line if self.current else 0,
            column=self.current.column if self.current else 0,
            offset=self.current.offset if self.current else 0,
            effects=effects
        )

    def parse_params(self) -> List[Param]:
        params = []
        if not self.match(TokenType.RPAREN):
            while True:
                name_tok = self.expect(TokenType.IDENT)
                name = name_tok.value
                type_ann = None
                if self.match(TokenType.COLON):
                    type_ann = self.parse_type_expr()
                params.append(Param(
                    type=NodeType.PARAM,
                    line=name_tok.line, column=name_tok.column, offset=name_tok.offset,
                    name=name, type_ann=type_ann
                ))
                if not self.match(TokenType.COMMA):
                    break
            self.expect(TokenType.RPAREN)
        return params

    def parse_struct_decl(self) -> StructDecl:
        struct_name_tok = self.expect(TokenType.IDENT)
        struct_name = struct_name_tok.value
        self.expect(TokenType.LBRACE)
        fields = []
        if not self.match(TokenType.RBRACE):
            while True:
                name_tok = self.expect(TokenType.IDENT)
                name = name_tok.value
                type_ann = None
                if self.match(TokenType.COLON):
                    type_ann = self.parse_type_expr()
                fields.append(Field(
                    type=NodeType.FIELD,
                    line=name_tok.line, column=name_tok.column, offset=name_tok.offset,
                    name=name, type_ann=type_ann
                ))
                if not self.match(TokenType.COMMA):
                    break
            self.expect(TokenType.RBRACE)
        return StructDecl(
            type=NodeType.STRUCT_DECL,
            line=struct_name_tok.line, column=struct_name_tok.column, offset=struct_name_tok.offset,
            name=struct_name, fields=fields
        )

    def parse_type_alias(self) -> TypeAlias:
        name_tok = self.expect(TokenType.IDENT)
        name = name_tok.value
        type_params = []
        if self.match(TokenType.LT):
            while True:
                param_tok = self.expect(TokenType.IDENT)
                type_params.append(param_tok.value)
                if not self.match(TokenType.COMMA):
                    break
            self.expect(TokenType.GT)
        self.expect(TokenType.ASSIGN)
        target = self.parse_type_expr()
        return TypeAlias(
            type=NodeType.TYPE_ALIAS,
            line=name_tok.line, column=name_tok.column, offset=name_tok.offset,
            name=name, type_params=type_params, target=target
        )

    def parse_const_decl(self) -> ConstDecl:
        name_tok = self.expect(TokenType.IDENT)
        name = name_tok.value
        type_ann = None
        if self.match(TokenType.COLON):
            type_ann = self.parse_type_expr()
        self.expect(TokenType.ASSIGN)
        value = self.parse_expr()
        return ConstDecl(
            type=NodeType.CONST_DECL,
            line=name_tok.line, column=name_tok.column, offset=name_tok.offset,
            name=name, type_ann=type_ann, value=value
        )

    def parse_var_decl(self) -> VarDecl:
        name_tok = self.expect(TokenType.IDENT)
        name = name_tok.value
        type_ann = None
        if self.match(TokenType.COLON):
            type_ann = self.parse_type_expr()
        self.expect(TokenType.ASSIGN)
        value = self.parse_expr()
        return VarDecl(
            type=NodeType.VAR_DECL,
            line=name_tok.line, column=name_tok.column, offset=name_tok.offset,
            name=name, type_ann=type_ann, value=value
        )

    def parse_block(self) -> Block:
        self.expect(TokenType.LBRACE)
        statements = []
        while not self.match(TokenType.RBRACE) and not self.at_end():
            statements.append(self.parse_stmt())
            # Optionally consume semicolon
            self.match(TokenType.SEMICOLON)
        return Block(
            type=NodeType.BLOCK,
            line=self.current.line if self.current else 0,
            column=self.current.column if self.current else 0,
            offset=self.current.offset if self.current else 0,
            statements=statements
        )

    def parse_stmt(self) -> Stmt:
        if self.current and self.current.type == TokenType.LBRACE:
            return self.parse_block()
        if self.current and self.current.type in (TokenType.FUNC, TokenType.STRUCT, TokenType.TYPE, TokenType.CONST, TokenType.VAR):
            if self.current.type == TokenType.FUNC:
                self.advance()
                return self.parse_func_decl()
            elif self.current.type == TokenType.STRUCT:
                self.advance()
                return self.parse_struct_decl()
            elif self.current.type == TokenType.TYPE:
                self.advance()
                return self.parse_type_alias()
            elif self.current.type == TokenType.CONST:
                self.advance()
                return self.parse_const_decl()
            elif self.current.type == TokenType.VAR:
                self.advance()
                return self.parse_var_decl()
        if self.match(TokenType.LET):
            return self.parse_let_stmt()
        elif self.match(TokenType.IF):
            return self.parse_if_stmt()
        elif self.match(TokenType.WHILE):
            return self.parse_while_stmt()
        elif self.match(TokenType.FOR):
            return self.parse_for_stmt()
        elif self.match(TokenType.RETURN):
            return self.parse_return_stmt()
        elif self.match(TokenType.ASSERT):
            return self.parse_assert_stmt()
        elif self.match(TokenType.TRY):
            return self.parse_try_stmt()
        else:
            expr = self.parse_expr()
            if isinstance(expr, Block):
                return expr
            return ExprStmt(
                type=NodeType.EXPR_STMT,
                line=expr.line, column=expr.column, offset=expr.offset,
                expression=expr
            )

    def parse_let_stmt(self) -> LetStmt:
        name_tok = self.expect(TokenType.IDENT)
        name = name_tok.value
        type_ann = None
        if self.match(TokenType.COLON):
            type_ann = self.parse_type_expr()
        self.expect(TokenType.ASSIGN)
        value = self.parse_expr()
        return LetStmt(
            type=NodeType.LET_STMT,
            line=name_tok.line, column=name_tok.column, offset=name_tok.offset,
            name=name, type_ann=type_ann, value=value
        )

    def parse_if_stmt(self) -> IfStmt:
        condition = self.parse_expr_no_struct_lit()
        self.expect(TokenType.THEN)
        then_branch = self.parse_block()
        else_branch = None
        if self.match(TokenType.ELSE):
            else_branch = self.parse_block()
        return IfStmt(
            type=NodeType.IF_STMT,
            line=self.current.line if self.current else 0,
            column=self.current.column if self.current else 0,
            offset=self.current.offset if self.current else 0,
            condition=condition, then_branch=then_branch, else_branch=else_branch
        )

    def parse_while_stmt(self) -> WhileStmt:
        condition = self.parse_expr_no_struct_lit()
        body = self.parse_block()
        return WhileStmt(
            type=NodeType.WHILE_STMT,
            line=self.current.line if self.current else 0,
            column=self.current.column if self.current else 0,
            offset=self.current.offset if self.current else 0,
            condition=condition, body=body
        )

    def parse_for_stmt(self) -> ForStmt:
        var_tok = self.expect(TokenType.IDENT)
        var = var_tok.value
        self.expect(TokenType.IN)
        iter_expr = self.parse_expr_no_struct_lit()
        body = self.parse_block()
        return ForStmt(
            type=NodeType.FOR_STMT,
            line=var_tok.line, column=var_tok.column, offset=var_tok.offset,
            var=var, iter_expr=iter_expr, body=body
        )

    def parse_return_stmt(self) -> ReturnStmt:
        value = None
        if not self.current.type in (TokenType.RBRACE, TokenType.SEMICOLON, TokenType.EOF):
            value = self.parse_expr()
        return ReturnStmt(
            type=NodeType.RETURN_STMT,
            line=self.current.line if self.current else 0,
            column=self.current.column if self.current else 0,
            offset=self.current.offset if self.current else 0,
            value=value
        )

    def parse_assert_stmt(self) -> AssertStmt:
        condition = self.parse_expr()
        return AssertStmt(
            type=NodeType.ASSERT_STMT,
            line=self.current.line if self.current else 0,
            column=self.current.column if self.current else 0,
            offset=self.current.offset if self.current else 0,
            condition=condition
        )

    def parse_try_stmt(self) -> TryStmt:
        try_block = self.parse_block()
        self.expect(TokenType.CATCH)
        var_tok = self.expect(TokenType.IDENT)
        var = var_tok.value
        catch_type = None
        if self.match(TokenType.COLON):
            catch_type = self.parse_type_expr()
        catch_block = self.parse_block()
        return TryStmt(
            type=NodeType.TRY_STMT,
            line=self.current.line if self.current else 0,
            column=self.current.column if self.current else 0,
            offset=self.current.offset if self.current else 0,
            try_block=try_block, catch_var=var, catch_type=catch_type, catch_block=catch_block
        )

    # Expression parsing with precedence (highest to lowest)
    def parse_expr(self) -> Expr:
        # Bound the recursion: deeply nested parentheses used to escape as a raw
        # RecursionError. Empirically the interpreter's own limit is hit at ~56 nested
        # levels (Python frame cost ~15/level with recursionlimit 1000), so guard at 50.
        depth = getattr(self, '_expr_depth', 0) + 1
        if depth > 50:
            raise SyntaxError("expression nesting too deep (>50 levels)")
        self._expr_depth = depth
        try:
            return self.parse_assignment()
        finally:
            self._expr_depth = depth - 1

    def parse_expr_no_struct_lit(self) -> Expr:
        """Parse expression without struct literal ambiguity (for for-loop iter expressions)."""
        old_flag = getattr(self, '_allow_struct_lit', True)
        self._allow_struct_lit = False
        try:
            return self.parse_assignment()
        finally:
            self._allow_struct_lit = old_flag

    def parse_assignment(self) -> Expr:
        """Parse assignment expressions (right-associative)."""
        left = self.parse_ternary()
        
        # Assignment operators are right-associative
        if self.match(TokenType.ASSIGN, TokenType.ASSIGN_ADD, TokenType.ASSIGN_SUB,
                      TokenType.ASSIGN_MUL, TokenType.ASSIGN_DIV, TokenType.ASSIGN_MOD,
                      TokenType.ASSIGN_AND, TokenType.ASSIGN_OR, TokenType.ASSIGN_XOR,
                      TokenType.ASSIGN_SHL, TokenType.ASSIGN_SHR):
            op = self.tokens[self.pos - 1].value
            right = self.parse_assignment()
            
            # Assignment target must be an identifier
            if isinstance(left, Ident):
                return AssignExpr(
                    type=NodeType.BINARY_EXPR,
                    line=left.line, column=left.column, offset=left.offset,
                    target=left, operator=op, value=right
                )
            else:
                raise SyntaxError(f"Invalid assignment target at line {left.line}, column {left.column}")
        
        return left

    def parse_ternary(self) -> Expr:
            # Check for 'if' ternary expression first (if condition then expr else expr)
            if self.match(TokenType.IF):
                condition = self.parse_expr()
                self.expect(TokenType.THEN)
                then_expr = self.parse_ternary()
                self.expect(TokenType.ELSE)
                else_expr = self.parse_ternary()
                return TernaryExpr(
                    type=NodeType.TERNARY_EXPR,
                    line=self.current.line if self.current else 0,
                    column=self.current.column if self.current else 0,
                    offset=self.current.offset if self.current else 0,
                    condition=condition, then_expr=then_expr, else_expr=else_expr
                )
        
            left = self.parse_logic_or()
        
            if self.match(TokenType.TERNARY_QUESTION):
                then_expr = self.parse_ternary()
                self.expect(TokenType.COLON)
                else_expr = self.parse_ternary()
                return TernaryExpr(
                    type=NodeType.TERNARY_EXPR,
                    line=left.line, column=left.column, offset=left.offset,
                    condition=left, then_expr=then_expr, else_expr=else_expr
                )
        
            return left

    def parse_logic_or(self) -> Expr:
        left = self.parse_logic_and()
        while self.match(TokenType.OR):
            op = '||'
            right = self.parse_logic_and()
            left = BinaryExpr(
                type=NodeType.BINARY_EXPR,
                line=left.line, column=left.column, offset=left.offset,
                left=left, operator=op, right=right
            )
        return left

    def parse_logic_and(self) -> Expr:
        left = self.parse_equality()
        while self.match(TokenType.AND):
            op = '&&'
            right = self.parse_equality()
            left = BinaryExpr(
                type=NodeType.BINARY_EXPR,
                line=left.line, column=left.column, offset=left.offset,
                left=left, operator=op, right=right
            )
        return left

    def parse_equality(self) -> Expr:
        left = self.parse_comparison()
        while self.match(TokenType.EQ, TokenType.NE):
            op = self.tokens[self.pos - 1].value
            right = self.parse_comparison()
            left = BinaryExpr(
                type=NodeType.BINARY_EXPR,
                line=left.line, column=left.column, offset=left.offset,
                left=left, operator=op, right=right
            )
        return left

    def parse_comparison(self) -> Expr:
        left = self.parse_range()
        while self.match(TokenType.LT, TokenType.GT, TokenType.LE, TokenType.GE):
            op = self.tokens[self.pos - 1].value
            right = self.parse_range()
            left = BinaryExpr(
                type=NodeType.BINARY_EXPR,
                line=left.line, column=left.column, offset=left.offset,
                left=left, operator=op, right=right
            )
        return left

    def parse_range(self) -> Expr:
        """Parse range expression: start..end (inclusive) or start..<end (exclusive)."""
        left = self.parse_additive()
        while self.match(TokenType.RANGE):
            op = '..'
            right = self.parse_additive()
            left = BinaryExpr(
                type=NodeType.BINARY_EXPR,
                line=left.line, column=left.column, offset=left.offset,
                left=left, operator=op, right=right
            )
        return left

    def parse_additive(self) -> Expr:
        left = self.parse_bitwise_or()
        while self.match(TokenType.PLUS, TokenType.MINUS):
            op = self.tokens[self.pos - 1].value
            right = self.parse_bitwise_or()
            left = BinaryExpr(
                type=NodeType.BINARY_EXPR,
                line=left.line, column=left.column, offset=left.offset,
                left=left, operator=op, right=right
            )
        return left

    def parse_bitwise_or(self) -> Expr:
        left = self.parse_bitwise_xor()
        while self.match(TokenType.BITWISE_OR):
            op = self.tokens[self.pos - 1].value
            right = self.parse_bitwise_xor()
            left = BinaryExpr(
                type=NodeType.BINARY_EXPR,
                line=left.line, column=left.column, offset=left.offset,
                left=left, operator=op, right=right
            )
        return left

    def parse_bitwise_xor(self) -> Expr:
        left = self.parse_bitwise_and()
        while self.match(TokenType.BITWISE_XOR):
            op = self.tokens[self.pos - 1].value
            right = self.parse_bitwise_and()
            left = BinaryExpr(
                type=NodeType.BINARY_EXPR,
                line=left.line, column=left.column, offset=left.offset,
                left=left, operator=op, right=right
            )
        return left

    def parse_bitwise_and(self) -> Expr:
        left = self.parse_shift()
        while self.match(TokenType.BITWISE_AND):
            op = self.tokens[self.pos - 1].value
            right = self.parse_shift()
            left = BinaryExpr(
                type=NodeType.BINARY_EXPR,
                line=left.line, column=left.column, offset=left.offset,
                left=left, operator=op, right=right
            )
        return left

    def parse_shift(self) -> Expr:
        left = self.parse_multiplicative()
        while self.match(TokenType.SHIFT_LEFT, TokenType.SHIFT_RIGHT):
            op = self.tokens[self.pos - 1].value
            right = self.parse_multiplicative()
            left = BinaryExpr(
                type=NodeType.BINARY_EXPR,
                line=left.line, column=left.column, offset=left.offset,
                left=left, operator=op, right=right
            )
        return left

    def parse_multiplicative(self) -> Expr:
        left = self.parse_unary()
        while self.match(TokenType.STAR, TokenType.SLASH, TokenType.PERCENT):
            op = self.tokens[self.pos - 1].value
            right = self.parse_unary()
            left = BinaryExpr(
                type=NodeType.BINARY_EXPR,
                line=left.line, column=left.column, offset=left.offset,
                left=left, operator=op, right=right
            )
        return left

    def parse_unary(self) -> Expr:
        if self.match(TokenType.MINUS, TokenType.NOT, TokenType.BITWISE_NOT,
                      TokenType.EXCLAMATION):
            op = self.tokens[self.pos - 1].value
            operand = self.parse_unary()
            return UnaryExpr(
                type=NodeType.UNARY_EXPR,
                line=self.current.line if self.current else 0,
                column=self.current.column if self.current else 0,
                offset=self.current.offset if self.current else 0,
                operator=op, operand=operand
            )
        return self.parse_postfix()

    def parse_postfix(self) -> Expr:
        left = self.parse_primary()
        while True:
            if self.match(TokenType.DOT):
                field_tok = self.expect(TokenType.IDENT)
                left = FieldAccess(
                    type=NodeType.BINARY_EXPR,
                    line=left.line, column=left.column, offset=left.offset,
                    left=left, operator='.', right=Ident(
                        type=NodeType.IDENT,
                        line=field_tok.line, column=field_tok.column, offset=field_tok.offset,
                        name=field_tok.value
                    )
                )
            elif self.match(TokenType.LBRACKET):
                index = self.parse_expr()
                self.expect(TokenType.RBRACKET)
                left = IndexExpr(
                    type=NodeType.BINARY_EXPR,
                    line=left.line, column=left.column, offset=left.offset,
                    left=left, operator='[]', right=index
                )
            elif self.match(TokenType.LPAREN):
                args = []
                if not self.match(TokenType.RPAREN):
                    while True:
                        args.append(self.parse_expr())
                        if not self.match(TokenType.COMMA):
                            break
                    self.expect(TokenType.RPAREN)
                left = CallExpr(
                    type=NodeType.CALL_EXPR,
                    line=left.line, column=left.column, offset=left.offset,
                    callee=left.name if isinstance(left, Ident) else '',
                    arguments=args
                )
            # Cast expression: expr as Type (H5: Gradual Typing)
            elif self.match(TokenType.CAST):
                target_type = self.parse_type_expr()
                left = CastExpr(
                    type=NodeType.CAST_EXPR,
                    line=left.line, column=left.column, offset=left.offset,
                    expr=left, target_type=target_type
                )
            else:
                break
        return left

    def parse_primary(self) -> Expr:
        # Literals
        if self.match(TokenType.INT):
            val = self.tokens[self.pos - 1].value
            return Literal(
                type=NodeType.LITERAL,
                line=self.current.line, column=self.current.column, offset=self.current.offset,
                value=val, literal_type='int'
            )
        if self.match(TokenType.FLOAT):
            val = self.tokens[self.pos - 1].value
            return Literal(
                type=NodeType.LITERAL,
                line=self.current.line, column=self.current.column, offset=self.current.offset,
                value=val, literal_type='float'
            )
        if self.match(TokenType.STRING):
            val = self.tokens[self.pos - 1].value
            return Literal(
                type=NodeType.LITERAL,
                line=self.current.line, column=self.current.column, offset=self.current.offset,
                value=val, literal_type='string'
            )
        if self.match(TokenType.BOOL):
            val = self.tokens[self.pos - 1].value
            return Literal(
                type=NodeType.LITERAL,
                line=self.current.line, column=self.current.column, offset=self.current.offset,
                value=val, literal_type='bool'
            )
        if self.match(TokenType.NULL):
            return Literal(
                type=NodeType.LITERAL,
                line=self.current.line, column=self.current.column, offset=self.current.offset,
                value=None, literal_type='null'
            )

        # Identifiers / Hebrew tokens
        # Struct literal check must come BEFORE generic IDENT match
        # because struct literal starts with IDENT followed by LBRACE.
        # It must also be suppressed inside contexts that disable it (loop/if conditions,
        # for-loop iterables) — otherwise `while i < n {` steals `n {` as a struct literal.
        if (getattr(self, '_allow_struct_lit', True)
                and self.current and self.current.type == TokenType.IDENT
                and self.peek() and self.peek().type == TokenType.LBRACE):
            return self.parse_struct_lit()

        if self.match(TokenType.IDENT):
            name = self.tokens[self.pos - 1].value
            return Ident(
                type=NodeType.IDENT,
                line=self.current.line, column=self.current.column, offset=self.current.offset,
                name=name
            )

        # Hebrew tokens as standalone keywords
        hebrew_map = {
            TokenType.LET: 'LET', TokenType.IF: 'IF', TokenType.THEN: 'THEN',
            TokenType.ELSE: 'ELSE', TokenType.WHILE: 'WHILE', TokenType.FOR: 'FOR',
            TokenType.FUNC: 'FUNC', TokenType.RETURN: 'RETURN', TokenType.MATCH: 'MATCH',
            TokenType.TYPE: 'TYPE', TokenType.STRUCT: 'STRUCT', TokenType.MODULE: 'MODULE',
            TokenType.IMPORT: 'IMPORT', TokenType.EXPORT: 'EXPORT', TokenType.CONST: 'CONST',
            TokenType.VAR: 'VAR', TokenType.ASSERT: 'ASSERT', TokenType.TRY: 'TRY',
            TokenType.CATCH: 'CATCH', TokenType.THROW: 'THROW', TokenType.ASYNC: 'ASYNC',
            TokenType.AWAIT: 'AWAIT',
        }
        for tt, kw in hebrew_map.items():
            if self.match(tt):
                return Ident(
                    type=NodeType.IDENT,
                    line=self.current.line, column=self.current.column, offset=self.current.offset,
                    name=kw
                )

        # Parenthesized expression
        if self.match(TokenType.LPAREN):
            expr = self.parse_expr()
            self.expect(TokenType.RPAREN)
            return expr

        # Array literal
        if self.match(TokenType.LBRACKET):
            return self.parse_array_lit()

        # Lambda
        if self.match(TokenType.BACKSLASH):
            return self.parse_lambda()

        # Match expression
        if self.match(TokenType.MATCH):
            return self.parse_match_expr()

        # Await
        if self.match(TokenType.AWAIT):
            return self.parse_await_expr()

        raise SyntaxError(f"Unexpected token: {self.current}")

    def parse_struct_lit(self) -> StructLit:
        struct_name_tok = self.expect(TokenType.IDENT)
        struct_name = struct_name_tok.value
        self.expect(TokenType.LBRACE)
        fields = []
        if not self.match(TokenType.RBRACE):
            while True:
                name_tok = self.expect(TokenType.IDENT)
                name = name_tok.value
                self.expect(TokenType.COLON)
                value = self.parse_expr()
                fields.append(FieldInit(
                    type=NodeType.FIELD_INIT,
                    line=name_tok.line, column=name_tok.column, offset=name_tok.offset,
                    name=name, value=value
                ))
                if not self.match(TokenType.COMMA):
                    break
            self.expect(TokenType.RBRACE)
        return StructLit(
            type=NodeType.STRUCT_LIT,
            line=struct_name_tok.line, column=struct_name_tok.column, offset=struct_name_tok.offset,
            name=struct_name, fields=fields
        )

    def parse_array_lit(self) -> ArrayLit:
        elements = []
        if not self.match(TokenType.RBRACKET):
            while True:
                elements.append(self.parse_expr())
                if not self.match(TokenType.COMMA):
                    break
            self.expect(TokenType.RBRACKET)
        return ArrayLit(
            type=NodeType.ARRAY_LIT,
            line=self.current.line, column=self.current.column, offset=self.current.offset,
            elements=elements
        )

    def parse_lambda(self) -> LambdaExpr:
        # Lambda can be \x -> expr (single param, no type) or \(x: int) -> expr
        if self.match(TokenType.LPAREN):
            # Parenthesized form: \(x: int, y: int) -> expr
            params = self.parse_params()
        else:
            # Single parameter without parens: \x -> expr
            name_tok = self.expect(TokenType.IDENT)
            name = name_tok.value
            type_ann = None
            if self.match(TokenType.COLON):
                type_ann = self.parse_type_expr()
            from svl.parser_rd import Param
            params = [Param(
                type=NodeType.PARAM,
                line=name_tok.line, column=name_tok.column, offset=name_tok.offset,
                name=name, type_ann=type_ann
            )]
        self.expect(TokenType.ARROW)
        body = self.parse_expr()
        return LambdaExpr(
            type=NodeType.LAMBDA_EXPR,
            line=self.current.line, column=self.current.column, offset=self.current.offset,
            params=params, return_type=None, body=body
        )

    def parse_match_expr(self) -> MatchExpr:
        subject = self.parse_expr()
        self.expect(TokenType.LBRACE)
        cases = []
        while not self.match(TokenType.RBRACE):
            cases.append(self.parse_case_clause())
        return MatchExpr(
            type=NodeType.MATCH_EXPR,
            line=self.current.line, column=self.current.column, offset=self.current.offset,
            subject=subject, cases=cases
        )

    def parse_case_clause(self) -> CaseClause:
        self.expect(TokenType.CASE)
        pattern = self.parse_pattern()
        self.expect(TokenType.FAT_ARROW)
        body = self.parse_expr()
        return CaseClause(
            type=NodeType.CASE_CLAUSE,
            line=self.current.line, column=self.current.column, offset=self.current.offset,
            pattern=pattern, body=body
        )

    def parse_pattern(self) -> Pattern:
        if self.match(TokenType.UNDERSCORE):
            return Pattern(
                type=NodeType.PATTERN,
                line=self.current.line, column=self.current.column, offset=self.current.offset,
                kind='wildcard', value=None
            )
        if self.match(TokenType.LITERAL):
            return Pattern(
                type=NodeType.PATTERN,
                line=self.current.line, column=self.current.column, offset=self.current.offset,
                kind='literal', value=str(self.tokens[self.pos - 1].value)
            )
        if self.match(TokenType.IDENT):
            name = self.tokens[self.pos - 1].value
            if self.match(TokenType.LBRACE):
                fields = []
                if not self.match(TokenType.RBRACE):
                    while True:
                        field_name_tok = self.expect(TokenType.IDENT)
                        field_name = field_name_tok.value
                        sub_pattern = None
                        if self.match(TokenType.COLON):
                            sub_pattern = self.parse_pattern()
                        fields.append(FieldPattern(
                            type=NodeType.FIELD_PATTERN,
                            line=field_name_tok.line, column=field_name_tok.column, offset=field_name_tok.offset,
                            name=field_name, pattern=sub_pattern
                        ))
                        if not self.match(TokenType.COMMA):
                            break
                    self.expect(TokenType.RBRACE)
                return Pattern(
                    type=NodeType.PATTERN,
                    line=self.current.line, column=self.current.column, offset=self.current.offset,
                    kind='struct', value=fields
                )
            return Pattern(
                type=NodeType.PATTERN,
                line=self.current.line, column=self.current.column, offset=self.current.offset,
                kind='ident', value=name
            )
        if self.match(TokenType.LPAREN):
            pattern = self.parse_pattern()
            self.expect(TokenType.RPAREN)
            return pattern
        raise SyntaxError(f"Expected pattern, got {self.current}")

    def parse_await_expr(self) -> AwaitExpr:
        expr = self.parse_expr()
        return AwaitExpr(
            type=NodeType.AWAIT_EXPR,
            line=self.current.line, column=self.current.column, offset=self.current.offset,
            expression=expr
        )

    def _parse_type_expr_atom(self) -> TypeExpr:
        # Simplified type expression parsing
        # Handle linear/unique qualifiers (H3: Linear Types)
        if self.current and self.current.type in (TokenType.LINEAR, TokenType.UNIQUE):
            qualifier_tok = self.current
            self.advance()
            inner_type = self.parse_type_expr()
            if qualifier_tok.type == TokenType.LINEAR:
                return TypeExpr(
                    type=NodeType.TYPE_EXPR,
                    line=qualifier_tok.line, column=qualifier_tok.column, offset=qualifier_tok.offset,
                    kind='linear', value=inner_type
                )
            else:  # UNIQUE
                return TypeExpr(
                    type=NodeType.TYPE_EXPR,
                    line=qualifier_tok.line, column=qualifier_tok.column, offset=qualifier_tok.offset,
                    kind='unique', value=inner_type
                )
        
        # Handle dependent types: Vec<T, n> (H4: Dependent Types)
        if self.current and self.current.type == TokenType.VEC:
            vec_tok = self.current
            self.advance()
            self.expect(TokenType.LT)
            element_type = self.parse_type_expr()
            self.expect(TokenType.COMMA)
            # Parse size as a simple expression (integer literal for now)
            size_expr = self.parse_primary()  # Parse simple literal
            self.expect(TokenType.GT)
            return TypeExpr(
                type=NodeType.TYPE_EXPR,
                line=vec_tok.line, column=vec_tok.column, offset=vec_tok.offset,
                kind='vec', value={'element_type': element_type, 'size': size_expr}
            )
        
        # Handle gradual typing: ? (dynamic type) (H5: Gradual Typing)
        if self.current and self.current.type == TokenType.TERNARY_QUESTION:
            # In type context, ? means dynamic type
            dyn_tok = self.current
            self.advance()
            return TypeExpr(
                type=NodeType.TYPE_EXPR,
                line=dyn_tok.line, column=dyn_tok.column, offset=dyn_tok.offset,
                kind='dynamic', value='?'
            )
        
        # Handle higher-kinded types: * and HKT application (H10: HKT)
        # Accept both KIND_STAR and STAR (multiplication operator) as kind star in type context
        if self.current and self.current.type in (TokenType.KIND_STAR, TokenType.STAR):
            star_tok = self.current
            self.advance()
            return TypeExpr(
                type=NodeType.TYPE_EXPR,
                line=star_tok.line, column=star_tok.column, offset=star_tok.offset,
                kind='kind_star', value=None
            )
        
        # Handle kind arrow: -> for kinds like * -> *
        if self.current and self.current.type == TokenType.ARROW:
            arrow_tok = self.current
            self.advance()
            from_kind = self.parse_type_expr()
            # Expect another kind (for kind arrow parsing)
            to_kind = self.parse_type_expr()
            return TypeExpr(
                type=NodeType.TYPE_EXPR,
                line=arrow_tok.line, column=arrow_tok.column, offset=arrow_tok.offset,
                kind='kind_arrow', value={'from': from_kind, 'to': to_kind}
            )
        
        # Handle modal types: □T and ◇T (H16: Modal Types)
        if self.current and self.current.type in (TokenType.BOX, TokenType.DIAMOND):
            modal_tok = self.current
            self.advance()
            inner_type = self.parse_type_expr()
            kind = 'box' if modal_tok.type == TokenType.BOX else 'diamond'
            return TypeExpr(
                type=NodeType.TYPE_EXPR,
                line=modal_tok.line, column=modal_tok.column, offset=modal_tok.offset,
                kind=kind, value=inner_type
            )
        
        # Handle quantified constraints: forall a. C a => D a (H13: Quantified Constraints)
        if self.current and self.current.type == TokenType.FORALL:
            forall_tok = self.current
            self.advance()
            type_vars = []
            while self.current and self.current.type == TokenType.IDENT:
                var_tok = self.current
                self.advance()
                type_vars.append(var_tok.value)
                if not self.match(TokenType.COMMA):
                    break
            # Optional dot after type variables (Haskell syntax: forall a. ...)
            self.match(TokenType.DOT)
            constraints = []
            # Parse constraints until we see => or ->
            while self.current and self.current.type not in (TokenType.FAT_ARROW, TokenType.ARROW):
                constraints.append(self.parse_type_expr())
                if not self.match(TokenType.COMMA):
                    break
            # Accept both => and -> as the final separator before body
            if self.match(TokenType.FAT_ARROW) or self.match(TokenType.ARROW):
                body = self.parse_type_expr()
                return TypeExpr(
                    type=NodeType.TYPE_EXPR,
                    line=forall_tok.line, column=forall_tok.column, offset=forall_tok.offset,
                    kind='forall', value={'type_vars': type_vars, 'constraints': constraints, 'body': body}
                )
            else:
                raise SyntaxError(f"Expected => or -> after constraints, got {self.current}")
        
        # Handle refinement types: { v: T | P } (H11: Refinement Types)
        if self.current and self.current.type == TokenType.LBRACE:
            # Check if this is a refinement type by looking ahead
            # Save position and try to parse as refinement
            saved_pos = self.pos
            saved_current = self.current
            self.advance()  # consume {
            if self.current and self.current.type == TokenType.IDENT:
                # Looks like refinement type: { v: T | P }
                var_tok = self.current
                var_name = var_tok.value
                self.advance()
                if self.match(TokenType.COLON):
                    base_type = self._parse_type_expr_atom()
                    # Accept both PIPE and BITWISE_OR as the pipe in refinement types
                    if self.match(TokenType.PIPE) or self.match(TokenType.BITWISE_OR):
                        predicate = self.parse_expr()
                        self.expect(TokenType.RBRACE)
                        return TypeExpr(
                            type=NodeType.TYPE_EXPR,
                            line=saved_current.line, column=saved_current.column, offset=saved_current.offset,
                            kind='refinement', value={'variable': var_name, 'base_type': base_type, 'predicate': predicate}
                        )
            # Not a refinement type, restore position
            self.pos = saved_pos
            self.current = saved_current
        
        # Handle intersection types: A & B (H12: Intersection Types)
        if self.current and self.current.type == TokenType.AMPERSAND:
            # This is handled at the expression level, but we can parse intersection types in type context
            # For now, intersection types are parsed as part of type expressions
            pass
        
        # Handle union types: A | B (H12: Union Types)
        # Union types are parsed at the expression level with BITWISE_OR
        # In type context, we need to handle union types specially
        pass
        
        # Primitive types are tokenized as IDENT with specific values
        if self.current and self.current.type == TokenType.IDENT:
            name = self.current.value
            name_lower = name.lower()
            if name_lower in ('int', 'float', 'string', 'bool', 'void', 'never'):
                self.advance()
                return TypeExpr(
                    type=NodeType.TYPE_EXPR,
                    line=self.current.line, column=self.current.column, offset=self.current.offset,
                    kind='prim', value=name_lower
                )
            # User-defined type or generic
            self.advance()
            if self.match(TokenType.LT):
                # Generic type
                args = []
                while True:
                    args.append(self.parse_type_expr())
                    if not self.match(TokenType.COMMA):
                        break
                self.expect(TokenType.GT)
                return TypeExpr(
                    type=NodeType.TYPE_EXPR,
                    line=self.current.line, column=self.current.column, offset=self.current.offset,
                    kind='generic', value={'name': name, 'args': args}
                )
            return TypeExpr(
                type=NodeType.TYPE_EXPR,
                line=self.current.line, column=self.current.column, offset=self.current.offset,
                kind='struct', value=name
            )
        if self.match(TokenType.FN):
            self.expect(TokenType.LPAREN)
            params = []
            if not self.match(TokenType.RPAREN):
                while True:
                    params.append(self.parse_type_expr())
                    if self.match(TokenType.COMMA):
                        continue
                    self.expect(TokenType.RPAREN)
                    break
            self.expect(TokenType.ARROW)
            return_type = self.parse_type_expr()
            return TypeExpr(
                type=NodeType.TYPE_EXPR,
                line=self.current.line, column=self.current.column, offset=self.current.offset,
                kind='func', value=FuncTypeDetail(params=params, return_type=return_type)
            )
        if self.match(TokenType.LPAREN):
            types = []
            while True:
                types.append(self.parse_type_expr())
                if not self.match(TokenType.COMMA):
                    break
                self.expect(TokenType.RPAREN)
            return TypeExpr(
                type=NodeType.TYPE_EXPR,
                line=self.current.line, column=self.current.column, offset=self.current.offset,
                kind='tuple', value=types
            )
        if self.match(TokenType.LBRACKET):
            elem_type = self.parse_type_expr()
            self.expect(TokenType.RBRACKET)
            return TypeExpr(
                type=NodeType.TYPE_EXPR,
                line=self.current.line, column=self.current.column, offset=self.current.offset,
                kind='array', value=elem_type
            )
        raise SyntaxError(f"Expected type expression, got {self.current}")

    def parse_type_expr(self) -> TypeExpr:
        # Type expression with intersection (A & B) / union (A | B) support (H12).
        # The atom parser handles single types; this combines them with & and |.
        left = self._parse_type_expr_atom()
        while self.current and self.current.type in (TokenType.BITWISE_AND, TokenType.BITWISE_OR):
            op_tok = self.current
            op = '&' if op_tok.type == TokenType.BITWISE_AND else '|'
            self.advance()
            right = self._parse_type_expr_atom()
            kind = 'intersection' if op == '&' else 'union'
            left = TypeExpr(
                type=NodeType.TYPE_EXPR,
                line=left.line, column=left.column, offset=left.offset,
                kind=kind, value={'left': left, 'right': right}
            )
        return left


# Missing AST node classes
@dataclass
class FieldAccess(ASTNode):
    left: Expr
    operator: str
    right: 'Ident'


@dataclass
class IndexExpr(ASTNode):
    left: Expr
    operator: str
    right: Expr


def parse(tokens: List[Token]) -> Program:
    """Convenience function to parse tokens.

    A RecursionError escaping from here is normalised to SyntaxError: a caller with a
    deeper stack can hit the interpreter limit before the in-parser depth guard, and an
    unclean crash is not an acceptable failure mode for bad input.
    """
    parser = Parser(tokens)
    try:
        return parser.parse()
    except RecursionError:
        raise SyntaxError("expression nesting too deep (parser recursion limit reached)") from None


if __name__ == '__main__':
    # Quick test
    test_code = '''
    module main {
      func main() type void {
        let x: int = 42
        if x > 0 then { return } else { return }
      }
    }
    '''
    tokens = tokenize(test_code)
    ast = parse(tokens)
    print(f"Parsed: {ast}")
    print(f"Modules: {len(ast.modules)}, Items: {len(ast.items)}")