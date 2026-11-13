"""LSP diagnostics carry real source spans, not a blanket line 0.

Before this, every diagnostic the language server published used
`Position(line=0)` regardless of where the defect was.  The type checker now records
the line of the statement it was checking when each diagnostic was raised, and the
server derives a range from it (falling back to a token line or a text search when the
message itself carries no position).
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from svl.lsp_server import _range_for
from svl.type_layer import TypeVerificationConfig, verify_type


SOURCE = """module m {
  func main() type int {
    let x: int = "hi"
    return x
  }
}
"""


class TestTypeLayerSpans:
    def test_each_error_carries_its_statement_line(self):
        result = verify_type(SOURCE, TypeVerificationConfig(verify_golden_refs=False))
        assert not result.passed
        assert len(result.error_lines) == len(result.errors)
        # `let x: int = "hi"` is line 3; `return x` is line 5.
        assert result.error_lines[0] == 3

    def test_a_clean_program_reports_no_spans(self):
        src = 'module m { func main() type int { return 42 } }'
        result = verify_type(src, TypeVerificationConfig(verify_golden_refs=False))
        assert result.passed
        assert result.errors == []
        assert result.error_lines == []


class TestRangeFor:
    def test_explicit_line_wins(self):
        rng = _range_for("anything", ["a", "b", "c"], line=2)
        assert rng.start.line == 1

    def test_line_embedded_in_the_message(self):
        rng = _range_for("Unexpected token: Token(ERROR, '$', line=3, col=2)", [])
        assert rng.start.line == 2

    def test_quoted_name_is_located_in_the_source(self):
        lines = ["module m {", "  func main() type int { return nope(1) }", "}"]
        rng = _range_for("unknown function 'nope'", lines)
        assert rng.start.line == 1

    def test_no_position_falls_back_to_line_zero(self):
        rng = _range_for("structural checksum mismatch", [])
        assert rng.start.line == 0
