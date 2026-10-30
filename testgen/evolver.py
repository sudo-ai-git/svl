"""Test case evolution via photonic-inspired mutation.

Implements photonic_evolve_adder-inspired mutation operators
that generate new test cases from existing ones, with verify
gates scoring test quality.
"""
from __future__ import annotations
import random
import numpy as np
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from copy import deepcopy
from .generator import TestCase, TestCaseGenerator
from .vector_store import TestVector, RingVectorStore


@dataclass
class MutationOperator:
    """A single mutation operation applied to a test case."""
    name: str
    description: str
    mutation_type: str  # "value" | "structure" | "parameter" | "boundary"
    strength: float = 0.5

    # Mutation operations
    VALUE_MUTATIONS = ["scale", "offset", "negate", "round", "truncate", "swap"]
    STRUCTURE_MUTATIONS = ["reorder_inputs", "add_input", "remove_input", "nest_inputs"]
    PARAMETER_MUTATIONS = ["change_dtype", "change_shape", "change_range"]
    BOUNDARY_MUTATIONS = ["zero", "max_value", "min_value", "inf", "nan"]


@dataclass
class EvolutionResult:
    """Result of evolving a test case."""
    original_id: str
    mutations_applied: List[str]
    new_test_case: Optional[TestCase] = None
    quality_score: float = 0.0
    verified: bool = False
    mutation_log: List[Dict[str, Any]] = field(default_factory=list)

    def __repr__(self) -> str:
        return f"<EvolutionResult {self.original_id}: {len(self.mutations_applied)} mutations, score={self.quality_score:.2f}>"


class TestEvolver:
    """Evolve test cases using photonic-inspired mutation operators.

    Inspired by photonic_evolve_adder: mutations swap, insert, delete
    test parameters, with verify gates scoring mutation quality.
    """

    def __init__(self, seed: int = 42):
        self.rng = random.Random(seed)
        self.np_rng = np.random.default_rng(seed)
        self._mutation_history: List[EvolutionResult] = []
        self._quality_scores: Dict[str, float] = {}

    def evolve(self, test_case: TestCase, vector_store: RingVectorStore = None,
               n_mutations: int = 3) -> List[EvolutionResult]:
        """Evolve a test case through multiple mutation operations."""
        results = []
        current = deepcopy(test_case)

        for i in range(n_mutations):
            mutation = self._select_mutation(current)
            mutated = self._apply_mutation(current, mutation)

            if mutated is None:
                continue

            # Score the mutation
            quality = self._score_mutation(mutated, current, mutation)

            result = EvolutionResult(
                original_id=test_case.id,
                mutations_applied=[mutation.name],
                new_test_case=mutated,
                quality_score=quality,
                mutation_log=[{"step": i, "mutation": mutation.name, "quality": quality}],
            )

            # Verify the mutated test
            result.verified = self._verify_mutation(mutated)

            # If verified, accept it
            if result.verified and result.quality_score > 0.3:
                current = mutated
                result.new_test_case = current

            results.append(result)

            # Track in vector store
            if vector_store and result.new_test_case:
                vector = TestVector(
                    id=result.new_test_case.id,
                    target=result.new_test_case.target,
                    inputs_hash=str(hash(str(result.new_test_case.inputs))),
                    expected=result.new_test_case.expected,
                    passed=result.verified,
                    oracle_method=result.new_test_case.expected_via,
                    confidence=result.quality_score,
                    tags=result.new_test_case.tags + ["evolved"],
                )
                vector_store.store(vector)

        return results

    def evolve_batch(self, test_cases: List[TestCase],
                     vector_store: RingVectorStore = None,
                     n_mutations: int = 3) -> List[EvolutionResult]:
        """Evolve a batch of test cases."""
        all_results = []
        for tc in test_cases:
            results = self.evolve(tc, vector_store, n_mutations)
            all_results.extend(results)
        return all_results

    # ─── Mutation operators ───────────────────────────

    def _select_mutation(self, test_case: TestCase) -> MutationOperator:
        """Select a mutation operator based on test case characteristics."""
        available = [
            MutationOperator("value_scale", "Scale numeric inputs", "value", 0.5),
            MutationOperator("value_offset", "Add offset to numeric inputs", "value", 0.3),
            MutationOperator("boundary_zero", "Set input to zero", "boundary", 0.7),
            MutationOperator("boundary_max", "Set input to max value", "boundary", 0.7),
            MutationOperator("reorder", "Reorder input parameters", "structure", 0.4),
            MutationOperator("add_param", "Add extra input parameter", "parameter", 0.3),
            MutationOperator("change_shape", "Change array shape", "parameter", 0.5),
            MutationOperator("boundary_inf", "Set input to infinity", "boundary", 0.6),
            MutationOperator("boundary_neg", "Negate input values", "value", 0.4),
            MutationOperator("swap_values", "Swap two input values", "value", 0.5),
        ]
        return self.rng.choice(available)

    def _apply_mutation(self, test_case: TestCase, mutation: MutationOperator) -> Optional[TestCase]:
        """Apply a mutation to a test case."""
        try:
            inputs = deepcopy(test_case.inputs)

            if mutation.mutation_type == "value":
                inputs = self._mutate_values(inputs, mutation)
            elif mutation.mutation_type == "boundary":
                inputs = self._mutate_boundaries(inputs, mutation)
            elif mutation.mutation_type == "structure":
                inputs = self._mutate_structure(inputs, mutation)
            elif mutation.mutation_type == "parameter":
                inputs = self._mutate_parameters(inputs, mutation)

            self._test_counter = getattr(self, '_test_counter', 0) + 1
            new_id = f"EV-{self._test_counter:04d}"

            return TestCase(
                id=new_id,
                target=test_case.target,
                description=f"{mutation.name}: {test_case.description}",
                inputs=inputs,
                expected=test_case.expected,
                expected_via=test_case.expected_via,
                complexity=test_case.complexity,
                tags=test_case.tags + [mutation.name],
                source=f"evolved:{mutation.name}",
            )
        except Exception:
            return None

    def _mutate_values(self, inputs: Dict, mutation: MutationOperator) -> Dict:
        """Mutate numeric values in inputs."""
        mutated = {}
        for k, v in inputs.items():
            if isinstance(v, (int, float)):
                if mutation.name == "value_scale":
                    factor = self.np_rng.uniform(0.5, 2.0)
                    mutated[k] = float(v * factor)
                elif mutation.name == "value_offset":
                    offset = self.np_rng.uniform(-1.0, 1.0)
                    mutated[k] = float(v + offset)
                elif mutation.name == "boundary_neg":
                    mutated[k] = float(-v)
                elif mutation.name == "swap_values":
                    mutated[k] = float(v)
                else:
                    mutated[k] = float(v)
            elif isinstance(v, list):
                arr = np.array(v)
                if arr.dtype.kind in 'biufc':  # numeric
                    if mutation.name == "value_scale":
                        arr = arr * self.np_rng.uniform(0.5, 2.0)
                    elif mutation.name == "boundary_zero":
                        arr = np.zeros_like(arr)
                    elif mutation.name == "boundary_max":
                        arr = np.full_like(arr, np.finfo(arr.dtype).max)
                    elif mutation.name == "boundary_inf":
                        arr = np.full_like(arr, np.inf)
                    elif mutation.name == "boundary_neg":
                        arr = -arr
                    mutated[k] = arr.tolist()
                else:
                    mutated[k] = v
            else:
                mutated[k] = v
        return mutated

    def _mutate_boundaries(self, inputs: Dict, mutation: MutationOperator) -> Dict:
        """Mutate inputs to boundary values."""
        mutated = {}
        for k, v in inputs.items():
            if isinstance(v, (int, float)):
                if mutation.name == "boundary_zero":
                    mutated[k] = 0
                elif mutation.name == "boundary_max":
                    mutated[k] = float('inf') if isinstance(v, float) else 2**31 - 1
                elif mutation.name == "boundary_inf":
                    mutated[k] = float('nan')
                elif mutation.name == "boundary_min":
                    mutated[k] = float('-inf') if isinstance(v, float) else -2**31
                else:
                    mutated[k] = float(v)
            elif isinstance(v, list):
                arr = np.array(v)
                if arr.dtype.kind in 'biufc':
                    if mutation.name == "boundary_zero":
                        mutated[k] = np.zeros_like(arr).tolist()
                    elif mutation.name == "boundary_max":
                        mutated[k] = np.full_like(arr, np.finfo(arr.dtype).max).tolist()
                    else:
                        mutated[k] = arr.tolist()
                else:
                    mutated[k] = v
            else:
                mutated[k] = v
        return mutated

    def _mutate_structure(self, inputs: Dict, mutation: MutationOperator) -> Dict:
        """Mutate input structure."""
        mutated = dict(inputs)
        if mutation.name == "reorder" and len(mutated) >= 2:
            keys = list(mutated.keys())
            self.rng.shuffle(keys)
            reordered = {k: mutated[k] for k in keys}
            mutated = reordered
        elif mutation.name == "add_param":
            new_key = f"extra_param_{self.rng.randint(0, 999)}"
            mutated[new_key] = float(self.np_rng.normal())
        return mutated

    def _mutate_parameters(self, inputs: Dict, mutation: MutationOperator) -> Dict:
        """Mutate parameter shapes and types."""
        mutated = dict(inputs)
        if mutation.name == "change_shape":
            for k, v in mutated.items():
                if isinstance(v, list) and len(v) > 1:
                    arr = np.array(v)
                    if arr.ndim >= 1:
                        new_shape = tuple(max(1, s + self.rng.randint(-1, 1)) for s in arr.shape)
                        try:
                            reshaped = arr.reshape(new_shape)
                            mutated[k] = reshaped.tolist()
                        except ValueError:
                            pass
        return mutated

    # ─── Scoring ──────────────────────────────────────

    def _score_mutation(self, mutated: TestCase, original: TestCase,
                         mutation: MutationOperator) -> float:
        """Score a mutation for quality (higher = better test)."""
        score = 0.5  # Base score

        # Boundary mutations are higher quality (catch edge cases)
        if mutation.mutation_type == "boundary":
            score += 0.3

        # Structural mutations add diversity
        if mutation.mutation_type == "structure":
            score += 0.2

        # Parameter mutations are moderate
        if mutation.mutation_type == "parameter":
            score += 0.1

        # Value mutations are baseline
        if mutation.mutation_type == "value":
            score += 0.05

        # Penalize if too similar to original
        input_diff = self._input_diversity(original.inputs, mutated.inputs)
        score += input_diff * 0.2

        # Random noise for exploration
        score += self.np_rng.uniform(-0.05, 0.05)

        return max(0.0, min(1.0, score))

    def _input_diversity(self, orig: Dict, mutated: Dict) -> float:
        """Measure how different mutated inputs are from original."""
        if not orig or not mutated:
            return 0.0
        total_diff = 0.0
        count = 0
        for k in set(list(orig.keys()) + list(mutated.keys())):
            if k in orig and k in mutated:
                o, m = orig[k], mutated[k]
                if isinstance(o, (int, float)) and isinstance(m, (int, float)):
                    if abs(o) > 1e-10:
                        total_diff += abs(m - o) / abs(o)
                    else:
                        total_diff += abs(m - o)
                    count += 1
        return total_diff / max(count, 1)

    def _verify_mutation(self, mutated: TestCase) -> bool:
        """Verify that a mutated test is still valid."""
        # A mutated test is valid if it has a target and inputs
        if not mutated.target or not mutated.inputs:
            return False
        # Check that inputs are not all NaN
        for v in mutated.inputs.values():
            if isinstance(v, float) and (v != v):  # NaN check
                return False
            if isinstance(v, list) and len(v) > 0:
                arr = np.array(v)
                if arr.dtype.kind in 'biufc' and not np.all(np.isfinite(arr)):
                    return False
        return True

    @property
    def history(self) -> List[EvolutionResult]:
        return self._mutation_history

    def quality_distribution(self) -> Dict[str, int]:
        """Return distribution of mutation quality scores."""
        scores = [r.quality_score for r in self._mutation_history]
        return {
            "high_quality": sum(1 for s in scores if s >= 0.7),
            "medium_quality": sum(1 for s in scores if 0.3 <= s < 0.7),
            "low_quality": sum(1 for s in scores if s < 0.3),
            "total": len(scores),
        }
