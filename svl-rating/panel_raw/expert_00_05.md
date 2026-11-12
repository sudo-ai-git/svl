# Expert report — language semantics & compiler correctness

## lexical-scoping  (addresses ['F1'], effort M, risk Medium — touches every name-resolution path; the 61 tests and bit-identical determinism must be re-verified.)

**Problem.** The backend keeps one flat local per name: `_compile_let_stmt` (compiler_wasm.py:500) appends `(stmt.name, ...)` and emits `local.set $name`, while `_compile_ident` (:1190) and `_compile_assign` (:779) resolve through the flat `_known_locals` set built by `_collect_local_names` (:428), so an inner `let x` overwrites the outer slot (P01 WAT: one `(local $x i32)`, two `local.set $x`).

**Proposal.** Add a per-function scope stack `List[Dict[source_name, (wasm_name, struct_name)]]` pushed/popped in `_compile_block` (:409); mangle each binding with a per-function counter in `_compile_let_stmt`, resolve innermost-first in `_compile_ident`/`_compile_assign`, bind params, `for`/`range` loop vars and `catch_var` in the same map, and key `_local_struct_types` (:196) by the mangled name. Delete `_collect_local_names`/`_known_locals`. In type_inference.py make `_check_if_stmt` (:815), `_check_while_stmt` (:834) and `_check_for_stmt` (:845) save/restore `self.env` and bind the loop var in a child env so the checker's scopes agree with the backend.

**Expected.** P01 `let x = 1; if 1==1 then { let x = 99 } else {}; return x` returns 1; the WAT has two locals (`$x`, `$x__v1`) and the trailing `local.get $x` reads the outer one.

**Spike.** Given the current single `$x` local, when `_compile_let_stmt` assigns a per-binding suffix and `_compile_ident` resolves innermost-first, then compiling and running P01 must yield 1, not 99.

## array-for-in  (addresses ['F2'], effort S, risk Low — best-effort type detection means an unannotated array-handle parameter still gets a loud compile error, not a silent 0; pair with lexical-scoping for correct loop-variable shadowing.)

**Problem.** `_compile_for_stmt` (compiler_wasm.py:582) routes every non-range iterable through the host `$iterator_next` import; the host stub (tests/conftest.py:63, probes.py:61) returns 0, so the loop exits immediately and P02 returns 0.

**Proposal.** Add `_is_array_iterable(expr)` (ArrayLit, `zeros(n)`, or an inferred type of kind array/tuple/generic 'List' via `_inferred_expr_type`) and `_compile_array_for_stmt`, which reuses the existing `[len, e0..]` layout: `len = i32.load(base)`, scan `idx` from 0 while `idx < len`, bind `var = i32.load(base + 4 + idx*4)`. For a non-array iterable raise SyntaxError instead of emitting `call $iterator_next`.

**Expected.** P02 `let a=[1,2,3]; let s=0; for x in a { s+=x }; return s` returns 6; the emitted WAT contains no `iterator_next` call.

**Spike.** Given the host `iterator_next` returns 0, when P02 is compiled with the array-scan lowering, then the loop body must execute 3 times; run the module and assert 6.

## short-circuit-logic  (addresses ['F3'], effort S, risk Low — pure structured control flow; wasmtime 50 accepts `if (result i32)`.)

**Problem.** `_compile_binary_expr` (compiler_wasm.py:903) compiles both operands and maps `&&`/`||` to `i32.and`/`i32.or` (:912), so the right operand is always evaluated and `10/x` traps when x is 0.

**Proposal.** Special-case `&&`/`||` before the generic path: compile the left, emit `if (result i32)`, compile the right in the taken branch and `i32.const 0` (for `&&`) or `i32.const 1` (for `||`) in the other, then `end`; optionally normalize the right with `i32.const 0; i32.ne` so the result is 0/1 as the type layer claims. Preserve left-to-right evaluation order.

**Expected.** `func f(x:int){ let r = x == 0 || 10/x > 1; return r }` called with f(0) returns 1 with no trap; today it traps. (P03's literal `x == 0 && 10/x > 1` still traps even with correct short-circuit because the left operand is true — the probe's expected 1 is unreachable; use `||` or `x != 0 &&`.)

**Spike.** Given the eager `i32.and`/`i32.or` lowering, when the `if (result i32)` form is emitted, then calling f(0) must skip the division; a hand-written WAT of this exact lowering already returned `[1, 1]` for x=0,2 in wasmtime 50.

## const-immutability  (addresses ['F6'], effort S, risk Low — additive check; verify that `var` and local `let` reassignment still compile.)

**Problem.** `_compile_assign` (compiler_wasm.py:779) emits `global.set $c` for a top-level const, but `_collect_declarations` (:239) declares `(global $c i32 (i32.const 5))` immutable, so the module fails validation (P09); the type checker never inspects AssignExpr at all.

**Proposal.** In type_inference.py track const names in a scoped set pushed/popped with function/block envs, add a `NodeType.EXPR_STMT` case to `_check_stmt` (:745), and reject an AssignExpr whose target Ident is const with `assignment to const 'c'`; `_check_const_decl` (:930) records the name. Add a backend backstop in `_compile_assign`: if the target is a global with `WasmMutability.CONST`, raise SyntaxError (covers strict=False).

**Expected.** P09 `const c: int = 5; func main() type int { c = 6 return c }` makes `verify_program` report a const-assignment problem and `compile_file_to_wasm` raise SVLVerificationError (probe PASS instead of invalid artifact).

**Spike.** Given `_check_stmt` has no EXPR_STMT case, when the const check is added, then `verify_program` on P09 must return a problem mentioning const and `compile_file_to_wasm` must raise SVLVerificationError.

## throw-try-error-model  (addresses ['F9'], effort M, risk Medium — new AST node plus unreachable-code emission after `br`; validate nested try/throw and throw inside loops.)

**Problem.** `_compile_try_stmt` (compiler_wasm.py:735) unconditionally raises SyntaxError, and `throw` is not a statement at all: `parse_stmt` (:1149) falls through to `parse_primary` (:1557), whose hebrew_map (:1621) turns THROW into `Ident('THROW')`, so the language has no error model (P26).

**Proposal.** Add a `ThrowStmt` AST node + `THROW_STMT` NodeType and a `parse_throw_stmt` called from `parse_stmt`. In the compiler keep a per-function stack of `(label, err_local)`; `_compile_try_stmt` emits `block $try`, initialises `err=0`, compiles the try block, emits `br $try`, then `local.get $err; if; bind catch_var; compile catch block; end`. `_compile_throw_stmt` sets the innermost `err` and emits `br $label` (compile error if the stack is empty). Add `_check_throw_stmt` to the type checker. Runtime traps stay uncaught and documented as such.

**Expected.** `module m { func main() type int { let r = 0 try { throw 7 } catch e { r = e } return r } }` returns 7, and P26's `try { let x = 1 } catch e { let y = 2 }` compiles (probe PASS); today both raise SyntaxError.

**Spike.** Given the current SyntaxError, when the block+flag lowering is compiled, then a throw must land in the catch (7) and a normal exit must skip it; the hand-written WAT pattern already validated both paths in wasmtime 50.

## import-link-or-reject  (addresses ['F10'], effort M, risk Medium — path resolution, cycles and an API change; P27 cannot PASS as written because it imports a nonexistent file from inside a module body.)

**Problem.** `Program.imports` (parser_rd.py:602) is never read by `WasmCompiler.compile` (compiler_wasm.py:203), and `import` inside a module body is parsed by `parse_primary`'s hebrew_map (:1621) into `Ident('IMPORT')`, which the compiler silently drops (P27 runs and returns 42).

**Proposal.** Reject `TokenType.IMPORT` in `parse_stmt` (:1149) with 'import must appear at top level'. In `compile_file_to_wasm` (:1503) add a `base_dir` parameter and a `_link_imports(program, base_dir)` step that resolves each `Import.path`, reads and parses the file, appends its modules/items, and detects cycles; unresolvable paths raise. The existing `module$func` namespacing and `_resolve_callee` suffix scan (:1057) already make cross-module calls work.

**Expected.** A real `import "other.svl"` where other.svl defines `module other { func answer() type int { return 42 } }` links and `main` returns 42 via `other$answer`; the probe's inline `import "other"` inside a module now raises SyntaxError (P27 becomes an honest rejection, not a silent 42).

**Spike.** Given the compiler never reads `program.imports`, when `_link_imports` is added, then a two-file program must resolve `answer()` to `other$answer`; assert the probe's malformed import is rejected before codegen.

