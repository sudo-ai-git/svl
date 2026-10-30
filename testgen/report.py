"""Test report generation and summary.

Produces structured reports from test execution results,
including pass/fail analysis, coverage metrics, and
photonic verification summaries.
"""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import datetime


@dataclass
class TestReport:
    """Complete test report for a test generation run."""
    report_id: str
    timestamp: str
    target_package: str
    total_tests: int
    passed_tests: int
    failed_tests: int
    pass_rate: float
    execution_time_ms: float
    test_results: List[Dict[str, Any]] = field(default_factory=list)
    oracle_results: Dict[str, Any] = field(default_factory=dict)
    verifier_results: Dict[str, Any] = field(default_factory=dict)
    evolution_stats: Dict[str, Any] = field(default_factory=dict)
    vector_store_stats: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __repr__(self) -> str:
        return (f"<TestReport {self.report_id}: {self.passed_tests}/{self.total_tests} "
                f"passed ({self.pass_rate:.1%})>")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "report_id": self.report_id,
            "timestamp": self.timestamp,
            "target_package": self.target_package,
            "summary": {
                "total": self.total_tests,
                "passed": self.passed_tests,
                "failed": self.failed_tests,
                "pass_rate": self.pass_rate,
                "execution_time_ms": self.execution_time_ms,
            },
            "test_results": self.test_results,
            "oracle_results": self.oracle_results,
            "verifier_results": self.verifier_results,
            "evolution_stats": self.evolution_stats,
            "vector_store_stats": self.vector_store_stats,
            "metadata": self.metadata,
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, default=str)

    def to_markdown(self) -> str:
        """Generate human-readable markdown report."""
        lines = [
            f"# Automated Test Generation Report",
            f"",
            f"**Report ID:** {self.report_id}",
            f"**Date:** {self.timestamp}",
            f"**Target:** {self.target_package}",
            f"",
            f"## Summary",
            f"",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Total Tests | {self.total_tests} |",
            f"| Passed | {self.passed_tests} |",
            f"| Failed | {self.failed_tests} |",
            f"| Pass Rate | {self.pass_rate:.1%} |",
            f"| Execution Time | {self.execution_time_ms:.0f}ms |",
            f"",
        ]

        if self.test_results:
            lines.append("## Test Results")
            lines.append("")
            lines.append("| ID | Target | Status | Time |")
            lines.append("|----|--------|--------|------|")
            for r in self.test_results:
                status = "✅" if r.get("passed") else "❌"
                lines.append(f"| {r.get('test_id', '?')} | {r.get('target', '?')} | {status} | {r.get('execution_time_ms', 0):.1f}ms |")
            lines.append("")

        if self.verifier_results:
            lines.append("## Photonic Verification")
            lines.append("")
            vs = self.verifier_results
            if "pass_rate" in vs:
                lines.append(f"- Gate Pass Rate: {vs['pass_rate']:.1%}")
            if "all_pass" in vs:
                lines.append(f"- All Gates Pass: {vs['all_pass']}")
            if "avg_confidence" in vs:
                lines.append(f"- Average Confidence: {vs['avg_confidence']:.2f}")
            lines.append("")

        if self.evolution_stats:
            lines.append("## Test Evolution")
            lines.append("")
            es = self.evolution_stats
            if "total" in es:
                lines.append(f"- Total Mutations: {es['total']}")
            if "high_quality" in es:
                lines.append(f"- High Quality: {es['high_quality']}")
            if "medium_quality" in es:
                lines.append(f"- Medium Quality: {es['medium_quality']}")
            if "low_quality" in es:
                lines.append(f"- Low Quality: {es['low_quality']}")
            lines.append("")

        return "\n".join(lines)

    def get_failed_tests(self) -> List[Dict[str, Any]]:
        """Get all failing test results."""
        return [r for r in self.test_results if not r.get("passed", True)]

    def get_passing_tests(self) -> List[Dict[str, Any]]:
        """Get all passing test results."""
        return [r for r in self.test_results if r.get("passed", False)]

    def add_test_result(self, result: Dict[str, Any]) -> None:
        """Add a test result to the report."""
        self.test_results.append(result)

    def add_metadata(self, key: str, value: Any) -> None:
        """Add metadata to the report."""
        self.metadata[key] = value


class TestSummary:
    """Aggregate summaries from multiple test reports."""

    def __init__(self):
        self.reports: List[TestReport] = []

    def add_report(self, report: TestReport) -> None:
        """Add a report to the summary."""
        self.reports.append(report)

    def overall_summary(self) -> Dict[str, Any]:
        """Generate overall summary across all reports."""
        total_tests = sum(r.total_tests for r in self.reports)
        total_passed = sum(r.passed_tests for r in self.reports)
        total_failed = sum(r.failed_tests for r in self.reports)
        total_time = sum(r.execution_time_ms for r in self.reports)
        all_pass_rate = total_passed / max(total_tests, 1)

        return {
            "total_reports": len(self.reports),
            "total_tests": total_tests,
            "total_passed": total_passed,
            "total_failed": total_failed,
            "overall_pass_rate": all_pass_rate,
            "total_execution_ms": total_time,
            "avg_tests_per_run": total_tests / max(len(self.reports), 1),
            "reports": [r.report_id for r in self.reports],
        }

    def format_summary(self) -> str:
        """Format overall summary as string."""
        s = self.overall_summary()
        lines = [
            "═══ Automated Test Generation Summary ═══",
            f"  Reports: {s['total_reports']}",
            f"  Total Tests: {s['total_tests']}",
            f"  Passed: {s['total_passed']}",
            f"  Failed: {s['total_failed']}",
            f"  Pass Rate: {s['overall_pass_rate']:.1%}",
            f"  Total Time: {s['total_execution_ms']:.0f}ms",
            f"  Avg per Run: {s['avg_tests_per_run']:.0f} tests",
            "═" * 40,
        ]
        return "\n".join(lines)
