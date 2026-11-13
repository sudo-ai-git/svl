"""Compile-time verification gate.

`README` claimed the three-layer stack "runs automatically on every compilation". It did not —
`compile_file_to_wasm` called nothing. This module is the gate that makes the claim true for
the checks that can actually fail.

What runs here, and why only this:

* **AST guard** — rejects forbidden constructs (e.g. `sum()`), a real policy check.
* **Type checker** (`verify_type`) — the one layer with real inference behind it.
* **Abstract interpretation** (`abstract_interpretation.analyze_program`) — proves
  out-of-bounds array indexes and division by a provably zero divisor, and refuses to
  compile them.  This is the H21 work; it only ever reports what it can *prove*, so a
  program that reaches this gate is either correct on those two points or the analysis
  says nothing about them.

What deliberately does NOT run here:

* **The 231-gate / viable-start search.** It is an artifact-integrity check over the
  *serialised* bytes, not a correctness check on the program, and `find_viable_start` is
  super-linear (measured ~16.9s of 17.2s at 100 statements), so putting it on the compile path
  would make every compile slow for no correctness gain. It belongs at package/attestation
  time — see `svl.package_registry`.
* **The BPSW "theorem" layer.** Measured to be constant-true: parity is 0 for every residue of
  {17,37,73} (all residues are below 2047, the first base-2 pseudoprime), so it cannot fail and
  gates nothing. Running it would only add cost and imply a guarantee it does not provide.
"""
from typing import Any, List

from svl.lexer import tokenize
from svl.parser_rd import parse


class SVLVerificationError(Exception):
    """Raised when a program fails the compile-time verification gate."""


def verify_program(source: str, ast: Any = None) -> List[str]:
    """Return a list of verification problems (empty list means the program passed).

    ``ast`` may be supplied when the caller already holds a parsed program — in
    particular the LINKED program.  Verifying an unlinked source with an `import`
    makes every imported name an unknown identifier, which is why the compile gate
    passes the linked AST.
    """
    problems: List[str] = []

    if ast is None:
        try:
            ast = parse(tokenize(source))
        except SyntaxError as exc:
            return [f"parse error: {exc}"]

    # 1. AST guard (policy: forbidden functions/constructs)
    try:
        from svl.ast_guard import ASTGuard
        for violation in ASTGuard().check(ast):
            problems.append(f"AST guard: {violation}")
    except Exception as exc:                                          # noqa: BLE001
        problems.append(f"AST guard error: {exc}")

    # 2. Type layer
    try:
        from svl.type_layer import verify_type
        result = verify_type(source, ast=ast)
        if not result.passed:
            problems.extend(result.errors or ["type verification failed"])
    except Exception as exc:                                          # noqa: BLE001
        problems.append(f"type verification error: {exc}")

    # 3. Abstract interpretation: provable out-of-bounds index / division by zero.
    #    Only findings the analysis can PROVE become problems; anything it cannot decide
    #    is silence, never a rejection.
    try:
        from svl.abstract_interpretation import analyze_program
        ai = analyze_program(ast)
        for f in ai.findings:
            if f.severity == 'error':
                problems.append(
                    f"abstract interpretation: {f.message} "
                    f"  [{f.function} line {f.line}]")
        for err in ai.internal_errors:
            problems.append(f"abstract interpretation error: {err}")
    except Exception as exc:                                          # noqa: BLE001
        problems.append(f"abstract interpretation error: {exc}")

    # 4. Contract prover (P2.1): proves requires/ensures/invariant over the AST using
    #    Z3.  Outside the decidable class the prover reports `unverified`, which is
    #    harmless — it never rejects a program it cannot decide.
    try:
        from svl.contract_prover import verify_contracts
        ok, contract_problems = verify_contracts(source=source, ast=ast)
        if not ok and contract_problems:
            problems.extend(contract_problems)
    except ImportError:
        pass  # z3 unavailable: contract proving is optional
    except Exception as exc:                                          # noqa: BLE001
        problems.append(f"contract prover error: {exc}")

    # 5. Refinement types: `{ v: T | P(v) }` obligations.  Introduction sites (a `let`
    #    with a refined annotation, a call to a refined parameter, a `return` against a
    #    refined result) must be PROVEN; bindings that are proven may then be ASSUMED.
    #    A proven counterexample is a hard error; an unmodelled predicate is silence.
    try:
        from svl.refinement_types import check_refinements
        problems.extend(check_refinements(ast))
    except ImportError:
        pass  # z3 unavailable
    except Exception as exc:                                          # noqa: BLE001
        problems.append(f"refinement check error: {exc}")

    # 6. Linear / unique types: the move discipline.  A moved value may not be used or
    #    moved again.  Unconsumed `linear` variables are warnings, NOT errors — a false
    #    positive would reject a correct program.
    try:
        from svl.linear_regions import check_linear_usage
        linear_errors, _linear_warnings = check_linear_usage(ast)
        problems.extend(linear_errors)
    except Exception as exc:                                          # noqa: BLE001
        problems.append(f"linear type check error: {exc}")

    return problems


def assert_verified(source: str, ast: Any = None) -> None:
    """Raise if the program does not pass the gate.

    A parse failure is re-raised as ``SyntaxError`` so callers keep seeing the same clean,
    specific error they saw before the gate existed (a malformed program is a syntax error,
    not a verification failure).
    """
    problems = verify_program(source, ast=ast)
    if not problems:
        return
    if len(problems) == 1 and problems[0].startswith("parse error: "):
        raise SyntaxError(problems[0][len("parse error: "):])
    raise SVLVerificationError(
        "refusing to compile — verification failed:\n  - " + "\n  - ".join(problems)
    )
