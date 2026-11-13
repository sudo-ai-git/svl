"""Whole-program specification: module-scoped clauses over the entry point.

A per-function contract says what a function guarantees.  A module-level clause says
what the PROGRAM guarantees — it applies to the module's entry point (the function
exported as `<module>_main`), so it covers the whole program's observable result.

    module m
      requires <expr>
      ensures  <expr>
    { func main() type int { ... } }

The clauses are merged with the entry point's own (`A && B`) and discharged by the same
contract prover — so a module spec is PROVED, not tested.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from svl.compiler_wasm import compile_file_to_wasm
from svl.lexer import tokenize
from svl.module_spec import check_module_spec, combined_entry_point, entry_point
from svl.parser_rd import parse
from svl.verify_gate import SVLVerificationError, verify_program


def _check(src):
    return check_module_spec(parse(tokenize(src)))


class TestModuleSpecification:
    def test_satisfied_spec_is_accepted(self):
        src = 'module m ensures result == 42 { func main() type int { return 42 } }'
        assert _check(src) == []
        assert verify_program(src) == []

    def test_violated_spec_is_refused(self):
        src = 'module m ensures result == 42 { func main() type int { return 7 } }'
        problems = _check(src)
        assert problems and "ensures" in problems[0] and "refuted" in problems[0]

    def test_violated_spec_is_refused_by_the_compile_path(self):
        src = 'module m ensures result == 42 { func main() type int { return 7 } }'
        with pytest.raises(SVLVerificationError, match="specification"):
            compile_file_to_wasm(src)

    def test_requires_clause_must_be_satisfiable(self):
        src = ('module m requires 1 == 2 ensures result == 1 '
               '{ func main() type int { return 1 } }')
        problems = _check(src)
        assert problems and "requires" in problems[0]

    def test_module_spec_merges_with_the_entry_points_own_contract(self):
        """Both the function's and the module's clauses must hold."""
        src = ('module m requires x > 0 { func main() type int '
               'requires 5 > 0 { return 1 } }')
        assert _check(src) == []

    def test_the_modules_requires_clause_is_merged(self):
        """The module's own `requires` must be discharged, not just the function's."""
        src = ('module m requires 1 == 2 ensures result == 1 '
               '{ func main() type int { return 1 } }')
        problems = _check(src)
        assert problems and "requires" in problems[0]

    def test_a_module_spec_beside_a_function_spec(self):
        src = ('module m ensures result > 0 { func main() type int '
               'ensures result > 0 { return 3 } }')
        assert _check(src) == []


class TestNoEntryPoint:
    def test_a_spec_without_main_describes_nothing(self):
        src = 'module m ensures result == 1 { func other() type int { return 1 } }'
        problems = _check(src)
        assert problems and "no entry point" in problems[0]

    def test_the_entry_point_is_the_function_named_main(self):
        module = parse(tokenize(
            'module m { func other() type int { return 0 } '
            'func main() type int { return 1 } }')).modules[0]
        func = entry_point(module)
        assert func is not None and func.name == 'main'

    def test_entry_point_is_none_when_absent(self):
        module = parse(tokenize(
            'module m { func other() type int { return 0 } }')).modules[0]
        assert entry_point(module) is None


class TestNoFalsePositives:
    def test_a_module_without_a_spec_is_unaffected(self):
        src = 'module m { func main() type int { return 1 } }'
        assert _check(src) == []

    def test_a_function_spec_alone_still_works(self):
        src = ('module m { func main() type int ensures result == 1 '
               '{ return 1 } }')
        assert _check(src) == []

    def test_a_module_spec_violated_in_one_of_two_modules(self):
        src = ('module a ensures result == 1 { func main() type int { return 1 } } '
               'module b ensures result == 2 { func main() type int { return 5 } }')
        problems = _check(src)
        assert problems and "module 'b'" in problems[0]

    def test_two_satisfied_modules(self):
        src = ('module a ensures result == 1 { func main() type int { return 1 } } '
               'module b ensures result == 2 { func main() type int { return 2 } }')
        assert _check(src) == []

    def test_the_entry_points_own_requires_still_applies(self):
        """The module spec must be discharged under the function's precondition."""
        src = ('module m ensures result == 1 { func main() type int '
               'requires 1 == 2 { return 1 } }')
        problems = _check(src)
        assert problems and "requires" in problems[0]


class TestCertificateCoverage:
    def test_the_artifact_records_the_module_spec_verdict(self):
        from svl.pcc_wasm import PCCWasmGenerator, extract_proofs_from_wasm_bytes
        src = 'module m ensures result == 42 { func main() type int { return 42 } }'
        module = PCCWasmGenerator().generate(src)
        layers = [p.layer for p in module.proofs]
        assert 'module-spec' in layers
        assert extract_proofs_from_wasm_bytes(
            module.to_wasm_bytes_with_proofs()) is not None

    def test_a_violated_module_spec_is_recorded_as_failed(self):
        from svl.pcc_wasm import PCCWasmGenerator
        src = 'module m ensures result == 42 { func main() type int { return 7 } }'
        module = PCCWasmGenerator().generate(src)
        spec = [p for p in module.proofs if p.layer == 'module-spec'][0]
        assert spec.passed is False
        assert spec.details['problems']

    def test_verify_pcc_wasm_covers_the_module_spec(self):
        """The certificate re-derives the whole gate, which now includes the spec."""
        from svl.pcc_wasm import PCCWasmGenerator, verify_pcc_wasm
        src = 'module m ensures result == 42 { func main() type int { return 42 } }'
        blob = PCCWasmGenerator().generate(src).to_wasm_bytes_with_proofs()
        ok, errors = verify_pcc_wasm(blob, src)
        assert ok, errors


class TestCombinedEntryPoint:
    def test_merging_both_clauses(self):
        from svl.parser_rd import BinaryExpr
        module = parse(tokenize(
            'module m requires 1 == 1 ensures result == 1 '
            '{ func main() type int requires 2 == 2 ensures result == 1 '
            '{ return 1 } }')).modules[0]
        func = entry_point(module)
        assert func is not None
        combined = combined_entry_point(module, func)
        assert isinstance(combined.requires, BinaryExpr)
        assert combined.requires.operator == '&&'
        assert isinstance(combined.ensures, BinaryExpr)
        assert combined.ensures.operator == '&&'
