# Expert report — type system & soundness

## check-call-arguments-and-return  (addresses F4, F5, P15, effort M, risk Medium — the checker was blind to arguments, so newly-surfaced errors may reject real programs; the pre-pass and arg check must be run over `examples/` and `tests/` before landing.)

**Problem.** `TypeInferencer._synth_call` (svl/type_inference.py:518-527) returns the callee's return type without synthesizing any argument, and `TypeChecker._check_return_stmt` (svl/type_inference.py:852-854) discards the synthesized type, so `return "hi"` in a `type int` function and `f("hi")` against `f(x: int)` both pass the strict gate (svl-rating/probes.py P15 FAIL).

**Proposal.** Three additions to `TypeChecker`. (a) In `_check_module` (svl/type_inference.py:739-743) add a signature pre-pass that extends the env with every `FuncDecl`'s `Type.func` before any body is checked — this also fixes recursion and forward references, which are unchecked today because the scheme is added at type_inference.py:913-915 *after* the body. (b) Rewrite `_synth_call`: `instantiate()` the scheme, check `len(expr.arguments) == len(params)`, `synthesize` each argument and `unify` it with the corresponding parameter, appending to `self.errors`. (c) Set `_current_return_type` in `_check_func_decl` before the body and compare it in `_check_return_stmt`. Host builtins in `BUILTIN_SIGNATURES` (type_inference.py:27-37) then get checked too, so `print_int(1.5)` and `zeros(1.5)` become errors instead of emitting an f64 operand into an i32 import.

**Expected.** `module m { func f() type int { return "hi" } func main() type int { return f() } }` -> `compile_file_to_wasm(..., strict=True)` raises `SVLVerificationError: Return type mismatch: Argument mismatch: string vs int` (probe P15 flips to PASS); `f("hi")` against `f(x: int)` -> refused; `print_int(1.5)` -> refused; `func f(x: int) type int { return x } func main() type int { let a = [1,2,3] return f(len(a)) }` still compiles and returns 3 (spike-verified).

**Spike.** Given the monkeypatched `_synth_call` and `_check_return_stmt` from the spike, when the gate is run over the 61 pytest programs plus `examples/*.svl`, then zero previously-passing tests regress and all four F4 sources are refused.

## lower-print-from-string-values  (addresses F5, P08, effort S, risk Low — it only widens an existing special case and turns a silent invalid-artifact path into a compile error.)

**Problem.** `_compile_call_expr` (svl/compiler_wasm.py:1039-1051) special-cases only a bare string `Literal`; any other single argument falls through to svl/compiler_wasm.py:1052-1055, which compiles one operand and emits `call $print` where the import needs `(i32 i32)`, so `let x = 5; print(x)` is rejected by wasmtime with 'expected i32 but nothing on stack' (probe P08 FAIL).

**Proposal.** Replace the literal-only special case with an argument-type-driven one. Add `WasmCompiler._arg_type(arg)` resolving, in order: the recorded `expr_types` entry, a string `Literal`, an `Ident` via `self._inferred_local_type(func.name, arg.name)`, or a `CallExpr` via `self.inferred.func_types[callee].args[-1]`. If the type is `prim/string`, emit `arg; i32.const 4; i32.add` (text start — word 0 is the length, per the layout documented at compiler_wasm.py:1439-1441) then `arg; i32.load` (length) then `call $print`. Otherwise raise `SyntaxError("print() takes a string ... use print_int() for integers")`.

**Expected.** `module m { func main() type void { let s = "hi" print(s) } }` assembles and the host import receives `(ptr=4, len=2)` (spike-verified); likewise a `string` parameter `(4, 3)` for "hey" and `print(g())` where `g() type string`. `let x = 5; print(x)` becomes a compile-time `SyntaxError` naming `print_int` instead of invalid WAT. Probe P08 PASS.

**Spike.** Given the patched `_compile_call_expr`, when the four string forms (literal, let-bound, parameter, function result) are assembled and run through `tests/conftest.py::instantiate`, then each host `print` call carries a correct (ptr, len) pair and the int case raises before any WAT is emitted.

## enforce-const-mutability  (addresses F6, P09, effort S, risk Low — pure rejection of a case that already produced an invalid artifact.)

**Problem.** `_compile_assign` (svl/compiler_wasm.py:779, Ident path 802-822) emits `global.set` for any target in `self.state.globals` (811-813) without consulting `WasmMutability`, so `const c: int = 5; c = 6` emits `global.set $c` against the immutable `(global $c i32 (i32.const 5))` generated at compiler_wasm.py:1414-1419 and module validation fails (probe P09 FAIL); the type layer has no constness at all (`_check_const_decl`, type_inference.py:930-942, is identical to `_check_var_decl`, 944-956, except the message).

**Proposal.** At the top of `_compile_assign` (svl/compiler_wasm.py:779), for an `Ident` target look up `self.state.globals[target.name].mutability` and raise `SyntaxError(f"cannot assign to const '{target.name}' ...")` when it is `WasmMutability.CONST`. This covers both `c = 6` and `c += 1` (the compound path at 814-818 routes through the same method). If constness should be a type-system property, the minimal honest version is a `const_names: set` recorded in `InferredTypes` (svl/type_lowering.py:29-43) from `_check_const_decl` and consulted by the backend — same behaviour, one extra source of truth.

**Expected.** `module m { const c: int = 5 func main() type void { c = 6 print_int(c) } }` -> `SyntaxError: cannot assign to const 'c'`; `var v: int = 5; v = 6` still assembles and prints 6. Probe P09 PASS ('refused').

**Spike.** Given the five-line guard, when the two const-assignment forms and the `var` control are compiled, then both const forms raise `SyntaxError` before WAT generation and the `var` program still assembles.

## type-layer-block-scopes  (addresses F1, F4, effort S, risk Low — strictly tighter scoping; a program that relied on the leak was relying on a bug.)

**Problem.** `_check_if_stmt` (svl/type_inference.py:815-832) builds `else_env` from the *then* environment and never restores `self.env`; `_check_while_stmt` (834-843) and `_check_for_stmt` (845-850) check bodies in the enclosing env with no child at all, so `if 1==1 then { let y: int = 1 } else {} let z: int = y` is accepted today — the type-side twin of runtime bug F1.

**Proposal.** Add one helper, `TypeChecker._check_scoped_block(block)`, that saves `outer = self.env`, creates `child = TypeEnv(bindings=dict(outer.bindings), parent=outer)`, sets `self.env = child`, checks the statements, and restores `self.env = outer` in a `finally`. Use it in `_check_if_stmt` (one child per branch, both parented on `outer`, then restore), `_check_while_stmt`, `_check_for_stmt` (binding the loop var in the child) and `_check_try_stmt` (replacing the manual restore at type_inference.py:877-881). `TypeEnv.extend` (type_inference.py:191-194) already returns a child; the defect is purely that callers never restore.

**Expected.** `module m { func main() type void { if 1==1 then { let y: int = 1 } else {} let z: int = y } }` -> refused ('void vs int'); the same `let z` *inside* the branch still checks; while-body and for-body lets no longer leak into the enclosing scope.

**Spike.** Given the helper, when the checker runs over `tests/` and `examples/`, then no program that binds a name inside a branch/body and references it outside still passes, and none of the 61 tests regress.

## host-import-signature-table  (addresses F5, F4, effort S, risk Low-Medium — a shared table can reject a call the old checker allowed, but only where the emitted WAT was invalid anyway.)

**Problem.** `BUILTIN_SIGNATURES` (svl/type_inference.py:27-37) and `HOST_IMPORT_SIGS` (svl/compiler_wasm.py:171-181) are two hand-maintained tables and the checker never consults the compiler's arity/valtypes, so `print_int(1.5)`, `len(1)` and `putc(1.5)` pass the gate and then emit an f64 operand to an i32 import — invalid WAT of exactly the F5 class.

**Proposal.** Make `HOST_IMPORT_SIGS` the single source of truth (it already carries `(param ...)` / `(result ...)`), derive `BUILTIN_SIGNATURES` from it at import time, and add `WasmCompiler._check_host_call(expr)` that walks the same table before emitting: arity, and operand valtype per parameter, using the `_arg_type` helper from the print fix. On mismatch raise `SyntaxError` naming the expected type. Keep `len`/`zeros` as codegen builtins but list them in the same table with their valtypes.

**Expected.** `module m { func main() type void { print_int(1.5) } }` and `let n = zeros(1.5)` -> `SyntaxError: print_int expects i32, got f64`; `print_int(3)`, `print("a")`, `len(a)` unchanged. Any module containing a host call now either type-checks or fails loudly.

**Spike.** Given the shared table, when every host call in `examples/` and `tests/` is compiled, then all of them pass the check and no test regresses.

## codegen-scope-stack  (addresses F1, P01, effort L, risk Medium — name resolution is touched in three places (let, ident, assign) and any missed path reintroduces 'unknown local' assembly failures.)

**Problem.** `WasmCompiler` keeps no scope stack: `_compile_let_stmt` appends `(stmt.name, val_type)` to a flat `func.locals` (svl/compiler_wasm.py:518) and every access emits `local.get $name` (1207) / `local.set $name` (519), while `_generate_wasm_function` dedupes by name keeping the first type (1475-1483) — so `let x=1; if 1==1 then { let x=99 } else {}; return x` returns 99 (probe P01 FAIL).

**Proposal.** Add `self._scopes: List[Dict[str, str]]` to `WasmCompiler`, pushed/popped in `_compile_if_stmt` (541-556), `_compile_while_stmt` (558), `_compile_for_stmt` (582/627) and nested `Block`s. `_compile_let_stmt` mints a fresh WASM name on collision (`x`, then `x__1`, `x__2`) and records `scopes[-1][stmt.name] = wasm_name`; `_compile_ident` and `_compile_assign` resolve through the stack with a globals fallback, so the name-based dedupe at 1475-1483 becomes a no-op. If the full stack is too invasive, the cheapest honest fix is to reject the collision in `_compile_let_stmt` ('duplicate local x in function f') — a two-line change that converts a silent wrong answer into a compile error.

**Expected.** `module m { func main() type int { let x = 1 if 1==1 then { let x = 99 } else {} return x } }` returns 1 (probe P01 PASS); with the fallback, the same program raises `SyntaxError: duplicate local 'x'` instead of returning 99.

**Spike.** Given the scope stack, when P01 plus every `examples/*.svl` program is compiled and run, then P01 returns 1 and the 61 tests plus the documented bubble_sort/sieve outputs are unchanged.

