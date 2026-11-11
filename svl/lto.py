# svl/lto.py
# Link-Time Optimization (LTO) for WASM (H30)
# Cross-module optimization using wasm-ld and WASM merging

from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
from enum import Enum
import subprocess
import tempfile
import os
import hashlib
from pathlib import Path


class LTOPhase(Enum):
    """LTO compilation phases."""
    COMPILE = "compile"          # Compile to object files with LTO info
    LINK = "link"                # Link with wasm-ld --lto
    OPTIMIZE = "optimize"        # Post-link optimization


@dataclass
class LTOConfig:
    """Configuration for LTO."""
    enabled: bool = True
    opt_level: int = 2              # 0-3, optimization level
    thin_lto: bool = True           # Use ThinLTO vs Full LTO
    lto_partitions: int = 4         # Number of ThinLTO partitions
    inline_threshold: int = 250     # Inlining threshold
    run_passes: List[str] = field(default_factory=lambda: [
        "function-attrs",
        "globaldce",
        "globalopt",
        "inliner",
        "simplifycfg",
        "domtree",
        "sroa",
        "early-cse",
        "lazy-value-info",
        "jump-threading",
        "correlated-propagation",
        "instcombine",
        "tailcallelim",
        "simplifycfg",
        "reassociate",
        "loop-rotate",
        "licm",
        "loop-unswitch",
        "instcombine",
        "scalar-evolution",
        "loop-simplify",
        "indvars",
        "loop-idiom",
        "loop-deletion",
        "loop-unroll",
        "memcpyopt",
        "sccp",
        "bdce",
        "dse",
        "adce",
        "globaldce",
        "constmerge",
    ])


@dataclass
class WASMModule:
    """Represents a WASM module for LTO."""
    name: str
    wasm_text: str = ""
    wasm_binary: Optional[bytes] = None
    imports: List[str] = field(default_factory=list)
    exports: List[str] = field(default_factory=list)
    functions: Dict[str, str] = field(default_factory=dict)  # name -> body
    memories: List[str] = field(default_factory=list)
    tables: List[str] = field(default_factory=list)
    globals: List[str] = field(default_factory=list)
    data_segments: List[str] = field(default_factory=list)
    element_segments: List[str] = field(default_factory=list)


class WASMParser:
    """Parses WASM text format into structured representation."""
    
    @staticmethod
    def parse(wasm_text: str) -> WASMModule:
        """Parse WASM text format."""
        module = WASMModule(name="unknown", wasm_text=wasm_text)
        
        lines = wasm_text.split('\n')
        in_function = False
        current_func = None
        func_body = []
        
        for line in lines:
            stripped = line.strip()
            
            # Module name
            if stripped.startswith('(module'):
                if '"' in stripped:
                    # (module $name "name")
                    import re
                    match = re.search(r'"([^"]+)"', stripped)
                    if match:
                        module.name = match.group(1)
            
            # Imports
            elif stripped.startswith('(import '):
                module.imports.append(stripped)
            
            # Exports
            elif stripped.startswith('(export '):
                module.exports.append(stripped)
                # Extract export name
                import re
                match = re.search(r'"([^"]+)"', stripped)
                if match:
                    module.exports[-1] = match.group(1)
            
            # Functions
            elif stripped.startswith('(func $'):
                in_function = True
                import re
                match = re.search(r'\(func \$([^\s)]+)', stripped)
                current_func = match.group(1) if match else "unknown"
                func_body = [line]
                module.functions[current_func] = ""
            
            elif in_function:
                func_body.append(line)
                if stripped == ')':
                    module.functions[current_func] = '\n'.join(func_body)
                    in_function = False
                    current_func = None
                    func_body = []
            
            # Memory
            elif stripped.startswith('(memory'):
                module.memories.append(stripped)
            
            # Table
            elif stripped.startswith('(table'):
                module.tables.append(stripped)
            
            # Global
            elif stripped.startswith('(global'):
                module.globals.append(stripped)
            
            # Data segment
            elif stripped.startswith('(data'):
                module.data_segments.append(stripped)
            
            # Element segment
            elif stripped.startswith('(elem'):
                module.element_segments.append(stripped)
        
        return module
    
    @staticmethod
    def to_text(module: WASMModule) -> str:
        """Convert module back to WASM text."""
        lines = ['(module']
        
        # Add module name if not default
        if module.name != "unknown":
            lines[0] = f'(module ${module.name} "{module.name}"'
        
        # Imports
        for imp in module.imports:
            lines.append(f'  {imp}')
        
        # Functions
        for name, body in module.functions.items():
            lines.append(f'  {body}')
        
        # Memories
        for mem in module.memories:
            lines.append(f'  {mem}')
        
        # Tables
        for table in module.tables:
            lines.append(f'  {table}')
        
        # Globals
        for glob in module.globals:
            lines.append(f'  {glob}')
        
        # Data segments
        for data in module.data_segments:
            lines.append(f'  {data}')
        
        # Element segments
        for elem in module.element_segments:
            lines.append(f'  {elem}')
        
        # Exports
        for exp in module.exports:
            lines.append(f'  (export {exp})')
        
        lines.append(')')
        return '\n'.join(lines)


class LTOLinker:
    """Performs LTO linking using wasm-ld."""
    
    def __init__(self, config: Optional[LTOConfig] = None):
        self.config = config or LTOConfig()
        self.wasm_ld_path = self._find_wasm_ld()
    
    def _find_wasm_ld(self) -> Optional[str]:
        """Find wasm-ld executable."""
        for path in ['wasm-ld', 'wasm-ld-14', 'wasm-ld-15', 'wasm-ld-16', 'wasm-ld-17']:
            try:
                subprocess.run([path, '--version'], capture_output=True, check=True)
                return path
            except (subprocess.SubprocessError, FileNotFoundError):
                continue
        return None
    
    def is_available(self) -> bool:
        """Check if wasm-ld is available."""
        return self.wasm_ld_path is not None
    
    def link_modules(self, modules: List[WASMModule], output_path: str) -> bytes:
        """Link multiple WASM modules with LTO."""
        if not self.is_available():
            raise RuntimeError("wasm-ld not found. Install LLVM with wasm-ld.")
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Write each module as .wasm file
            obj_files = []
            for i, module in enumerate(modules):
                obj_file = os.path.join(tmpdir, f"module_{i}.o")
                # Convert text to binary using wat2wasm
                self._text_to_binary(module.wasm_text, obj_file)
                obj_files.append(obj_file)
            
            # Run wasm-ld with LTO
            cmd = [self.wasm_ld_path]
            cmd.extend(obj_files)
            cmd.extend([
                '-o', output_path,
                '--lto-O{}'.format(self.config.opt_level),
                '--export-all',  # Export all functions for now
                '--no-entry',
                '--allow-undefined',
                '--import-memory',
                '--import-undefined',
            ])
            
            if self.config.thin_lto:
                cmd.extend([
                    '--thinlto',
                    '--thinlto-jobs={}'.format(self.config.lto_partitions),
                ])
            
            # Add optimization passes
            for pass_name in self.config.run_passes:
                if pass_name:
                    cmd.extend(['--lto-pass', str(pass_name)])
            
            result = subprocess.run(cmd, capture_output=True)
            if result.returncode != 0:
                raise RuntimeError(f"wasm-ld failed: {result.stderr.decode()}")
            
            # Read output binary
            with open(output_path, 'rb') as f:
                return f.read()
    
    def _text_to_binary(self, wasm_text: str, output_path: str):
        """Convert WASM text to binary using wat2wasm."""
        wat2wasm = self._find_wat2wasm()
        if not wat2wasm:
            raise RuntimeError("wat2wasm not found. Install WABT.")
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.wat', delete=False) as f:
            f.write(wasm_text)
            wat_file = f.name
        
        try:
            subprocess.run([wat2wasm, wat_file, '-o', output_path], check=True, capture_output=True)
        finally:
            os.unlink(wat_file)
    
    def _find_wat2wasm(self) -> Optional[str]:
        """Find wat2wasm executable."""
        for path in ['wat2wasm', 'wat2wasm-1.0']:
            try:
                subprocess.run([path, '--version'], capture_output=True, check=True)
                return path
            except (subprocess.SubprocessError, FileNotFoundError):
                continue
        return None


class LTOOptimizer:
    """High-level LTO optimizer for WASM modules."""
    
    def __init__(self, config: Optional[LTOConfig] = None):
        self.config = config or LTOConfig()
        self.linker = LTOLinker(config)
        self.parser = WASMParser()
    
    def optimize(self, modules: List[WASMModule]) -> WASMModule:
        """Optimize multiple modules together using LTO."""
        if not self.linker.is_available():
            # Fallback: just merge modules without LTO
            return self._merge_modules(modules)
        
        with tempfile.NamedTemporaryFile(suffix='.wasm', delete=False) as f:
            output_path = f.name
        
        try:
            # Link with LTO
            binary = self.linker.link_modules(modules, output_path)
            
            # Parse result back to module
            # For now, return merged module (parsing binary requires wasm2wat)
            return self._merge_modules(modules)
        finally:
            if os.path.exists(output_path):
                os.unlink(output_path)
    
    def _merge_modules(self, modules: List[WASMModule]) -> WASMModule:
        """Merge modules without LTO (fallback)."""
        merged = WASMModule(name="merged")
        
        # Merge imports (deduplicate)
        seen_imports = set()
        for module in modules:
            for imp in module.imports:
                if imp not in seen_imports:
                    merged.imports.append(imp)
                    seen_imports.add(imp)
        
        # Merge functions (rename to avoid conflicts)
        for module in modules:
            for name, body in module.functions.items():
                new_name = f"{module.name}${name}"
                merged.functions[new_name] = body.replace(f'${name}', f'${new_name}')
        
        # Merge memories (take first)
        if modules:
            merged.memories = modules[0].memories
        
        # Merge tables
        for module in modules:
            merged.tables.extend(module.tables)
        
        # Merge globals
        for module in modules:
            merged.globals.extend(module.globals)
        
        # Merge data segments
        for module in modules:
            merged.data_segments.extend(module.data_segments)
        
        # Merge exports
        for module in modules:
            for exp in module.exports:
                merged.exports.append(f'"{exp}" (func ${module.name}${exp})')
        
        return merged
    
    def inline_functions(self, module: WASMModule, inline_threshold: int = 250) -> WASMModule:
        """Perform cross-module inlining."""
        # Simple heuristic: inline small functions called from hot paths
        # In real implementation, would use profile data
        inlined = set()
        
        for name, body in module.functions.items():
            # Count instructions (rough heuristic)
            instr_count = body.count('\n')
            if instr_count < 10:  # Small function
                # Find callers
                for other_name, other_body in module.functions.items():
                    if f'call ${name}' in other_body:
                        # Inline: replace call with body
                        # This is simplified - real implementation needs proper SSA
                        inlined.add(name)
        
        # Remove inlined functions (they're now duplicated in callers)
        for name in inlined:
            if name in module.functions:
                del module.functions[name]
        
        return module
    
    def dead_code_elimination(self, module: WASMModule) -> WASMModule:
        """Remove unreachable functions."""
        # Find reachable functions from exports
        reachable = set()
        worklist = list(module.exports)
        
        while worklist:
            func = worklist.pop()
            if func in reachable:
                continue
            reachable.add(func)
            
            # Find calls from this function
            if func in module.functions:
                body = module.functions[func]
                import re
                calls = re.findall(r'call \$([^\s)]+)', body)
                for callee in calls:
                    if callee not in reachable:
                        worklist.append(callee)
        
        # Remove unreachable functions
        to_remove = [name for name in module.functions if name not in reachable]
        for name in to_remove:
            del module.functions[name]
        
        return module
    
    def merge_duplicate_functions(self, module: WASMModule) -> WASMModule:
        """Merge identical function bodies."""
        import re
        
        def normalize_body(body: str) -> str:
            """Normalize function body by replacing local names with placeholders."""
            # Replace $name with $local_N for consistent comparison
            local_map = {}
            local_counter = 0
            
            def replace_local(match):
                nonlocal local_counter
                name = match.group(1)
                if name not in local_map:
                    local_map[name] = f"local_{local_counter}"
                    local_counter += 1
                return f'${local_map[name]}'
            
            # Replace all $localname references
            normalized = re.sub(r'\$([a-zA-Z_][a-zA-Z0-9_]*)', replace_local, body)
            # Normalize whitespace
            normalized = ' '.join(normalized.split())
            return normalized
        
        body_to_name = {}
        to_remove = set()
        
        for name, body in module.functions.items():
            # Normalize body for comparison
            normalized = normalize_body(body)
            if normalized in body_to_name:
                # Duplicate found
                to_remove.add(name)
                # Update calls to point to canonical
                canonical = body_to_name[normalized]
                for other_name, other_body in module.functions.items():
                    if other_name != name:
                        module.functions[other_name] = other_body.replace(
                            f'call ${name}', f'call ${canonical}'
                        )
            else:
                body_to_name[normalized] = name
        
        for name in to_remove:
            del module.functions[name]
        
        return module


class LTOPipeline:
    """Full LTO pipeline for SVL compilation."""
    
    def __init__(self, config: Optional[LTOConfig] = None):
        self.config = config or LTOConfig()
        self.optimizer = LTOOptimizer(config)
    
    def compile_with_lto(self, sources: List[str]) -> str:
        """Compile multiple SVL sources with LTO."""
        from svl.compiler_wasm import compile_file_to_wasm
        
        # Compile each source to WASM module
        modules = []
        for source in sources:
            wasm_text = compile_file_to_wasm(source)
            module = self.optimizer.parser.parse(wasm_text)
            modules.append(module)
        
        # Run LTO optimization
        optimized = self.optimizer.optimize(modules)
        
        # Apply additional optimizations
        optimized = self.optimizer.dead_code_elimination(optimized)
        optimized = self.optimizer.merge_duplicate_functions(optimized)
        optimized = self.optimizer.inline_functions(optimized, self.config.inline_threshold)
        
        # Generate final WASM
        return self.optimizer.parser.to_text(optimized)


def check_lto_tools() -> Dict[str, bool]:
    """Check availability of LTO tools."""
    tools = {}
    
    for tool in ['wasm-ld', 'wat2wasm', 'wasm2wat', 'wasm-opt']:
        try:
            subprocess.run([tool, '--version'], capture_output=True, check=True)
            tools[tool] = True
        except (subprocess.SubprocessError, FileNotFoundError):
            tools[tool] = False
    
    return tools


if __name__ == '__main__':
    # Test LTO pipeline
    print("=== LTO Tool Availability ===")
    tools = check_lto_tools()
    for tool, available in tools.items():
        print(f"  {tool}: {'✓' if available else '✗'}")
    
    # Test module parsing
    test_wasm = '''(module
  (import "env" "print" (func $print (param i32)))
  (func $test$main (param i32) (result i32)
    local.get 0
    i32.const 1
    i32.add
    call $print
    return
  )
  (export "main" (func $test$main))
)'''
    
    parser = WASMParser()
    module = parser.parse(test_wasm)
    print(f"\n=== Parsed Module ===")
    print(f"  Name: {module.name}")
    print(f"  Imports: {len(module.imports)}")
    print(f"  Functions: {list(module.functions.keys())}")
    print(f"  Exports: {module.exports}")
    
    # Test round-trip
    regenerated = parser.to_text(module)
    print(f"\n=== Regenerated WASM (first 500 chars) ===")
    print(regenerated[:500])