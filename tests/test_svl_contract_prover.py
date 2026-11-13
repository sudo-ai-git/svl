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
        """A genuinely preserved invariant passes BOTH entry and preservation.

        The precondition `0 <= i <= 10` is what establishes the invariant on entry; a
        loop over an unconstrained parameter does not make `i <= 10` true for every i.
        """
        src = '''
        module test {
          func sum(i: int) type int
            requires i >= 0 && i <= 10
          {
            while i < 10
              invariant i >= 0 && i <= 10
            { i += 1 }
            return i
          }
        }
        '''
        problems = verify_program(src)
        assert problems == [], f"preserved invariant should pass, got {problems}"

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


class TestContractProverSoundness:
    """Regression tests for defects that made the prover prove false theorems.

    Each test here was written against a specific bug; each one fails if that bug
    comes back.  A test in this class that cannot fail is not a regression test.
    """

    def test_contract_in_second_function_is_checked(self):
        """A broken contract in the SECOND function must still be reported.

        Regression: the driver used to `break` after the first function with a
        contract, so `bad`'s `return 0 - 1` was never examined.
        """
        src = '''
        module test {
          func good(a: int) type int requires a > 0 ensures result > 0 { return a }
          func bad(a: int) type int requires a > 0 ensures result > 0 { return 0 - 1 }
        }
        '''
        problems = verify_program(src)
        assert any('bad' in p and 'ensures' in p for p in problems), (
            f"broken second-function contract not reported: {problems}")

    def test_changed_parameter_does_not_verify_vacuously(self):
        """`x = 0; x = 5; ensures result == x + 1` must be REFUTED, not proven.

        Regression: the body's post-state bindings used to be asserted into the
        antecedent.  For a body that changes `x`, that makes the antecedent
        unsatisfiable (`x == 0 && x == 5`), and an unsatisfiable antecedent discharges
        every obligation vacuously — this program then "proved".  The body is now
        SUBSTITUTED into the clause: `result` is 5 and the post-state `x` is 5, so
        `5 == 5 + 1` is false.
        """
        src = '''
        module test {
          func f(x: int) type int
            requires x == 0
            ensures result == x + 1
          {
            x = 5
            return x
          }
        }
        '''
        problems = verify_program(src)
        assert any('ensures' in p for p in problems), (
            "the body returns 5 with x = 5, so 'result == x + 1' is false; "
            "the obligation must not be discharged vacuously")

    def test_sequencing_is_modelled(self):
        """`x = 0; x = 5` ends holding 5 — no spurious contradiction."""
        src = '''
        module test {
          func f(x: int) type int
            requires x == 0
            ensures result == 5
          {
            x = 0
            x = 5
            return x
          }
        }
        '''
        problems = verify_program(src)
        assert problems == [], f"sequenced assignments should be modelled: {problems}"

    def test_compound_assignment_resolves_in_invariant(self):
        """`i += 1` must resolve to `i + 1` so the invariant is actually checked.

        Regression: a compound assignment on a name with no prior binding was marked
        tainted, so the preservation obligation was reported `unverified` — silently
        skipping the proof rather than checking it.  The gate reports no problem for an
        unverified obligation, so this asserts the prover's status directly.

        Asserting on the status (not on "no gate problems") is what makes this test
        able to fail: a `unverified` result and a `proven` result both produce an empty
        problem list.
        """
        src = '''
        module test {
          func sum(i: int) type int
            requires i >= 0 && i <= 10
          {
            while i < 10
              invariant i >= 0 && i <= 10
            { i += 1 }
            return i
          }
        }
        '''
        from svl.contract_prover import prove_contracts
        result = prove_contracts(src)
        preserved = [r for label, r in result.invariant_results
                     if r.obligation == 'invariant: preserved by the body']
        assert preserved, f"no preservation obligation reported: {result.invariant_results}"
        assert all(r.status == 'proven' for r in preserved), (
            f"`i += 1` must resolve so the invariant is proved, not declined: "
            f"{[r.status for r in preserved]}")

        # And the gate stays silent for a genuinely correct contract.
        assert verify_program(src) == []

    def test_invariant_that_is_not_preserved_is_refuted(self):
        """An invariant the body violates is a defect.

        Regression: guarding the preservation antecedent with `!cond` instead of `cond`
        made `i <= 5` verify vacuously — the only witness (`i = 5`) is a state where
        `i < 10` holds, which the `!cond` guard excludes.
        """
        src = '''
        module test {
          func sum(i: int) type int
            requires i >= 0 && i <= 5
          {
            while i < 10
              invariant i >= 0 && i <= 5
            { i += 1 }
            return i
          }
        }
        '''
        problems = verify_program(src)
        assert any('not preserved' in p for p in problems), (
            f"an invariant broken by the body must be refuted: {problems}")

    def test_invariant_not_established_on_entry_is_refuted(self):
        """An invariant that does not hold on entry is a defect."""
        src = '''
        module test {
          func sum(i: int) type int {
            while i < 10
              invariant i <= 10
            { i += 1 }
            return i
          }
        }
        '''
        problems = verify_program(src)
        assert any('not established on entry' in p for p in problems), (
            f"i <= 10 is not established for an arbitrary parameter: {problems}")

    def test_requires_contradiction_is_not_a_vacuous_pass(self):
        """An unsatisfiable `requires` is a defect, not a pass."""
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
        assert any('requires' in p for p in problems), (
            f"an empty contract domain is a defect: {problems}")

    def test_unmodelled_loop_reports_unverified_not_proven(self):
        """A body the prover cannot model must DECLINE, never claim a proof."""
        src = '''
        module test {
          func f(n: int) type int
            ensures result == 0
          {
            let i = 0
            while i < 10 { i = i + 1 }
            return i
          }
        }
        '''
        from svl.contract_prover import prove_contracts
        result = prove_contracts(src)
        by_fn = dict(result.ensures_results)
        assert 'f' in by_fn, f"function f not checked: {result.ensures_results}"
        assert by_fn['f'].status == 'unverified', (
            f"a loop taints the obligation; it must not report proven: {by_fn['f']}")
        assert not by_fn['f'].passed

    def test_branch_local_binding_does_not_create_false_counterexample(self):
        """A return is checked against the bindings on ITS OWN path.

        Regression: the branch states were joined first and then every return was
        checked against all of them, so the `then` branch's `return 10` was also checked
        under the `else` branch's `x == 0`.  That refused a correct program at compile
        time — a false positive, which is worse than the defect being checked for.
        """
        src = '''
        module test {
          func f(c: int) type int
            ensures result >= x
          {
            let x = 0
            if c > 0 then { x = 10; return 10 } else { return 0 }
          }
        }
        '''
        problems = verify_program(src)
        assert problems == [], f"correct branch-local contract refused: {problems}"

    def test_branch_local_violation_is_still_refuted(self):
        """The same shape, genuinely violated on one branch, is still caught."""
        src = '''
        module test {
          func f(c: int) type int
            ensures result >= x
          {
            let x = 10
            if c > 0 then { x = 0; return 0 } else { return 0 }
          }
        }
        '''
        problems = verify_program(src)
        assert any('ensures' in p for p in problems), (
            f"a violation on the else path must be caught: {problems}")