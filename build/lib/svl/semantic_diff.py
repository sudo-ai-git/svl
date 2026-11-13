# svl/semantic_diff.py
# Semantic Diff for SVL
# Structural diff based on AST, types, and verification artifacts

from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
from enum import Enum
from svl.parser_rd import parse, ASTNode, NodeType, Program, Module, FuncDecl
from svl.lexer import tokenize
from svl.theorem_layer import verify_theorem_layer, TheoremVerificationConfig
from svl.differential import verify_semantic_diff, SemanticDiff, DifferentialVerifier


class ASTDiffKind(Enum):
    """Kind of AST difference."""
    NODE_ADDED = "node_added"
    NODE_REMOVED = "node_removed"
    NODE_MODIFIED = "node_modified"
    NODE_MOVED = "node_moved"


@dataclass
class ASTDiff:
    """Single AST difference."""
    kind: ASTDiffKind
    node_type: str
    path: List[str]  # Path to node in AST
    old_value: Optional[Any] = None
    new_value: Optional[Any] = None
    line: Optional[int] = None


@dataclass
class StructuredSemanticDiff:
    """Complete structured semantic diff."""
    textual_diff: str  # Unified diff of source
    ast_diffs: List[ASTDiff] = field(default_factory=list)
    verification_diff: Optional[SemanticDiff] = None
    type_signature_changes: List[Dict[str, Any]] = field(default_factory=list)
    exported_symbols: Dict[str, List[str]] = field(default_factory=dict)  # added, removed, modified


class SemanticDiffEngine:
    """Engine for computing structured semantic diffs."""
    
    def __init__(self, config: Optional[TheoremVerificationConfig] = None):
        self.config = config or TheoremVerificationConfig()
        self.differential_verifier = DifferentialVerifier(config)
        
    def compute_ast_diff(self, old_ast: ASTNode, new_ast: ASTNode) -> List[ASTDiff]:
        """Compute structural diff between two ASTs."""
        diffs = []
        
        def get_node_id(node: ASTNode) -> str:
            """Generate stable ID for a node."""
            return f"{node.type.value}:{getattr(node, 'name', 'anon')}:{node.line}:{node.column}"
        
        def collect_nodes(ast: ASTNode, path: List[str] = None) -> Dict[str, ASTNode]:
            """Collect all nodes with their paths."""
            if path is None:
                path = []
            nodes = {}
            node_id = get_node_id(ast)
            nodes[node_id] = ast
            
            if hasattr(ast, '__dataclass_fields__'):
                for field_name in ast.__dataclass_fields__:
                    value = getattr(ast, field_name)
                    if isinstance(value, ASTNode):
                        child_nodes = collect_nodes(value, path + [field_name])
                        nodes.update(child_nodes)
                    elif isinstance(value, list):
                        for i, item in enumerate(value):
                            if isinstance(item, ASTNode):
                                child_nodes = collect_nodes(item, path + [f"{field_name}[{i}]"])
                                nodes.update(child_nodes)
            return nodes
        
        old_nodes = collect_nodes(old_ast)
        new_nodes = collect_nodes(new_ast)
        
        old_ids = set(old_nodes.keys())
        new_ids = set(new_nodes.keys())
        
        # Removed nodes
        for node_id in old_ids - new_ids:
            node = old_nodes[node_id]
            diffs.append(ASTDiff(
                kind=ASTDiffKind.NODE_REMOVED,
                node_type=node.type.value,
                path=node_id.split(':'),
                old_value=str(node),
                line=node.line
            ))
        
        # Added nodes
        for node_id in new_ids - old_ids:
            node = new_nodes[node_id]
            diffs.append(ASTDiff(
                kind=ASTDiffKind.NODE_ADDED,
                node_type=node.type.value,
                path=node_id.split(':'),
                new_value=str(node),
                line=node.line
            ))
        
        # Modified nodes (same ID, different content)
        for node_id in old_ids & new_ids:
            old_node = old_nodes[node_id]
            new_node = new_nodes[node_id]
            if str(old_node) != str(new_node):
                diffs.append(ASTDiff(
                    kind=ASTDiffKind.NODE_MODIFIED,
                    node_type=old_node.type.value,
                    path=node_id.split(':'),
                    old_value=str(old_node),
                    new_value=str(new_node),
                    line=old_node.line
                ))
        
        return diffs
    
    def extract_type_signatures(self, source: str) -> Dict[str, Any]:
        """Extract type signatures from source for comparison."""
        signatures = {}
        
        try:
            tokens = tokenize(source)
            ast = parse(tokens)
            
            def visit(node: ASTNode):
                if isinstance(node, FuncDecl):
                    param_types = []
                    for p in node.params:
                        if p.type_ann:
                            param_types.append(str(p.type_ann))
                    return_type = str(node.return_type) if node.return_type else "void"
                    signatures[node.name] = {
                        'params': param_types,
                        'return': return_type,
                        'line': node.line
                    }
                elif hasattr(node, '__dataclass_fields__'):
                    for f in node.__dataclass_fields__:
                        value = getattr(node, f)
                        if isinstance(value, ASTNode):
                            visit(value)
                        elif isinstance(value, list):
                            for item in value:
                                if isinstance(item, ASTNode):
                                    visit(item)
        except Exception:
            pass
            
        return signatures
    
    def compare_type_signatures(self, old_sigs: Dict, new_sigs: Dict) -> List[Dict[str, Any]]:
        """Compare type signatures between versions."""
        changes = []
        
        old_names = set(old_sigs.keys())
        new_names = set(new_sigs.keys())
        
        # Removed functions
        for name in old_names - new_names:
            changes.append({
                'kind': 'function_removed',
                'name': name,
                'old_signature': old_sigs[name]
            })
        
        # Added functions
        for name in new_names - old_names:
            changes.append({
                'kind': 'function_added',
                'name': name,
                'new_signature': new_sigs[name]
            })
        
        # Modified functions
        for name in old_names & new_names:
            old_sig = old_sigs[name]
            new_sig = new_sigs[name]
            if old_sig != new_sig:
                changes.append({
                    'kind': 'function_modified',
                    'name': name,
                    'old_signature': old_sig,
                    'new_signature': new_sig
                })
        
        return changes
    
    def compute_full_diff(self, old_source: str, new_source: str) -> StructuredSemanticDiff:
        """Compute complete structured semantic diff."""
        # Textual diff
        import difflib
        textual = "\n".join(difflib.unified_diff(
            old_source.splitlines(keepends=True),
            new_source.splitlines(keepends=True),
            fromfile='old', tofile='new'
        ))
        
        # AST diff
        old_tokens = tokenize(old_source)
        old_ast = parse(old_tokens)
        new_tokens = tokenize(new_source)
        new_ast = parse(new_tokens)
        
        ast_diffs = self.compute_ast_diff(old_ast, new_ast)
        
        # Type signature diff
        old_sigs = self.extract_type_signatures(old_source)
        new_sigs = self.extract_type_signatures(new_source)
        type_changes = self.compare_type_signatures(old_sigs, new_sigs)
        
        # Verification diff
        verification_diff = self.differential_verifier.verify_diff(old_source, new_source)
        
        # Exported symbols (functions, structs, etc.)
        exported = self._extract_exports(old_source, new_source)
        
        return StructuredSemanticDiff(
            textual_diff=textual,
            ast_diffs=ast_diffs,
            verification_diff=verification_diff,
            type_signature_changes=type_changes,
            exported_symbols=exported
        )
    
    def _extract_exports(self, old_source: str, new_source: str) -> Dict[str, List[str]]:
        """Extract exported symbols from both versions."""
        def get_exports(source: str) -> Set[str]:
            exports = set()
            try:
                tokens = tokenize(source)
                ast = parse(tokens)
                
                def visit(node: ASTNode):
                    if isinstance(node, (FuncDecl,)):
                        exports.add(node.name)
                    elif hasattr(node, '__dataclass_fields__'):
                        for f in node.__dataclass_fields__:
                            value = getattr(node, f)
                            if isinstance(value, ASTNode):
                                visit(value)
                            elif isinstance(value, list):
                                for item in value:
                                    if isinstance(item, ASTNode):
                                        visit(item)
            except Exception:
                pass
            return exports
        
        old_exports = get_exports(old_source)
        new_exports = get_exports(new_source)
        
        return {
            'added': list(new_exports - old_exports),
            'removed': list(old_exports - new_exports),
            'unchanged': list(old_exports & new_exports)
        }
    
    def format_structured_diff(self, diff: StructuredSemanticDiff, max_ast_diffs: int = 20) -> str:
        """Format structured diff for human output."""
        lines = []
        lines.append("=" * 70)
        lines.append("STRUCTURED SEMANTIC DIFF")
        lines.append("=" * 70)
        
        # Summary
        if diff.verification_diff:
            lines.append(f"Verification: {'CHANGED' if diff.verification_diff.overall_changed else 'UNCHANGED'}")
            lines.append(f"  {diff.verification_diff.summary}")
        
        lines.append(f"AST Diffs: {len(diff.ast_diffs)} total")
        lines.append(f"Type Signature Changes: {len(diff.type_signature_changes)}")
        
        if diff.exported_symbols:
            exp = diff.exported_symbols
            lines.append(f"Exports - Added: {len(exp['added'])}, Removed: {len(exp['removed'])}")
        
        lines.append("")
        
        # AST diffs (limited)
        if diff.ast_diffs:
            lines.append("AST DIFFS (first {}):".format(min(max_ast_diffs, len(diff.ast_diffs))))
            for ad in diff.ast_diffs[:max_ast_diffs]:
                kind_symbol = {'node_added': '+', 'node_removed': '-', 'node_modified': '~', 'node_moved': '>'}.get(ad.kind.value, '?')
                lines.append(f"  {kind_symbol} {ad.kind.value}: {ad.node_type} at line {ad.line}")
                if ad.old_value and ad.kind != ASTDiffKind.NODE_ADDED:
                    lines.append(f"    - {ad.old_value[:80]}")
                if ad.new_value and ad.kind != ASTDiffKind.NODE_REMOVED:
                    lines.append(f"    + {ad.new_value[:80]}")
            if len(diff.ast_diffs) > max_ast_diffs:
                lines.append(f"  ... and {len(diff.ast_diffs) - max_ast_diffs} more")
            lines.append("")
        
        # Type signature changes
        if diff.type_signature_changes:
            lines.append("TYPE SIGNATURE CHANGES:")
            for tc in diff.type_signature_changes:
                kind = tc['kind']
                name = tc['name']
                if kind == 'function_added':
                    lines.append(f"  + func {name}{tc['new_signature']}")
                elif kind == 'function_removed':
                    lines.append(f"  - func {name}{tc['old_signature']}")
                elif kind == 'function_modified':
                    lines.append(f"  ~ func {name}: {tc['old_signature']} -> {tc['new_signature']}")
            lines.append("")
        
        return "\n".join(lines)


def compute_semantic_diff(old_source: str, new_source: str,
                          config: Optional[TheoremVerificationConfig] = None) -> StructuredSemanticDiff:
    """Convenience function to compute structured semantic diff."""
    engine = SemanticDiffEngine(config)
    return engine.compute_full_diff(old_source, new_source)


if __name__ == '__main__':
    print("=== Semantic Diff Test ===")
    
    from svl.golden_refs import get_golden_ref
    
    ref = get_golden_ref('psalm119_aleph')
    original = ref.source
    
    # Test cases
    mutated1 = original.replace('aleph: int = 1', 'aleph: int = 2')
    mutated2 = original + '\n  const extra: int = 999'
    
    config = TheoremVerificationConfig(
        block_size=512,
        use_cython=True,
        verify_syntax_first=True,
        verify_types_first=True,
        verify_golden_refs=True,
        use_smt=True
    )
    
    print("\n--- Test 1: Constant change ---")
    diff1 = compute_semantic_diff(original, mutated1, config)
    engine = SemanticDiffEngine(config)
    print(engine.format_structured_diff(diff1))
    
    print("\n--- Test 2: Statement addition ---")
    diff2 = compute_semantic_diff(original, mutated2, config)
    print(engine.format_structured_diff(diff2))
    
    print("\n✓ Semantic Diff test complete!")