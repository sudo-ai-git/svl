"""Hebrew keyword surface: the 22-letter alias, pinned by execution.

The Hebrew alphabet spells the 22 SVL keywords; the ASCII spellings are aliases for the same
tokens.  Two properties define "alias" here and both are easy to let regress silently:

* every intended letter maps to its intended token (22/22), and
* a program written with the Hebrew keywords compiles to **byte-identical** WASM to its ASCII
  spelling.  They are one language with two spellings, not two languages.

Final forms (sofit: ך ם ן ף ץ) are **excluded by design** -- see KB §3.  A sofit letter only
occurs at the end of a Hebrew word, so using one as a keyword would be ambiguous; they lex as
ordinary identifiers rather than as tokens or as errors.

This module is deliberately data + two checks.  It invents no new semantics.
"""
from typing import Any, Dict, List

from svl.lexer import HEBREW_TOKENS, TokenType, tokenize

# The intended 22-letter keyword surface, written out as data so a drift in either
# `HEBREW_TOKENS` or the intended design shows up as a failed check rather than a surprise.
HEBREW_KEYWORDS: Dict[str, str] = {
    'א': 'LET', 'ב': 'IF', 'ג': 'THEN', 'ד': 'ELSE', 'ה': 'WHILE',
    'ו': 'FOR', 'ז': 'FUNC', 'ח': 'RETURN', 'ט': 'MATCH', 'י': 'TYPE',
    'כ': 'STRUCT', 'ל': 'MODULE', 'מ': 'IMPORT', 'נ': 'EXPORT', 'ס': 'CONST',
    'ע': 'VAR', 'פ': 'ASSERT', 'צ': 'TRY', 'ק': 'CATCH', 'ר': 'THROW',
    'ש': 'ASYNC', 'ת': 'AWAIT',
}

# Final forms, deliberately NOT keywords.
SOFIT_LETTERS: Dict[str, str] = {
    'ך': 'final KAF', 'ם': 'final MEM', 'ן': 'final NUN',
    'ף': 'final PE', 'ץ': 'final TSADI',
}

# ASCII alias for each Hebrew keyword, used to build the transliteration.
ASCII_ALIAS: Dict[str, str] = {
    'LET': 'let', 'IF': 'if', 'THEN': 'then', 'ELSE': 'else', 'WHILE': 'while',
    'FOR': 'for', 'FUNC': 'func', 'RETURN': 'return', 'MATCH': 'match', 'TYPE': 'type',
    'STRUCT': 'struct', 'MODULE': 'module', 'IMPORT': 'import', 'EXPORT': 'export',
    'CONST': 'const', 'VAR': 'var', 'ASSERT': 'assert', 'TRY': 'try', 'CATCH': 'catch',
    'THROW': 'throw', 'ASYNC': 'async', 'AWAIT': 'await',
}


def verify_mapping() -> Dict[str, bool]:
    """Check every intended Hebrew letter maps to its intended token (expect 22/22)."""
    out: Dict[str, bool] = {}
    for letter, token_name in HEBREW_KEYWORDS.items():
        token = HEBREW_TOKENS.get(letter)
        out[letter] = token is not None and token.name == token_name
    return out


def to_hebrew(source: str) -> str:
    """Rewrite the ASCII keywords in `source` to their Hebrew letters.

    Longest alias first so `assert` is not consumed as `assert`->`as`+`sert`.  Only whole
    words are replaced: a naive str.replace would corrupt identifiers containing a keyword as
    a substring, so this matches on word boundaries.
    """
    import re
    out = source
    for token_name, alias in sorted(ASCII_ALIAS.items(), key=lambda kv: -len(kv[1])):
        letter = next(l for l, t in HEBREW_KEYWORDS.items() if t == token_name)
        out = re.sub(r'\b' + re.escape(alias) + r'\b', letter, out)
    return out


def verify_alias(source: str) -> Dict[str, Any]:
    """Compile `source` and its Hebrew spelling; they must produce identical WAT.

    Returns the comparison plus the individual hashes, so a failure can be located.
    """
    import hashlib
    from svl.compiler_wasm import compile_file_to_wasm

    ascii_wat = compile_file_to_wasm(source)
    hebrew_wat = compile_file_to_wasm(to_hebrew(source))
    return {
        'identical': ascii_wat == hebrew_wat,
        'ascii_sha256': hashlib.sha256(ascii_wat.encode()).hexdigest(),
        'hebrew_sha256': hashlib.sha256(hebrew_wat.encode()).hexdigest(),
        'ascii_bytes': len(ascii_wat),
    }


def verify_sofit_excluded() -> Dict[str, bool]:
    """Final forms must NOT be keywords -- they lex as identifiers (documented, not a defect)."""
    out: Dict[str, bool] = {}
    for letter in SOFIT_LETTERS:
        tokens = [t for t in tokenize(letter) if t.type != TokenType.EOF]
        out[letter] = len(tokens) == 1 and tokens[0].type == TokenType.IDENT
    return out
