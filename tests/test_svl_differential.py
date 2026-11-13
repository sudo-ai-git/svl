"""P1.4 — differential conformance: the reference interpreter vs the compiled WASM.

Every program here runs through BOTH implementations; a disagreement means one of them
is wrong about what the source says.  Before this suite the compiler was the spec.
"""
import pytest

from svl.differential_exec import differential, run_suite

PROGRAMS = {
    "arithmetic": ("module m { func main() type int { let a = 7 let b = 3 "
                   "return a * b + a - b } }"),
    "print_int": 'module m { func main() type void { print_int(42) print("\\n") } }',
    "while_sum": ("module m { func main() type int { let i = 0 let s = 0 "
                  "while i <= 5 { s += i i += 1 } return s } }"),
    "for_range": ("module m { func main() type int { let s = 0 for i in 0..5 { s += i } "
                  "return s } }"),
    "for_array": ("module m { func main() type int { let a = [1,2,3] let s = 0 "
                  "for x in a { s += x } return s } }"),
    "array_write": ("module m { func main() type int { let a = [10,20,30] a[1] = 99 "
                    "return a[1] } }"),
    "zeros_len": ("module m { func main() type int { let a = zeros(5) a[2] = 7 "
                  "return len(a) * 10 + a[2] } }"),
    "struct_literal": ("module m { struct P { x: int  y: int } "
                       "func main() type int { let p: P = P{x: 3, y: 4} "
                       "return p.x + p.y } }"),
    "struct_write": ("module m { struct P { x: int } "
                     "func main() type int { let p: P = P{x: 1} p.x = 9 return p.x } }"),
    "match": ("module m { func main() type int { let x = 2 "
              "let r = match x { case 1 => 10 case 2 => 20 case _ => 30 } "
              "return r } }"),
    "recursion": ("module m { func fib(n: int) type int { if n < 2 then { return n } "
                  "else { } return fib(n-1) + fib(n-2) } "
                  "func main() type int { return fib(10) } }"),
    "if_else": ("module m { func main() type int { let x = 5 "
                "if x > 3 then { return 1 } else { return 2 } } }"),
    "ternary": ("module m { func main() type int { let c = 0 "
                "let r = if c then 10 else 20 return r } }"),
    "bitwise": ("module m { func main() type int { let a = 12 let b = 10 "
                "return (a & b) + (a | b) } }"),
    "assert": "module m { func main() type int { assert 1 == 1 return 3 } }",
    "try_catch": ("module m { func main() type int { try { throw 7 } "
                  "catch e { return e } } }"),
    "const_var": ("module m { const N: int = 6 var c: int = 1 "
                  "func main() type int { c = c + N return c } }"),
    "string_print": 'module m { func main() type void { print("hello") } }',
    "division": ("module m { func main() type int { let a = 17 let b = 5 "
                 "return a / b * 10 + a % b } }"),
    "nested_loops": ("module m { func main() type int { let s = 0 "
                     "for i in 0..3 { for j in 0..3 { s += i * j } } return s } }"),
    "mixed_print": ('module m { func main() type void { print("x=") print_int(5) '
                    'print("\\n") } }'),
}


@pytest.mark.parametrize("name", sorted(PROGRAMS))
def test_interpreter_agrees_with_wasm(wasmtime_module, name):
    result = differential(PROGRAMS[name])
    assert result["agree"], f"{name}: interpreter={result['interpreter']} wasm={result['wasm']}"


def test_the_whole_suite_agrees(wasmtime_module):
    agreed, total, failures = run_suite(PROGRAMS)
    assert agreed == total, f"{agreed}/{total} agree; failures: {failures}"
