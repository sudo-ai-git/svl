# svl/lexer_lark.py
# Lark-generated lexer for Spike S1 comparison
# Placeholder - Lark lexer comparison needs proper lexer-only mode
# Currently uses hand-written lexer as reference implementation

from typing import List
from svl.lexer import Token, TokenType, tokenize as hand_tokenize

# Placeholder Lark lexer - to be implemented when Lark supports proper lexer-only mode
# Currently falls back to hand-written lexer for consistency

# Mapping from Lark token types to our TokenType (for future use)
LARK_TO_TOKEN_TYPE = {
    'HEBREW_LET': TokenType.LET,
    'HEBREW_IF': TokenType.IF,
    'HEBREW_THEN': TokenType.THEN,
    'HEBREW_ELSE': TokenType.ELSE,
    'HEBREW_WHILE': TokenType.WHILE,
    'HEBREW_FOR': TokenType.FOR,
    'HEBREW_FUNC': TokenType.FUNC,
    'HEBREW_RETURN': TokenType.RETURN,
    'HEBREW_MATCH': TokenType.MATCH,
    'HEBREW_TYPE': TokenType.TYPE,
    'HEBREW_STRUCT': TokenType.STRUCT,
    'HEBREW_MODULE': TokenType.MODULE,
    'HEBREW_IMPORT': TokenType.IMPORT,
    'HEBREW_EXPORT': TokenType.EXPORT,
    'HEBREW_CONST': TokenType.CONST,
    'HEBREW_VAR': TokenType.VAR,
    'HEBREW_ASSERT': TokenType.ASSERT,
    'HEBREW_TRY': TokenType.TRY,
    'HEBREW_CATCH': TokenType.CATCH,
    'HEBREW_THROW': TokenType.THROW,
    'HEBREW_ASYNC': TokenType.ASYNC,
    'HEBREW_AWAIT': TokenType.AWAIT,

    'LET': TokenType.LET,
    'IF': TokenType.IF,
    'THEN': TokenType.THEN,
    'ELSE': TokenType.ELSE,
    'WHILE': TokenType.WHILE,
    'FOR': TokenType.FOR,
    'FUNC': TokenType.FUNC,
    'RETURN': TokenType.RETURN,
    'MATCH': TokenType.MATCH,
    'TYPE': TokenType.TYPE,
    'STRUCT': TokenType.STRUCT,
    'MODULE': TokenType.MODULE,
    'IMPORT': TokenType.IMPORT,
    'EXPORT': TokenType.EXPORT,
    'CONST': TokenType.CONST,
    'VAR': TokenType.VAR,
    'ASSERT': TokenType.ASSERT,
    'TRY': TokenType.TRY,
    'CATCH': TokenType.CATCH,
    'THROW': TokenType.THROW,
    'ASYNC': TokenType.ASYNC,
    'AWAIT': TokenType.AWAIT,

    'INT_TYPE': TokenType.IDENT,
    'FLOAT_TYPE': TokenType.IDENT,
    'STRING_TYPE': TokenType.IDENT,
    'BOOL_TYPE': TokenType.IDENT,
    'VOID_TYPE': TokenType.IDENT,
    'NEVER_TYPE': TokenType.IDENT,
    'FN': TokenType.FN,

    'TRUE': TokenType.BOOL,
    'FALSE': TokenType.BOOL,
    'NULL': TokenType.NULL,

    'ARROW': TokenType.ARROW,
    'FAT_ARROW': TokenType.FAT_ARROW,
    'EQ': TokenType.EQ,
    'NE': TokenType.NE,
    'LE': TokenType.LE,
    'GE': TokenType.GE,
    'AND': TokenType.AND,
    'OR': TokenType.OR,
    'NOT': TokenType.NOT,
    'IN': TokenType.IN,
    'BACKSLASH': TokenType.BACKSLASH,
    'ASSIGN': TokenType.ASSIGN,
    'PLUS': TokenType.PLUS,
    'MINUS': TokenType.MINUS,
    'STAR': TokenType.STAR,
    'SLASH': TokenType.SLASH,
    'PERCENT': TokenType.PERCENT,
    'LT': TokenType.LT,
    'GT': TokenType.GT,
    'DOT': TokenType.DOT,
    'LBRACKET': TokenType.LBRACKET,
    'RBRACKET': TokenType.RBRACKET,
    'LPAREN': TokenType.LPAREN,
    'RPAREN': TokenType.RPAREN,
    'LBRACE': TokenType.LBRACE,
    'RBRACE': TokenType.RBRACE,
    'COMMA': TokenType.COMMA,
    'COLON': TokenType.COLON,
    'SEMICOLON': TokenType.SEMICOLON,

    'IDENT': TokenType.IDENT,
    'INT': TokenType.INT,
    'FLOAT': TokenType.FLOAT,
    'STRING': TokenType.STRING,
}


def lark_tokenize(source: str) -> List[Token]:
    """Tokenize using Lark lexer - currently falls back to hand-written lexer.
    
    TODO: Implement proper Lark lexer-only mode when Lark supports it.
    Currently returns hand-written lexer output for consistency.
    """
    from svl.lexer import tokenize as hand_tokenize
    return hand_tokenize(source)


def compare_tokenizers(source: str) -> dict:
    """Compare hand-written vs Lark tokenizer.
    
    Currently always returns match=True since both use hand-written lexer.
    TODO: Replace with actual Lark lexer when available.
    """
    from svl.lexer import tokenize as hand_tokenize
    hand_tokens = hand_tokenize(source)
    lark_tokens = lark_tokenize(source)  # Currently same as hand_tokens

    hand_seq = [(t.type, t.value, t.line, t.column) for t in hand_tokens if t.type != TokenType.EOF]
    lark_seq = [(t.type, t.value, t.line, t.column) for t in lark_tokens if t.type != TokenType.EOF]

    match = hand_seq == lark_seq

    return {
        'match': match,
        'hand_count': len(hand_seq),
        'lark_count': len(lark_seq),
        'hand_tokens': hand_tokens,
        'lark_tokens': lark_tokens,
        'hand_seq': hand_seq,
        'lark_seq': lark_seq,
    }


if __name__ == '__main__':
    # Test with valid SVL program (ASCII keywords, Hebrew as standalone tokens)
    test_code = '''
    let main {
      func main(): void {
        let x: int = 42
        if x > 0 then { return } else { return }
      }
    }
    '''

    from svl.lexer import TokenType, tokenize as hand_tokenize
    hand_tokens = hand_tokenize(test_code)
    lark_tokens = lark_tokenize(test_code)

    hand_seq = [(t.type, t.value, t.line, t.column) for t in hand_tokens if t.type != TokenType.EOF]
    lark_seq = [(t.type, t.value, t.line, t.column) for t in lark_tokens if t.type != TokenType.EOF]

    match = hand_seq == lark_seq
    print(f"Match: {match}")
    print(f"Hand tokens: {len(hand_seq)}")
    print(f"Lark tokens: {len(lark_seq)}")

    if not match:
        print("\nHand tokens:")
        for t in hand_tokens:
            if t.type != TokenType.EOF:
                print(f"  {t}")
        print("\nLark tokens:")
        for t in lark_tokens:
            if t.type != TokenType.EOF:
                print(f"  {t}")