"""Tests for the contract prover (P2.1): requires / ensures / invariant."""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from svl.verify_gate import verify_program


class TestRequiresEnsuresInvariant:
    """Contract prover: pre/post conditions and loop invariants checked by Z3."""

    def test_ensures_broken_is_refuted(self):
        """ensures clause violated by body: counterexample found."""
        src = '''
        module test {
          func add(a: int, b: int) type int
            requires a > 0
            ensures result >= a
          {
            return a - b
          }
        }
        '''
        problems = verify_program(src)
        assert any('ensures' in p for p in problems), f"expected an ensures problem, got {problems}"
        assert verify_program(src), "broken contract should fail the gate"

    def test_ensures_correct_is_proven(self):
        """ensures clause satisfied by body: proven."""
        src = '''
        module test {
          func add(a: int, b: int) type int
            requires a > 0
            ensures result == a + b
          {
            return a + b
          }
        }
        '''
        problems = verify_program(src)
        assert problems == [], f"contract should have passed, got {problems}"

    def test_requires_unsatisfiable_is_refuted(self):
        """requires clause that is a contradiction (unsat): counterexample found."""
        src = '''
        module test {
          func divide(x: int) type int
            requires x < 0 && x > 0
          {
            return 42
          }
        }
        '''
        problems = verify_program(src)
        assert any('requires' in p for p in problems), f"expected a requires problem, got {problems}"

    def test_requires_satisfiable_is_proven(self):
        """requires clause that is satisfiable: proven."""
        src = '''
        module test {
          func add(a: int, b: int) type int
            requires a > 0
          {
            return a + b
          }
        }
        '''
        problems = verify_program(src)
        assert problems == [], f"contract should have passed, got {problems}"

    def test_invariant_preserved(self):
        """loop invariant preserved: gate does not crash."""
        src = '''
        module test {
          func sum(i: int) type int {
            while i < 10
              invariant i >= 0 && i <= 10
            { i += 1 }
            return i
          }
        }
        '''
        problems = verify_program(src)
        assert not [p for p in problems if 'invariant: not preserved' in p], problems

    def test_no_contracts_compiles(self):
        """contract-free program passes the gate."""
        src = '''
        module test {
          func add(a: int, b: int) type int {
            return a + b
          }
        }
        '''
        problems = verify_program(src)
        assert problems == [], f"contract-free program should pass, got {problems}"

    def test_ensures_with_result(self):
        """ensures using 'result' keyword."""
        src = '''
        module test {
          func mul(a: int, b: int) type int
            requires a > 0 && b > 0
            ensures result == a * b
          {
            return a * b
          }
        }
        '''
        problems = verify_program(src)
        assert problems == [], f"contract should pass, got {problems}"

    def test_assert_still_works_with_contracts(self):
        """assert statements still work alongside contracts."""
        src = '''
        module test {
          func add(a: int, b: int) type int
            requires a > 0
            ensures result == a + b
          {
            assert a + b >= a
            return a + b
          }
        }
        '''
        problems = verify_program(src)
        assert problems == [], f"asserts should still pass with contracts, got {problems}"