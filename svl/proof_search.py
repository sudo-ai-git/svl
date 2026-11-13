"""Automated proof search over SVL's tactic engine.

This is NOT LLM-guided search: it is a bounded breadth-first search over sequences of
the deterministic tactics in ``svl.tactics``.  The distinction is deliberate — an
"AI-assisted" claim would require a model call and could not be reproduced or gated.

The search is honest about its limits:

* it explores at most ``max_depth`` tactic applications and ``max_nodes`` states;
* it reports ``found=False`` with the number of nodes explored when the budget runs out,
  never a silent success;
* a visited-set keyed on the goal/hypothesis text prevents re-expanding a state, so the
  search terminates even when a tactic is idempotent.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from svl.tactics import (
    Goal,
    ProofState,
    Tactic,
    TacticResult,
)


@dataclass
class SearchResult:
    found: bool
    script: List[Tactic] = field(default_factory=list)
    nodes_explored: int = 0
    depth_reached: int = 0
    message: str = ""

    def __bool__(self) -> bool:
        return self.found


def _state_key(state: ProofState) -> Tuple:
    """A hashable identity for a proof state (used only to avoid re-expansion)."""
    goals = tuple(str(g.statement) for g in state.goals)
    hyps = tuple(sorted((k, str(v)) for k, v in state.hypotheses.items()))
    return (goals, hyps)


def _script_key(script: Sequence[Tactic]) -> Tuple:
    return tuple(type(t).__name__ + repr(getattr(t, "__dict__", {})) for t in script)


def search_proof(goal: Any,
                 tactics: Sequence[Tactic],
                 hypotheses: Optional[Dict[str, Any]] = None,
                 max_depth: int = 4,
                 max_nodes: int = 512) -> SearchResult:
    """Find a sequence of `tactics` that closes `goal`, within a bounded budget.

    `goal` may be a ``Goal`` or a proposition string understood by
    ``svl.tactics.parse_prop``.
    """
    if isinstance(goal, Goal):
        initial = ProofState(goals=[goal], hypotheses=dict(hypotheses or {}))
    else:
        initial = ProofState(goals=[Goal(statement=goal)],
                             hypotheses=dict(hypotheses or {}))

    if not initial.goals:
        return SearchResult(True, [], 0, 0, "the goal was already closed")

    frontier: List[Tuple[ProofState, List[Tactic], int]] = [(initial, [], 0)]
    visited = {_state_key(initial)}
    nodes = 0
    deepest = 0

    while frontier:
        state, script, depth = frontier.pop(0)
        nodes += 1
        deepest = max(deepest, depth)
        if nodes > max_nodes:
            return SearchResult(
                False, [], nodes, deepest,
                f"budget exhausted: {max_nodes} states explored without closing the goal")
        if depth >= max_depth:
            continue

        for tactic in tactics:
            try:
                result, new_state, _message = tactic.apply(state)
            except Exception:                                    # noqa: BLE001
                continue
            if result == TacticResult.FAILURE:
                continue
            new_script = script + [tactic]
            if result == TacticResult.SUCCESS and not new_state.goals:
                return SearchResult(True, new_script, nodes, depth + 1,
                                    "proof found")
            key = _state_key(new_state)
            if key in visited:
                continue
            visited.add(key)
            frontier.append((new_state, new_script, depth + 1))

    return SearchResult(
        False, [], nodes, deepest,
        f"no proof within {max_depth} steps ({nodes} states explored)")


def describe_script(script: Sequence[Tactic]) -> str:
    """A one-line rendering of a tactic script, for reports and diagnostics."""
    names = []
    for tactic in script:
        label = type(tactic).__name__
        if label == "Apply":
            label += f"({getattr(tactic, 'lemma_name', '?')})"
        elif label in ("Exact", "Rewrite", "Induction", "Cases"):
            label += f"({getattr(tactic, 'term', None) or getattr(tactic, 'equality', None) or getattr(tactic, 'variable', None) or getattr(tactic, 'expression', None)})"
        names.append(label)
    return "; ".join(names)


def main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse

    from svl.tactics import assumption, intro, trivial

    parser = argparse.ArgumentParser(prog="svl-prove",
                                     description="Search for a tactic proof of a proposition")
    parser.add_argument("goal", help="e.g. 'A -> A'")
    parser.add_argument("--depth", type=int, default=4)
    args = parser.parse_args(argv)

    result = search_proof(args.goal, [intro, trivial, assumption],
                          max_depth=args.depth)
    if result:
        print(f"proven: {describe_script(result.script)}")
        return 0
    print(f"not proven: {result.message}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
