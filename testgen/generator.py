"""Test case generation from discovered functions.

Generates property-based test cases by analyzing function signatures,
docstrings, and source code to produce inputs and expected behaviors.
"""
from __future__ import annotations
import inspect
import random
import math
import numpy as np
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from .discovery import DiscoveredFunction, DiscoveredClass


@dataclass
class TestCase:
    """A single generated test case."""
    id: str
    target: str  # function/class.qualified_name
    description: str
    inputs: Dict[str, Any]
    expected: Any = None
    expected_via: str = ""  # "cmat" | "verify" | "quant" | "manual" | "property"
    complexity: str = "medium"
    tags: List[str] = field(default_factory=list)
    source: str = ""  # How this test was generated
    passes: Optional[bool] = None
    verified: bool = False

    def __repr__(self) -> str:
        status = "✓" if self.passes else ("✗" if self.passes is False else "?")
        return f"[{status}] {self.id}: {self.target}({list(self.inputs.keys())})"


class TestCaseGenerator:
    """Generate test cases from discovered functions using deterministic analysis."""

    def __init__(self, seed: int = 42):
        self.rng = random.Random(seed)
        self.np_rng = np.random.default_rng(seed)
        self._test_counter = 0

    def generate_for_function(self, func: DiscoveredFunction) -> List[TestCase]:
        """Generate test cases for a single discovered function."""
        tests = []
        name = func.name
        module = func.module

        # Generate based on function characteristics
        if "cgemm" in name:
            tests.extend(self._generate_cgemm_tests(func))
        elif "phase" in name or "phase_matmul" in name:
            tests.extend(self._generate_phase_tests(func))
        elif "quant" in name or "AdcQuantizer" in name:
            tests.extend(self._generate_quant_tests(func))
        elif "gate_" in name:
            tests.extend(self._generate_gate_tests(func))
        elif "ringbuf" in name.lower() or "RingBuffer" in name:
            tests.extend(self._generate_ringbuf_tests(func))
        elif "token" in name.lower() or "tokenstep" in name:
            tests.extend(self._generate_tokenstep_tests(func))
        elif "live" in name.lower():
            tests.extend(self._generate_live_tests(func))
        elif "coherent" in name:
            tests.extend(self._generate_coherent_tests(func))
        else:
            tests.extend(self._generate_generic_tests(func))

        return tests

    def generate_for_class(self, cls: DiscoveredClass) -> List[TestCase]:
        """Generate test cases for all methods of a discovered class."""
        tests = []
        for method in cls.methods:
            tests.extend(self.generate_for_function(method))
        return tests

    def generate_batch(self, functions: List[DiscoveredFunction],
                       classes: List[DiscoveredClass] | None = None) -> List[TestCase]:
        """Generate a batch of test cases for multiple targets."""
        all_tests = []
        for func in functions:
            tests = self.generate_for_function(func)
            all_tests.extend(tests)
        if classes:
            for cls in classes:
                tests = self.generate_for_class(cls)
                all_tests.extend(tests)
        return all_tests

    # ─── Specific generators ────────────────────────────────

    def _generate_cgemm_tests(self, func: DiscoveredFunction) -> List[TestCase]:
        """Generate matrix multiplication test cases."""
        tests = []
        self._test_counter += 1

        # Small square matrices
        inputs = {"A": self.np_rng.normal(size=(4, 4)).astype(np.float32).tolist(),
                   "B": self.np_rng.normal(size=(4, 4)).astype(np.float32).tolist()}
        tests.append(TestCase(
            id=f"TC-{self._test_counter:04d}",
            target=func.qualified_name,
            description="Small 4x4 float32 GEMM",
            inputs=inputs,
            expected_via="cmat",
            complexity="low",
            tags=["cgemm", "small", "float32"],
            source="property: square_matrix",
        ))

        # Complex matrices
        inputs = {"A": self.np_rng.normal(size=(8, 8)).astype(np.complex64).tolist(),
                   "B": self.np_rng.normal(size=(8, 8)).astype(np.complex64).tolist()}
        tests.append(TestCase(
            id=f"TC-{self._test_counter:04d}",
            target=func.qualified_name,
            description="Complex 8x8 GEMM",
            inputs=inputs,
            expected_via="cmat",
            complexity="medium",
            tags=["cgemm", "complex", "phase"],
            source="property: complex_matrix",
        ))

        # Blocked vs dense consistency
        self._test_counter += 1
        tests.append(TestCase(
            id=f"TC-{self._test_counter:04d}",
            target=f"{func.module}.cgemm_blocked",
            description="Blocked cgemm matches dense cgemm",
            inputs={"A": self.np_rng.normal(size=(64, 64)).astype(np.complex64).tolist(),
                     "B": self.np_rng.normal(size=(64, 64)).astype(np.complex64).tolist(),
                     "block": 32},
            expected_via="verify",
            complexity="high",
            tags=["cgemm_blocked", "blocked", "consistency"],
            source="property: blocked_vs_dense",
        ))
        return tests

    def _generate_phase_tests(self, func: DiscoveredFunction) -> List[TestCase]:
        """Generate phase matmul test cases."""
        tests = []
        self._test_counter += 1
        size = self.rng.choice([4, 8, 16])
        inputs = {"A": self.np_rng.normal(size=(size, size)).astype(np.complex64).tolist(),
                   "B": self.np_rng.normal(size=(size, size)).astype(np.complex64).tolist()}
        tests.append(TestCase(
            id=f"TC-{self._test_counter:04d}",
            target=func.qualified_name,
            description=f"Phase matmul with {size}x{size} complex matrices",
            inputs=inputs,
            expected_via="cmat",
            complexity="low",
            tags=["phase_matmul", "coherent"],
            source="property: phase_decomposition",
        ))
        return tests

    def _generate_quant_tests(self, func: DiscoveredFunction) -> List[TestCase]:
        """Generate quantization test cases."""
        tests = []
        self._test_counter += 1
        din = self.rng.choice([8, 16])
        dout = self.rng.choice([4, 8])
        enob = self.rng.choice([6, 8, 10])

        inputs = {"x": self.np_rng.normal(size=(32, 32)).astype(np.float32).tolist()}
        tests.append(TestCase(
            id=f"TC-{self._test_counter:04d}",
            target=func.qualified_name,
            description=f"ADC quantize din={din} dout={dout} enob={enob}",
            inputs={"din": din, "dout": dout, "adc_enob": enob},
            expected_via="quant",
            complexity="low",
            tags=["quant", "adc", "bit_sliced"],
            source="property: quantization_range",
        ))
        return tests

    def _generate_gate_tests(self, func: DiscoveredFunction) -> List[TestCase]:
        """Generate verification gate test cases."""
        tests = []
        self._test_counter += 1
        tests.append(TestCase(
            id=f"TC-{self._test_counter:04d}",
            target=func.qualified_name,
            description=f"Verification gate: {func.name}",
            inputs={},
            expected_via="verify",
            complexity="low",
            tags=["verify", "gate"],
            source="property: gate_pass_criteria",
        ))
        return tests

    def _generate_ringbuf_tests(self, func: DiscoveredFunction) -> List[TestCase]:
        """Generate ring buffer test cases."""
        tests = []
        self._test_counter += 1
        size = self.rng.choice([4, 8, 16, 32])
        inputs = {"val": float(self.np_rng.normal())}
        tests.append(TestCase(
            id=f"TC-{self._test_counter:04d}",
            target=func.qualified_name,
            description=f"RingBuffer push/pop with size={size}",
            inputs={"size": size, "operations": ["push", "pop"] * max(1, size // 2)},
            expected_via="property",
            complexity="low",
            tags=["ringbuf", "fifo", "deterministic"],
            source="property: ring_buffer_fifo",
        ))
        return tests

    def _generate_tokenstep_tests(self, func: DiscoveredFunction) -> List[TestCase]:
        """Generate token step driver test cases."""
        tests = []
        self._test_counter += 1
        n_tokens = self.rng.choice([10, 50, 100])
        tests.append(TestCase(
            id=f"TC-{self._test_counter:04d}",
            target=func.qualified_name,
            description=f"Token step driver with n_tokens={n_tokens}",
            inputs={"n_tokens": n_tokens},
            expected_via="property",
            complexity="low",
            tags=["tokenstep", "lockstep", "driver"],
            source="property: token_lockstep",
        ))
        return tests

    def _generate_live_tests(self, func: DiscoveredFunction) -> List[TestCase]:
        """Generate LiveCoprocessor test cases."""
        tests = []
        self._test_counter += 1
        tests.append(TestCase(
            id=f"TC-{self._test_counter:04d}",
            target=func.qualified_name,
            description="LiveCoprocessor phase register operations",
            inputs={"register": self.rng.randint(0, 255),
                     "phi": float(self.np_rng.uniform(0, 2 * math.pi))},
            expected_via="property",
            complexity="low",
            tags=["live", "phase_register", "mmap"],
            source="property: phase_register_io",
        ))
        return tests

    def _generate_coherent_tests(self, func: DiscoveredFunction) -> List[TestCase]:
        """Generate coherence measurement test cases."""
        tests = []
        self._test_counter += 1
        size = self.rng.choice([4, 8, 16])
        A = self.np_rng.normal(size=(size, size)).astype(np.complex64)
        B = self.np_rng.normal(size=(size, size)).astype(np.complex64)
        tests.append(TestCase(
            id=f"TC-{self._test_counter:04d}",
            target=func.qualified_name,
            description=f"Coherent mean with {size}x{size} matrices",
            inputs={"A": A.tolist(), "B": B.tolist()},
            expected_via="cmat",
            complexity="low",
            tags=["coherent", "phase_coherence"],
            source="property: coherence_measurement",
        ))
        return tests

    def _generate_generic_tests(self, func: DiscoveredFunction) -> List[TestCase]:
        """Generate generic test cases for any function."""
        tests = []
        self._test_counter += 1
        params = []
        for pname in range(func.param_count):
            params.append(f"arg{pname}")

        inputs = {}
        for p in params[:4]:  # Limit to 4 params for simplicity
            inputs[p] = float(self.np_rng.normal())

        tests.append(TestCase(
            id=f"TC-{self._test_counter:04d}",
            target=func.qualified_name,
            description=f"Generic test for {func.name}",
            inputs=inputs,
            expected_via="property",
            complexity="medium",
            tags=["generic", "property_based"],
            source="property: generic_input_space",
        ))
        return tests
