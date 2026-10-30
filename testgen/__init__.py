"""pcomp Automated Test Generation — Idea 12: Photonically-computed test oracles.

The testgen package implements automated test generation for the pcomp framework
and grAIl agent loop using deterministic photonic verification:

  1. DISCOVERY  — Reflect on pcomp/grAIl modules to enumerate functions/classes
  2. GENERATION — Produce property-based test cases via deterministic analysis
  3. ORACLE     — Compute expected outputs using cmat/verify/quant
  4. EXECUTION  — Run tests against actual code
  5. VERIFICATION — Confirm outputs through photonic gates
  6. STORAGE    — Accumulate test vectors in ringbuf
  7. EVOLUTION  — Mutate test cases via photonic-inspired evolution

Usage:
    from testgen import AutomatedTestGenerator
    gen = AutomatedTestGenerator()
    report = gen.run_pcomp_pipeline()
    gen.print_report()
"""
from __future__ import annotations

__version__ = "1.0.0"

from .discovery import FunctionDiscovery, ClassDiscovery, ModuleInspector
from .generator import TestCase, TestCaseGenerator
from .oracle import TestOracle, PhotonicOracle
from .verifier import PhotonicVerifier, GateVerifier
from .vector_store import RingVectorStore, TestVectorBank
from .evolver import TestEvolver, MutationOperator
from .runner import TestRunner, TestResult
from .report import TestReport, TestSummary
from .main import AutomatedTestGenerator, PipelineConfig

__all__ = [
    "AutomatedTestGenerator",
    "PipelineConfig",
    "FunctionDiscovery",
    "ClassDiscovery",
    "ModuleInspector",
    "TestCase",
    "TestCaseGenerator",
    "TestOracle",
    "PhotonicOracle",
    "PhotonicVerifier",
    "GateVerifier",
    "RingVectorStore",
    "TestVectorBank",
    "TestEvolver",
    "MutationOperator",
    "TestRunner",
    "TestResult",
    "TestReport",
    "TestSummary",
]
