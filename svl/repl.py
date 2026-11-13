# svl/repl.py
# Interactive REPL with Live Verification (Spike S11)
# Line-by-line verification, block verification on blank line
# Live feedback: syntax errors, type errors, theorem status

from typing import Optional, List, Dict, Any, Sequence
from dataclasses import dataclass, field
import sys
import readline  # For history/completion

from svl.syntax_layer import verify_syntax, SyntaxVerificationConfig, VerifyResult
from svl.type_layer import verify_type, TypeVerificationConfig, TypeVerifyResult
from svl.theorem_layer import verify_theorem_layer, TheoremVerificationConfig, TheoremVerifyResultWrapper
from svl.golden_refs import get_golden_ref


@dataclass
class ReplState:
    """REPL session state."""
    buffer: List[str] = field(default_factory=list)
    history: List[str] = field(default_factory=list)
    module_name: str = "repl"
    in_block: bool = False
    block_depth: int = 0
    # Top-level declarations that survive between blocks, so a later block can call a
    # function defined in an earlier one.
    definitions: List[str] = field(default_factory=list)


@dataclass
class ReplConfig:
    """REPL configuration."""
    prompt: str = "svl> "
    continuation_prompt: str = "  ... "
    verify_on_line: bool = True
    verify_on_block: bool = True
    show_timing: bool = True
    max_history: int = 1000


def run_wat(wat: str, foreign: Optional[Sequence[bytes]] = None):
    """Assemble, validate, instantiate and run a WAT module's `<module>_main`.

    Returns (return_value, printed_bytes); return_value is None when the module has no
    exported entry point.  Shared by the REPL and the Jupyter kernel so both execute
    through the same host ABI.

    ``foreign`` is a sequence of compiled foreign WASM modules (``.wasm`` bytes).  Any
    `extern "c"` import that is not one of the builtin host stubs must be provided by
    one of them, with a matching signature; otherwise `ForeignModuleError` is raised
    before the program runs.
    """
    import wasmtime

    binary = wasmtime.wat2wasm(wat)
    engine = wasmtime.Engine()
    module = wasmtime.Module(engine, binary)
    store = wasmtime.Store(engine)
    linker = wasmtime.Linker(engine)
    i32 = wasmtime.ValType.i32()
    out = bytearray()
    memory = {}

    def read_mem(ptr, n):
        if "m" not in memory or ptr < 0 or n < 0:
            return b""
        return bytes(memory["m"].read(store, ptr, ptr + n))

    linker.define_func("env", "print", wasmtime.FuncType([i32, i32], []),
                       lambda p, n: out.extend(read_mem(p, n)))
    linker.define_func("env", "print_int", wasmtime.FuncType([i32], []),
                       lambda v: out.extend(str(v).encode()))
    linker.define_func("env", "putc", wasmtime.FuncType([i32], []),
                       lambda c: out.append(c & 0xFF))
    linker.define_func("env", "clear", wasmtime.FuncType([], []), lambda: None)
    linker.define_func("env", "malloc", wasmtime.FuncType([i32], [i32]), lambda n: 1 << 20)
    linker.define_func("env", "iterator_next", wasmtime.FuncType([i32], [i32]), lambda h: 0)
    linker.define_func("env", "await", wasmtime.FuncType([i32], [i32]), lambda x: x)

    from svl.foreign_link import define_foreign, load_foreign_module
    # Always planned, even with no foreign modules: a program that declares an
    # `extern` and is given nothing to satisfy it must say so here, not trap later
    # with wasmtime's generic "unknown import".
    define_foreign(store, linker, module,
                   [load_foreign_module(engine, f) for f in foreign or []])

    inst = linker.instantiate(store, module)
    exports = inst.exports(store)
    names = [e.name for e in module.exports]
    if "memory" in names:
        memory["m"] = exports["memory"]
    entry = next((n for n in names if n.endswith("_main")), None)
    if entry is None:
        return None, bytes(out)
    return exports[entry](store), bytes(out)


class SVLRepl:
    """SVL REPL with live verification."""

    def __init__(self, config: Optional[ReplConfig] = None):
        self.config = config or ReplConfig()
        self.state = ReplState()
        
        # Verification configs
        self.syntax_config = SyntaxVerificationConfig(
            block_size=512, use_cython=True,
            verify_golden_refs=False, run_mutation_tests=False
        )
        self.type_config = TypeVerificationConfig(
            block_size=512, use_cython=True,
            verify_golden_refs=False
        )
        self.theorem_config = TheoremVerificationConfig(
            block_size=512, use_cython=True,
            verify_syntax_first=True, verify_types_first=True,
            verify_golden_refs=False
        )

    def run(self):
        """Main REPL loop."""
        print("SVL REPL - Self-Verifying Language")
        print("Type 'help' for commands, 'exit' to quit")
        print("Blank line executes block, Ctrl+C cancels")
        
        # Setup readline
        self._setup_readline()
        
        while True:
            try:
                # Determine prompt
                prompt = self.config.continuation_prompt if self.state.in_block else self.config.prompt
                
                line = input(prompt)
                
                # Handle empty line: execute the accumulated buffer.  The old
                # condition (`if self.state.in_block`) meant a single top-level
                # statement like `let x = 1` was never executed.
                if not line.strip():
                    if self.state.buffer:
                        self._execute_block()
                    continue
                
                # Handle special commands
                if self._handle_command(line.strip()):
                    continue
                
                # Add to buffer
                self.state.buffer.append(line)
                self.state.history.append(line)
                
                # Track block depth
                self._update_block_depth(line)
                
                # Line-by-line verification
                if self.config.verify_on_line and not self.state.in_block:
                    self._verify_current_line(line)
                
            except KeyboardInterrupt:
                print("\n^C")
                self._reset_buffer()
            except EOFError:
                print("\nGoodbye!")
                break
            except Exception as e:
                print(f"Error: {e}")
                self._reset_buffer()

    def _setup_readline(self):
        """Setup readline for history and completion."""
        try:
            readline.set_history_length(self.config.max_history)
            readline.parse_and_bind("tab: complete")
            readline.set_completer(self._completer)
        except:
            pass  # readline not available

    def _completer(self, text: str, state: int) -> Optional[str]:
        """Tab completion."""
        keywords = [
            'module', 'import', 'export', 'func', 'struct', 'type',
            'const', 'var', 'let', 'if', 'then', 'else', 'while',
            'for', 'in', 'return', 'assert', 'try', 'catch', 'throw',
            'async', 'await', 'match', 'case', 'true', 'false', 'null',
            'int', 'float', 'string', 'bool', 'void', 'never',
            'help', 'exit', 'clear', 'reset', 'verify', 'compile'
        ]
        options = [k for k in keywords if k.startswith(text)]
        if state < len(options):
            return options[state]
        return None

    def _handle_command(self, line: str) -> bool:
        """Handle REPL commands."""
        cmd = line.lower()
        
        if cmd in ('exit', 'quit', 'q'):
            print("Goodbye!")
            sys.exit(0)
        elif cmd in ('help', 'h', '?'):
            self._print_help()
            return True
        elif cmd in ('clear', 'cls'):
            print("\033[2J\033[H", end="")
            return True
        elif cmd in ('reset',):
            self._reset_buffer()
            print("Buffer cleared")
            return True
        elif cmd == 'verify':
            self._verify_full_buffer()
            return True
        elif cmd == 'compile':
            self._compile_buffer()
            return True
        elif cmd == 'history':
            for i, h in enumerate(self.state.history[-20:], 1):
                print(f"  {i}: {h}")
            return True
        elif cmd.startswith('load '):
            filename = cmd[5:].strip()
            self._load_file(filename)
            return True
        elif cmd.startswith('save '):
            filename = cmd[5:].strip()
            self._save_file(filename)
            return True
        
        return False

    def _print_help(self):
        print("""
SVL REPL Commands:
  help, h, ?       - Show this help
  exit, quit, q    - Exit REPL
  clear, cls       - Clear screen
  reset            - Clear current buffer
  verify           - Verify entire buffer (all 3 layers)
  compile          - Compile buffer to WASM
  history          - Show command history
  load <file>      - Load SVL file into buffer
  save <file>      - Save buffer to file

Verification:
  - Line-by-line: after each complete statement
  - Block: on blank line (executes block)
  - Full: 'verify' command runs all 3 layers

SVL Syntax (22 Hebrew tokens with ASCII aliases):
  module, func, struct, type, const, var, let
  if, then, else, while, for, in, return
  assert, try, catch, throw, async, await
  match, case, true, false, null
  int, float, string, bool, void, never
""")

    def _reset_buffer(self):
        self.state.buffer = []
        self.state.in_block = False
        self.state.block_depth = 0

    def _update_block_depth(self, line: str):
        """Track brace depth for block detection."""
        for ch in line:
            if ch == '{':
                self.state.block_depth += 1
                self.state.in_block = True
            elif ch == '}':
                self.state.block_depth = max(0, self.state.block_depth - 1)
                if self.state.block_depth == 0:
                    self.state.in_block = False

    def _is_complete_statement(self, buffer: List[str]) -> bool:
        """Check if buffer forms a complete statement."""
        if not buffer:
            return False
        source = '\n'.join(buffer)
        # Quick check: balanced braces
        open_braces = source.count('{')
        close_braces = source.count('}')
        if open_braces != close_braces:
            return False
        # Check for incomplete assignments (ends with =, ,, or operator)
        stripped = buffer[-1].strip()
        if stripped.endswith(('=', ',', '+', '-', '*', '/', '%', '>', '<', '<=', '>=', '==', '!=', '&&', '||', '->')):
            return False
        # If braces are balanced, statement is complete regardless of control structures
        return True

    def _split_definitions(self, lines: List[str]):
        """Split a block into (top-level declarations, remaining statement lines).

        Multi-line declarations are captured by brace balancing, so a `func ... { ... }`
        typed across several lines is kept whole.
        """
        defs, stmts, i = [], [], 0
        while i < len(lines):
            stripped = lines[i].strip()
            if stripped.startswith(('func ', 'struct ', 'const ', 'var ', 'type ')):
                chunk = [lines[i]]
                depth = lines[i].count('{') - lines[i].count('}')
                i += 1
                while depth > 0 and i < len(lines):
                    chunk.append(lines[i])
                    depth += lines[i].count('{') - lines[i].count('}')
                    i += 1
                defs.append('\n'.join(chunk))
            else:
                stmts.append(lines[i])
                i += 1
        return defs, stmts

    def _wrapped_source(self) -> str:
        """Wrap the buffer in `module repl { <definitions> func main() ... }`.

        The verification layers only accept declarations at top level, so a bare
        `let x = 1` raised "Unexpected token at top level" before it could be evaluated.
        Declarations from earlier blocks are replayed so later blocks can use them.
        """
        block_defs, stmts = self._split_definitions(self.state.buffer)
        all_defs = list(self.state.definitions)
        for definition in block_defs:
            if definition not in all_defs:
                all_defs.append(definition)
        prefix = '\n'.join(all_defs)
        body = '\n'.join(stmts)
        # A block with a `return` needs a result type; a statement-only block must be
        # void, or the backend's fall-through `unreachable` traps on a `let`-only body.
        ret_type = 'int' if 'return' in body else 'void'
        return (f"module {self.state.module_name} {{\n{prefix}\n"
                f"func main() type {ret_type} {{\n{body}\n}}\n}}")

    def _verify_current_line(self, line: str):
        """Verify a single line (if it's a complete statement)."""
        self.state.buffer.append(line)
        if self._is_complete_statement(self.state.buffer):
            self._verify_buffer_incremental()
        self.state.buffer.pop()  # Remove the line we just added for checking

    def _verify_buffer_incremental(self):
        """Incremental verification of current buffer."""
        if not self.state.buffer:
            return
        
        source = self._wrapped_source()
        
        # Syntax check
        syntax_result = verify_syntax(source, self.syntax_config)
        
        if not syntax_result.passed:
            self._print_errors("Syntax", syntax_result.error_message or syntax_result.ast_guard_violations)
            return
        
        # Type check (only if syntax passed)
        type_result = verify_type(source, self.type_config)
        
        if not type_result.passed:
            self._print_errors("Type", type_result.errors)
            return
        
        # Theorem check (only if types passed)
        theorem_result = verify_theorem_layer(source, self.theorem_config)
        
        if not theorem_result.passed:
            self._print_errors("Theorem", theorem_result.errors)
            return
        
        # All passed
        if self.config.show_timing:
            print("  ✓ Verified (syntax, types, theorem)")

    def _verify_full_buffer(self):
        """Full verification of entire buffer (all 3 layers)."""
        if not self.state.buffer:
            print("Buffer empty")
            return
        
        source = self._wrapped_source()
        print("Running full verification...")
        
        import time
        start = time.perf_counter()
        
        syntax_result = verify_syntax(source, self.syntax_config)
        syntax_time = (time.perf_counter() - start) * 1000
        
        start = time.perf_counter()
        type_result = verify_type(source, self.type_config)
        type_time = (time.perf_counter() - start) * 1000
        
        start = time.perf_counter()
        theorem_result = verify_theorem_layer(source, self.theorem_config)
        theorem_time = (time.perf_counter() - start) * 1000
        
        total_time = syntax_time + type_time + theorem_time
        
        print(f"\n=== Verification Results ===")
        print(f"Syntax:  {'✓ PASS' if syntax_result.passed else '✗ FAIL'} ({syntax_time:.1f}ms)")
        if not syntax_result.passed:
            print(f"  Errors: {syntax_result.error_message or syntax_result.ast_guard_violations}")
        
        print(f"Types:   {'✓ PASS' if type_result.passed else '✗ FAIL'} ({type_time:.1f}ms)")
        if not type_result.passed:
            print(f"  Errors: {type_result.errors}")
        
        print(f"Theorem: {'✓ PASS' if theorem_result.passed else '✗ FAIL'} ({theorem_time:.1f}ms)")
        if not theorem_result.passed:
            print(f"  Errors: {theorem_result.errors}")
        
        print(f"Total:   {total_time:.1f}ms")

    def _execute_block(self):
        """Execute the current block: verify, compile, run, print the result.

        Top-level declarations in the block are kept in `state.definitions`, so a later
        block can call a function (or use a const) defined in an earlier one.
        """
        if not self.state.buffer:
            return
        
        source = self._wrapped_source()
        print("Executing block...")
        self._verify_full_buffer()

        block_defs, _ = self._split_definitions(self.state.buffer)
        for definition in block_defs:
            if definition not in self.state.definitions:
                self.state.definitions.append(definition)

        from svl.compiler_wasm import compile_file_to_wasm
        try:
            wat = compile_file_to_wasm(source)
        except Exception as e:
            print(f"Compilation failed: {e}")
            self._reset_buffer()
            return

        try:
            rv, out = run_wat(wat)
            if out:
                sys.stdout.write(out.decode("utf-8", "replace"))
            if rv is not None:
                print(f"[{self.state.module_name}_main() returned {rv}]")
        except Exception as e:
            print(f"Execution failed: {e}")

        # Clear buffer after execution
        self._reset_buffer()

    def _compile_buffer(self):
        """Compile current buffer to WASM."""
        if not self.state.buffer:
            print("Buffer empty")
            return
        
        source = '\n'.join(self.state.buffer)
        if not source.strip().startswith('module'):
            source = f"module {self.state.module_name} {{\n{source}\n}}"
        
        from svl.compiler_wasm import compile_file_to_wasm
        try:
            wasm = compile_file_to_wasm(source)
            print("WASM compilation successful!")
            print(f"Output length: {len(wasm)} chars")
            print(wasm[:500] + ("..." if len(wasm) > 500 else ""))
        except Exception as e:
            print(f"Compilation failed: {e}")

    def _load_file(self, filename: str):
        """Load SVL file into buffer."""
        try:
            with open(filename, 'r') as f:
                content = f.read()
            self.state.buffer = content.split('\n')
            print(f"Loaded {filename} ({len(self.state.buffer)} lines)")
        except Exception as e:
            print(f"Load failed: {e}")

    def _save_file(self, filename: str):
        """Save buffer to file."""
        try:
            with open(filename, 'w') as f:
                f.write('\n'.join(self.state.buffer))
            print(f"Saved to {filename}")
        except Exception as e:
            print(f"Save failed: {e}")

    def _print_errors(self, layer: str, errors: Any):
        if isinstance(errors, list):
            for e in errors:
                print(f"  {layer} Error: {e}")
        else:
            print(f"  {layer} Error: {errors}")


def run_repl():
    """Entry point for REPL."""
    repl = SVLRepl()
    repl.run()


if __name__ == '__main__':
    run_repl()