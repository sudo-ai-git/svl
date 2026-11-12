# Expert report — runtime, codegen & memory

## memory-grow-reset  (addresses ['F8'], effort M, risk Medium - memory.grow can return -1 and must trap, and resetting the heap at main entry clobbers live allocations if main is re-entered or recursive.)

**Problem.** The emitted $alloc (svl/compiler_wasm.py:1388-1398) is a pure bump allocator over a fixed (memory 16) (1 MiB, lines 1403-1404) with no memory.grow and no reset; a program allocating 800 KiB returns from the first main() and traps on the second.

**Proposal.** Extend the $alloc body to compare p+n against memory.size*65536 and emit memory.grow with the missing page delta (trap on -1) before bumping; emit a $heap_reset function (global.set $heap (i32.const <heap_base>)) and call it at the top of the exported main body in _compile_functions (lines 382-407), or export it for the host. Keep the initial 16 pages so small programs keep their current footprint.

**Expected.** module m { func main() type int { let n = 200000 let a = zeros(n) a[0] = 1 return a[0] } } returns 1 on the first and second call in one Store; a single run allocating 2 MiB (zeros(500000)) no longer traps; P16 reports memory.grow present = True.

**Spike.** Given a module compiled from zeros(300000) (1.2 MiB) with the new $alloc, When the exported main is invoked twice in one wasmtime Store, Then both calls return without an out-of-bounds trap and the WAT contains memory.grow; if the page-delta arithmetic is wrong the second call traps.

## print-type-dispatch  (addresses ['F5'], effort S, risk Low - the type layer already infers string (type_inference.py:461); the only hazards are double-evaluating a string expression and the float case.)

**Problem.** _compile_call_expr (svl/compiler_wasm.py:1039-1051) special-cases only print(<string literal>); every other single argument falls through to lines 1052-1055, which push one operand and emit call $print, but $print takes (i32,i32) (HOST_IMPORT_SIGS line 173), so let x = 5 print(x) fails wasmtime.Module validation.

**Proposal.** In _compile_call_expr, dispatch on self._inferred_expr_type(arg): string-typed -> keep the literal fast path, and for a general string expression store the pointer in a temp local then emit ptr+4 and i32.load of the length word; int/bool -> emit call $print_int (already declared line 174); float/array -> add a print_float host import or raise a clear SyntaxError. Do not evaluate a string expression twice.

**Expected.** module m { func main() type void { let x = 5 print(x) return } } validates and runs (P08 PASS); let s = 'hi' print(s) prints hi; print('hi') is unchanged.

**Spike.** Given let x = 5 print(x), When compiled and passed to wasmtime.Module, Then it validates and the host print_int receives 5; given let s = 'hi' print(s), Then the host print receives a pointer to hi and length 2.

## const-immutability-check  (addresses ['F6'], effort S, risk Low - it turns an invalid artifact into a clear compile error; no currently-valid program is affected.)

**Problem.** _compile_assign (svl/compiler_wasm.py:802-822) emits global.set for any global target, including a const declared with WasmMutability.CONST (line 281); WASM rejects global.set on an immutable global, so const c: int = 5 ... c = 6 produces an invalid module.

**Proposal.** In _compile_assign, when is_global is true, look up self.state.globals[target.name].mutability and raise SyntaxError('cannot assign to const ...') if it is CONST, before emitting any instruction. Optionally mirror the check in the type layer's assignment path so strict=True refuses it too; the backend check is the load-bearing one.

**Expected.** const c: int = 5 func main() type int { c = 6 return c } is refused with a clear error (P09 PASS); var c: int = 5 ... c = 6 still compiles and runs.

**Spike.** Given the P09 source, When compiled with strict=True, Then compilation raises before codegen and no global.set on an immutable global is emitted; given the same source with var instead of const, Then it compiles and returns 6.

## pcc-binary-custom-section  (addresses ['F7'], effort S, risk Low - binary custom sections are standard; the only risks are section ordering and the required probe/API change.)

**Problem.** PCCWasmModule.to_wasm_with_proofs (svl/pcc_wasm.py:33-59) inserts a text line (custom 'svl-proofs' '<hex>') before the closing paren; wasmtime.wat2wasm has no custom-section syntax (verified: (module (custom 'x' 'a')) -> 'expected valid module field'), so the artifact never assembles. The correct binary helpers WasmCustomSection.create_proof_section (lines 281-301) are unused.

**Proposal.** Add PCCWasmModule.to_wasm_bytes_with_proofs() that runs wat2wasm on the plain WAT and appends WasmCustomSection.create_proof_section(proof_data) to the module binary; make extract_proofs_from_wasm (lines 215-231) scan the binary for section code 0 / name 'svl-proofs' instead of the text regex. Update probe P10 to validate the binary with wasmtime.Module(engine, bytes) - as written it asserts a WAT form that no correct PCC can produce, so it is a probe defect, not a feature.

**Expected.** PCCWasmGenerator().generate('module m { func main() type int { return 7 } }').to_wasm_bytes_with_proofs() validates with wasmtime.Module and extract_proofs_from_wasm recovers source_hash plus the three proof layers; P10 (binary form) PASS.

**Spike.** Given a PCC module built from return 7, When the bytes are passed to wasmtime.Module, Then it validates; When the trailing custom section is parsed, Then source_hash and the three proofs round-trip. If a trailing custom section is rejected, insert it before the code section.

## for-in-array-lowering  (addresses ['F2'], effort M, risk Medium - a false negative in the inferred type falls back to the silent no-op, so the fallback must be a compile error; the iterable expression must be evaluated exactly once.)

**Problem.** _compile_for_stmt (svl/compiler_wasm.py:582-625) routes every non-range loop through the iterator_next host import, which the harness implements as return 0 (tests/conftest.py:63, svl-rating/probes.py:61), so for x in [1,2,3] { s += x } returns 0; the array layout is already [len, e0, ...] (lines 1168-1188), so a direct loop is available.

**Proposal.** In _compile_for_stmt, before the iterator path, read t = self._inferred_expr_type(stmt.iter_expr); if t is not None and t.kind in ('array','generic','tuple') (or iter_expr is an ArrayLit), emit an index loop: evaluate the iterable once into a temp base local, load len = i32.load base, then a counting loop with an index local i and stmt.var = i32.load(base + 4 + i*4), reusing the range-loop pattern at lines 627-667. If the type is not array-like and no iterator protocol exists, raise a clear SyntaxError rather than silently iterating zero times.

**Expected.** module m { func main() type int { let a = [1,2,3] let s = 0 for x in a { s += x } return s } } returns 6 (P02 PASS); for x in zeros(1000) iterates 1000 times instead of 0.

**Spike.** Given the P02 source, When compiled with the array path, Then the WAT contains an i32.load of the length word and a counting loop and main returns 6; given a non-array iterable with no iterator implementation, Then compilation fails loudly instead of returning 0.

## scope-aware-locals  (addresses ['F1'], effort L, risk Medium/High - it touches every name-resolution site (_compile_ident, _compile_assign, _field_offset/_local_struct_types, _known_locals); a missed site converts a wrong answer into an unknown-local error, so the 61-test suite must stay green.)

**Problem.** WasmFunction.locals is a flat list (svl/compiler_wasm.py:159); _compile_let_stmt appends stmt.name (line 518) and every access emits local.get $name (line 1207) / local.set $name (line 821), so an inner let overwrites the outer binding: let x = 1; if 1==1 then { let x = 99 } else {}; return x returns 99. _collect_local_names (lines 428-455) also flattens nested blocks, so shadowing is undetectable.

**Proposal.** Maintain self._scopes (list of dicts source-name -> unique wasm name) seeded with the function params; in _compile_let_stmt allocate a fresh name like name@<counter>, emit local.set to it, and push the binding; resolve through _scopes innermost-first in _compile_ident and _compile_assign, falling back to globals; push/pop a scope in _compile_block and the loop bodies. _generate_wasm_function already dedups locals by name (lines 1475-1483), so each unique name is emitted once.

**Expected.** let x = 1 if 1 == 1 then { let x = 99 } else { } return x returns 1 (P01 PASS); the WAT contains two distinct locals; a name bound inside a block is not visible outside it.

**Spike.** Given the P01 source, When compiled with the scope resolver, Then the WAT has two distinct locals and main returns 1; given { let y = 2 return y }, Then y resolves to the inner local and returns 2.

