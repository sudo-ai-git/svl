"""Main orchestration for automated test generation.

Coordinates discovery, generation, oracle computation, execution,
verification, storage, and evolution into a complete pipeline.
"""
from __future__ import annotations
import sys
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List
import numpy as np
import datetime as _datetime

# Add paths for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, "/home/sudosudo/photonic-backup")
sys.path.insert(0, "/home/sudosudo/.local/lib/python3.12/site-packages")

from .discovery import FunctionDiscovery, ClassDiscovery, ModuleInspector
from .generator import TestCase, TestCaseGenerator
from .oracle import TestOracle, PhotonicOracle
from .verifier import GateVerifier, PhotonicVerifier
from .vector_store import RingVectorStore, TestVectorBank
from .evolver import TestEvolver
from .runner import TestRunner, TestResult
from .report import TestReport, TestSummary


@dataclass
class PipelineConfig:
    """Configuration for the automated test generation pipeline."""
    target_modules: List[str] = field(default_factory=lambda: ["pcomp"])
    include_classes: bool = True
    include_functions: bool = True
    generate_tests_per_function: int = 3
    use_oracle: bool = True
    use_verifier: bool = True
    use_evolution: bool = True
    store_in_ringbuf: bool = True
    ringbuf_capacity: int = 1024
    evolution_mutations: int = 2
    seed: int = 42
    output_report: bool = True
    report_path: str = "testgen_report.json"


class AutomatedTestGenerator:
    """Main pipeline: discover -> generate -> oracle -> execute -> verify -> store -> evolve."""

    def __init__(self, config: PipelineConfig = None) -> None:
        self.config = config or PipelineConfig()
        self.config.seed = self.config.seed or 42
        self._rng = np.random.default_rng(self.config.seed)

        # Pipeline components
        self.discovery = FunctionDiscovery()
        self.generator = TestCaseGenerator(seed=self.config.seed)
        self.oracle = TestOracle()
        self.verifier = GateVerifier()
        self.evolver = TestEvolver(seed=self.config.seed)
        self.runner = TestRunner()

        # Storage
        if self.config.store_in_ringbuf:
            self.vector_store = RingVectorStore(capacity=self.config.ringbuf_capacity)
        else:
            self.vector_store = RingVectorStore(capacity=0)

        # Results
        self._test_cases: List[TestCase] = []
        self._results: List[TestResult] = []
        self._report: Any = None

    def run(self) -> TestReport:
        """Execute the full automated test generation pipeline."""
        functions, classes = self._discover()
        self._test_cases = self._generate(functions, classes)
        oracle_results = self._compute_oracles()
        self._results = self._execute_tests()
        verifier_results = self._verify_tests()
        evolution_stats = self._evolve_tests()
        vector_stats = self._store_vectors()
        self._report = self._create_report(
            functions=functions, classes=classes,
            oracle_results=oracle_results,
            verifier_results=verifier_results,
            evolution_stats=evolution_stats,
            vector_stats=vector_stats,
        )
        return self._report

    def run_pcomp_pipeline(self) -> TestReport:
        """Run full pipeline for pcomp package."""
        self.config.target_modules = ["pcomp"]
        return self.run()

    def run_grAIl_pipeline(self) -> TestReport:
        """Run full pipeline for grAIl package."""
        self.config.target_modules = ["grAIl"]
        return self.run()

    # ─── Pipeline phases ─────────────────────────

    def _discover(self) -> tuple:
        """Phase 1: Discover functions and classes."""
        all_funcs = []
        all_classes = []
        for module in self.config.target_modules:
            try:
                funcs, classes = self.discovery.discover_package(module)
                all_funcs.extend(funcs)
                all_classes.extend(classes)
            except Exception:
                try:
                    funcs, classes = self.discovery.discover_module(module)
                    all_funcs.extend(funcs)
                    all_classes.extend(classes)
                except Exception:
                    pass
        return all_funcs, all_classes

    def _generate(self, functions: list, classes: list) -> List[TestCase]:
        """Phase 2: Generate test cases."""
        all_cases = []
        if self.config.include_functions:
            for func in functions:
                all_cases.extend(self.generator.generate_for_function(func))
        if self.config.include_classes:
            for cls in classes:
                all_cases.extend(self.generator.generate_for_class(cls))
        if self.config.generate_tests_per_function > 0:
            from collections import defaultdict
            by_target = defaultdict(list)
            for tc in all_cases:
                by_target[tc.target].append(tc)
            all_cases = [c for target_cases in by_target.values() for c in target_cases[:self.config.generate_tests_per_function]]
        self._test_cases = all_cases
        return all_cases

    def _compute_oracles(self) -> Dict[str, Any]:
        """Phase 3: Compute expected outputs via oracle."""
        oracle_results = {}
        for tc in self._test_cases:
            if self.config.use_oracle:
                oracle_results[tc.id] = self.oracle.compute_expected(tc)
        return oracle_results

    def _execute_tests(self) -> List[TestResult]:
        """Phase 4: Execute test cases."""
        self._results = self.runner.run(self._test_cases)
        return self._results

    def _verify_tests(self) -> Dict[str, Any]:
        """Phase 5: Verify test outputs through photonic gates."""
        verifier_results = {}
        if self.config.use_verifier:
            for result in self._results:
                tc = next((t for t in self._test_cases if t.id == result.test_id), None)
                if tc:
                    verifier_results[result.test_id] = self.verifier.verify_test(tc, result.actual_output)
        return verifier_results

    def _evolve_tests(self) -> Dict[str, Any]:
        """Phase 6: Evolve test cases."""
        stats = {"total": 0, "high_quality": 0, "medium_quality": 0, "low_quality": 0}
        if self.config.use_evolution and self._test_cases:
            evolutions = self.evolver.evolve_batch(
                self._test_cases[:20],
                vector_store=self.vector_store if self.config.store_in_ringbuf else None,
                n_mutations=self.config.evolution_mutations,
            )
            stats["total"] = len(evolutions)
            qdist = self.evolver.quality_distribution()
            stats.update(qdist)
        return stats

    def _store_vectors(self) -> Dict[str, Any]:
        """Phase 7: Store test vectors in ring buffer."""
        if not self.config.store_in_ringbuf:
            return {"stored": 0, "capacity": 0}
        for result in self._results:
            tc = next((t for t in self._test_cases if t.id == result.test_id), None)
            if tc:
                self.vector_store.store(self._result_to_vector(result, tc))
        return self.vector_store.stats()

    def _result_to_vector(self, result: TestResult, tc: TestCase) -> Any:
        """Convert a test result to a TestVector."""
        from .vector_store import TestVector
        return TestVector(
            id=result.test_id,
            target=result.target,
            inputs_hash=str(hash(str(tc.inputs))),
            expected=tc.expected,
            result=result.actual_output,
            passed=result.passed,
            oracle_method=tc.expected_via,
            confidence=result.confidence,
            tags=[tc.target.split(".")[-1]],
        )

    def _create_report(self, functions: list, classes: list,
                        oracle_results: Dict, verifier_results: Dict,
                        evolution_stats: Dict, vector_stats: Dict) -> TestReport:
        """Phase 8: Create final report."""
        runner_summary = self.runner.summary()
        verifier_summary = self.verifier.summary()
        report_id = f"TG-{self.config.seed:04d}-{_datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"

        test_results = []
        for r in self._results:
            test_results.append({
                "test_id": r.test_id,
                "target": r.target,
                "passed": r.passed,
                "execution_time_ms": r.execution_time_ms,
                "error": r.error,
                "confidence": r.confidence,
                "oracle_method": r.oracle_method,
            })

        report = TestReport(
            report_id=report_id,
            timestamp=_datetime.datetime.utcnow().isoformat(),
            target_package=", ".join(self.config.target_modules),
            total_tests=runner_summary["total"],
            passed_tests=runner_summary["passed"],
            failed_tests=runner_summary["failed"],
            pass_rate=runner_summary["pass_rate"],
            execution_time_ms=runner_summary["total_execution_ms"],
            test_results=test_results,
            oracle_results={"total": len(oracle_results)},
            verifier_results={
                "pass_rate": verifier_summary.get("pass_rate", 0),
                "all_pass": verifier_summary.get("all_pass", False),
                "avg_confidence": verifier_summary.get("avg_confidence", 0),
            },
            evolution_stats=evolution_stats,
            vector_store_stats=vector_stats,
            metadata={"seed": self.config.seed, "n_functions": len(functions), "n_classes": len(classes)},
        )
        self._report = report
        return report

    def print_report(self) -> None:
        """Print the test report to stdout."""
        if self._report:
            print(self._report.to_markdown())
        else:
            print("No report available. Run pipeline first.")

    def save_report(self, path: str = "testgen_report.json") -> str:
        """Save the test report to JSON file."""
        if self._report:
            with open(path, "w") as f:
                f.write(self._report.to_json())
            return path
        return ""


def main() -> None:
    """Run automated test generation from command line."""
    import argparse
    parser = argparse.ArgumentParser(description="Automated Test Generation for pcomp/grAIl")
    parser.add_argument("--module", default="pcomp", help="Target module")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--no-evolve", action="store_true", help="Skip evolution")
    parser.add_argument("--output", default="testgen_report.json", help="Report output path")
    args = parser.parse_args()

    config = PipelineConfig(
        target_modules=[args.module],
        seed=args.seed,
        use_evolution=not args.no_evolve,
        report_path=args.output,
    )
    gen = AutomatedTestGenerator(config)
    report = gen.run()
    gen.print_report()
    print(f"\nReport saved to: {gen.save_report()}")


if __name__ == "__main__":
    main()
