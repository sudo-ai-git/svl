# svl/pgo.py
# Profile-Guided Optimization (PGO) for WASM Compiler (H29)
# Infrastructure for collecting and using profile data to guide optimization

from typing import Dict, List, Optional, Any, Callable, Tuple
from dataclasses import dataclass, field
from enum import Enum
import json
import os
import hashlib
from pathlib import Path


class PGOPhase(Enum):
    INSTRUMENT = "instrument"
    COLLECT = "collect"
    OPTIMIZE = "optimize"


@dataclass
class ProfileData:
    """Profile data collected from instrumented execution."""
    function_counts: Dict[str, int] = field(default_factory=dict)
    block_counts: Dict[str, int] = field(default_factory=dict)
    edge_counts: Dict[str, int] = field(default_factory=dict)  # "func:from->to" -> count
    value_profiles: Dict[str, Dict[str, int]] = field(default_factory=dict)  # type profiles for polymorphic sites
    call_counts: Dict[str, int] = field(default_factory=dict)  # "caller->callee" -> count
    
    def merge(self, other: 'ProfileData'):
        """Merge another profile into this one."""
        for k, v in other.function_counts.items():
            self.function_counts[k] = self.function_counts.get(k, 0) + v
        for k, v in other.block_counts.items():
            self.block_counts[k] = self.block_counts.get(k, 0) + v
        for k, v in other.edge_counts.items():
            self.edge_counts[k] = self.edge_counts.get(k, 0) + v
        for k, v in other.value_profiles.items():
            if k not in self.value_profiles:
                self.value_profiles[k] = {}
            for k2, v2 in v.items():
                self.value_profiles[k][k2] = self.value_profiles[k].get(k2, 0) + v2
        for k, v in other.call_counts.items():
            self.call_counts[k] = self.call_counts.get(k, 0) + v


@dataclass
class PGOSummary:
    """Summary of profile data for optimization decisions."""
    hot_functions: List[str]  # Functions with high execution count
    hot_blocks: List[str]     # Basic blocks with high execution count
    hot_edges: List[str]      # Control flow edges with high frequency
    inlining_candidates: List[Tuple[str, str]]  # (caller, callee) pairs for inlining
    devirtualization_sites: List[str]  # Call sites with monomorphic targets
    loop_trip_counts: Dict[str, int]   # Estimated loop iterations
    type_feedback: Dict[str, str]      # Observed types at polymorphic sites


class PGOInstrumenter:
    """Instruments WASM code for profile collection."""
    
    def __init__(self, profile_dir: str = "./pgo_profile"):
        self.profile_dir = Path(profile_dir)
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self.profile_file = self.profile_dir / "profile.json"
        self.instrumented_functions: Dict[str, str] = {}  # func_name -> original_body_hash
    
    def instrument_module(self, wasm_text: str) -> str:
        """Instrument WASM module with profiling counters."""
        lines = wasm_text.split('\n')
        instrumented = []
        in_function = False
        current_func = None
        func_body_lines = []
        
        for line in lines:
            stripped = line.strip()
            
            if stripped.startswith('(func $'):
                # Function start
                in_function = True
                current_func = self._extract_func_name(stripped)
                func_body_lines = []
                instrumented.append(line)
                
            elif in_function and stripped == ')':
                # Function end - add instrumentation
                if current_func:
                    instrumented.extend(self._add_instrumentation(current_func, func_body_lines))
                instrumented.append(line)
                in_function = False
                current_func = None
                func_body_lines = []
                
            elif in_function:
                func_body_lines.append(line)
                instrumented.append(line)
            else:
                instrumented.append(line)
        
        # Add profile runtime imports
        instrumented = self._add_runtime_imports(instrumented)
        
        return '\n'.join(instrumented)
    
    def _extract_func_name(self, line: str) -> str:
        """Extract function name from (func $name ...) line."""
        import re
        match = re.search(r'\(func \$([^\s)]+)', line)
        return match.group(1) if match else "unknown"
    
    def _add_runtime_imports(self, lines: List[str]) -> List[str]:
        """Add imports for profiling runtime."""
        # Find the imports section
        new_lines = []
        imports_added = False
        
        for line in lines:
            new_lines.append(line)
            if not imports_added and line.strip() == '(import "env" "malloc"':
                # Add profiling imports after malloc
                new_lines.append('  (import "pgo" "profile_count" (func $pgo_profile_count (param i32 i32)))')
                new_lines.append('  (import "pgo" "profile_edge" (func $pgo_profile_edge (param i32 i32 i32)))')
                new_lines.append('  (import "pgo" "profile_value" (func $pgo_profile_value (param i32 i32 i32)))')
                new_lines.append('  (import "pgo" "profile_call" (func $pgo_profile_call (param i32 i32)))')
                imports_added = True
        
        return new_lines
    
    def _add_instrumentation(self, func_name: str, body_lines: List[str]) -> List[str]:
        """Add profiling instrumentation to function body."""
        if not body_lines:
            return []
        
        instrumented = []
        block_id = 0
        
        # Function entry counter
        func_id = self._get_func_id(func_name)
        instrumented.append(f'  ;; PGO: function entry')
        instrumented.append(f'  i32.const {func_id}')
        instrumented.append(f'  i32.const 1')
        instrumented.append(f'  call $pgo_profile_count')
        
        for i, line in enumerate(body_lines):
            instrumented.append(line)
            
            # Instrument block entries (lines with 'block' or 'loop' or 'if')
            stripped = line.strip()
            if stripped.startswith('block ') or stripped.startswith('loop ') or stripped.startswith('if '):
                block_id += 1
                edge_id = self._get_edge_id(func_name, f"entry->{block_id}")
                instrumented.append(f'  ;; PGO: block entry {block_id}')
                instrumented.append(f'  i32.const {func_id}')
                instrumented.append(f'  i32.const {block_id}')
                instrumented.append(f'  i32.const 1')
                instrumented.append(f'  call $pgo_profile_edge')
        
        return instrumented
    
    def _get_func_id(self, func_name: str) -> int:
        """Get stable ID for function."""
        return int(hashlib.md5(func_name.encode()).hexdigest()[:8], 16) % 1000000
    
    def _get_edge_id(self, func_name: str, edge: str) -> int:
        """Get stable ID for edge."""
        key = f"{func_name}:{edge}"
        return int(hashlib.md5(key.encode()).hexdigest()[:8], 16) % 1000000


class PGOProfiler:
    """Runtime profiler that collects profile data."""
    
    def __init__(self, profile_dir: str = "./pgo_profile"):
        self.profile_dir = Path(profile_dir)
        self.profile_file = self.profile_dir / "profile.json"
        self.data = ProfileData()
    
    def record_count(self, func_id: int, count: int = 1):
        """Record function/block execution count."""
        pass  # Implemented in host runtime
    
    def record_edge(self, func_id: int, from_block: int, to_block: int, count: int = 1):
        """Record control flow edge."""
        pass
    
    def record_value(self, site_id: int, type_id: int, count: int = 1):
        """Record type feedback at polymorphic site."""
        pass
    
    def record_call(self, caller_id: int, callee_id: int, count: int = 1):
        """Record function call."""
        pass
    
    def save(self):
        """Save profile data to disk."""
        data = {
            'function_counts': self.data.function_counts,
            'block_counts': self.data.block_counts,
            'edge_counts': self.data.edge_counts,
            'value_profiles': self.data.value_profiles,
            'call_counts': self.data.call_counts,
        }
        with open(self.profile_file, 'w') as f:
            json.dump(data, f)
    
    def load(self) -> ProfileData:
        """Load profile data from disk."""
        if self.profile_file.exists():
            with open(self.profile_file, 'r') as f:
                data = json.load(f)
            profile = ProfileData()
            profile.function_counts = data.get('function_counts', {})
            profile.block_counts = data.get('block_counts', {})
            profile.edge_counts = data.get('edge_counts', {})
            profile.value_profiles = data.get('value_profiles', {})
            profile.call_counts = data.get('call_counts', {})
            return profile
        return ProfileData()


class PGOOptimizer:
    """Uses profile data to guide optimizations."""
    
    def __init__(self, profile: ProfileData):
        self.profile = profile
        self.summary = self._analyze_profile()
    
    def _analyze_profile(self) -> PGOSummary:
        """Analyze profile data to generate optimization summary."""
        # Hot functions: top 20% by execution count
        func_counts = self.profile.function_counts
        if func_counts:
            sorted_funcs = sorted(func_counts.items(), key=lambda x: x[1], reverse=True)
            threshold = sorted_funcs[len(sorted_funcs) // 5][1] if len(sorted_funcs) >= 5 else 0
            hot_functions = [f for f, c in sorted_funcs if c >= threshold]
        else:
            hot_functions = []
        
        # Hot blocks
        block_counts = self.profile.block_counts
        if block_counts:
            sorted_blocks = sorted(block_counts.items(), key=lambda x: x[1], reverse=True)
            threshold = sorted_blocks[len(sorted_blocks) // 5][1] if len(sorted_blocks) >= 5 else 0
            hot_blocks = [b for b, c in sorted_blocks if c >= threshold]
        else:
            hot_blocks = []
        
        # Hot edges
        edge_counts = self.profile.edge_counts
        if edge_counts:
            sorted_edges = sorted(edge_counts.items(), key=lambda x: x[1], reverse=True)
            threshold = sorted_edges[len(sorted_edges) // 5][1] if len(sorted_edges) >= 5 else 0
            hot_edges = [e for e, c in sorted_edges if c >= threshold]
        else:
            hot_edges = []
        
        # Inlining candidates: hot call sites
        inlining_candidates = []
        for call_key, count in self.profile.call_counts.items():
            if count > 1000:  # Threshold for inlining consideration
                parts = call_key.split('->')
                if len(parts) == 2:
                    inlining_candidates.append((parts[0], parts[1]))
        
        # Devirtualization sites: monomorphic call sites
        devirtualization_sites = []
        for site, types in self.profile.value_profiles.items():
            if len(types) == 1:
                # Monomorphic - good for devirtualization
                devirtualization_sites.append(site)
        
        # Loop trip counts (estimated from back-edge frequencies)
        loop_trip_counts = {}
        for edge, count in self.profile.edge_counts.items():
            if 'backedge' in edge or 'loop' in edge:
                func_name = edge.split(':')[0]
                loop_trip_counts[func_name] = count
        
        # Type feedback
        type_feedback = {}
        for site, types in self.profile.value_profiles.items():
            if types:
                most_common = max(types.items(), key=lambda x: x[1])[0]
                type_feedback[site] = most_common
        
        return PGOSummary(
            hot_functions=hot_functions,
            hot_blocks=hot_blocks,
            hot_edges=hot_edges,
            inlining_candidates=inlining_candidates,
            devirtualization_sites=devirtualization_sites,
            loop_trip_counts=loop_trip_counts,
            type_feedback=type_feedback,
        )
    
    def should_inline(self, caller: str, callee: str) -> bool:
        """Decide if a call should be inlined based on profile."""
        return (caller, callee) in self.summary.inlining_candidates
    
    def should_devirtualize(self, call_site: str) -> bool:
        """Decide if a call site should be devirtualized."""
        return call_site in self.summary.devirtualization_sites
    
    def get_hot_functions(self) -> List[str]:
        """Get list of hot functions."""
        return self.summary.hot_functions
    
    def get_loop_trip_count(self, func_name: str) -> Optional[int]:
        """Get estimated loop trip count for a function."""
        return self.summary.loop_trip_counts.get(func_name)
    
    def get_type_feedback(self, site: str) -> Optional[str]:
        """Get observed type at polymorphic site."""
        return self.summary.type_feedback.get(site)


class PGOPipeline:
    """Full PGO pipeline: instrument -> run -> optimize."""
    
    def __init__(self, profile_dir: str = "./pgo_profile"):
        self.profile_dir = profile_dir
        self.instrumenter = PGOInstrumenter(profile_dir)
        self.profiler = PGOProfiler(profile_dir)
    
    def instrument(self, wasm_text: str) -> str:
        """Phase 1: Instrument WASM for profiling."""
        return self.instrumenter.instrument_module(wasm_text)
    
    def collect_profile(self, runs: int = 1) -> ProfileData:
        """Phase 2: Run instrumented code and collect profiles."""
        # In real implementation, would run the WASM and collect data
        # For now, return empty profile
        return ProfileData()
    
    def optimize(self, wasm_text: str, profile: ProfileData) -> str:
        """Phase 3: Recompile with profile-guided optimizations."""
        optimizer = PGOOptimizer(profile)
        # Apply optimizations based on profile
        # This would modify the WASM text
        return wasm_text
    
    def run_full_pgo(self, wasm_text: str, profile_runs: int = 10) -> str:
        """Run full PGO pipeline."""
        # Phase 1: Instrument
        instrumented = self.instrument(wasm_text)
        
        # Phase 2: Collect (would run instrumented code)
        profile = self.collect_profile(profile_runs)
        
        # Phase 3: Optimize
        optimized = self.optimize(wasm_text, profile)
        
        return optimized


def create_pgo_runtime() -> str:
    """Create the host-side PGO runtime (JavaScript/Python)."""
    return '''
// PGO Runtime for WASM (JavaScript version for browser/Node.js)
class PGORuntime {
    constructor() {
        this.functionCounts = new Map();
        this.blockCounts = new Map();
        this.edgeCounts = new Map();
        this.valueProfiles = new Map();
        this.callCounts = new Map();
    }
    
    profile_count(funcId, count) {
        const key = `func:${funcId}`;
        this.functionCounts.set(key, (this.functionCounts.get(key) || 0) + count);
    }
    
    profile_edge(funcId, fromBlock, toBlock) {
        const key = `edge:${funcId}:${fromBlock}->${toBlock}`;
        this.edgeCounts.set(key, (this.edgeCounts.get(key) || 0) + 1);
    }
    
    profile_value(siteId, typeId) {
        const key = `value:${siteId}`;
        if (!this.valueProfiles.has(key)) {
            this.valueProfiles.set(key, new Map());
        }
        const types = this.valueProfiles.get(key);
        types.set(typeId, (types.get(typeId) || 0) + 1);
    }
    
    profile_call(callerId, calleeId) {
        const key = `call:${callerId}->${calleeId}`;
        this.callCounts.set(key, (this.callCounts.get(key) || 0) + 1);
    }
    
    saveProfile() {
        return {
            functionCounts: Object.fromEntries(this.functionCounts),
            blockCounts: Object.fromEntries(this.blockCounts),
            edgeCounts: Object.fromEntries(this.edgeCounts),
            valueProfiles: Object.fromEntries(
                Array.from(this.valueProfiles.entries()).map(([k, v]) => [k, Object.fromEntries(v)])
            ),
            callCounts: Object.fromEntries(this.callCounts),
        };
    }
}

const pgoRuntime = new PGORuntime();
export const pgo_profile_count = (funcId, count) => pgoRuntime.profile_count(funcId, count);
export const pgo_profile_edge = (funcId, fromBlock, toBlock) => pgoRuntime.profile_edge(funcId, fromBlock, toBlock);
export const pgo_profile_value = (siteId, typeId) => pgoRuntime.profile_value(siteId, typeId);
export const pgo_profile_call = (callerId, calleeId) => pgoRuntime.profile_call(callerId, calleeId);
'''


if __name__ == '__main__':
    # Test PGO pipeline
    test_wasm = '''(module
  (func $test$main (param i32) (result i32)
    local.get 0
    i32.const 1
    i32.add
    return
  )
)'''
    
    pipeline = PGOPipeline("./test_pgo")
    instrumented = pipeline.instrument(test_wasm)
    print("=== Instrumented WASM ===")
    print(instrumented[:2000])
    print("...")
    
    print("\n=== PGO Runtime (JS) ===")
    print(create_pgo_runtime()[:1000])
    print("...")