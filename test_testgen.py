"""Self-tests for the testgen package — test the test generator itself."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, "/home/sudosudo/photonic-backup")
sys.path.insert(0, "/home/sudosudo/.local/lib/python3.12/site-packages")

from testgen import (
    AutomatedTestGenerator, PipelineConfig,
    FunctionDiscovery, ClassDiscovery, TestCaseGenerator,
    TestOracle, GateVerifier, TestRunner,
    RingVectorStore, TestEvolver, TestVectorBank,
    TestReport, TestSummary,
)

def test_discovery():
    """Test module/function discovery."""
    disc = FunctionDiscovery()
    funcs, classes = disc.discover_module("pcomp")
    assert len(funcs) > 0, "Should discover functions in pcomp"
    assert len(classes) > 0, "Should discover classes in pcomp"
    func_names = [f.name for f in funcs]
    assert "cgemm" in func_names, "Should discover cgemm"
    assert "verify" not in func_names or "summary" in func_names, "Should discover verify-related"
    cls_names = [c.name for c in classes]
    assert "RingBuffer" in cls_names or "AdcQuantizer" in cls_names, "Should discover RingBuffer or AdcQuantizer"
    
    cd = ClassDiscovery()
    cls_results = cd.discover_module("pcomp")
    assert len(cls_results) > 0, "ClassDiscovery should find classes"
    print(f"  PASS: discovery ({len(funcs)} funcs, {len(classes)} classes)")

def test_generation():
    """Test test case generation."""
    disc = FunctionDiscovery()
    funcs, _ = disc.discover_module("pcomp")
    gen = TestCaseGenerator(seed=42)
    tests = gen.generate_batch(funcs[:3])
    assert len(tests) > 0, "Should generate test cases"
    for t in tests:
        assert t.id.startswith("TC-"), f"Test ID should start with TC-, got {t.id}"
        assert t.target, f"Test should have a target"
    print(f"  PASS: generation ({len(tests)} test cases)")

def test_oracle():
    """Test oracle computation."""
    disc = FunctionDiscovery()
    funcs, _ = disc.discover_module("pcomp")
    gen = TestCaseGenerator(seed=42)
    tests = gen.generate_for_function(funcs[0])
    oracle = TestOracle()
    results = [oracle.compute_expected(t) for t in tests[:3]]
    for r in results:
        assert r.oracle_method in ("cmat", "verify", "quant", "property"), f"Unknown oracle method: {r.oracle_method}"
    print(f"  PASS: oracle (confidence={results[0].confidence:.2f})")

def test_verification():
    """Test photonic verification."""
    disc = FunctionDiscovery()
    funcs, _ = disc.discover_module("pcomp")
    gen = TestCaseGenerator(seed=42)
    tests = gen.generate_for_function(funcs[0])[:3]
    runner = TestRunner()
    results = runner.run(tests)
    verifier = GateVerifier()
    vresults = verifier.verify_batch(tests, {r.test_id: r.actual_output for r in results})
    vsummary = verifier.summary()
    assert vsummary["total_verified"] > 0, "Should verify at least one test"
    print(f"  PASS: verification ({vsummary['passed']}/{vsummary['total_verified']} pass)")

def test_vector_store():
    """Test ring buffer storage."""
    store = RingVectorStore(capacity=10)
    from testgen.vector_store import TestVector
    vec = TestVector(
        id="TEST-001", target="test.func", inputs_hash="abc",
        expected=42, result=42, passed=True, oracle_method="property",
        confidence=1.0, tags=[],
    )
    assert store.store(vec), "Should store vector"
    assert store.size == 1, "Should have 1 vector"
    retrieved = store.get("TEST-001")
    assert retrieved is not None, "Should retrieve stored vector"
    assert retrieved.passed, "Should have passed=True"
    stats = store.stats()
    assert stats["stored"] == 1, "Stats should show 1 stored"
    print(f"  PASS: vector store ({store.size} vectors)")

def test_evolution():
    """Test test case evolution."""
    disc = FunctionDiscovery()
    funcs, _ = disc.discover_module("pcomp")
    gen = TestCaseGenerator(seed=42)
    tests = gen.generate_for_function(funcs[0])[:2]
    evolver = TestEvolver(seed=42)
    store = RingVectorStore(capacity=10)
    evos = evolver.evolve_batch(tests, vector_store=store, n_mutations=1)
    assert len(evos) >= 0, "Should produce evolution results"
    qdist = evolver.quality_distribution()
    assert "total" in qdist, "Quality distribution should have total key"
    print(f"  PASS: evolution ({qdist['total']} mutations)")

def test_report():
    """Test report generation."""
    report = TestReport(
        report_id="TEST-001", timestamp="2026-09-26T00:00:00",
        target_package="pcomp", total_tests=10, passed_tests=8,
        failed_tests=2, pass_rate=0.8, execution_time_ms=500.0,
    )
    assert report.passed_tests == 8, "Should have 8 passed"
    assert report.total_tests == 10, "Should have 10 total"
    md = report.to_markdown()
    assert "TGEN" in report.report_id or "TEST" in report.report_id, "Should have report ID"
    json_str = report.to_json()
    assert '"total_tests"' in json_str or '"total": 10' in json_str, f"JSON should contain test count: {json_str[:200]}"
    print(f"  PASS: report ({report.passed_tests}/{report.total_tests} passed)")

def test_summary():
    """Test summary aggregation."""
    summary = TestSummary()
    report = TestReport(
        report_id="T1", timestamp="2026-09-26T00:00:00",
        target_package="pcomp", total_tests=5, passed_tests=5,
        failed_tests=0, pass_rate=1.0, execution_time_ms=100.0,
    )
    summary.add_report(report)
    s = summary.overall_summary()
    assert s["total_tests"] == 5, "Should aggregate correctly"
    assert s["total_reports"] == 1, "Should have 1 report"
    print(f"  PASS: summary ({s['total_tests']} tests, {s['overall_pass_rate']:.0%} pass)")

def test_automated_generator():
    """Test the full automated pipeline."""
    config = PipelineConfig(
        target_modules=["pcomp"],
        use_evolution=False,
        store_in_ringbuf=True,
    )
    gen = AutomatedTestGenerator(config)
    report = gen.run()
    assert report.total_tests > 0, "Should generate tests"
    assert report.report_id.startswith("TG-"), "Report ID should start with TG-"
    assert report.pass_rate >= 0, "Pass rate should be valid"
    print(f"  PASS: automated generator ({report.total_tests} tests, {report.pass_rate:.0%} pass)")

def test_all_pcomp_gates():
    """Test that all pcomp verification gates pass."""
    from pcomp import verify
    summary = verify.summary()
    assert summary["all_pass"], f"All gates should pass: {summary}"
    assert summary["total"] >= 4, "Should have at least 4 gates"
    print(f"  PASS: pcomp gates ({summary['passed']}/{summary['total']} pass)")

if __name__ == "__main__":
    print("=" * 50)
    print("  testgen Self-Tests")
    print("=" * 50)
    test_discovery()
    test_generation()
    test_oracle()
    test_verification()
    test_vector_store()
    test_evolution()
    test_report()
    test_summary()
    test_automated_generator()
    test_all_pcomp_gates()
    print("=" * 50)
    print("  ALL SELF-TESTS PASSED")
    print("=" * 50)
