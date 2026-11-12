# SVL Programmer's Knowledge Base
## Self-Verifying Language (SVL) - Complete Reference Guide

---

## Table of Contents
1. [Language Overview](#1-language-overview)
2. [Syntax & Grammar](#2-syntax--grammar)
3. [Type System](#3-type-system)
4. [Verification Layers](#4-verification-layers)
5. [Tooling](#5-tooling)
6. [Standard Library](#6-standard-library)
7. [Package Management](#7-package-management)
8. [Best Practices](#8-best-practices)
9. [Troubleshooting](#9-troubleshooting)
10. [Examples](#10-examples)
11. [Extended Syntax (H2–H16)](#11-extended-syntax-h2h16)
12. [Verification Extensions (H17–H24, H38–H40)](#12-verification-extensions-h17h24-h38h40)
13. [Compiler Optimizations & Runtime (H25–H32)](#13-compiler-optimizations--runtime-h25h32)
14. [Build & Tooling Ecosystem (H33–H35, H41–H48)](#14-build--tooling-ecosystem-h33h35-h41h48)
15. [Spike Suite Status](#15-spike-suite-status)

---

## 1. Language Overview

### What is SVL?
SVL (Self-Verifying Language) is a programming language with **built-in three-layer verification** that runs automatically on every compilation:

| Layer | Name | Technology | Purpose |
|-------|------|------------|---------|
| **L1** | Syntax | 231-Gate Checksums | Structural integrity via SUM/LINEAR/ROLLING mod 231 |
| **L2** | Types | Mod-5 Dual-Stream | Mod-5 buckets + Z/2 negation + structural checksums |
| **L3** | Theorem | BPSW Monodromy — **informational only** | hash-primality parity via SHA256 + BPSW on primes {37,73,17}; constant-true (0/60 programs fail it), **not** part of `passed` |
| **L3+** | SMT (opt-in) | Z3 theorem layer | the real prover: tri-state `proven` / `counterexample` / `unverified` |

### Key Properties
- **22 tokens** mapped to Hebrew alphabet (א-ת)
- **Deterministic compilation** - bit-identical WASM output across runs
- **Real prover** - the interval analyser proves out-of-bounds / division-by-zero and
  refuses them; the Z3 SMT layer discharges every `assert` (opt-in)
- **No self-hosting** - `svl/compiler_svl.svl` is a stub; the claim is retracted (2026-11-12)

### Target Platform
- **WASM (WebAssembly)** - runs in browsers, Node.js, wasmtime, wasmer
- **Linear memory model** - bump allocator with `memory.grow` and a heap reset at the entry
  point, so allocating programs are re-runnable
- **Host ABI** - `env.print`, `env.malloc`, `env.await` imports

---

## 2. Syntax & Grammar

### 2.1 The 22 Tokens (Hebrew Alphabet)

| # | Token | Hebrew | ASCII Alias | Arity | Meaning |
|---|-------|--------|-------------|-------|---------|
| 1 | `LET` | א | `let` | 2 | Variable binding |
| 2 | `IF` | ב | `if` | 3 | Conditional branch |
| 3 | `THEN` | ג | `then` | 0 | Then-branch marker |
| 4 | `ELSE` | ד | `else` | 0 | Else-branch marker |
| 5 | `WHILE` | ה | `while` | 2 | Loop construct |
| 6 | `FOR` | ו | `for` | 3 | Iteration construct |
| 7 | `FUNC` | ז | `func` | 3 | Function definition |
| 8 | `RETURN` | ח | `return` | 1 | Return from function |
| 9 | `MATCH` | ט | `match` | 2 | Pattern matching |
| 10 | `TYPE` | י | `type` | 2 | Type annotation |
| 11 | `STRUCT` | כ | `struct` | 2 | Struct definition |
| 12 | `MODULE` | ל | `module` | 2 | Module declaration |
| 13 | `IMPORT` | מ | `import` | 1 | Import module |
| 14 | `EXPORT` | נ | `export` | 1 | Export symbol |
| 15 | `CONST` | ס | `const` | 2 | Constant binding |
| 16 | `VAR` | ע | `var` | 2 | Mutable variable |
| 17 | `ASSERT` | פ | `assert` | 1 | Assertion/check |
| 18 | `TRY` | צ | `try` | 1 | Try block |
| 19 | `CATCH` | ק | `catch` | 2 | Catch handler |
| 20 | `THROW` | ר | `throw` | 1 | Throw exception |
| 21 | `ASYNC` | ש | `async` | 2 | Async function |
| 22 | `AWAIT` | ת | `await` | 1 | Await expression |

**Note**: Final forms (sofit: ך ם ן ף ץ) are **excluded** - 22 standard letters only.

### 2.2 Grammar Overview (EBNF)

```ebnf
program       = module_decl, { import_decl }, { export_decl }, { top_level };
module_decl   = MODULE, IDENT, block;
import_decl   = IMPORT, STRING;
export_decl   = EXPORT, IDENT;
top_level     = func_decl | struct_decl | const_decl | var_decl | type_alias_decl;

func_decl     = FUNC, IDENT, param_list, [TYPE, type_expr], block;
struct_decl   = STRUCT, IDENT, field_list;
type_alias_decl = TYPE, IDENT, [generic_params], "=", type_expr;
const_decl    = CONST, IDENT, [TYPE, type_expr], expr;
var_decl      = VAR, IDENT, [TYPE, type_expr], expr;

block         = "{", { stmt }, "}";
stmt          = let_stmt | if_stmt | while_stmt | for_stmt | return_stmt
              | assert_stmt | try_stmt | expr_stmt;

expr          = logic_or;
logic_or      = logic_and, { "||", logic_and };
logic_and     = equality, { "&&", equality };
equality      = comparison, { ("==" | "!="), comparison };
comparison    = additive, { ("<" | ">" | "<=" | ">="), additive };
additive      = multiplicative, { ("+" | "-"), multiplicative };
multiplicative = unary, { ("*" | "/" | "%"), unary };
unary         = ("-" | "!"), unary | postfix;
postfix       = primary, { "." IDENT | "[" expr "]" | "(" [expr {"," expr}] ")" };
primary       = literal | IDENT | "(" expr ")" | struct_lit | call
              | await_expr | lambda_expr | array_lit;
```

### 2.3 Operator Precedence (Highest to Lowest)

| Level | Operators | Associativity |
|-------|-----------|---------------|
| 9 | `AWAIT`, `.`, `[]`, `()`, `-` (unary), `!` | Left/Right |
| 8 | `*`, `/`, `%` | Left |
| 7 | `+`, `-` (binary) | Left |
| 6 | `<`, `>`, `<=`, `>=` | Left |
| 5 | `==`, `!=` | Left |
| 4 | `&&` | Left |
| 3 | `||` | Left |
| 2 | `=` (in LET), `,` | Right |
| 1 | `->` (lambda), `=>` (match) | Right |

---

## 3. Type System

### 3.1 Mod-5 Type Buckets (Dual-Stream)

Every type maps to one of 5 buckets (mod-5 residue classes):

| Bucket | Residue | Category | Types |
|--------|---------|----------|-------|
| **B0** | 0 (mod 5) | Base/Primitive | `int`, `float`, `bool`, `void`, `never`, `string` |
| **B1** | 1 (mod 5) | Containers | `List<T>`, `Dict<K,V>`, `Set<T>`, `Array<T>`, `Option<T>`, `Tuple<...>` |
| **B2** | 2 (mod 5) | Functions | `fn(...) -> ...`, `AsyncFn(...) -> ...`, closures |
| **B3** | 3 (mod 5) | Async/Effects | `Future<T>`, `Stream<T>`, `Async<T>`, `IO<T>` |
| **B4** | 4 (mod 5) | Errors/Exceptions | `Result<T,E>`, `Error`, `Exception`, `panic` |

### 3.2 Z/2 Negation (Single Involution)

```
B0 ↔ B4,  B1 ↔ B3,  B2 ↔ B2
```

```svl
// Z/2 negation is involutive: negate(negate(x)) = x
z2_negate(B0) = B4
z2_negate(B4) = B0
z2_negate(B1) = B3
z2_negate(B3) = B1
z2_negate(B2) = B2
```

### 3.3 Variance Under Z/2

| Bucket | Variance | Types | Negation Effect |
|--------|----------|-------|-----------------|
| B0 | Invariant | `int`, `float`, `bool` | B0↔B4 preserves invariance |
| B1 | Covariant | `List`, `Option`, `Future` | B1↔B3 preserves covariance |
| B2 | Contravariant | Function arguments | B2↔B2 flips variance |
| B3 | Covariant | `Future`, `Stream` | B3↔B1 preserves covariance |
| B4 | Invariant | `Result`, `Error` | B4↔B0 preserves invariance |

### 3.4 Type Constructors

```svl
// Primitives
int, float, string, bool, void, never

// Containers (B1)
List<int>
Dict<string, int>
Option<int>          // None | Some(int)
Result<int, string>  // Ok(int) | Err(string)
Array<int>
Tuple<int, string>

// Functions (B2)
fn(int, string) -> bool
AsyncFn(int) -> Result<int, Error>

// Async/Effects (B3)
Future<int>
Stream<string>

// Errors (B4)
Result<int, Error>
Error
```

### 3.5 Generic Types

```svl
// Generic type alias
type Pair<T, U> = Tuple<T, U>

// Generic struct
struct Pair<T, U> {
  first: T,
  second: U
}

// Generic function
func map<T, U>(f: fn(T) -> U, xs: List<T>) type List<U> { ... }

// Usage
let add1: fn(int) -> int = \x -> x + 1
let nums: List<int> = [1, 2, 3]
let result: List<int> = map(add1, nums)  // [2, 3, 4]
```

---

## 4. Verification Layers

### 4.1 Layer 1: Syntax (231-Gate)

**Mathematical Basis**: 231 = 3 × 7 × 11

**Three Checksums per AST Node**:
```
SUM     = (Σ bytes) mod 231
LINEAR  = (Σ (i+1) * byte[i]) mod 231
ROLLING = (H*31 + byte[i]) mod 231,  H_0 = 0
```
The third channel was originally `PRODUCT = Π(b+1) mod 231`, which was **degenerate**:
it is 0 whenever any byte has `b+1` divisible by 3, 7 or 11, so 2000/2000 random 512-byte
windows produced 0.  It was replaced (2026-11-12) with the rolling hash above; 31 is
coprime to 231, so the channel is non-degenerate and a one-byte change alters it with
probability ≈ 1 − 1/231.

**Verification Gates**:
1. **AST Guard** - Forbids `sum()` on iterables (requires `neumaier_sum()`)
2. **Golden References** - Psalm 119 Aleph, Genesis 1:1
3. **Mutation Test** - 3+ injected corruptions must be caught
4. **Meta-Checksum** - `SUM ⊕ LINEAR ⊕ ROLLING mod 231` for tamper detection

**Viable Start Detection**: Exactly **one** viable start position per 512-byte block where all three checksums match expected values.

### 4.2 Layer 2: Types (Mod-5 Dual-Stream)

**Semantic Stream**: Ordinal (1-22) + Mod-5 bucket
- Hebrew token ordinal for keywords
- `hash(name) mod 22` for user types

**Structural Stream**: 3-channel checksums (mod 37, 73, 11)
- Type expression serialized canonically → 3 checksums
- **Agreement = exact match** of all 3 checksums

**Both streams must agree** for type validity.

### 4.3 Layer 3: Theorem (BPSW Monodromy)

**Program Hash → BPSW Check**:
```python
program_hash = SHA256(canonical_AST_serialization)

For each prime p ∈ {37, 73, 17}:
  - h_mod_p = program_hash % p
  - If h_mod_p == 0: treated as composite
  - MR = Miller-Rabin base 2 on h_mod_p
  - Lucas = Lucas Selfridge test on h_mod_p
  - Parity = MR XOR Lucas (0=even, 1=odd)
  - Expected: all parities even (0)
```

**Custom Constants (from MEMORY)**:
| Prime p | π(p) = 2(p+1) | ord₂(p) | Divisibility |
|---------|---------------|---------|--------------|
| 37 | 76 | 36 | 37\|π(73)=148, 38\|π(37)=76 |
| 73 | 148 | 9 | 74\|π(73)=148 |
| 17 | 36 | 8 | 18\|π(17)=36 |

**Note**: Only Genesis 1:1 (2701 = 37×73) happens to have all even parities by mathematical coincidence. This is a **probabilistic** layer - not all valid programs pass.

---

## 5. Tooling

### 5.1 REPL (Interactive Shell)

```bash
python3 -m svl.repl
```

**Commands**:
```
svl> help                    # Show help
svl> exit / quit / q         # Exit
svl> clear / cls             # Clear screen
svl> reset                   # Clear buffer
svl> verify                  # Full 3-layer verification
svl> compile                 # Compile to WASM
svl> history                 # Show command history
svl> load <file>             # Load SVL file
svl> save <file>             # Save buffer
```

**Verification Modes**:
- **Line-by-line**: After each complete statement
- **Block**: On blank line (executes block)
- **Full**: `verify` command runs all 3 layers

**Executes (2026-11-12):** the buffer is wrapped in `module repl { <definitions> func main() ... }`
before verification and then compiled and run, so a block prints its result. Top-level
declarations (`func`/`struct`/`const`/`var`/`type`) persist across blocks — a later block can
call a function defined in an earlier one.

**Example Session**:
```
svl> let x: int = 42
  ✓ Verified (syntax, types, theorem)

svl> func main() type void {
...   let x: int = 42
...   return
... }
  ✓ Verified (syntax, types, theorem)
```

### 5.2 LSP Server (Language Server Protocol)

```bash
python3 -m svl.lsp_server
```

**Capabilities**:
- **Diagnostics** - Real-time 3-layer verification errors
- **Completion** - 28 keywords + user-defined symbols
- **Hover** - Hebrew token meanings (e.g., `LET` → "Variable binding (א)")
- Semantic Tokens - Syntax highlighting (11 token types)
- Go to Definition - Planned (LSIF indexer available — see §14.8)

**Configure in VS Code**:
```json
{
  "svl-lsp": {
    "command": "python3",
    "args": ["-m", "svl.lsp_server"]
  }
}
```

### 5.3 Compiler

```bash
# Compile to WASM
python3 -c "
from svl.compiler_wasm import compile_file_to_wasm
wasm = compile_file_to_wasm(source)
print(wasm)
"

# Verify determinism
python3 -c "
from svl.compiler_wasm import verify_wasm_determinism
verify_wasm_determinism(source, runs=5)  # Returns True/False
"
```

**Output**: WASM text format (`.wat`) with:
- Linear memory (1 page = 64KB)
- Function imports: `env.print`, `env.malloc`, `env.await`
- Deterministic output (fixed `PYTHONHASHSEED=0`, ordered maps)

### 5.4 Package Manager

```bash
# Create package
python3 -m svl.package_manager create mypkg 1.0.0 source.svl \
  --description "My package" --author "Author"

# Install (from registry)
python3 -m svl.package_manager install mypkg 1.0.0

# Publish to registry (sign with registry key, see §14.5)
python3 -m svl.package_registry publish ...

# List installed
python3 -m svl.package_manager list

# Verify installed
python3 -m svl.package_manager verify mypkg 1.0.0
```

**Package Format** (`.svl` + `metadata.json` + `module.wasm`):
```json
{
  "name": "mypkg",
  "version": "1.0.0",
  "wasm_sha256": "abc123...",
  "source_sha256": "def456...",
  "verification": {"syntax": true, "types": true, "theorem": false},
  "entry_point": "main"
}
```

---

## 6. Standard Library (Minimal)

### Built-in Types
```svl
// Primitives
int, float, string, bool, void, never

// Type constructors
List<T>, Dict<K,V>, Option<T>, Result<T,E>
Array<T>, Tuple<T...>
fn(...) -> ..., AsyncFn(...) -> ...
Future<T>, Stream<T>
Result<T,E>, Error
```

### Built-in Functions (Host ABI)
```svl
// I/O (via env imports)
import "env" "print" (func $print (param i32 i32))  // ptr, len

// Memory
import "env" "malloc" (func $malloc (param i32) (result i32))

// Async
import "env" "await" (func $await (param i32) (result i32))

// Iteration
import "env" "iterator_next" (func $iterator_next (param i32) (result i32))
```

### Neumaier Summation (Required)
```svl
// ✗ FORBIDDEN - use neumaier_sum instead
let x: float = sum([1.0, 2.0, 3.0])

// ✓ REQUIRED - AST Guard enforces this
let x: float = neumaier_sum([1.0, 2.0, 3.0])
```

---

## 7. Package Management

### Creating a Package
```bash
# Directory structure
mypkg/
├── source.svl          # Source code
├── metadata.json       # Auto-generated
└── module.wasm         # Auto-generated

# Create
python3 -m svl.package_manager create mypkg 1.0.0 source.svl \
  --description "My library" --author "Me"
```

### Package Structure (Installed)
```
~/.svl/packages/
├── mypkg/
│   └── 1.0.0/
│       ├── source.svl
│       ├── module.wasm
│       └── metadata.json
```

### Index (`~/.svl/index.json`)
```json
{
  "packages": {
    "mypkg": {
      "1.0.0": {
        "name": "mypkg",
        "version": "1.0.0",
        "wasm_sha256": "abc123...",
        "verification": {"syntax": true, "types": true, "theorem": false}
      }
    }
  }
}
```

---

## 8. Best Practices

### 8.1 Writing Verifiable Code

1. **Always use `neumaier_sum`** for floating-point summation
2. **Explicit type annotations** for function signatures
3. **Use `const` over `var`** when possible (immutable = B0/B4 stable)
4. **Prefer `Option<T>` over `null`** - B1 bucket, handles absence safely
5. **Use `Result<T,E>` for errors** - B4 bucket, explicit error handling

### 8.2 Performance Tips

```svl
// ✓ Good: the type checker's inferred types drive codegen
func add(x: int, y: int) type int { return x + y }

// ✓ Also fine: an un-annotated parameter is typed by inference
func add(x, y) type int { return x + y }
```

Types reach the backend (`svl/type_lowering.py`, consumed by `compiler_wasm.py`): locals,
parameters and globals are lowered to the WASM valtype the checker inferred (`int`→`i32`,
`float`→`f64`), arithmetic and comparisons select `f64.*` vs `i32.*` from the operand
types, struct-typed locals are resolved from the inferred type, and a tail
`return f(args)` with a matching signature becomes a WASM `return_call`. Before this, an
un-annotated `let x = 1.5` emitted an **i32** local holding an `f64.const` — the text
parsed but the module failed validation, and `x + y` on two floats emitted `i32.add`.

// ✓ Good: Structs over tuples for complex data
struct Point { x: int, y: int }
let p: Point = Point { x: 1, y: 2 }

// ✗ Avoid: Nested tuples (harder to verify)
let p: Tuple<int, int> = (1, 2)
```

### 8.3 Verification-Friendly Patterns

```svl
// ✓ Assert preconditions
func divide(x: int, y: int) type int {
  assert y != 0
  return x / y
}

// ✓ Use match for exhaustive checking
func unwrap(opt: Option<int>) type int {
  match opt {
    case Some(v) => v
    case None => 0
  }
}

// ✓ Explicit returns
func main() type void {
  let x: int = 42
  return  // Explicit, not implicit
}
```

---

## 9. Troubleshooting

### Common Errors

| Error | Cause | Fix |
|-------|-------|-----|
| `SyntaxError: Unexpected token` | Missing brace, wrong keyword | Check brace balance, use ASCII aliases |
| `Forbidden function 'sum()'` | Used `sum()` instead of `neumaier_sum()` | Replace with `neumaier_sum()` |
| `Type checking error` | Type mismatch | Add explicit type annotations |
| `Theorem verification failed` | Probabilistic - BPSM parity odd | Expected for most programs; Genesis 1:1 is special |
| `WASM compilation not deterministic` | Non-deterministic compilation | Ensure `PYTHONHASHSEED=0`, ordered maps |

### Debugging Tips

```bash
# Verbose verification
python3 -c "
from svl.syntax_layer import verify_syntax, SyntaxVerificationConfig
config = SyntaxVerificationConfig(verify_golden_refs=True, run_mutation_tests=True)
result = verify_syntax(source, config)
print(f'Syntax: {result.passed}, Viable: {result.viable_start}')
"

# Check type layer
python3 -c "
from svl.type_layer import verify_type, TypeVerificationConfig
result = verify_type(source)
print(f'Types: {result.passed}, Errors: {result.errors}')
"

# Check theorem layer
python3 -c "
from svl.theorem_layer import verify_theorem_layer
result = verify_theorem_layer(source)
print(f'Theorem: {result.passed}, Parities: {result.all_parities_even}')
"
```

### Verification Output Format
```
=== Verification Results ===
Syntax:  ✓ PASS (3.5ms)
Types:   ✓ PASS (2.4ms)
Theorem: ✗ FAIL (2.3ms)
  Errors: []
Total:   8.1ms
```

---

## 10. Examples

### 10.1 Hello World
```svl
module hello {
  func main() type void {
    let msg: string = "Hello, World!"
    return
  }
}
```

### 10.2 Fibonacci
```svl
module fib {
  func fib(n: int) type int {
    if n <= 1 then { return n } else {
      return fib(n - 1) + fib(n - 2)
    }
  }

  func main() type void {
    let result: int = fib(10)
    assert result == 55
    return
  }
}
```

### 10.3 Pattern Matching
```svl
module match_demo {
  struct Option { value: int, has_value: bool }

  func get_or_default(opt: Option, default: int) type int {
    match opt {
      case { value: v, has_value: true } => v
      case _ => default
    }
  }
}
```

### 10.4 Async/Await
```svl
module async_demo {
  async fetch_data(id: int) type string {
    await sleep(100)
    return "data_" + id
  }

  func main() type void {
    let result: string = await fetch_data(42)
    assert result == "data_42"
    return
  }
}
```

### 10.5 Generic Map
```svl
module generics {
  func map<T, U>(f: fn(T) -> U, xs: List<T>) type List<U> {
    match xs {
      case [] => []
      case [x, ...rest] => [f(x), ...map(f, rest)]
    }
  }

  func main() type void {
    let add1: fn(int) -> int = \x -> x + 1
    let nums: List<int> = [1, 2, 3]
    let result: List<int> = map(add1, nums)
    assert result == [2, 3, 4]
    return
  }
}
```

### 10.6 Self-Verification (Compiler Bootstrap)
```svl
module svl_compiler {
  import "ast"
  import "lexer"
  import "parser"
  import "serialization"
  import "gate231"
  import "mod5_types"
  import "type_inference"
  import "bpsw_monodromy"

  func self_verify() type bool {
    let self_source: string = read_self_source()
    let tokens: List<Token> = tokenize(self_source)
    let ast: Program = parse(tokens)

    let syntax_ok: bool = verify_syntax(ast)
    let type_ok: bool = verify_types(ast)
    let theorem_ok: bool = verify_theorem(ast)

    assert syntax_ok && type_ok && theorem_ok
    return true
  }

  func main() type void {
    let result: bool = self_verify()
    assert result
    return
  }
}
```

---

## 11. Extended Syntax (H2–H16)

> **Status note**: All H2–H16 extensions are **parser-verified** (41/43 spike suite, 2026-11-12). Call them "syntax-level" — the type-checker/compiler backends for most are partial. Where a dedicated engine exists it is listed; where not, treat the feature as parse-only until the engine lands.

### 11.1 Effect System with Row Polymorphism (H2)

```svl
func f() type int !IO { return 42 }
func g() type int !{IO, State} { return 1 }
func h() type int !{IO, State, Exception} { return 0 }
```

- Effect annotations are **post-return-type**: `type int !E`.
- `!E` for a single effect row, `!{E1, E2}` for a row of effects.
- Covered in `svl/parser_rd.py` (effect grammar), no dedicated engine yet.

### 11.2 Linear / Uniqueness Types (H3)

```svl
func f(x: linear int) type int { return x }
func g(x: unique int) type int { return x }
func h(x: linear unique int) type int { return x }
```

- Qualifiers `linear` (use-once) and `unique` (no aliasing), composable.
- Region-based inference engine exists in `svl/linear_regions.py` (`RegionInferenceEngine`): `declare_variable`, `move_variable`, `borrow_variable`, `return_borrow` — tracks moved/borrowed state per function.

### 11.3 Dependent Types for Array Bounds (H4)

```svl
func f() type int {
  let v: vec<int, 10> = [1,2,3,4,5,6,7,8,9,10]
  return v[0]
}
func h() type int {
  let v: vec<vec<int, 3>, 2> = [[1,2,3],[4,5,6]]
  return v[0][0]
}
```

- `vec<T, N>` syntax with a literal bound `N`; nested `vec<vec<T,N>,M>` supported.
- Bound checking as a proof obligation is **not yet** wired into the theorem layer.

### 11.4 Gradual Typing with Blame (H5)

```svl
let x: ? = 42
let y: ? = 42 as int
let z: ? = 42 as ?
```

- `?` is the dynamic type. `as` casts carry optional blame labels; runtime cast-checking is not implemented (parse-level).

### 11.5 Macro System (H6)

```svl
macro m { x => x + 1; y => y * 2 }
macro myvec { x => [x] }
```

- Macro definitions are parsed with `macro NAME { pat => expansion; ... }`. Hygienic expansion is not yet implemented.

### 11.6 Module Functors (H7)

```svl
module type Ordered {
  func cmp(a: int, b: int) type int { return 0 }
}
module functor Map(Ord: Ordered) {
  type map = int
}
```

- `module type SIG { }` signatures + `module functor F(P: SIG) { }` functors parse; application/instantiation not yet implemented.

### 11.7 Algebraic Effects with Handlers (H8)

```svl
effect IO { read() -> string; write(s: string) -> void }
effect State { get() -> int; set(v: int) -> void }
effect Exception { raise(msg: string) -> void }
```

- Effect declarations parse; handler compilation to WASM is not yet implemented.

### 11.8 Type Classes with Coherence (H9)

```svl
class Eq a where { eq(a: a, b: a) -> bool }
instance Eq int { eq(a: int, b: int) -> bool { return a == b } }
class Ord a where { cmp(a: a, b: a) -> int }
```

- Classes and instances parse; coherence checking not yet implemented.

### 11.9 Higher-Kinded Types (H10)

```svl
func f() type * { return 0 }
func g(x: *) type * { return x }
```

- `*` (kind star) accepted in type position via the HKT patch (`parse_type_expr` accepts both `KIND_STAR` and `STAR`).
- Dedicated kind inference engine in `svl/kind_inference.py`: `KindExpr` (`star`, `arrow`, `row`), `KindInference` (`infer_kind`, `unify_kinds`, `generalize_kind`), `check_hkt_application`.

### 11.10 Refinement Types (H11)

```svl
func f(x: { v: int | v > 0 }) type int { return x }
func g(x: { v: int | v < 100 }) type int { return x }
```

- Refinement syntax `{ v: T | P }` parses; predicate solving (SMT-backed) is not yet wired.

### 11.11 Intersection and Union Types (H12)

```svl
func f(x: int & string) type int { return 0 }
func g(x: int | string) type int { return 0 }
func h(x: int & string | bool) type int { return 0 }   // chains
```

- `&` intersection and `|` union in type position are **fully parsed** (implemented 2026-11-11): `parse_type_expr()` is a wrapper over `_parse_type_expr_atom()` that loops on `BITWISE_AND`/`BITWISE_OR` and builds `TypeExpr` nodes with `kind='intersection'` / `kind='union'` (`value={'left': ..., 'right': ...}`).
- Subtyping/type-checker rules are not yet implemented; serialization covers the new nodes via the generic `TypeExpr` path.
- **Pitfall**: refinement base types must be parsed with `_parse_type_expr_atom()` — using the union wrapper there would consume the `|` inside `{ v: int | v > 0 }`.

### 11.12 Quantified Constraints (H13)

```svl
func f() type forall a. Int => a { return 0 }
```

- `forall a. Constraint => T` quantified constraint syntax parses.

### 11.13 Type-Level Computation / Type Families (H14)

```python
from svl.type_families import TypeFamilyEngine, TypeFamilyDecl, TypeFamilyEquation
from svl.parser_rd import NodeType, TypeExpr

def type_expr(kind, value):   # small helper: build a TypeExpr
    return TypeExpr(type=NodeType.TYPE_EXPR, line=1, column=1, offset=0, kind=kind, value=value)

def prim(name): return type_expr('prim', name)

engine = TypeFamilyEngine()
# Builtin declarations ('List', 'Maybe', 'Tuple') have EMPTY equation sets —
# declaring them registers the names but evaluate() returns None for them.
# A family only computes once it has equations:
fam = TypeFamilyDecl(
    name='Elem',
    params=['a'],
    equations=[TypeFamilyEquation(
        lhs={'name': 'Elem', 'args': [{'name': 'List', 'args': ['a']}]},
        rhs=prim('a'),
        constraints=[],
    )],
    is_open=False,
)
engine.declare_family(fam)
list_of_int = type_expr('generic', {'name': 'List', 'args': [prim('int')]})
result = engine.evaluate('Elem', [list_of_int])   # -> prim 'a'
```

- Engine: `TypeFamilyEngine.declare_family() / evaluate(family_name, args)` where `args: List[TypeExpr]` (NOT strings — passing `['int']` raises `AttributeError`).
- `TypeFamilyParser` parses `TypeFamilyDecl`/`TypeFamilyEquation` declarations; `parse_type_family_decl` CLI entry point.
- **Pitfall**: `create_builtin_families()` registers 3 names but ships **zero equations** — evaluation against them always returns `None`. Use your own declared families with `TypeFamilyEquation` entries.

### 11.14 Modal Types for Staging (H16)

```svl
func f(x: box int) type box int { return x }
func g(x: diamond int) type diamond int { return x }
```

- `box`/`diamond` modality syntax parses; staging semantics not yet implemented.

---

## 12. Verification Extensions (H17–H24, H38–H40)

### 12.1 SMT-Based Theorem Layer (H17/H19)

`svl/smt_theorem.py` — Z3-backed theorem checking with graceful fallback to BPSW.

```python
from svl.smt_theorem import SMTTheoremLayer, verify_with_smt, verify_with_smt_or_bpsw
from svl.theorem_layer import verify_theorem_layer
result = verify_theorem_layer(source)
print(f'Theorem: {result.passed}, SMT: {result.smt_verified}')
```

- Logics: QF_LIA, QF_NIA, QF_BV, LIA, NIA, BV, AUFLIA (`SMTLogic`, `SMTConfig`).
- Symbolic execution / counterexample generation framework (H19) lives in the same module.
- `verify_with_smt_or_bpsw()` runs SMT first and falls back to BPSW only on failure/unavailability.
- **Pitfall**: only run SMT after BPSW passes — it is additive, not a replacement.

**What it models (2026-11-12):** straight-line `+ - *` and comparisons, `if`/`else`, **arrays**
(z3 `Array`: literals, `zeros(n)`, `a[i]` read/write, `len`), compound assignment
(`+= -= *=`), and **loops with invariants**.

**Loop invariants are proposed and then PROVED before use.** For `while i < n { ... i += 1 }`
the layer proposes `i <= n` from the condition plus `i >= <initialiser>`; it then asks Z3
for (a) entry — the invariant holds on the state that reaches the loop, and (b) preservation
— assuming the invariant and the condition, one body execution re-establishes it. Only if
both are `unsat` is the invariant used. If either fails, the loop is reported as
`unverified`, exactly as before. Nothing is assumed without a proof.

```python
from svl.smt_theorem import verify_with_smt
r = verify_with_smt('module t { func main() type int {'
                    ' let i = 0 while i < 10 { i += 1 }'
                    ' assert i == 10 return 0 } }')
print(r.status)          # 'proven'
r = verify_with_smt('module t { func main() type int {'
                    ' let i = 0 while i < 10 { i += 1 }'
                    ' assert i == 5 return 0 } }')
print(r.status, r.counterexamples[0]['counterexample'])   # counterexample {'i__loop1b': 10}
```

**Honest limits:** nested loops, iterator (`for x in xs`) loops, and non-integer bounds are
declined. A variable the loop modifies that the invariant does **not** constrain (an
accumulator such as `s += i`) is marked *stale*: an assertion mentioning it after the loop
is reported as `unverified`, never discharged against an unconstrained value — a spurious
counterexample is worse than no answer.

### 12.2 Incremental 231-Gate Checksums (H18)

`svl/incremental_checksum.py` — O(1)-style incremental update of the 231-gate triple.

```python
from svl.incremental_checksum import IncrementalChecksum
ic = IncrementalChecksum()
for byte in b"Hello, World! ":
    ic.append_byte(byte)
ic.update_byte(0, ord('J'))        # in-place edit, checksums recomputed incrementally
print(ic.get_checksums())          # (SUM, LINEAR, ROLLING) mod 231
```

- `IncrementalChecksumManager` tracks checksums per buffer for IDE-style feedback.

### 12.3 Proof-Carrying Code for WASM (H20)

`svl/pcc_wasm.py` — embeds verification proofs as WASM custom sections.

```python
from svl.pcc_wasm import PCCWasmGenerator, verify_pcc_wasm, extract_proofs_from_wasm

gen = PCCWasmGenerator()
module = gen.generate(source, deterministic=True)     # or generate_from_ast(ast)
pcc_wasm_text = module.to_wasm_with_proofs()          # WASM incl. proof custom section
ok_local = module.verify_proofs()                     # self-check embedded proofs
ok, errors = verify_pcc_wasm(pcc_wasm_text, source)   # re-checks embedded proof externally
proofs = extract_proofs_from_wasm(pcc_wasm_text)      # -> dict of extracted proof artifacts
```

- `PCCWasmGenerator` produces `PCCWasmModule` with a `WasmCustomSection`; `verify_pcc_wasm(wasm_text, source)` re-checks the embedded proof against the source.
- **Pitfall**: the module's output method is `to_wasm_with_proofs()` (not `to_wasm_text`).

### 12.4 Abstract Interpretation for the Type Layer (H21)

`svl/abstract_interpretation.py` — interval + congruence domains with widening/narrowing.

```python
from svl.abstract_interpretation import AbstractInterpreter, IntervalDomain, CongruenceDomain
from svl.abstract_interpretation import create_type_analysis_domain, analyze_type_bounds
```

- Domains: `Interval` (overflow/div-by-zero), `Congruence` (modular invariants), `ProductDomain` (combined).
- Entry points: `analyze_type_bounds(ast)` (warning dict for bounds/overflow/div-zero), `AbstractInterpreter(domain).analyze_program(ast)`.
- **Pitfall**: both entry points take a **parsed AST** (`Program`), not source text.

### 12.5 Differential Verification (H22) & Semantic Diff (H39)

```python
from svl.differential import DifferentialVerifier   # compares all 3 layers across versions
from svl.semantic_diff import SemanticDiffEngine    # AST-structural diff
```

- `differential.py`: layer-by-layer comparison, detects semantic changes even when both versions pass.
- `semantic_diff.py`: AST node diffing, type signature comparison, exported-symbol tracking.

### 12.6 Property-Based Testing (H38)

- Spike-verified integration of property testing alongside the verification suite; generators exercise parser/type/compiler pipelines.

### 12.7 Error Messages with Repair Suggestions (H40)

- **Basic error messages only** — repair suggestions are NOT implemented. The spike notes this explicitly, so don't promise auto-fix output.

---

## 13. Compiler Optimizations & Runtime (H25–H32)

**One optimization is on the compile path: tail-call optimization (H27).** The other six
hypotheses in this range — SIMD vectorization (H26), escape analysis (H28), WASM GC
(H25), PGO (H29), LTO (H30) and hot reloading (H32) — were standalone libraries the
compiler never called. They were **removed on 2026-11-12** rather than left as dead code
sustaining an "optimization stack" claim. The RL pass-selection compiler (H49) was removed
for the same reason: every one of its passes was a no-op.

### 13.1 Tail Call Optimization (H27) — WIRED

`compiler_wasm.py` lowers a tail `return f(args)` to a WASM `return_call` when **both**
hold:

* `f` is a function in the **same module** (host imports are not tail-called), and
* the callee's signature (params and results) is **identical** to the caller's.

Anything else falls back to a plain `call` + `return`. The signature guard is a correctness
requirement, not a heuristic: a mismatched `return_call` is invalid WAT.

```python
from svl.compiler_wasm import compile_file_to_wasm
wat = compile_file_to_wasm('''
module t {
  func fact(n: int, acc: int) type int {
    if n == 0 then { return acc }
    else { return fact(n - 1, n * acc) }
  }
  func main() type int { return fact(20000, 1) }
}
''')
assert 'return_call' in wat
```

**Verified by execution, not by text inspection**: the 20000-deep tail-recursive call
completes, while the non-tail form (`return n * fact(n - 1)`) traps with stack exhaustion
and is **not** rewritten. Spike H27 fails when `wasmtime` is unavailable rather than
passing by skipping.

### 13.2 AOT Compilation with Cranelift (H31) — STUB

Spike-verified: `wasmtime` is available in the environment. The AOT pipeline is a stub in
`smt_theorem.py`; treat it as **not implemented** — there is no production path.

### 13.3 What was removed, and why

| Module | What it actually was | Decision |
|---|---|---|
| `simd_vectorization.py` | placeholders: `_extract_loop_bounds` returned `(0, 100, 1)` regardless of the source; the emitter hard-coded a `sum` local and declared v128 values as `i32` locals, emitting invalid WAT. The H26 spike passed on a **text** check of the emitted ops and never assembled the module. | deleted; the vectorized path was removed from `compiler_wasm.py`, so `for i in 0..4 { s = s + a[i] * b[i] }` now compiles to a correct scalar loop (verified: 70) |
| `tco.py` | a heuristic tail-call analyzer with a duplicated `_find_calls` and no emitter | deleted; the real `return_call` lowering lives in the backend |
| `escape_analysis.py` | an analysis reporting which objects could be stack-allocated; the backend has no stack allocation, so nothing consumed it | deleted |
| `wasm_gc.py` | emitted GC type declarations that no instruction used; the backend models structs as raw memory | deleted, and the dead `generate_wasm_gc_types` / `lower_type_to_wasm_gc` were removed from the backend |
| `pgo.py` | `collect_profile()` returned an empty `ProfileData`; `optimize()` returned its input unchanged | deleted |
| `lto.py` | `_merge_modules` renamed functions with a naive text `replace`; `inline_functions` **deleted** small functions that were still called; exports were compared against function names | deleted |
| `hot_reload.py` | state-schema migration, not codegen; nothing on the compile path | deleted |
| `rl_compiler.py` | every pass (`inline`, `dce`, `const_fold`, `loop_unroll`, `licm`, `cse`) returned the module unchanged | deleted |

### 13.4 Type-directed lowering — the type layer drives codegen

`compiler_wasm.py` runs the type checker (`svl/type_lowering.py`) before emitting anything
and lowers from its inferred types:

| Decision | Source |
|---|---|
| local / parameter / global WASM valtype | annotation if present, else the inferred type (`int`→`i32`, `float`→`f64`) |
| `+ - * / %` and comparisons | inferred operand types → `f64.*` or `i32.*`; mixed int/float is a compile error |
| unary `-` on a float | `f64.neg` |
| struct field resolution | annotation, struct literal, or the inferred type of the local (`let q = p`) |
| un-annotated parameters | included in the signature with their inferred type (previously dropped) |

Before this, `let x = 1.5` emitted an **i32** local holding an `f64.const` — the text parsed
but the module failed validation — and `x + y` on two floats emitted `i32.add`. The mapping
is conservative: a type the checker cannot classify falls back to the previous `i32`
behaviour, so a program the checker cannot classify compiles exactly as before.

**Rule:** a module that cannot change the compiled artifact, and is documented as if it
does, is deleted rather than relabelled. Do not re-add one without wiring it into
`compile_file_to_wasm` and verifying the effect by assembling and **running** the output.

### 13.5 Lowerings added 2026-11-12 (panel-driven fixes)

| Lowering | Where | Effect |
|---|---|---|
| Scope-aware alpha-renaming | `svl/scope.py`, called from `compile_to_wasm` | every `let`/`for`/`catch` binding gets a unique local; an inner binding no longer overwrites an outer one |
| Array `for-in` | `_compile_for_stmt` | scans the `[len, e0..]` layout directly instead of the broken iterator protocol |
| Short-circuit `&&`/`||` | `_compile_binary_expr` | the right operand runs only when the left does not decide the result; the interval AI is short-circuit-aware |
| `memory.grow` + heap reset | `_generate_wasm_module` | allocating programs are re-runnable in one Store instead of trapping past a fixed 1 MiB |
| `try`/`catch`/`throw` | `_compile_try_stmt` / `_compile_throw_stmt` | error-flag lowering (WASM MVP has no exceptions) |
| `print` type dispatch | `_compile_call_expr` | `int`/`bool` → `print_int`; a string expression → `(ptr, len)` |
| Import linking | `compile_file_to_wasm(base_dir=...)` | resolves and links imported files; an inline `import` is rejected |
| ROLLING channel | `svl/gate231.py` | replaces the degenerate `Π(b+1)` PRODUCT with `H=(H*31+b) mod 231` |
| Free list | `$alloc` / `$free` (`free(ptr)`) | exact-size blocks are reclaimed and reused; the heap resets at the entry point |
| Non-array iterators | `_compile_for_stmt` | a non-range, non-array iterable is a clear compile error, not a silent no-op |
| `extern` host import | `ExternDecl` → `_collect_extern` → `(import "env" ...)` | `extern "c" func name(...)` is callable like any function (first FFI surface) |
| SMT on the compile path | `compile_file_to_wasm(..., prove=True)` | discharges every `assert` with Z3; raises `SVLVerificationError` on a counterexample |

---

## 14. Build & Tooling Ecosystem (H33–H35, H41–H48)

### 14.1 LSP with Tree-sitter Grammar (H33)

- `svl/tree_sitter_grammar.py`: `save_grammar_to_file()` writes `svl_grammar.json`; `generate_highlight_queries()` writes highlight queries. Works alongside the hand-written `lsp_server.py`.
- Regenerate after grammar changes: `python3 -m svl.tree_sitter_grammar` (exposes `save_grammar_to_file`).
- **Boot fix (2026-11-12):** handlers must be registered as the **unbound** functions
  (`server.feature(X)(SVLLanguageServer.method)`). Passing `server.method` gave
  `AttributeError: 'method' object has no attribute 'reg_name'` and the server died on boot.

### 14.2 Interactive Theorem Proving / Tactics (H34)

`svl/tactics.py` — tactic language for interactive proofs.

```python
from svl.tactics import TacticInterpreter, Goal, Intro, Assumption

interpreter = TacticInterpreter()
interpreter.start_proof(Goal(statement="A -> A", name="identity"), hypotheses=[])
interpreter.run_tactic(Intro())       # pushes hypothesis
interpreter.run_tactic(Assumption())  # closes goal from hypothesis
```

- Tactics: `Intro`, `Assumption`, `Apply`, `Exact`, `Simplify`, `Rewrite`, `Induction`, `Cases`, `Contradiction`, `Trivial` — plus lowercase helpers `intro()`, `assumption()`, `apply()`, `exact()`, ... that construct them.
- Combinators: `seq(t1, t2)`, `orelse(t1, t2)`, `repeat(n, t)`, `try_t(t)`.
- `TacticInterpreter` supports undo, save/load state, `get_goals()`/`get_hypotheses()`/`is_complete()`; `SVLTacticBridge` connects to the SVL theorem layer.

### 14.3 Time-Travel Debugging (H35)

`svl/time_travel.py` — deterministic execution recording and replay.

```python
from svl.time_travel import TimeTravelDebugger, DeterministicReplayer, ExecutionTrace

trace = ExecutionTrace(
    program_hash=b"\x00" * 32, start_time=0.0, end_time=1.0,
    events=[], initial_state={}, final_state={},
)
dbg = TimeTravelDebugger(trace)   # or load an existing one: ExecutionTrace.load(path)
dbg.step_forward(); dbg.step_backward(); dbg.jump_to(10)
dbg.set_breakpoint(instruction_ptr=0x1005)
dbg.set_watchpoint(address=0x2000)
dbg.replay_to_breakpoint()        # step until breakpoint/watchpoint
replayer = DeterministicReplayer(trace)
replayer.replay(start_idx=0, end_idx=-1, callback=print)      # full replay
replayer.replay_function("main", occurrence=0)                # call→return slice
bug = replayer.find_bug(lambda ev: ev.event_type == "trap")   # locate first trap
```

- `TimeTravelCLI`: `next`, `prev`, `jump`, `break`, `watch`, `continue`, `stack`, `info`, `event`, `list`, `help`.
- **Pitfalls**: optional event fields — use `getattr`/`get`; `get_current_event()` may be `None`.

### 14.4 FFI via Component Model (H41) & WIT Generation (H42)

`svl/component_model.py` — WIT generation + host bindings.

```python
from svl.component_model import WitGenerator, ComponentModelFFI, WitWorld, WitInterface, WitFunction

gen = WitGenerator()
interface = gen.generate_from_module('math', functions)   # list[dict] -> WitInterface
world = WitWorld(name='math', exports=[interface])
ffi = ComponentModelFFI()
rust = ffi.generate_host_bindings(world, 'rust')
```

- `wit_generation.py`: `generate_wit_file(program, path)`, `generate_wit_from_svl_source(source, path)`, `generate_wit_package(...)`, `validate_wit_syntax(...)`; `SVLWitGenerator.generate_from_program()`.

### 14.5 Package Registry with Verification (H43)

`svl/package_registry.py` — publish/verify with attestations (replaces the "not yet implemented" notes in §5.4/§7).

```python
from svl.package_registry import PackageRegistry, VerificationAttestation

reg = PackageRegistry(storage_path="~/.svl/registry")
reg.publish_package(package_path="pkg.tar.gz", metadata={...}, content_hash="sha256:...", signer_key_pem="...")
reg.verify_package("mypkg", "1.0.0", content=b"...", verifier_id="hermes")
reg.add_verification("mypkg", "1.0.0", content_hash="sha256:...", verifier_id="hermes",
                     signature="sig...", public_key="pk...")   # or revoke_verification(name, attestation_id)
```

- CLI: `python3 -m svl.package_registry publish ...` / `verify ...` via `PackageRegistryCLI`.

### 14.6 Incremental Compilation (H44)

`svl/incremental.py` — query-based incremental compiler (Salsa when available).

```python
from svl.incremental import create_incremental_compiler

compiler = create_incremental_compiler()
ast = compiler.get_ast("main.svl")             # caches parse by path + mtime
compiler.get_verified_ast("main.svl")          # syntax+type+theorem, cached
compiler.invalidate_file("main.svl")           # drop cache on edit
```

- `create_incremental_compiler()` returns **`IncrementalCompiler`** when Salsa is installed, **`FallbackIncrementalCompiler`** otherwise. Both expose `get_ast(path)` / `get_verified_ast(path)` / `invalidate_file(path)`.
- `get_wasm(path)` and `get_source(path)` exist **only on the Salsa-backed `IncrementalCompiler`**. Call `hasattr(compiler, 'get_wasm')` before using them, or handle the fallback.
- Query classes: `SourceFileQuery`, `ParsedASTQuery`, `TypeCheckedQuery`, `VerifiedQuery`, `CompiledWASMQuery`.

### 14.7 Distributed Build Cache (H45)

`svl/distributed_build.py` — content-addressed cache + REAPI-style remote execution.

```python
from svl.distributed_build import (DistributedBuildCache, ReapiClient,
                                   SVLBuildActionGenerator, LocalExecutor)

cache = DistributedBuildCache(local_cache_path="./.svl-cache", remote_client=ReapiClient(endpoint="grpc://build:50051"))
gen = SVLBuildActionGenerator(cache=cache)
action = gen.compile_module(source_path="src/main.svl", output_path="out/main.wasm", options={})
result = cache.get_or_execute(action)             # cache hit -> cached BuildArtifact
```

- `ContentAddressableStore` (put/get/has), `ReapiClient` (connect/execute/get_capabilities), `SVLBuildActionGenerator` actions: `compile_module`, `verify_module`, `run_tests`.
- `LocalExecutor(cache=cache)` runs actions locally where a remote isn't available; `DistributedBuildCache.get_stats()` reports hit rates.

### 14.8 LSIF for Code Navigation (H46)

`svl/lsif.py` — emits LSIF (Language Server Index Format) for cross-repo navigation.

```python
from svl.lsif import generate_lsif_for_svl, generate_lsif_for_program

generate_lsif_for_svl(source, file_path="src/main.svl", project_root=".", output_path="dump.lsif")
```

- `LsifEmitter.emit_program()` / `write_lsif()`; vertices for definitions, references, hover, monikers.

### 14.9 Docs Generation from Verification (H47)

`svl/docs_generation.py` — generate Markdown/HTML/JSON docs from verified programs.

```python
from svl.docs_generation import SVLDocGenerator, DocFormat, generate_verification_report

gen = SVLDocGenerator(include_verification=True)
project = gen.generate_from_program(ast)                    # DocProject (name, version, modules)
gen.write_docs(project, output_dir="./docs", formats=[DocFormat.MARKDOWN, DocFormat.HTML])
report = generate_verification_report(verification_result)  # verification metrics page
```

- `write_docs` formats are **`DocFormat` enum members**, not strings (`DocFormat.MARKDOWN`/`HTML`/`JSON`; defaults to all three). Files: `README.md`, `index.html`, `docs.json`.
- `DocSymbol`/`DocModule`/`DocProject` model the output; `to_markdown()`/`to_html()`/`to_json()` render individually.
- `extract_examples_from_verification()` pulls runnable examples from your test/verify suite.

### 14.10 Jupyter Kernel (H48)

`svl/jupyter_kernel.py` — IPython kernel protocol for SVL.

```bash
python3 -m svl.jupyter_kernel          # or use launch_kernel()
# then register: jupyter kernelspec install ...
```

- `SVLKernel.do_execute` / `do_complete` / `do_inspect` implement the messaging protocol; `SVLKernelConfig` controls verification-on-execute.

### 14.12 Verified Raft Consensus (H50)

`svl/raft.py` + `svl/raft_test.py` — deterministic Raft with leader election, log replication, verification.

```python
from svl.raft import create_raft_cluster, SVLRaftVerifier

cluster = create_raft_cluster(5)          # deterministic seeds
for i in range(50):
    cluster.step(0.1)
    if i % 20 == 0 and i > 0:
        cluster.submit_command({'op': 'set', 'key': f'key{i}', 'value': f'value{i}'})
leader = cluster.get_leader()
verifier = SVLRaftVerifier()
verifier.verify_election_safety(cluster)          # True
verifier.verify_log_matching(cluster)             # True
check = cluster.verify_cluster()                  # {'all_verified': True, ...}
```

- Partition handling: `cluster.partition([leader_id])` → `heal_partition()`; verified to elect a *new* leader in the majority side with fixed `PARTITION_SEED`.
- Persistence: `node.persist()` / `load_persisted()` round-trips term, voted_for, log.
- **Historical note**: the H50 spike previously failed with `NameError: name 'random' is not defined` (module-scope import bug in `spike_runner.py`, fixed 2026-11-11). All raft primitives + property verifiers pass.
- **Known limitation**: split-vote/election timeout tuning in minority partitions — use deterministic seeds; a pre-vote extension is the production hardening path.

---

## 15. Spike Suite Status

Run: `cd /home/sudosudo/.openclaw/workspace && python -m svl.spike_runner`

**Current (2026-11-12): 41 / 43 PASS (95.3%).** The set is 43 after the dead-optimization
removals; the two failures are the self-declared unimplemented stubs.

| Status | Spikes |
|--------|--------|
| ✅ PASS | H1–H24, H27 (real backend TCO), H31 (documented stub), H33–H35, H38–H48, H50 |
| ❌ NOT IMPLEMENTED | H36 Visual AST/Type Explorer |
| ❌ NOT IMPLEMENTED | H37 AI-Assisted Proof Search |
| ➖ REMOVED | H25, H26, H28, H29, H30, H32, H49 — dead libraries, deleted (see §13.3) |

H36 and H37 fail because they are genuinely unimplemented (spike notes: "Visual explorer not implemented" / "AI proof search not implemented") — not because of a bug.

**2026-11-11 fixes folded into this run:**
- H50 Raft spike: was failing on `NameError: name 'random' is not defined` (missing module-scope import) — raft logic itself always passed.
- H12 Intersection/Union: spike only tokenized, never parsed, while the parser had `pass` placeholders. Parser now implements `&`/`|` type expressions (`parse_type_expr()` wrapper over `_parse_type_expr_atom()`), and the spike actually parses.

---

## Appendix: Quick Reference

### ASCII Aliases (All Keywords)
```
let, if, then, else, while, for
func, return, match, type, struct, module
import, export, const, var, assert, try
catch, throw, async, await
in, fn, true, false, null
int, float, string, bool, void, never
```

### Extended Syntax Keywords (H2–H16)
```
effect, linear, unique, vec, macro, functor
class, instance, forall, box, diamond
```

### Operators
```
+ - * / %           # Arithmetic
== != < > <= >=     # Comparison
&& || !             # Logical
=                   # Assignment (in let)
->                  # Lambda arrow
=>                  # Match arrow
.                   # Field access
[]                  # Indexing
()                  # Call / grouping
& |                 # Intersection / union (type position, H12)
as                  # Cast (gradual typing, H5)
!E, !{E1,E2}        # Effect row suffix (H2)
```

### File Extensions
- `.svl` - Source files
- `.wat` - WASM text format
- `.wasm` - WASM binary
- `metadata.json` - Package metadata

---

*SVL Knowledge Base v0.2.1 | Generated from BUILD_PLAN_2_SELF_VERIFYING_LANGUAGE.md | Spike suite 41/43 PASS (2026-11-12)*