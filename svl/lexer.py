# svl/lexer.py
# Hand-written lexer for 22 Hebrew tokens
# Spike S1: Compare with Lark-generated lexer

from dataclasses import dataclass
from typing import List, Optional, Any
from enum import Enum, auto


class TokenType(Enum):
    # 22 Hebrew tokens
    LET = auto()      # א
    IF = auto()       # ב
    THEN = auto()     # ג
    ELSE = auto()     # ד
    WHILE = auto()    # ה
    FOR = auto()      # ו
    FUNC = auto()     # ז
    RETURN = auto()   # ח
    MATCH = auto()    # ט
    TYPE = auto()     # י
    STRUCT = auto()   # כ
    MODULE = auto()   # ל
    IMPORT = auto()   # מ
    EXPORT = auto()   # נ
    CONST = auto()    # ס
    VAR = auto()      # ע
    ASSERT = auto()   # פ
    TRY = auto()      # צ
    CATCH = auto()    # ק
    THROW = auto()    # ר
    ASYNC = auto()    # ש
    AWAIT = auto()    # ת

    # Standard tokens
    IDENT = auto()
    INT = auto()
    FLOAT = auto()
    STRING = auto()
    BOOL = auto()
    NULL = auto()

    # Effect tokens (H2: Effect System)
    EXCLAMATION = auto()     # !
    EFFECT = auto()          # effect keyword
    HANDLE = auto()          # handle keyword
    
    # Linear/Uniqueness type qualifiers (H3: Linear Types)
    LINEAR = auto()          # linear
    UNIQUE = auto()          # unique
    
    # Dependent type tokens (H4: Dependent Types)
    VEC = auto()             # Vec
    NAT = auto()             # Nat
    
    # Gradual typing tokens (H5: Gradual Typing)
    DYNAMIC = auto()         # ? (dynamic type)
    CAST = auto()            # as (cast operator)
    
    # Macro system tokens (H6: Macro System)
    MACRO = auto()           # macro
    MACRO_RULES = auto()     # macro_rules
    
    # Module functor tokens (H7: Module Functors)
    MODULE_TYPE = auto()     # module type
    MODULE_FUNCTOR = auto()  # module functor
    
    # Algebraic effects tokens (H8: Algebraic Effects)
    EFFECT_KW = auto()       # effect
    HANDLE_KW = auto()       # handle
    WITH_KW = auto()         # with
    
    # Type class tokens (H9: Type Classes)
    CLASS_KW = auto()        # class
    INSTANCE_KW = auto()     # instance
    WHERE_KW = auto()        # where
    
    # Higher-kinded type tokens (H10: HKT)
    KIND_STAR = auto()       # *
    KIND_ARROW = auto()      # -> (for kinds)
    
    # Refinement type tokens (H11: Refinement Types)
    REFINEMENT = auto()      # { v: T | P(v) }
    PIPE = auto()            # | (for refinement)
    
    # Intersection/Union type tokens (H12: Intersection/Union Types)
    AMPERSAND = auto()       # &
    UNION = auto()           # |
    
    # Quantified constraint tokens (H13: Quantified Constraints)
    FORALL = auto()          # forall
    IMPLIES = auto()         # =>
    
    # Modal type tokens (H16: Modal Types)
    BOX = auto()             # □ (box/necessity)
    DIAMOND = auto()         # ◇ (diamond/possibility)
    
    # Type family tokens (H14: Type Families)
    TYPE_FAMILY = auto()     # type family

    # Operators
    PLUS = auto()
    MINUS = auto()
    STAR = auto()
    SLASH = auto()
    PERCENT = auto()
    EQ = auto()
    NE = auto()
    LT = auto()
    GT = auto()
    LE = auto()
    GE = auto()
    AND = auto()
    OR = auto()
    NOT = auto()
    IN = auto()
    ASSIGN = auto()
    ARROW = auto()    # ->
    FAT_ARROW = auto()  # =>
    FN = auto()
    BACKSLASH = auto()  # \
    DOT = auto()
    LBRACKET = auto()
    RBRACKET = auto()
    LPAREN = auto()
    RPAREN = auto()
    LBRACE = auto()
    RBRACE = auto()
    COMMA = auto()
    COLON = auto()
    SEMICOLON = auto()

    # Bitwise operators
    BITWISE_AND = auto()   # &
    BITWISE_OR = auto()    # |
    BITWISE_XOR = auto()   # ^
    BITWISE_NOT = auto()   # ~
    SHIFT_LEFT = auto()    # <<
    SHIFT_RIGHT = auto()   # >>

    # Assignment operators
    ASSIGN_ADD = auto()    # +=
    ASSIGN_SUB = auto()    # -=
    ASSIGN_MUL = auto()    # *=
    ASSIGN_DIV = auto()    # /=
    ASSIGN_MOD = auto()    # %=
    ASSIGN_AND = auto()    # &=
    ASSIGN_OR = auto()     # |=
    ASSIGN_XOR = auto()    # ^=
    ASSIGN_SHL = auto()    # <<=
    ASSIGN_SHR = auto()    # >>=

    # Ternary/conditional
    TERNARY_QUESTION = auto()  # ?

    # Range operator
    RANGE = auto()           # ..

    # Match / pattern tokens
    CASE = auto()            # case
    UNDERSCORE = auto()      # _ (wildcard pattern)

    # Special
    EOF = auto()
    ERROR = auto()
    
    # Version tokens (H1: Semantic Versioning)
    VERSION = auto()           # 1.2.3
    VERSION_CONSTRAINT = auto()  # ^1.0.0, ~2.1.0, >=1.0.0
    AT = auto()                # @


# Hebrew token mapping (22 standard letters, no final forms)
# Code points MUST be the regular (non-final) forms: ן/ץ/ך/ם/ף are NOT tokens.
HEBREW_TOKENS = {
    '\u05D0': TokenType.LET,      # א
    '\u05D1': TokenType.IF,       # ב
    '\u05D2': TokenType.THEN,     # ג
    '\u05D3': TokenType.ELSE,     # ד
    '\u05D4': TokenType.WHILE,    # ה
    '\u05D5': TokenType.FOR,      # ו
    '\u05D6': TokenType.FUNC,     # ז
    '\u05D7': TokenType.RETURN,   # ח
    '\u05D8': TokenType.MATCH,    # ט
    '\u05D9': TokenType.TYPE,     # י
    '\u05DB': TokenType.STRUCT,   # כ
    '\u05DC': TokenType.MODULE,   # ל
    '\u05DE': TokenType.IMPORT,   # מ
    '\u05E0': TokenType.EXPORT,   # נ
    '\u05E1': TokenType.CONST,    # ס
    '\u05E2': TokenType.VAR,      # ע
    '\u05E4': TokenType.ASSERT,   # פ
    '\u05E6': TokenType.TRY,      # צ
    '\u05E7': TokenType.CATCH,    # ק
    '\u05E8': TokenType.THROW,    # ר
    '\u05E9': TokenType.ASYNC,    # ש
    '\u05EA': TokenType.AWAIT,    # ת
}

# Reverse mapping for debugging
TOKEN_TO_HEBREW = {v: k for k, v in HEBREW_TOKENS.items()}


@dataclass(frozen=True)
class Token:
    type: TokenType
    value: Any
    line: int
    column: int
    offset: int  # byte offset from start of input

    def __repr__(self):
        if self.type in HEBREW_TOKENS.values():
            hebrew = TOKEN_TO_HEBREW.get(self.type, '?')
            return f"Token({self.type.name}, '{hebrew}', line={self.line}, col={self.column})"
        return f"Token({self.type.name}, '{self.value}', line={self.line}, col={self.column})"


class Lexer:
    def __init__(self, source: str):
        self.source = source
        self.length = len(source)
        self.pos = 0          # byte position
        self.line = 1
        self.column = 1
        self.tokens: List[Token] = []

    def tokenize(self) -> List[Token]:
        while self.pos < self.length:
            self._skip_whitespace_and_comments()
            if self.pos >= self.length:
                break
            self._scan_token()
        self.tokens.append(Token(TokenType.EOF, '', self.line, self.column, self.pos))
        return self.tokens

    def _skip_whitespace_and_comments(self):
        while self.pos < self.length:
            ch = self.source[self.pos]
            if ch in ' \t\r\n':
                if ch == '\n':
                    self.line += 1
                    self.column = 1
                else:
                    self.column += 1
                self.pos += 1
            elif ch == '/' and self.pos + 1 < self.length:
                next_ch = self.source[self.pos + 1]
                if next_ch == '/':
                    # Single-line comment
                    self.pos += 2
                    self.column += 2
                    while self.pos < self.length and self.source[self.pos] != '\n':
                        self.pos += 1
                        self.column += 1
                elif next_ch == '*':
                    # Multi-line comment
                    self.pos += 2
                    self.column += 2
                    while self.pos + 1 < self.length:
                        if self.source[self.pos] == '*' and self.source[self.pos + 1] == '/':
                            self.pos += 2
                            self.column += 2
                            break
                        if self.source[self.pos] == '\n':
                            self.line += 1
                            self.column = 1
                        else:
                            self.column += 1
                        self.pos += 1
                else:
                    break
            else:
                break

    def _scan_token(self):
        start_pos = self.pos
        start_line = self.line
        start_col = self.column
        ch = self.source[self.pos]

        # Hebrew tokens (single character)
        if ch in HEBREW_TOKENS:
            token_type = HEBREW_TOKENS[ch]
            self.tokens.append(Token(token_type, ch, start_line, start_col, start_pos))
            self.pos += 1
            self.column += 1
            return

        # String literals
        if ch == '"':
            self._scan_string(start_pos, start_line, start_col)
            return

        # Wildcard `_` — a lone underscore is the match wildcard pattern, but `_foo`
        # is still an ordinary identifier.
        if ch == '_':
            nxt = self.source[self.pos + 1] if self.pos + 1 < self.length else ''
            if not (nxt.isalnum() or nxt == '_'):
                self._emit(TokenType.UNDERSCORE, '_', 1, start_pos, start_line, start_col)
                return

        # Identifiers and keywords (ASCII)
        if ch.isalpha() or ch == '_':
            self._scan_identifier(start_pos, start_line, start_col)
            return

        # Numbers
        if ch.isdigit():
            self._scan_number(start_pos, start_line, start_col)
            return

        # Operators and punctuation
        self._scan_operator_or_punct(start_pos, start_line, start_col)

    def _scan_string(self, start_pos: int, start_line: int, start_col: int):
        self.pos += 1  # Skip opening quote
        self.column += 1
        value = ''
        while self.pos < self.length:
            ch = self.source[self.pos]
            if ch == '"':
                self.pos += 1
                self.column += 1
                break
            elif ch == '\\':
                self.pos += 1
                self.column += 1
                if self.pos < self.length:
                    esc = self.source[self.pos]
                    escapes = {'n': '\n', 't': '\t', 'r': '\r', '\\': '\\', '"': '"', "'": "'"}
                    value += escapes.get(esc, esc)
                    self.pos += 1
                    self.column += 1
            elif ch == '\n':
                # Unclosed string
                self.tokens.append(Token(TokenType.ERROR, value, start_line, start_col, start_pos))
                return
            else:
                value += ch
                self.pos += 1
                self.column += 1
        else:
            # EOF without closing quote
            self.tokens.append(Token(TokenType.ERROR, value, start_line, start_col, start_pos))
            return

        self.tokens.append(Token(TokenType.STRING, value, start_line, start_col, start_pos))

    def _scan_identifier(self, start_pos: int, start_line: int, start_col: int):
        value = ''
        while self.pos < self.length:
            ch = self.source[self.pos]
            if ch.isalnum() or ch == '_':
                value += ch
                self.pos += 1
                self.column += 1
            else:
                break

        # Check for keywords (ASCII aliases for Hebrew tokens)
        keywords = {
            'let': TokenType.LET, 'if': TokenType.IF, 'then': TokenType.THEN,
            'else': TokenType.ELSE, 'while': TokenType.WHILE, 'for': TokenType.FOR,
            'func': TokenType.FUNC, 'return': TokenType.RETURN, 'match': TokenType.MATCH,
            'type': TokenType.TYPE, 'struct': TokenType.STRUCT, 'module': TokenType.MODULE,
            'import': TokenType.IMPORT, 'export': TokenType.EXPORT, 'const': TokenType.CONST,
            'var': TokenType.VAR, 'assert': TokenType.ASSERT, 'try': TokenType.TRY,
            'catch': TokenType.CATCH, 'throw': TokenType.THROW, 'async': TokenType.ASYNC,
            'await': TokenType.AWAIT,
            'in': TokenType.IN,
            'fn': TokenType.FN,
            'effect': TokenType.EFFECT, 'handle': TokenType.HANDLE,
            'linear': TokenType.LINEAR, 'unique': TokenType.UNIQUE,
            'vec': TokenType.VEC, 'nat': TokenType.NAT,
            'as': TokenType.CAST,
            'macro': TokenType.MACRO, 'macro_rules': TokenType.MACRO_RULES,
            'module_type': TokenType.MODULE_TYPE, 'module_functor': TokenType.MODULE_FUNCTOR,
            'functor': TokenType.MODULE_FUNCTOR,
            'effect': TokenType.EFFECT_KW, 'handle': TokenType.HANDLE_KW, 'with': TokenType.WITH_KW,
            'class': TokenType.CLASS_KW, 'instance': TokenType.INSTANCE_KW, 'where': TokenType.WHERE_KW,
            'forall': TokenType.FORALL, 'implies': TokenType.IMPLIES,
            'box': TokenType.BOX, 'diamond': TokenType.DIAMOND,
            'case': TokenType.CASE,
            'true': TokenType.BOOL, 'false': TokenType.BOOL, 'null': TokenType.NULL,
            'int': TokenType.IDENT, 'float': TokenType.IDENT, 'string': TokenType.IDENT,
            'bool': TokenType.IDENT, 'void': TokenType.IDENT, 'never': TokenType.IDENT,
        }
        token_type = keywords.get(value, TokenType.IDENT)
        if token_type == TokenType.BOOL:
            self.tokens.append(Token(token_type, value == 'true', start_line, start_col, start_pos))
        elif token_type == TokenType.NULL:
            self.tokens.append(Token(token_type, None, start_line, start_col, start_pos))
        else:
            self.tokens.append(Token(token_type, value, start_line, start_col, start_pos))

    def _scan_number(self, start_pos: int, start_line: int, start_col: int):
        value = ''
        is_float = False
        is_version = False
        dot_count = 0
        while self.pos < self.length:
            ch = self.source[self.pos]
            if ch.isdigit():
                value += ch
                self.pos += 1
                self.column += 1
            elif ch == '.':
                # Check if next char is digit
                if self.pos + 1 < self.length and self.source[self.pos + 1].isdigit():
                    dot_count += 1
                    if dot_count == 1 and not is_float:
                        is_float = True
                        value += ch
                        self.pos += 1
                        self.column += 1
                    elif dot_count == 2:
                        # Version number: 1.2.3
                        is_version = True
                        value += ch
                        self.pos += 1
                        self.column += 1
                    else:
                        break
                else:
                    break
            else:
                break

        if is_version:
            self.tokens.append(Token(TokenType.VERSION, value, start_line, start_col, start_pos))
        elif is_float:
            self.tokens.append(Token(TokenType.FLOAT, float(value), start_line, start_col, start_pos))
        else:
            self.tokens.append(Token(TokenType.INT, int(value), start_line, start_col, start_pos))

    def _scan_operator_or_punct(self, start_pos: int, start_line: int, start_col: int):
        ch = self.source[self.pos]

        # Multi-character operators (check longest first)
        three_char = self.source[self.pos:self.pos+3] if self.pos + 2 < self.length else ''
        two_char = self.source[self.pos:self.pos+2] if self.pos + 1 < self.length else ''

        # Three char operators
        if three_char == '<<=':
            self._emit(TokenType.ASSIGN_SHL, '<<=', 3, start_pos, start_line, start_col)
        elif three_char == '>>=':
            self._emit(TokenType.ASSIGN_SHR, '>>=', 3, start_pos, start_line, start_col)
        # Two char operators
        elif two_char == '==':
            self._emit(TokenType.EQ, '==', 2, start_pos, start_line, start_col)
        elif two_char == '!=':
            self._emit(TokenType.NE, '!=', 2, start_pos, start_line, start_col)
        elif two_char == '<=':
            self._emit(TokenType.LE, '<=', 2, start_pos, start_line, start_col)
        elif two_char == '>=':
            self._emit(TokenType.GE, '>=', 2, start_pos, start_line, start_col)
        elif two_char == '&&':
            self._emit(TokenType.AND, '&&', 2, start_pos, start_line, start_col)
        elif two_char == '||':
            self._emit(TokenType.OR, '||', 2, start_pos, start_line, start_col)
        elif two_char == '->':
            self._emit(TokenType.ARROW, '->', 2, start_pos, start_line, start_col)
        elif two_char == '=>':
            self._emit(TokenType.FAT_ARROW, '=>', 2, start_pos, start_line, start_col)
        elif two_char == '<<':
            self._emit(TokenType.SHIFT_LEFT, '<<', 2, start_pos, start_line, start_col)
        elif two_char == '>>':
            self._emit(TokenType.SHIFT_RIGHT, '>>', 2, start_pos, start_line, start_col)
        elif two_char == '+=':
            self._emit(TokenType.ASSIGN_ADD, '+=', 2, start_pos, start_line, start_col)
        elif two_char == '-=':
            self._emit(TokenType.ASSIGN_SUB, '-=', 2, start_pos, start_line, start_col)
        elif two_char == '*=':
            self._emit(TokenType.ASSIGN_MUL, '*=', 2, start_pos, start_line, start_col)
        elif two_char == '/=':
            self._emit(TokenType.ASSIGN_DIV, '/=', 2, start_pos, start_line, start_col)
        elif two_char == '%=':
            self._emit(TokenType.ASSIGN_MOD, '%=', 2, start_pos, start_line, start_col)
        elif two_char == '&=':
            self._emit(TokenType.ASSIGN_AND, '&=', 2, start_pos, start_line, start_col)
        elif two_char == '|=':
            self._emit(TokenType.ASSIGN_OR, '|=', 2, start_pos, start_line, start_col)
        elif two_char == '^=':
            self._emit(TokenType.ASSIGN_XOR, '^=', 2, start_pos, start_line, start_col)
        elif two_char == '..':
            self._emit(TokenType.RANGE, '..', 2, start_pos, start_line, start_col)
        # Single char
        elif ch == '+':
            self._emit(TokenType.PLUS, '+', 1, start_pos, start_line, start_col)
        elif ch == '-':
            self._emit(TokenType.MINUS, '-', 1, start_pos, start_line, start_col)
        elif ch == '*':
            self._emit(TokenType.STAR, '*', 1, start_pos, start_line, start_col)
        elif ch == '/':
            self._emit(TokenType.SLASH, '/', 1, start_pos, start_line, start_col)
        elif ch == '%':
            self._emit(TokenType.PERCENT, '%', 1, start_pos, start_line, start_col)
        elif ch == '=':
            self._emit(TokenType.ASSIGN, '=', 1, start_pos, start_line, start_col)
        elif ch == '<':
            self._emit(TokenType.LT, '<', 1, start_pos, start_line, start_col)
        elif ch == '>':
            self._emit(TokenType.GT, '>', 1, start_pos, start_line, start_col)
        elif ch == '&':
            self._emit(TokenType.BITWISE_AND, '&', 1, start_pos, start_line, start_col)
        elif ch == '|':
            self._emit(TokenType.BITWISE_OR, '|', 1, start_pos, start_line, start_col)
        elif ch == '^':
            self._emit(TokenType.BITWISE_XOR, '^', 1, start_pos, start_line, start_col)
        elif ch == '~':
            self._emit(TokenType.BITWISE_NOT, '~', 1, start_pos, start_line, start_col)
        elif ch == '□':
            self._emit(TokenType.BOX, '□', 1, start_pos, start_line, start_col)
        elif ch == '◇':
            self._emit(TokenType.DIAMOND, '◇', 1, start_pos, start_line, start_col)
        elif ch == '.':
            self._emit(TokenType.DOT, '.', 1, start_pos, start_line, start_col)
        elif ch == '[':
            self._emit(TokenType.LBRACKET, '[', 1, start_pos, start_line, start_col)
        elif ch == ']':
            self._emit(TokenType.RBRACKET, ']', 1, start_pos, start_line, start_col)
        elif ch == '(':
            self._emit(TokenType.LPAREN, '(', 1, start_pos, start_line, start_col)
        elif ch == ')':
            self._emit(TokenType.RPAREN, ')', 1, start_pos, start_line, start_col)
        elif ch == '{':
            self._emit(TokenType.LBRACE, '{', 1, start_pos, start_line, start_col)
        elif ch == '}':
            self._emit(TokenType.RBRACE, '}', 1, start_pos, start_line, start_col)
        elif ch == ',':
            self._emit(TokenType.COMMA, ',', 1, start_pos, start_line, start_col)
        elif ch == ':':
            self._emit(TokenType.COLON, ':', 1, start_pos, start_line, start_col)
        elif ch == ';':
            self._emit(TokenType.SEMICOLON, ';', 1, start_pos, start_line, start_col)
        elif ch == '?':
            self._emit(TokenType.TERNARY_QUESTION, '?', 1, start_pos, start_line, start_col)
        elif ch == '!':
            self._emit(TokenType.EXCLAMATION, '!', 1, start_pos, start_line, start_col)
        elif ch == '@':
            self._emit(TokenType.AT, '@', 1, start_pos, start_line, start_col)
        elif ch == '\\':
            self._emit(TokenType.BACKSLASH, '\\', 1, start_pos, start_line, start_col)
        elif ch in '^~><=':
            # Version constraint operators: ^, ~, >=, <=, >, <
            # Check for two-char constraints first
            two_char = self.source[self.pos:self.pos+2] if self.pos + 1 < self.length else ''
            if two_char in ('>=', '<=', '!='):
                self._emit(TokenType.VERSION_CONSTRAINT, two_char, 2, start_pos, start_line, start_col)
            else:
                self._emit(TokenType.VERSION_CONSTRAINT, ch, 1, start_pos, start_line, start_col)
        else:
            # Unknown character
            self.tokens.append(Token(TokenType.ERROR, ch, start_line, start_col, start_pos))
            self.pos += 1
            self.column += 1

    def _scan_lambda(self, start_pos: int, start_line: int, start_col: int):
        # Consume backslash
        self.pos += 1
        self.column += 1
        # Lambda parameter (simple: just an identifier)
        if self.pos < self.length and (self.source[self.pos].isalpha() or self.source[self.pos] == '_'):
            param_start = self.pos
            param = ''
            while self.pos < self.length and (self.source[self.pos].isalnum() or self.source[self.pos] == '_'):
                param += self.source[self.pos]
                self.pos += 1
                self.column += 1
            # Emit backslash as part of lambda syntax
            self.tokens.append(Token(TokenType.ERROR, '\\' + param, start_line, start_col, start_pos))
        else:
            self.tokens.append(Token(TokenType.ERROR, '\\', start_line, start_col, start_pos))

    def _emit(self, token_type: TokenType, value: str, length: int, start_pos: int, start_line: int, start_col: int):
        self.tokens.append(Token(token_type, value, start_line, start_col, start_pos))
        self.pos += length
        self.column += length


def tokenize(source: str) -> List[Token]:
    """Convenience function to tokenize source code."""
    lexer = Lexer(source)
    return lexer.tokenize()


if __name__ == '__main__':
    # Quick test
    test_code = '''
    MODULE main {
      FUNC main(): void {
        LET x: int = 42
        IF x > 0 THEN { RETURN } ELSE { RETURN }
      }
    }
    '''
    tokens = tokenize(test_code)
    for t in tokens:
        print(t)