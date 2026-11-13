"""Parametric polymorphism: `func id<T>(x: T) -> T`, monomorphised per call site.

Before this, generic syntax did not exist at all (only generic *type aliases*, which are
transparent substitutions, and generic *constructors* like `Option<int>`).  SVL had no
way to write one function that works at several types.

The implementation is monomorphisation driven by the checker's inference:

* the parser accepts `<T, U>` after the function name (and `-> T` as an alternative to
  the `type T` introducer);
* the checker binds each parameter to a fresh type variable, generalises it into the
  function's scheme, and records — per call site — which concrete type each parameter
  was solved to;
* the backend emits one WASM function per distinct instantiation, keyed by the
  substituted types, and points the call site at it.

Nested generics resolve SYMBOLICALLY: inside `twice<T>`, the call `id(x)` is recorded as
`id<T>`; when `twice<int>` is compiled the substitution `{T: int}` turns that into
`id<int>`.  Recursion inside a generic resolves back to the instance being compiled.
"""
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from svl.compiler_wasm import compile_file_to_wasm
from svl.repl import run_wat
from svl.verify_gate import SVLVerificationError


def _run(src):
    return run_wat(compile_file_to_wasm(src))[0]


def _refused(src):
    with pytest.raises(SVLVerificationError):
        compile_file_to_wasm(src)


class TestIdentity:
    def test_int(self):
        src = ('module m { func id<T>(x: T) -> T { return x } '
               ' func main() type int { return id(42) } }')
        assert _run(src) == 42

    def test_two_int_calls_share_one_instance(self):
        src = ('module m { func id<T>(x: T) -> T { return x } '
               ' func main() type int { return id(40) + id(2) } }')
        assert _run(src) == 42

    def test_float_instantiation_is_a_real_f64(self):
        """The specialisation must lower T=f64 everywhere, not fall back to i32."""
        src = ('module m { func id<T>(x: T) -> T { return x } '
               ' func main() type float { return id(2.5) } }')
        assert _run(src) == 2.5

    def test_mixed_instantiations_in_one_program(self):
        src = ('module m { func id<T>(x: T) -> T { return x } '
               ' func main() type float { let a: float = id(1.5) '
               ' let b: int = id(2)  return a + 1.0 } }')
        assert _run(src) == 2.5

    def test_arrow_and_type_introducers_agree(self):
        arrow = ('module m { func id<T>(x: T) -> T { return x } '
                 ' func main() type int { return id(42) } }')
        keyword = ('module m { func id<T>(x: T) type T { return x } '
                   ' func main() type int { return id(42) } }')
        assert compile_file_to_wasm(arrow) == compile_file_to_wasm(keyword)


class TestTypeParameters:
    def test_two_parameters(self):
        src = ('module m { func first<T, U>(a: T, b: U) -> T { return a } '
               ' func main() type int { return first(7, 2.5) } }')
        assert _run(src) == 7

    def test_array_argument(self):
        src = ('module m { func first<T>(a: [T]) -> T { return a[0] } '
               ' func main() type int { return first([40, 2]) } }')
        assert _run(src) == 40

    def test_struct_argument(self):
        src = ('module m { struct P { a: int, b: int } '
               ' func id<T>(x: T) -> T { return x } '
               ' func main() type int { let p: P = P { a: 40, b: 2 } '
               ' let q: P = id(p)  return q.a + q.b } }')
        assert _run(src) == 42

    def test_generic_arithmetic_respects_the_instantiated_width(self):
        """A generic `a + b` must emit f64.add for T=float and i32.add for T=int."""
        float_src = ('module m { func add<T>(a: T, b: T) -> T { return a + b } '
                     ' func main() type float { return add(1.5, 2.5) } }')
        int_src = ('module m { func add<T>(a: T, b: T) -> T { return a + b } '
                   ' func main() type int { return add(40, 2) } }')
        assert _run(float_src) == 4.0
        assert _run(int_src) == 42

    def test_call_before_definition_uses_the_prebound_scheme(self):
        src = ('module m { func main() type int { return id(42) } '
               ' func id<T>(x: T) -> T { return x } }')
        assert _run(src) == 42

    def test_symbolic_argument_from_an_enclosing_generic(self):
        """`b(p)` where `p` came from an earlier generic call must still resolve."""
        src = ('module m { func a<T>(x: T) -> T { return x } '
               ' func main() type int { let p: int = a(1)  let q: int = b(p) '
               ' return q }  func b<U>(y: U) -> U { return y } }')
        assert _run(src) == 1


class TestNestedAndRecursive:
    def test_generic_calling_generic(self):
        src = ('module m { func twice<T>(x: T) -> T { return inner(x) } '
               ' func inner<U>(y: U) -> U { return y } '
               ' func main() type int { return twice(42) } }')
        assert _run(src) == 42

    def test_three_levels(self):
        src = ('module m { func a3<T>(x: T) -> T { return b3(x) } '
               ' func b3<U>(y: U) -> U { return c3(y) } '
               ' func c3<V>(z: V) -> V { return z } '
               ' func main() type int { return a3(42) } }')
        assert _run(src) == 42

    def test_nested_float_does_not_use_the_int_instance(self):
        src = ('module m { func twice<T>(x: T) -> T { return inner(x) } '
               ' func inner<U>(y: U) -> U { return y } '
               ' func main() type float { return twice(1.5) } }')
        assert _run(src) == 1.5

    def test_recursive_generic_resolves_to_its_own_instance(self):
        src = ('module m { func count<T>(n: int, acc: T) -> T '
               ' { if n <= 0 then { return acc } '
               ' else { return count(n - 1, acc) } } '
               ' func main() type int { return count(5, 7) } }')
        assert _run(src) == 7

    def test_recursive_generic_with_two_instances(self):
        src = ('module m { func count<T>(n: int, acc: T) -> T '
               ' { if n <= 0 then { return acc } '
               ' else { return count(n - 1, acc) } } '
               ' func main() type float { let a: float = count(3, 1.5) '
               ' let b: int = count(4, 10)  return a + 2.5 } }')
        assert _run(src) == 4.0


class TestRefusals:
    def test_generic_entry_point_is_refused(self):
        _refused('module m { func main<T>() type int { return 1 } }')

    def test_an_inference_variable_that_is_not_determined_is_refused(self):
        """`make()` has no arguments, so T cannot be known; guessing would be wrong."""
        _refused('module m { func make<T>() -> T { return 0 } '
                 ' func main() type int { return make() } }')

    def test_arity_mismatch_is_still_refused(self):
        _refused('module m { func one<T>(x: T) -> T { return x } '
                 ' func main() type int { return one(1, 2) } }')

    def test_a_wrong_argument_type_is_still_refused(self):
        _refused('module m { func one<T>(x: T, y: int) -> T { return x } '
                 ' func main() type int { return one(1, "no") } }')


class TestNonRegressions:
    def test_a_unused_generic_emits_nothing(self):
        src = ('module m { func unused<T>(x: T) -> T { return x } '
               ' func main() type int { return 42 } }')
        wat = compile_file_to_wasm(src)
        assert '$m$unused' not in wat
        assert _run(src) == 42

    def test_named_functions_are_unaffected(self):
        src = ('module m { func add(a: int, b: int) type int { return a + b } '
               ' func main() type int { return add(40, 2) } }')
        assert _run(src) == 42

    def test_an_unknown_callee_is_still_refused(self):
        _refused('module m { func main() type int { return nope(1) } }')

    def test_output_is_identical_across_hash_seeds(self):
        """Specialisation ordering must not depend on set/dict iteration order."""
        src = ('module m { func a<T>(x: T) -> T { return b(x) } '
               ' func b<U>(y: U) -> U { return y } '
               ' func main() type int { return a(42) + a(1) } }')
        code = ("from svl.compiler_wasm import compile_file_to_wasm\n"
                "import hashlib, sys\n"
                f"src = {src!r}\n"
                "print(hashlib.sha256(compile_file_to_wasm(src).encode()).hexdigest())\n")
        digests = set()
        for seed in ("0", "1", "12345", "random"):
            env = dict(os.environ, PYTHONHASHSEED=seed,
                       PYTHONPATH=os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
            out = subprocess.run([sys.executable, "-c", code], capture_output=True,
                                 text=True, env=env, check=True)
            digests.add(out.stdout.strip())
        assert len(digests) == 1, f"non-deterministic output across hash seeds: {digests}"
