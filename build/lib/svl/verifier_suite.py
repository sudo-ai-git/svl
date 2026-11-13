"""Labeled verifier corpus — the verifier must agree with a human label on every program.

The probes assert individual behaviours; this suite asserts the *whole verdict* against a
label: a program that must be refused (out-of-bounds, division by zero, a type error, a
false assertion) and a program that must be allowed (correct code, including loops the
interval analyser cannot bound).  Both directions are required — a gate that only ever
refuses is as useless as one that only ever passes.

`kill_switch_*` disable one check at a time and require the suite to NOTICE.  A corpus
that still passes with a check disabled is not a corpus; it is decoration.
"""
from typing import Dict, List, Tuple

# -- must be REFUSED by the verifier stack (gate + SMT) ------------------------
MUST_REFUSE: Dict[str, str] = {
    "oob_literal_index": ("module m { func main() type int { let a = [1,2,3] let i = 5 "
                          "return a[i] } }"),
    "oob_negative_offset": ("module m { func main() type int { let a = [1,2,3] "
                            "let i = 9 return a[i] } }"),
    "div_by_zero": ("module m { func main() type int { let z = 0 return 10 / z } }"),
    "let_type_mismatch": ('module m { func main() type int { let x: int = "hi" '
                         "return 0 } }"),
    "false_assert": "module m { func main() type int { assert 1 == 2 return 0 } }",
    "assert_refuted_by_value": ("module m { func main() type int { let x = 0 "
                                "assert x > 0 return 0 } }"),
    "return_type_mismatch": ('module m { func f() type int { return "hi" } '
                            "func main() type int { return 0 } }"),
    "call_arg_mismatch": ('module m { func f(x: int) type int { return x } '
                          'func main() type int { return f("hi") } }'),
    "unknown_identifier": ("module m { func main() type int { return not_declared } }"),
    "unknown_call": ("module m { func main() type int { return nope(1) } }"),
    "const_reassignment": ("module m { const c: int = 5 func main() type int { c = 6 "
                           "return c } }"),
    "const_compound_assignment": ("module m { const c: int = 5 func main() type int "
                                  "{ c += 1 return c } }"),
    "unsupported_linear": ("module m { func main() type int { let x: linear int = 5 "
                           "return x } }"),
    "unsupported_unique": ("module m { func main() type int { let x: unique int = 5 "
                           "return x } }"),
    "unsupported_refinement": ("module m { func main() type int { let x: {v: int | v > 0} "
                               "= -5 return x } }"),
    "unsupported_intersection": ("module m { func main() type int { let x: int & string = 5 "
                                 "return x } }"),
    "unsupported_union": ("module m { func main() type int { let x: int | string = 5 "
                           "return x } }"),
    "unsupported_vec": ("module m { func main() type int { let v: vec<int, 10> = [1] "
                        "return v[0] } }"),
    "unsupported_dynamic": ("module m { func main() type int { let x: ? = 42 "
                            "return x } }"),
    "unsupported_modal": ("module m { func main() type int { let x: box int = 5 "
                          "return x } }"),
    "try_around_provable_trap": ("module m { func main() type int { try { let a = [1,2,3] "
                                 "let i = 5 return a[i] } catch e { return 0 } } }"),
}

# -- must be ALLOWED (the verifier stack stays silent) -------------------------
MUST_PASS: Dict[str, str] = {
    "arithmetic": "module m { func main() type int { return 7 * 3 + 2 } }",
    "array_in_range": ("module m { func main() type int { let a = [1,2,3] "
                       "return a[1] } }"),
    "array_runtime_index": ("module m { func f(a: int, i: int) type int { return a[i] } "
                            "func main() type int { return f(0, 0) } }"),
    "for_range_accumulate": ("module m { func main() type int { let s = 0 "
                             "for i in 0..10 { s += i } return s } }"),
    "while_loop": ("module m { func main() type int { let i = 0 while i < 5 { i += 1 } "
                   "return i } }"),
    "true_assert": "module m { func main() type int { assert 1 == 1 return 0 } }",
    "float_arithmetic": "module m { func main() type float { return 1.5 + 2.5 } }",
    "struct_field": ("module m { struct P { x: int } func main() type int "
                     "{ let p: P = P{x: 3} return p.x } }"),
    "recursion": ("module m { func fib(n: int) type int { if n < 2 then { return n } "
                  "else { } return fib(n-1) + fib(n-2) } "
                  "func main() type int { return fib(8) } }"),
    "match": ("module m { func main() type int { let x = 1 "
              "let r = match x { case 1 => 10 case _ => 20 } return r } }"),
    "try_catch_throw": ("module m { func main() type int { try { throw 7 } "
                        "catch e { return e } } }"),
    "zeros_len": ("module m { func main() type int { let a = zeros(5) a[0] = 1 "
                  "return len(a) } }"),
    "for_array": ("module m { func main() type int { let a = [1,2,3] let s = 0 "
                  "for x in a { s += x } return s } }"),
    "ternary": ("module m { func main() type int { let c = 1 "
                "let r = if c then 10 else 20 return r } }"),
    "bitwise": "module m { func main() type int { return (12 & 10) + (12 | 10) } }",
    "const_var": ("module m { const N: int = 6 var c: int = 1 "
                  "func main() type int { c = c + N return c } }"),
    "division_nonzero": ("module m { func main() type int { let a = 17 let b = 5 "
                         "return a / b } }"),
    "comparison_branch": ("module m { func main() type int { let x = 5 "
                          "if x > 3 then { return 1 } else { return 2 } } }"),
    "short_circuit": ("module m { func f(x: int) type bool { return x != 0 && 10 / x > 1 } "
                      "func main() type bool { return f(0) } }"),
    "nested_loops": ("module m { func main() type int { let s = 0 "
                     "for i in 0..3 { for j in 0..3 { s += i * j } } return s } }"),
    "print_and_int": ('module m { func main() type void { print_int(42) print("\\n") } }'),
}


def check(source: str) -> Tuple[bool, List[str]]:
    """Return (refused, reasons) using the compile-time gate AND the SMT layer."""
    reasons: List[str] = []
    try:
        from svl.verify_gate import verify_program
        reasons.extend(verify_program(source))
    except Exception as exc:                                      # noqa: BLE001
        reasons.append(f"gate raised {type(exc).__name__}: {exc}")
    try:
        from svl.smt_theorem import verify_with_smt
        result = verify_with_smt(source)
        if result.status == "counterexample":
            reasons.append(f"SMT counterexample: {result.error_message}")
    except ImportError:
        pass
    except Exception as exc:                                      # noqa: BLE001
        reasons.append(f"SMT raised {type(exc).__name__}: {exc}")
    return (len(reasons) > 0), reasons


def run_suite(refuse: Dict[str, str] = None,
              allow: Dict[str, str] = None) -> List[str]:
    """Return a list of label disagreements (empty means the verifier agrees)."""
    refuse = MUST_REFUSE if refuse is None else refuse
    allow = MUST_PASS if allow is None else allow
    failures: List[str] = []
    for name, src in refuse.items():
        refused, reasons = check(src)
        if not refused:
            failures.append(f"must-REFUSE but passed: {name}")
    for name, src in allow.items():
        refused, reasons = check(src)
        if refused:
            failures.append(f"must-PASS but refused: {name}: {reasons[:1]}")
    return failures


def kill_switch_type_checker() -> List[str]:
    """Disable the `let` type check and require the suite to notice."""
    import svl.type_inference as ti
    original = ti.TypeChecker._check_let_stmt
    ti.TypeChecker._check_let_stmt = lambda self, stmt: None
    try:
        return run_suite()
    finally:
        ti.TypeChecker._check_let_stmt = original


def kill_switch_interval_ai() -> List[str]:
    """Disable the interval analyser and require the suite to notice."""
    import svl.abstract_interpretation as ai
    original = ai.analyze_program

    def silent(ast):
        return ai.AnalysisResult()

    ai.analyze_program = silent
    try:
        return run_suite()
    finally:
        ai.analyze_program = original


if __name__ == '__main__':
    failures = run_suite()
    print(f"corpus: {len(MUST_REFUSE)} must-refuse, {len(MUST_PASS)} must-pass")
    print(f"disagreements: {len(failures)}")
    for line in failures:
        print("  ", line)
    for name, switcher in (("type checker", kill_switch_type_checker),
                           ("interval AI", kill_switch_interval_ai)):
        noticed = switcher()
        print(f"kill-switch ({name} disabled): {len(noticed)} disagreements "
              f"({'noticed' if noticed else 'NOTICED NOTHING'})")
