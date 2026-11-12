"""SMT layer: loop invariants and arrays.

Each case states the status the layer must report. `proven` means every assertion was
discharged; `counterexample` means a concrete refutation was found; `unverified` means
the layer declined to model something — which must never be reported as success.
"""
import pytest

from svl.smt_theorem import verify_with_smt

CASES = [
    # (name, source, expected status)
    ("while count to 10",
     "module t { func main() type int { let i = 0 while i < 10 { i += 1 }"
     " assert i == 10 return 0 } }", "proven"),

    ("while false assertion is refuted",
     "module t { func main() type int { let i = 0 while i < 10 { i += 1 }"
     " assert i == 5 return 0 } }", "counterexample"),

    ("for sum accumulator is stale, not refuted",
     "module t { func main() type int { let s = 0 for i in 0..10 { s += i }"
     " assert s == 45 return 0 } }", "unverified"),

    ("array literal reads",
     "module t { func main() type int { let a: int = [1, 2, 3]"
     " assert a[0] == 1 assert a[2] == 3 return 0 } }", "proven"),

    ("zeros then store",
     "module t { func main() type int { let a = zeros(5) a[0] = 7"
     " assert a[0] == 7 return 0 } }", "proven"),

    ("array written in a loop, asserted after",
     "module t { func main() type int { let a = zeros(10) let i = 0"
     " while i < len(a) { a[i] = i i += 1 } assert a[3] == 3 return 0 } }",
     "unverified"),

    ("assertion inside a loop holds",
     "module t { func main() type int { let i = 0 while i < 10 {"
     " assert i < 10 i += 1 } return 0 } }", "proven"),

    ("assertion inside a loop is refuted",
     "module t { func main() type int { let i = 0 while i < 10 {"
     " assert i < 5 i += 1 } return 0 } }", "counterexample"),

    ("array read-back inside a loop",
     "module t { func main() type int { let a = zeros(10) let i = 0"
     " while i < len(a) { a[i] = i assert a[i] == i i += 1 } return 0 } }",
     "proven"),

    ("len of zeros",
     "module t { func main() type int { let a = zeros(5)"
     " assert len(a) == 5 return 0 } }", "proven"),

    ("non-provable loop is declined",
     "module t { func f(n: int) type int { let i = 0 while i < n { i += 2 }"
     " assert i > 0 return 0 } }", "unverified"),

    ("zero-trip for loop is a no-op",
     "module t { func main() type int { let i = 0 for j in 5..5 { i += 1 }"
     " assert i == 0 return 0 } }", "proven"),

    ("nested loop is declined",
     "module t { func main() type int { let i = 0 while i < 10 {"
     " let j = 0 while j < 5 { j += 1 } i += 1 } assert i == 10 return 0 } }",
     "unverified"),

    ("compound assignment is modelled",
     "module t { func main() type int { let x = 10 x += 5 x *= 2"
     " assert x == 30 return 0 } }", "proven"),
]


@pytest.mark.parametrize("name,source,expected", CASES, ids=[c[0] for c in CASES])
def test_smt_status(name, source, expected):
    result = verify_with_smt(source)
    assert result.status == expected, (
        f"{name}: expected {expected}, got {result.status} "
        f"(checked={result.assertions_checked} proven={result.assertions_proven} "
        f"unverified={result.unverified})")


def test_counterexample_carries_a_model():
    result = verify_with_smt(
        "module t { func main() type int { let i = 0 while i < 10 { i += 1 }"
        " assert i == 5 return 0 } }")
    assert result.status == "counterexample"
    assert result.counterexamples
    assert result.counterexamples[0]["counterexample"]


def test_vacuous_program_reports_vacuous():
    result = verify_with_smt("module t { func main() type int { return 0 } }")
    assert result.status == "vacuous"
    assert not result.complete


def test_division_is_declined_not_mis_modelled():
    """/ and % truncate in WASM i32 but are Euclidean in Z3 — modelling one as the
    other would produce false proofs, so the layer must decline."""
    result = verify_with_smt(
        "module t { func f(a: int, b: int) type int { assert a / b == 0 return 0 } }")
    assert result.status in ("unverified", "counterexample")
