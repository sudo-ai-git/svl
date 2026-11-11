# svl/parser_pratt.py
# Pratt Parser for SVL (Spike S2-B)
# Top-down operator precedence parsing

from typing import List, Optional, Callable, Dict, Any
from enum import Enum

from svl.lexer import Token, TokenType, tokenize
from svl.parser_rd import (
    ASTNode, NodeType,
    Program, Module, Import, Export,
    FuncDecl, StructDecl, TypeAlias, ConstDecl, VarDecl,
    Block, LetStmt, IfStmt, WhileStmt, ForStmt, ReturnStmt,
    AssertStmt, TryStmt, ExprStmt,
    BinaryExpr, UnaryExpr, CallExpr, MatchExpr, AwaitExpr,
    LambdaExpr, StructLit, ArrayLit, Ident, Literal,
    CaseClause, Pattern, FieldPattern, FieldInit,
    Param, Field, TypeExpr, FuncTypeDetail,
)


# Precedence levels (higher = tighter binding)
class Precedence(Enum):
    LOWEST = 1
    ASSIGN = 2          # =
    LOGICAL_OR = 3      # ||
    LOGICAL_AND = 4     # &&
    EQUALITY = 5        # == !=
    COMPARISON = 6      # < > <= >=
    ADDITIVE = 7        # + -
    MULTIPLICATIVE = 8  # * / %
    UNARY = 9           # - !
    POSTFIX = 10        # . [] ()
    PRIMARY = 11        # literals, identifiers


# Pratt parser function types
PrefixParseFn = Callable[['PrattParser'], Any]
InfixParseFn = Callable[['PrattParser', Any], Any]


class PrattParser:
    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.pos = 0
        self.current = tokens[0] if tokens else None

        # Prefix parsers (nud)
        self.prefix_parsers: Dict[TokenType, PrefixParseFn] = {
            TokenType.IDENT: self._parse_ident,
            TokenType.INT: self._parse_literal,
            TokenType.FLOAT: self._parse_literal,
            TokenType.STRING: self._parse_literal,
            TokenType.BOOL: self._parse_literal,
            TokenType.NULL: self._parse_literal,
            TokenType.MINUS: self._parse_prefix_expr,
            TokenType.NOT: self._parse_prefix_expr,
            TokenType.LPAREN: self._parse_grouped_expr,
            TokenType.LBRACE: self._parse_struct_lit,
            TokenType.LBRACKET: self._parse_array_lit,
            TokenType.BACKSLASH: self._parse_lambda,
            TokenType.MATCH: self._parse_match_expr,
            TokenType.AWAIT: self._parse_await_expr,
            # Hebrew tokens as identifiers/keywords
            TokenType.LET: self._parse_let_expr,
            TokenType.IF: self._parse_if_expr,
            TokenType.WHILE: self._parse_while_expr,
            TokenType.FOR: self._parse_for_expr,
            TokenType.FUNC: self._parse_func_expr,
            TokenType.RETURN: self._parse_return_expr,
            TokenType.ASSERT: self._parse_assert_expr,
            TokenType.TRY: self._parse_try_expr,
        }

        # Infix parsers (led)
        self.infix_parsers: Dict[TokenType, InfixParseFn] = {
            TokenType.PLUS: self._parse_infix_expr,
            TokenType.MINUS: self._parse_infix_expr,
            TokenType.STAR: self._parse_infix_expr,
            TokenType.SLASH: self._parse_infix_expr,
            TokenType.PERCENT: self._parse_infix_expr,
            TokenType.EQ: self._parse_infix_expr,
            TokenType.NE: self._parse_infix_expr,
            TokenType.LT: self._parse_infix_expr,
            TokenType.GT: self._parse_infix_expr,
            TokenType.LE: self._parse_infix_expr,
            TokenType.GE: self._parse_infix_expr,
            TokenType.AND: self._parse_infix_expr,
            TokenType.OR: self._parse_infix_expr,
            TokenType.ASSIGN: self._parse_assign_expr,
            TokenType.DOT: self._parse_field_access,
            TokenType.LBRACKET: self._parse_index_expr,
            TokenType.LPAREN: self._parse_call_expr,
        }

        # Precedence mapping
        self.precedences: Dict[TokenType, int] = {
            TokenType.ASSIGN: Precedence.ASSIGN.value,
            TokenType.OR: Precedence.LOGICAL_OR.value,
            TokenType.AND: Precedence.LOGICAL_AND.value,
            TokenType.EQ: Precedence.EQUALITY.value,
            TokenType.NE: Precedence.EQUALITY.value,
            TokenType.LT: Precedence.COMPARISON.value,
            TokenType.GT: Precedence.COMPARISON.value,
            TokenType.LE: Precedence.COMPARISON.value,
            TokenType.GE: Precedence.COMPARISON.value,
            TokenType.PLUS: Precedence.ADDITIVE.value,
            TokenType.MINUS: Precedence.ADDITIVE.value,
            TokenType.STAR: Precedence.MULTIPLICATIVE.value,
            TokenType.SLASH: Precedence.MULTIPLICATIVE.value,
            TokenType.PERCENT: Precedence.MULTIPLICATIVE.value,
            TokenType.DOT: Precedence.POSTFIX.value,
            TokenType.LBRACKET: Precedence.POSTFIX.value,
            TokenType.LPAREN: Precedence.POSTFIX.value,
        }

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

    def current_precedence(self) -> int:
        if self.current and self.current.type in self.precedences:
            return self.precedences[self.current.type]
        return Precedence.LOWEST.value

    def peek_precedence(self) -> int:
        nxt = self.peek()
        if nxt and nxt.type in self.precedences:
            return self.precedences[nxt.type]
        return Precedence.LOWEST.value

    def parse_expression(self, precedence: int = Precedence.LOWEST.value) -> Any:
        # Prefix (nud)
        tok_type = self.current.type if self.current else None
        prefix_fn = self.prefix_parsers.get(tok_type)
        if not prefix_fn:
            raise SyntaxError(f"No prefix parser for {tok_type}")

        left = prefix_fn(self)

        # Infix (led) - loop while next token has higher precedence
        while (self.current and self.current.type != TokenType.EOF and
               precedence < self.current_precedence()):
            tok_type = self.current.type
            infix_fn = self.infix_parsers.get(tok_type)
            if not infix_fn:
                break
            left = infix_fn(self, left)

        return left

    # ===== Prefix Parsers =====

    def _parse_ident(self, parser: 'PrattParser') -> Any:
        name = self.current.value
        self.advance()
        return Ident(
            type=NodeType.IDENT,
            line=self.current.line, column=self.current.column, offset=self.current.offset,
            name=name
        )

    def _parse_literal(self, parser: 'PrattParser') -> Any:
        tok = self.current
        self.advance()

        if tok.type == TokenType.INT:
            lit_type = 'int'
            value = int(tok.value)
        elif tok.type == TokenType.FLOAT:
            lit_type = 'float'
            value = float(tok.value)
        elif tok.type == TokenType.STRING:
            lit_type = 'string'
            value = tok.value
        elif tok.type == TokenType.BOOL:
            lit_type = 'bool'
            value = tok.value
        elif tok.type == TokenType.NULL:
            lit_type = 'null'
            value = None
        else:
            raise SyntaxError(f"Unknown literal type: {tok.type}")

        return Literal(
            type=NodeType.LITERAL,
            line=tok.line, column=tok.column, offset=tok.offset,
            value=value, literal_type=lit_type
        )

    def _parse_prefix_expr(self, parser: 'PrattParser') -> Any:
        tok = self.current
        op = tok.value
        self.advance()
        right = self.parse_expression(Precedence.UNARY.value)
        return UnaryExpr(
            type=NodeType.UNARY_EXPR,
            line=tok.line, column=tok.column, offset=tok.offset,
            operator=op, operand=right
        )

    def _parse_grouped_expr(self, parser: 'PrattParser') -> Any:
        self.advance()  # consume (
        expr = self.parse_expression()
        self.expect(TokenType.RPAREN)
        return expr

    def _parse_struct_lit(self, parser: 'PrattParser') -> Any:
        name_tok = self.current
        # Struct literal: Name { ... }
        # But we're at { - need to check if previous was ident
        # For now, treat as array/object literal
        self.advance()
        fields = []
        if not self.match(TokenType.RBRACE):
            while True:
                name_tok = self.expect(TokenType.IDENT)
                name = name_tok.value
                self.expect(TokenType.COLON)
                value = self.parse_expression()
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
            line=name_tok.line, column=name_tok.column, offset=name_tok.offset,
            name='', fields=fields  # name determined by context
        )

    def _parse_array_lit(self, parser: 'PrattParser') -> Any:
        self.advance()
        elements = []
        if not self.match(TokenType.RBRACKET):
            while True:
                elements.append(self.parse_expression())
                if not self.match(TokenType.COMMA):
                    break
            self.expect(TokenType.RBRACKET)
        return ArrayLit(
            type=NodeType.ARRAY_LIT,
            line=self.current.line, column=self.current.column, offset=self.current.offset,
            elements=elements
        )

    def _parse_lambda(self, parser: 'PrattParser') -> Any:
        self.advance()
        # Parse lambda: \params -> body
        # Expect (params) -> body
        self.expect(TokenType.LPAREN)
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
        self.expect(TokenType.ARROW)
        body = self.parse_expression()
        return LambdaExpr(
            type=NodeType.LAMBDA_EXPR,
            line=self.current.line, column=self.current.column, offset=self.current.offset,
            params=params, return_type=None, body=body
        )

    def _parse_match_expr(self, parser: 'PrattParser') -> Any:
        self.advance()
        subject = self.parse_expression()
        self.expect(TokenType.LBRACE)
        cases = []
        while not self.match(TokenType.RBRACE):
            cases.append(self._parse_case_clause())
        return MatchExpr(
            type=NodeType.MATCH_EXPR,
            line=self.current.line, column=self.current.column, offset=self.current.offset,
            subject=subject, cases=cases
        )

    def _parse_case_clause(self) -> Any:
        self.expect(TokenType.CASE)
        pattern = self._parse_pattern()
        self.expect(TokenType.FAT_ARROW)
        body = self.parse_expression()
        return CaseClause(
            type=NodeType.CASE_CLAUSE,
            line=self.current.line, column=self.current.column, offset=self.current.offset,
            pattern=pattern, body=body
        )

    def _parse_pattern(self) -> Any:
        if self.match(TokenType.UNDERSCORE):
            return Pattern(
                type=NodeType.PATTERN,
                line=self.current.line, column=self.current.column, offset=self.current.offset,
                kind='wildcard', value=None
            )
        if self.current and self.current.type in (TokenType.INT, TokenType.FLOAT, TokenType.STRING, TokenType.BOOL):
            tok = self.current
            self.advance()
            return Pattern(
                type=NodeType.PATTERN,
                line=tok.line, column=tok.column, offset=tok.offset,
                kind='literal', value=tok.value
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
                            sub_pattern = self._parse_pattern()
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
            pattern = self._parse_pattern()
            self.expect(TokenType.RPAREN)
            return pattern
        raise SyntaxError(f"Expected pattern, got {self.current}")

    def _parse_await_expr(self, parser: 'PrattParser') -> Any:
        self.advance()
        expr = self.parse_expression()
        return AwaitExpr(
            type=NodeType.AWAIT_EXPR,
            line=self.current.line, column=self.current.column, offset=self.current.offset,
            expression=expr
        )

    # Statement-like expressions (for expression position)
    def _parse_let_expr(self, parser: 'PrattParser') -> Any:
        self.advance()
        name_tok = self.expect(TokenType.IDENT)
        name = name_tok.value
        type_ann = None
        if self.match(TokenType.COLON):
            type_ann = self.parse_type_expr()
        self.expect(TokenType.ASSIGN)
        value = self.parse_expression()
        return LetStmt(
            type=NodeType.LET_STMT,
            line=name_tok.line, column=name_tok.column, offset=name_tok.offset,
            name=name, type_ann=type_ann, value=value
        )

    def _parse_if_expr(self, parser: 'PrattParser') -> Any:
        self.advance()
        condition = self.parse_expression()
        self.expect(TokenType.THEN)
        then_branch = self.parse_block()
        else_branch = None
        if self.match(TokenType.ELSE):
            else_branch = self.parse_block()
        return IfStmt(
            type=NodeType.IF_STMT,
            line=self.current.line, column=self.current.column, offset=self.current.offset,
            condition=condition, then_branch=then_branch, else_branch=else_branch
        )

    def _parse_while_expr(self, parser: 'PrattParser') -> Any:
        self.advance()
        condition = self.parse_expression()
        body = self.parse_block()
        return WhileStmt(
            type=NodeType.WHILE_STMT,
            line=self.current.line, column=self.current.column, offset=self.current.offset,
            condition=condition, body=body
        )

    def _parse_for_expr(self, parser: 'PrattParser') -> Any:
        self.advance()
        var_tok = self.expect(TokenType.IDENT)
        var = var_tok.value
        self.expect(TokenType.IN)
        iter_expr = self.parse_expression()
        body = self.parse_block()
        return ForStmt(
            type=NodeType.FOR_STMT,
            line=var_tok.line, column=var_tok.column, offset=var_tok.offset,
            var=var, iter_expr=iter_expr, body=body
        )

    def _parse_func_expr(self, parser: 'PrattParser') -> Any:
        self.advance()
        name_tok = self.expect(TokenType.IDENT)
        name = name_tok.value
        self.expect(TokenType.LPAREN)
        params = self._parse_params()
        self.expect(TokenType.RPAREN)
        return_type = None
        if self.match(TokenType.TYPE):
            return_type = self.parse_type_expr()
        body = self.parse_block()
        return FuncDecl(
            type=NodeType.FUNC_DECL,
            line=name_tok.line, column=name_tok.column, offset=name_tok.offset,
            name=name, params=params, return_type=return_type, body=body
        )

    def _parse_return_expr(self, parser: 'PrattParser') -> Any:
        self.advance()
        value = None
        if self.current and self.current.type not in (TokenType.RBRACE, TokenType.SEMICOLON, TokenType.EOF):
            value = self.parse_expression()
        return ReturnStmt(
            type=NodeType.RETURN_STMT,
            line=self.current.line, column=self.current.column, offset=self.current.offset,
            value=value
        )

    def _parse_assert_expr(self, parser: 'PrattParser') -> Any:
        self.advance()
        condition = self.parse_expression()
        return AssertStmt(
            type=NodeType.ASSERT_STMT,
            line=self.current.line, column=self.current.column, offset=self.current.offset,
            condition=condition
        )

    def _parse_try_expr(self, parser: 'PrattParser') -> Any:
        self.advance()
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
            line=self.current.line, column=self.current.column, offset=self.current.offset,
            try_block=try_block, catch_var=var, catch_type=catch_type, catch_block=catch_block
        )

    # ===== Infix Parsers =====

    def _parse_infix_expr(self, parser: 'PrattParser', left: Any) -> Any:
        tok = self.current
        op = tok.value
        self.advance()
        right = self.parse_expression(self.current_precedence())
        return BinaryExpr(
            type=NodeType.BINARY_EXPR,
            line=tok.line, column=tok.column, offset=tok.offset,
            left=left, operator=op, right=right
        )

    def _parse_assign_expr(self, parser: 'PrattParser', left: Any) -> Any:
        tok = self.current
        op = tok.value
        self.advance()
        right = self.parse_expression(Precedence.ASSIGN.value)
        return BinaryExpr(
            type=NodeType.BINARY_EXPR,
            line=tok.line, column=tok.column, offset=tok.offset,
            left=left, operator=op, right=right
        )

    def _parse_field_access(self, parser: 'PrattParser', left: Any) -> Any:
        self.advance()
        field_tok = self.expect(TokenType.IDENT)
        field = Ident(
            type=NodeType.IDENT,
            line=field_tok.line, column=field_tok.column, offset=field_tok.offset,
            name=field_tok.value
        )
        return BinaryExpr(
            type=NodeType.BINARY_EXPR,
            line=left.line, column=left.column, offset=left.offset,
            left=left, operator='.', right=field
        )

    def _parse_index_expr(self, parser: 'PrattParser', left: Any) -> Any:
        self.advance()
        index = self.parse_expression()
        self.expect(TokenType.RBRACKET)
        return BinaryExpr(
            type=NodeType.BINARY_EXPR,
            line=left.line, column=left.column, offset=left.offset,
            left=left, operator='[]', right=index
        )

    def _parse_call_expr(self, parser: 'PrattParser', left: Any) -> Any:
        self.advance()
        args = []
        if not self.match(TokenType.RPAREN):
            while True:
                args.append(self.parse_expression())
                if not self.match(TokenType.COMMA):
                    break
            self.expect(TokenType.RPAREN)
        callee_name = left.name if isinstance(left, Ident) else ''
        return CallExpr(
            type=NodeType.CALL_EXPR,
            line=left.line, column=left.column, offset=left.offset,
            callee=callee_name, arguments=args
        )

    # ===== Helper methods =====

    def _parse_params(self) -> List[Param]:
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

    def parse_block(self) -> Block:
        self.expect(TokenType.LBRACE)
        statements = []
        while not self.match(TokenType.RBRACE) and not self.at_end():
            statements.append(self.parse_statement())
        return Block(
            type=NodeType.BLOCK,
            line=self.current.line if self.current else 0,
            column=self.current.column if self.current else 0,
            offset=self.current.offset if self.current else 0,
            statements=statements
        )

    def parse_statement(self) -> Any:
        if self.current and self.current.type == TokenType.LBRACE:
            return self.parse_block()
        # Declarations
        if self.current and self.current.type in (TokenType.FUNC, TokenType.STRUCT, TokenType.TYPE, TokenType.CONST, TokenType.VAR):
            if self.current.type == TokenType.FUNC:
                self.advance()
                return self._parse_func_decl()
            elif self.current.type == TokenType.STRUCT:
                self.advance()
                return self._parse_struct_decl()
            elif self.current.type == TokenType.TYPE:
                self.advance()
                return self._parse_type_alias()
            elif self.current.type == TokenType.CONST:
                self.advance()
                return self._parse_const_decl()
            elif self.current.type == TokenType.VAR:
                self.advance()
                return self._parse_var_decl()
        # LET statement
        if self.match(TokenType.LET):
            return self._parse_let_stmt()
        elif self.match(TokenType.IF):
            return self._parse_if_stmt()
        elif self.match(TokenType.WHILE):
            return self._parse_while_stmt()
        elif self.match(TokenType.FOR):
            return self._parse_for_stmt()
        elif self.match(TokenType.RETURN):
            return self._parse_return_stmt()
        elif self.match(TokenType.ASSERT):
            return self._parse_assert_stmt()
        elif self.match(TokenType.TRY):
            return self._parse_try_stmt()
        else:
            expr = self.parse_expression()
            if isinstance(expr, Block):
                return expr
            return ExprStmt(
                type=NodeType.EXPR_STMT,
                line=expr.line, column=expr.column, offset=expr.offset,
                expression=expr
            )

    def _parse_let_stmt(self) -> Any:
        name_tok = self.expect(TokenType.IDENT)
        name = name_tok.value
        type_ann = None
        if self.match(TokenType.COLON):
            type_ann = self.parse_type_expr()
        self.expect(TokenType.ASSIGN)
        value = self.parse_expression()
        return LetStmt(
            type=NodeType.LET_STMT,
            line=name_tok.line, column=name_tok.column, offset=name_tok.offset,
            name=name, type_ann=type_ann, value=value
        )

    def _parse_if_stmt(self) -> Any:
        condition = self.parse_expression()
        self.expect(TokenType.THEN)
        then_branch = self.parse_block()
        else_branch = None
        if self.match(TokenType.ELSE):
            else_branch = self.parse_block()
        return IfStmt(
            type=NodeType.IF_STMT,
            line=self.current.line, column=self.current.column, offset=self.current.offset,
            condition=condition, then_branch=then_branch, else_branch=else_branch
        )

    def _parse_while_stmt(self) -> Any:
        condition = self.parse_expression()
        body = self.parse_block()
        return WhileStmt(
            type=NodeType.WHILE_STMT,
            line=self.current.line, column=self.current.column, offset=self.current.offset,
            condition=condition, body=body
        )

    def _parse_for_stmt(self) -> Any:
        var_tok = self.expect(TokenType.IDENT)
        var = var_tok.value
        self.expect(TokenType.IN)
        iter_expr = self.parse_expression()
        body = self.parse_block()
        return ForStmt(
            type=NodeType.FOR_STMT,
            line=var_tok.line, column=var_tok.column, offset=var_tok.offset,
            var=var, iter_expr=iter_expr, body=body
        )

    def _parse_return_stmt(self) -> Any:
        value = None
        if self.current and self.current.type not in (TokenType.RBRACE, TokenType.SEMICOLON, TokenType.EOF):
            value = self.parse_expression()
        return ReturnStmt(
            type=NodeType.RETURN_STMT,
            line=self.current.line, column=self.current.column, offset=self.current.offset,
            value=value
        )

    def _parse_assert_stmt(self) -> Any:
        condition = self.parse_expression()
        return AssertStmt(
            type=NodeType.ASSERT_STMT,
            line=self.current.line, column=self.current.column, offset=self.current.offset,
            condition=condition
        )

    def _parse_try_stmt(self) -> Any:
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
            line=self.current.line, column=self.current.column, offset=self.current.offset,
            try_block=try_block, catch_var=var, catch_type=catch_type, catch_block=catch_block
        )

    def _parse_func_decl(self) -> Any:
        name_tok = self.expect(TokenType.IDENT)
        name = name_tok.value
        self.expect(TokenType.LPAREN)
        params = self._parse_params()
        return_type = None
        if self.match(TokenType.TYPE):
            return_type = self.parse_type_expr()
        body = self.parse_block()
        return FuncDecl(
            type=NodeType.FUNC_DECL,
            line=name_tok.line, column=name_tok.column, offset=name_tok.offset,
            name=name, params=params, return_type=return_type, body=body
        )

    def _parse_struct_decl(self) -> Any:
        name_tok = self.expect(TokenType.IDENT)
        name = name_tok.value
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
            line=name_tok.line, column=name_tok.column, offset=name_tok.offset,
            name=name, fields=fields
        )

    def _parse_type_alias(self) -> Any:
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

    def _parse_const_decl(self) -> Any:
        name_tok = self.expect(TokenType.IDENT)
        name = name_tok.value
        type_ann = None
        if self.match(TokenType.COLON):
            type_ann = self.parse_type_expr()
        self.expect(TokenType.ASSIGN)
        value = self.parse_expression()
        return ConstDecl(
            type=NodeType.CONST_DECL,
            line=name_tok.line, column=name_tok.column, offset=name_tok.offset,
            name=name, type_ann=type_ann, value=value
        )

    def _parse_var_decl(self) -> Any:
        name_tok = self.expect(TokenType.IDENT)
        name = name_tok.value
        type_ann = None
        if self.match(TokenType.COLON):
            type_ann = self.parse_type_expr()
        self.expect(TokenType.ASSIGN)
        value = self.parse_expression()
        return VarDecl(
            type=NodeType.VAR_DECL,
            line=name_tok.line, column=name_tok.column, offset=name_tok.offset,
            name=name, type_ann=type_ann, value=value
        )

    def at_end(self) -> bool:
        return self.current is None or self.current.type == TokenType.EOF

    def parse_type_expr(self) -> TypeExpr:
        # Simplified - same as RD parser
        if self.current and self.current.type == TokenType.IDENT:
            name = self.current.value
            if name in ('int', 'float', 'string', 'bool', 'void', 'never'):
                self.advance()
                return TypeExpr(
                    type=NodeType.TYPE_EXPR,
                    line=self.current.line, column=self.current.column, offset=self.current.offset,
                    kind='prim', value=name
                )
            self.advance()
            if self.match(TokenType.LT):
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
                    if not self.match(TokenType.COMMA):
                        break
                    self.expect(TokenType.RPAREN)
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


def parse(tokens: List[Token]) -> Program:
    """Parse tokens into Program AST using Pratt parser."""
    parser = PrattParser(tokens)
    modules = []
    imports = []
    exports = []
    items = []

    while not parser.at_end():
        if parser.match(TokenType.MODULE):
            modules.append(parser._parse_module())
        elif parser.match(TokenType.IMPORT):
            imports.append(parser._parse_import())
        elif parser.match(TokenType.EXPORT):
            exports.append(parser._parse_export())
        else:
            items.append(parser.parse_statement())

    return Program(
        type=NodeType.PROGRAM,
        line=1, column=1, offset=0,
        modules=modules, imports=imports, exports=exports, items=items
    )


# Delegate missing methods to avoid duplication
def _delegate_methods():
    from svl.parser_rd import Parser as RDParser
    PrattParser._parse_module = RDParser.parse_module
    PrattParser._parse_import = RDParser.parse_import
    PrattParser._parse_export = RDParser.parse_export

_delegate_methods()


if __name__ == '__main__':
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