# 001 — Lexical scoping (F1)

**Given** the backend keeps one flat local per name (`_compile_let_stmt` emits `local.set $name`
and `_compile_ident` resolves through a flat name set), so an inner `let x` overwrites the outer
binding,
**When** a scope-aware alpha-renaming pass gives every binding a unique name and resolves
references innermost-first,
**Then** `let x = 1; if 1==1 then { let x = 99 } else {}; return x` must return **1**, and the WAT
must contain two distinct locals.

Panel proposals covered: `lexical-scoping`, `codegen-scope-stack`, `scope-aware-locals`.

## Approach

Standalone AST pass (`rename_scopes`) that pushes/pops a scope per block, mints
`name__vN` for every binding (let / for-var / param / catch-var), and rewrites every
`Ident` reference through the scope stack. `FieldAccess.right` is a field name, not a
variable, and is deliberately skipped. The renamed AST is handed to the real
`compile_to_wasm`, so the type checker sees consistent names.

## Run

```bash
python spikes/svl-improvements/001-lexical-scoping/spike.py
```
