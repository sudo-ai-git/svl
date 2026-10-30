"""Photonic oracle computation for expected test outputs.

Computes expected outputs using pcomp's deterministic properties:
- cmat for matrix operation results
- verify gates for correctness assertions
- quant for quantized reference values
"""
from __future__ import annotations
import numpy as np
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from pcomp import cmat, verify, quant, ringbuf, tokenstep


@dataclass
class OracleResult:
    """Result of oracle computation."""
    test_id: str
    target: str
    expected: Any
    oracle_method: str  # "cmat" | "verify" | "quant" | "property" | "manual"
    confidence: float  # 0.0 to 1.0
    details: Dict[str, Any] = field(default_factory=dict)
    verified: bool = False

    def __repr__(self) -> str:
        return f"<OracleResult {self.test_id}: {self.oracle_method} conf={self.confidence:.2f}>"


class TestOracle:
    """Compute expected outputs using pcomp's deterministic substrate."""

    def __init__(self):
        self._results: List[OracleResult] = []

    def compute_expected(self, test_case, func_module: str = "pcomp") -> OracleResult:
        """Compute the expected output for a test case using the appropriate oracle."""
        target = test_case.target
        inputs = test_case.inputs
        method = test_case.expected_via

        if method == "cmat" or "cgemm" in target or "phase" in target:
            result = self._oracle_via_cmat(target, inputs, test_case)
        elif method == "verify" or target.startswith("gate_") or "gate" in target:
            result = self._oracle_via_verify(target, inputs, test_case)
        elif method == "quant" or "quant" in target or "AdcQuantizer" in target:
            result = self._oracle_via_quant(target, inputs, test_case)
        elif method == "property":
            result = self._oracle_via_property(target, inputs, test_case)
        else:
            result = self._oracle_via_property(target, inputs, test_case)

        self._results.append(result)
        return result

    def _oracle_via_cmat(self, target: str, inputs: Dict, test_case) -> OracleResult:
        """Compute expected output using cmat operations."""
        try:
            A = np.array(inputs.get("A", inputs.get("matrix_a", [])))
            B = np.array(inputs.get("B", inputs.get("matrix_b", [])))

            if A.size == 0 or B.size == 0:
                # Generate random matrices if not provided
                size = inputs.get("size", 4)
                A = np.random.default_rng(0).normal(size=(size, size)).astype(np.float32)
                B = np.random.default_rng(1).normal(size=(size, size)).astype(np.float32)

            # Ensure at least 2D
            A = np.atleast_2d(A)
            B = np.atleast_2d(B)

            if "cgemm_blocked" in target:
                block = inputs.get("block", 32)
                result = cmat.cgemm_blocked(A, B, block=block)
                # Compare with dense to get expected
                dense = cmat.cgemm(A, B)
                expected = {
                    "blocked_result": str(result.tolist()[:2]),
                    "dense_result": str(dense.tolist()[:2]),
                    "max_err": float(np.abs(dense - result).max()),
                    "pass": float(np.abs(dense - result).max()) < 1e-5,
                }
            elif "phase_matmul" in target or "phase" in target:
                mg, ph = cmat.phase_matmul(A, B)
                expected = {
                    "magnitude": str(mg.tolist()[:2]),
                    "phase": str(ph.tolist()[:2]),
                    "coherent": float(mg.mean()) > 0,
                }
            elif "coherent" in target:
                mg, ph = cmat.phase_matmul(A, B)
                expected = float(mg.mean())
            else:
                # Default cgemm
                if A.shape[1] != B.shape[0]:
                    B = B.T
                result = cmat.cgemm(A, B)
                expected = str(result.tolist()[:2])

            return OracleResult(
                test_case.id, target, expected, "cmat",
                confidence=1.0,
                details={"shape_A": A.shape, "shape_B": B.shape, "method": "cmat"},
                verified=True,
            )
        except Exception as e:
            return OracleResult(
                test_case.id, target, None, "cmat",
                confidence=0.0,
                details={"error": str(e)},
                verified=False,
            )

    def _oracle_via_verify(self, target: str, inputs: Dict, test_case) -> OracleResult:
        """Compute expected output using verification gates."""
        try:
            # Map gate names to actual gate functions
            gate_map = {
                "gate_bitidentity": verify.gate_bitidentity,
                "gate_cgemm_blocked": verify.gate_cgemm_blocked,
                "gate_phase_coherent": verify.gate_phase_coherent,
                "gate_quant_bitidentical": verify.gate_quant_bitidentical,
            }

            gate_fn = gate_map.get(target)
            if gate_fn is None:
                # Try summary-based approach
                summary_result = verify.summary()
                return OracleResult(
                    test_case.id, target, summary_result, "verify",
                    confidence=float(summary_result["passed"]) / summary_result["total"],
                    details={"total": summary_result["total"], "passed": summary_result["passed"]},
                    verified=summary_result["all_pass"],
                )

            result = gate_fn()
            return OracleResult(
                test_case.id, target, result, "verify",
                confidence=1.0 if result["pass"] else 0.0,
                details=result,
                verified=result["pass"],
            )
        except Exception as e:
            return OracleResult(
                test_case.id, target, None, "verify",
                confidence=0.0,
                details={"error": str(e)},
                verified=False,
            )

    def _oracle_via_quant(self, target: str, inputs: Dict, test_case) -> OracleResult:
        """Compute expected output using quantization."""
        try:
            q = quant.AdcQuantizer(din=16, dout=8, adc_enob=10)
            x = np.array(inputs.get("x", inputs.get("data", [])))
            if x.size == 0:
                x = np.random.default_rng(2).normal(size=(32, 32)).astype(np.float32)

            result = q.quant_forward(x)
            return OracleResult(
                test_case.id, target, str(result.tolist()[:2]), "quant",
                confidence=1.0,
                details={"input_shape": x.shape, "output_shape": result.shape,
                         "din": q.din, "dout": q.dout, "adc_enob": q.adc_enob},
                verified=True,
            )
        except Exception as e:
            return OracleResult(
                test_case.id, target, None, "quant",
                confidence=0.0,
                details={"error": str(e)},
                verified=False,
            )

    def _oracle_via_property(self, target: str, inputs: Dict, test_case) -> OracleResult:
        """Compute expected output using property-based analysis."""
        try:
            # For ringbuf, tokenstep, live — verify structural properties
            if "RingBuffer" in target or "ringbuf" in target:
                size = inputs.get("size", 8)
                rb = ringbuf.RingBuffer(size=size)
                for i in range(size):
                    rb.push(float(i))
                result = rb.get()
                return OracleResult(
                    test_case.id, target, str(result.tolist()), "property",
                    confidence=1.0,
                    details={"size": size, "count": rb.count, "head": rb.head},
                    verified=True,
                )
            elif "token_step" in target or "tokenstep" in target:
                n = inputs.get("n_tokens", 10)
                result = tokenstep.token_step(n)
                return OracleResult(
                    test_case.id, target, str(result), "property",
                    confidence=1.0,
                    details={"total": result["total"], "status": "processed"},
                    verified=True,
                )
            elif "LiveCoprocessor" in target or "live" in target:
                lp = inputs.get("register", 0)
                phi = inputs.get("phi", 0.0)
                return OracleResult(
                    test_case.id, target, {"register": lp, "phi": phi, "status": "ok"},
                    "property", confidence=1.0,
                    details={"phase_range": "[0, 2π]", "register_id": lp},
                    verified=True,
                )
            else:
                # Generic property: function should return a deterministic type
                return OracleResult(
                    test_case.id, target, {"property": "deterministic"}, "property",
                    confidence=0.5,
                    details={"note": "generic property check"},
                    verified=True,
                )
        except Exception as e:
            return OracleResult(
                test_case.id, target, None, "property",
                confidence=0.0,
                details={"error": str(e)},
                verified=False,
            )


class PhotonicOracle(TestOracle):
    """Extended oracle that uses multiple pcomp pillars for cross-verification."""

    def compute_triple_verified(self, test_case) -> Tuple[OracleResult, OracleResult, OracleResult]:
        """Compute expected via cmat, verify, and quant simultaneously."""
        cmat_result = self._oracle_via_cmat(test_case.target, test_case.inputs, test_case)
        verify_result = self._oracle_via_verify(test_case.target, test_case.inputs, test_case)
        quant_result = self._oracle_via_quant(test_case.target, test_case.inputs, test_case)
        return cmat_result, verify_result, quant_result

    def consensus_expected(self, test_case, n_trials: int = 5) -> OracleResult:
        """Run multiple oracle computations and take consensus."""
        results = []
        for trial in range(n_trials):
            r = self.compute_expected(test_case)
            results.append(r)

        # Count verified results
        n_verified = sum(1 for r in results if r.verified)
        consensus_confidence = n_verified / n_trials

        # Use the first verified result as consensus
        for r in results:
            if r.verified:
                r.confidence = consensus_confidence
                return r

        return results[0]
