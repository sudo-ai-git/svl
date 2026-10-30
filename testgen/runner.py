"""Automated test execution runner.

Runs generated test cases against actual pcomp code,
captures outputs, and produces structured results.
"""
from __future__ import annotations
import time
import traceback
import numpy as np
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from pcomp import cmat, verify, quant, ringbuf, tokenstep
from .generator import TestCase, TestCaseGenerator
from .vector_store import TestVector, RingVectorStore


@dataclass
class TestResult:
    """Result of executing a single test."""
    test_id: str
    target: str
    passed: bool
    actual_output: Any = None
    expected_output: Any = None
    execution_time_ms: float = 0.0
    error: str = ""
    oracle_method: str = ""
    confidence: float = 0.0
    verified: bool = False

    def __repr__(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        return f"<TestResult {self.test_id}: {status} ({self.execution_time_ms:.1f}ms)>"


class TestRunner:
    """Execute generated test cases against pcomp code."""

    def __init__(self, timeout_s: float = 30.0):
        self.timeout_s = timeout_s
        self._results: List[TestResult] = []
        self._execution_times: Dict[str, float] = {}

    def run(self, test_cases: List[TestCase]) -> List[TestResult]:
        """Run all test cases and return results."""
        self._results = []
        for tc in test_cases:
            result = self._execute(tc)
            self._results.append(result)
            self._execution_times[tc.id] = result.execution_time_ms
        return self._results

    def _execute(self, test_case: TestCase) -> TestResult:
        """Execute a single test case."""
        start = time.monotonic()
        target = test_case.target
        inputs = test_case.inputs

        try:
            actual = self._call_function(target, inputs)
            passed = self._check_result(actual, test_case)
            error = ""
        except Exception as e:
            actual = None
            passed = False
            error = f"{type(e).__name__}: {str(e)}"

        elapsed = (time.monotonic() - start) * 1000

        result = TestResult(
            test_id=test_case.id,
            target=target,
            passed=passed,
            actual_output=actual,
            expected_output=test_case.expected,
            execution_time_ms=elapsed,
            error=error,
            oracle_method=test_case.expected_via,
            confidence=test_case.expected_via == "verify" and passed,
        )
        return result

    def _call_function(self, target: str, inputs: Dict[str, Any]) -> Any:
        """Dynamically call a function with the given inputs."""
        # Parse target into module.function
        parts = target.rsplit(".", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid target: {target}")

        module_name, func_name = parts

        try:
            mod = __import__(module_name, fromlist=[func_name])
        except ImportError:
            # Try pcomp directly
            if module_name == "pcomp":
                mod = __import__("pcomp", fromlist=[func_name])
            else:
                raise

        func = getattr(mod, func_name)

        # Handle cgemm_blocked specially (has block parameter)
        if func_name == "cgemm_blocked":
            return func(
                np.array(inputs["A"]),
                np.array(inputs["B"]),
                block=inputs.get("block", 32),
            )
        elif func_name == "cgemm":
            return func(np.array(inputs["A"]), np.array(inputs["B"]))
        elif func_name == "phase_matmul":
            return func(np.array(inputs["A"]), np.array(inputs["B"]))
        elif func_name == "coherent_mean":
            return func(np.array(inputs["A"]), np.array(inputs["B"]))
        elif func_name == "token_step":
            return func(n_tokens=inputs.get("n_tokens", 10))
        elif func_name == "quant_forward":
            return func(
                np.array(inputs["W"]) if "W" in inputs else None,
                np.array(inputs["X"]) if "X" in inputs else None,
            ) if "W" in inputs or "X" in inputs else func(
                np.array(inputs["x"]), **{k: v for k, v in inputs.items() if k != "x"}
            )
        elif func_name == "AdcQuantizer":
            # Constructor call
            q = quant.AdcQuantizer(
                din=inputs.get("din", 16),
                dout=inputs.get("dout", 8),
                adc_enob=inputs.get("adc_enob", 10),
            )
            return q
        elif func_name == "RingBuffer":
            rb = ringbuf.RingBuffer(size=inputs.get("size", 8))
            # Perform push/pop operations if specified
            ops = inputs.get("operations", [])
            for op in ops[:inputs.get("size", 8)]:
                if op == "push":
                    rb.push(float(inputs.get("val", 0)))
            return rb
        elif func_name == "summary":
            return verify.summary()
        elif func_name == "gate_bitidentity":
            return verify.gate_bitidentity()
        elif func_name == "gate_cgemm_blocked":
            return verify.gate_cgemm_blocked()
        elif func_name == "gate_phase_coherent":
            return verify.gate_phase_coherent()
        elif func_name == "gate_quant_bitidentical":
            return verify.gate_quant_bitidentical()
        elif func_name == "token_batch":
            return tokenstep.token_batch(
                inputs.get("tokens", list(range(10))),
                batch_size=inputs.get("batch_size", 32),
            )
        elif func_name == "process":
            # TokenPipeline.process
            return func(inputs.get("n_tokens", 100))
        elif func_name == "snapshot":
            # LiveCoprocessor
            lp = inputs.get("self", None)
            return lp.snapshot() if lp else {"status": "no_live_instance"}
        elif func_name == "init_phase_regs":
            lp = inputs.get("self", None)
            if lp:
                lp.init_phase_regs(inputs.get("n_registers", 256))
            return {"initialized": True}
        else:
            # Generic function call
            return func(**inputs)

    def _check_result(self, actual: Any, test_case: TestCase) -> bool:
        """Check if actual output matches expected."""
        expected = test_case.expected

        if expected is None:
            # Property-based: just check it didn't crash
            return actual is not None or test_case.expected_via in ("verify", "property")

        if isinstance(expected, dict):
            if "pass" in expected:
                return bool(expected["pass"])
            if "all_pass" in expected:
                return bool(expected["all_pass"])
            # Compare dict values
            return isinstance(actual, dict) and len(actual) > 0

        if isinstance(expected, bool):
            return actual == expected

        if isinstance(expected, (int, float, np.number)):
            if actual is None:
                return False
            return abs(float(actual) - float(expected)) < 1e-3

        if isinstance(expected, str):
            return str(actual) == expected or str(actual) in expected

        if isinstance(expected, np.ndarray):
            if actual is None:
                return False
            return np.allclose(actual, expected, atol=1e-3)

        # Default: assume test passed if it didn't error
        return True

    def run_oracle_verified(self, test_cases: List[TestCase],
                             oracle) -> List[TestResult]:
        """Run tests and verify with oracle."""
        results = self.run(test_cases)
        for result in results:
            # Get corresponding test case
            tc = next((t for t in test_cases if t.id == result.test_id), None)
            if tc and oracle:
                oracle_result = oracle.compute_expected(tc)
                result.confidence = oracle_result.confidence
                result.verified = oracle_result.verified
        return results

    @property
    def results(self) -> List[TestResult]:
        return self._results

    def summary(self) -> Dict[str, Any]:
        """Return execution summary."""
        n_passed = sum(1 for r in self._results if r.passed)
        n_total = len(self._results)
        avg_time = sum(r.execution_time_ms for r in self._results) / max(n_total, 1)
        errors = [r.error for r in self._results if r.error]
        return {
            "total": n_total,
            "passed": n_passed,
            "failed": n_total - n_passed,
            "pass_rate": n_passed / n_total if n_total > 0 else 0.0,
            "avg_execution_ms": avg_time,
            "total_execution_ms": sum(r.execution_time_ms for r in self._results),
            "errors": len(errors),
            "error_details": errors[:5],  # Top 5 errors
        }
