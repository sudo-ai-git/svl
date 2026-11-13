# svl/differential.py
# Differential Verification for SVL
# Compares two program versions across all 3 verification layers

from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
from svl.theorem_layer import verify_theorem_layer, TheoremVerificationConfig, TheoremVerifyResultWrapper
from svl.syntax_layer import verify_syntax, SyntaxVerificationConfig, VerifyResult
from svl.type_layer import verify_type, TypeVerificationConfig, TypeVerifyResult
from svl.golden_refs import get_golden_ref


class DiffKind(Enum):
    """Kind of semantic difference."""
    SYNTAX_CHANGE = "syntax_change"
    TYPE_CHANGE = "type_change"
    THEOREM_CHANGE = "theorem_change"
    MONODROMY_CHANGE = "monodromy_change"
    SMT_CHANGE = "smt_change"
    NO_CHANGE = "no_change"


@dataclass
class LayerDiff:
    """Difference in a single verification layer."""
    layer: str
    old_passed: bool
    new_passed: bool
    changed: bool
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SemanticDiff:
    """Complete semantic diff between two program versions."""
    old_source: str
    new_source: str
    overall_changed: bool
    diffs: List[LayerDiff] = field(default_factory=list)
    summary: str = ""
    
    # Detailed comparisons
    syntax_diff: Optional[LayerDiff] = None
    type_diff: Optional[LayerDiff] = None
    theorem_diff: Optional[LayerDiff] = None
    smt_diff: Optional[LayerDiff] = None


class DifferentialVerifier:
    """Verifies semantic differences between program versions."""
    
    def __init__(self, config: Optional[TheoremVerificationConfig] = None):
        self.config = config or TheoremVerificationConfig()
        
    def verify_diff(self, old_source: str, new_source: str) -> SemanticDiff:
        """
        Compute semantic diff between two program versions.
        
        Compares all verification layers:
        1. Syntax (231-gate checksums, AST guard)
        2. Types (Mod-5, Z/2, Dual-stream)
        3. Theorem (BPSW Monodromy + SMT)
        """
        # Verify old version
        old_syntax = verify_syntax(old_source, SyntaxVerificationConfig(
            block_size=self.config.block_size,
            use_cython=self.config.use_cython,
            verify_golden_refs=self.config.verify_golden_refs,
            run_mutation_tests=False
        ))
        
        old_types = verify_type(old_source, TypeVerificationConfig(
            block_size=self.config.block_size,
            use_cython=self.config.use_cython,
            verify_golden_refs=self.config.verify_golden_refs
        ))
        
        old_theorem = verify_theorem_layer(old_source, self.config)
        
        # Verify new version
        new_syntax = verify_syntax(new_source, SyntaxVerificationConfig(
            block_size=self.config.block_size,
            use_cython=self.config.use_cython,
            verify_golden_refs=self.config.verify_golden_refs,
            run_mutation_tests=False
        ))
        
        new_types = verify_type(new_source, TypeVerificationConfig(
            block_size=self.config.block_size,
            use_cython=self.config.use_cython,
            verify_golden_refs=self.config.verify_golden_refs
        ))
        
        new_theorem = verify_theorem_layer(new_source, self.config)
        
        # Build layer diffs
        diffs = []
        
        # Syntax diff
        syntax_changed = old_syntax.passed != new_syntax.passed
        syntax_diff = LayerDiff(
            layer="syntax",
            old_passed=old_syntax.passed,
            new_passed=new_syntax.passed,
            changed=syntax_changed,
            details={
                'old_viable_start': old_syntax.viable_start,
                'new_viable_start': new_syntax.viable_start,
                'old_checksums_match': old_syntax.checksums_match,
                'new_checksums_match': new_syntax.checksums_match,
                'old_guard_violations': len(old_syntax.ast_guard_violations),
                'new_guard_violations': len(new_syntax.ast_guard_violations),
            }
        )
        diffs.append(syntax_diff)
        
        # Type diff
        type_changed = old_types.passed != new_types.passed
        type_diff = LayerDiff(
            layer="types",
            old_passed=old_types.passed,
            new_passed=new_types.passed,
            changed=type_changed,
            details={
                'old_mod5': old_types.mod5_consistency,
                'new_mod5': new_types.mod5_consistency,
                'old_z2': old_types.z2_consistency,
                'new_z2': new_types.z2_consistency,
                'old_dual_stream': old_types.dual_stream_agreement,
                'new_dual_stream': new_types.dual_stream_agreement,
                'old_errors': len(old_types.errors),
                'new_errors': len(new_types.errors),
            }
        )
        diffs.append(type_diff)
        
        # Theorem diff
        theorem_changed = old_theorem.passed != new_theorem.passed
        monodromy_changed = old_theorem.monodromy_results != new_theorem.monodromy_results
        theorem_diff = LayerDiff(
            layer="theorem",
            old_passed=old_theorem.passed,
            new_passed=new_theorem.passed,
            changed=theorem_changed or monodromy_changed,
            details={
                'old_parities_even': old_theorem.all_parities_even,
                'new_parities_even': new_theorem.all_parities_even,
                'monodromy_changed': monodromy_changed,
                'old_hash': old_theorem.program_hash_hex[:16],
                'new_hash': new_theorem.program_hash_hex[:16],
                'old_smt_verified': old_theorem.smt_verified,
                'new_smt_verified': new_theorem.smt_verified,
            }
        )
        diffs.append(theorem_diff)
        
        # SMT diff (if both have SMT results)
        smt_diff = None
        if old_theorem.smt_verified or new_theorem.smt_verified:
            smt_changed = old_theorem.smt_verified != new_theorem.smt_verified
            smt_diff = LayerDiff(
                layer="smt",
                old_passed=old_theorem.smt_verified,
                new_passed=new_theorem.smt_verified,
                changed=smt_changed,
                details={
                    'old_smt_logic': old_theorem.smt_logic,
                    'new_smt_logic': new_theorem.smt_logic,
                    'old_smt_time': old_theorem.smt_solver_time_ms,
                    'new_smt_time': new_theorem.smt_solver_time_ms,
                }
            )
            diffs.append(smt_diff)
        
        # Overall changed if any layer changed
        overall_changed = any(d.changed for d in diffs)
        
        # Build summary
        changed_layers = [d.layer for d in diffs if d.changed]
        if changed_layers:
            summary = f"Semantic changes detected in: {', '.join(changed_layers)}"
        else:
            summary = "No semantic changes detected (textual changes only)"
            
        return SemanticDiff(
            old_source=old_source,
            new_source=new_source,
            overall_changed=overall_changed,
            diffs=diffs,
            summary=summary,
            syntax_diff=syntax_diff,
            type_diff=type_diff,
            theorem_diff=theorem_diff,
            smt_diff=smt_diff
        )
    
    def verify_diff_from_files(self, old_file: str, new_file: str) -> SemanticDiff:
        """Compute semantic diff from two files."""
        with open(old_file, 'r') as f:
            old_source = f.read()
        with open(new_file, 'r') as f:
            new_source = f.read()
        return self.verify_diff(old_source, new_source)
    
    def format_diff(self, diff: SemanticDiff, verbose: bool = False) -> str:
        """Format semantic diff for human-readable output."""
        lines = []
        lines.append("=" * 60)
        lines.append("SEMANTIC DIFF")
        lines.append("=" * 60)
        lines.append(f"Overall: {'CHANGED' if diff.overall_changed else 'UNCHANGED'}")
        lines.append(f"Summary: {diff.summary}")
        lines.append("")
        
        for layer_diff in diff.diffs:
            status = "CHANGED" if layer_diff.changed else "unchanged"
            lines.append(f"  {layer_diff.layer.upper()}: {status}")
            lines.append(f"    Old: {'PASS' if layer_diff.old_passed else 'FAIL'}")
            lines.append(f"    New: {'PASS' if layer_diff.new_passed else 'FAIL'}")
            
            if verbose:
                for key, value in layer_diff.details.items():
                    lines.append(f"    {key}: {value}")
            lines.append("")
        
        return "\n".join(lines)


def verify_semantic_diff(old_source: str, new_source: str, 
                         config: Optional[TheoremVerificationConfig] = None) -> SemanticDiff:
    """Convenience function to compute semantic diff."""
    verifier = DifferentialVerifier(config)
    return verifier.verify_diff(old_source, new_source)


def verify_semantic_diff_files(old_file: str, new_file: str,
                               config: Optional[TheoremVerificationConfig] = None) -> SemanticDiff:
    """Convenience function to compute semantic diff from files."""
    verifier = DifferentialVerifier(config)
    return verifier.verify_diff_from_files(old_file, new_file)


# CLI integration
def format_diff_for_pr_comment(diff: SemanticDiff) -> str:
    """Format diff for GitHub PR comment."""
    if not diff.overall_changed:
        return "✅ **No semantic changes detected** - Only textual/formatting changes."
    
    lines = []
    lines.append("## ⚠️ Semantic Changes Detected")
    lines.append("")
    lines.append(f"**Summary**: {diff.summary}")
    lines.append("")
    
    for layer_diff in diff.diffs:
        if layer_diff.changed:
            status = "🔴 FAIL" if not layer_diff.new_passed else "🟡 CHANGED"
            lines.append(f"- **{layer_diff.layer.upper()}**: {status}")
            if layer_diff.old_passed != layer_diff.new_passed:
                lines.append(f"  - Old: {'✅ PASS' if layer_diff.old_passed else '❌ FAIL'}")
                lines.append(f"  - New: {'✅ PASS' if layer_diff.new_passed else '❌ FAIL'}")
    
    return "\n".join(lines)


if __name__ == '__main__':
    print("=== Differential Verification Test ===")
    
    from svl.golden_refs import get_golden_ref
    
    ref = get_golden_ref('psalm119_aleph')
    original = ref.source
    
    # Create mutations
    mutated1 = original.replace('aleph: int = 1', 'aleph: int = 2')
    mutated2 = original + '\n  const extra: int = 999'
    mutated3 = original  # No change
    
    config = TheoremVerificationConfig(
        block_size=512,
        use_cython=True,
        verify_syntax_first=True,
        verify_types_first=True,
        verify_golden_refs=True,
        use_smt=True
    )
    
    print("\n--- Test 1: Constant change ---")
    diff1 = verify_semantic_diff(original, mutated1, config)
    print(DifferentialVerifier(config).format_diff(diff1))
    
    print("\n--- Test 2: Statement addition ---")
    diff2 = verify_semantic_diff(original, mutated2, config)
    print(DifferentialVerifier(config).format_diff(diff2))
    
    print("\n--- Test 3: No change ---")
    diff3 = verify_semantic_diff(original, mutated3, config)
    print(DifferentialVerifier(config).format_diff(diff3))
    
    print("\n✓ Differential Verification test complete!")