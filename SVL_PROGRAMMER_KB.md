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
14. [Build & Tooling Ecosystem (H33–H35, H41–H49)](#14-build--tooling-ecosystem-h33h35-h41h49)
15. [Spike Suite Status](#15-spike-suite-status)

---

## 1. Language Overview

### What is SVL?
SVL (Self-Verifying Language) is a programming language with **built-in three-layer verification** that runs automatically on every compilation:

| Layer | Name | Technology | Purpose |
|-------|------|------------|---------|
| **L1** | Syntax | 231-Gate Checksums | Structural integrity via SUM/LINEAR/PRODUCT mod 231 |
| **L2** | Types | Mod-5 Dual-Stream | Mod-5 buckets + Z/2 negation + structural checksums |
| **L3** | Theorem | BPSW Monodromy | Cryptographic verification via SHA256 + BPSW on primes {37,73,17} |

### Key Properties
- **22 tokens** mapped to Hebrew alphabet (א-ת)
- **Deterministic compilation** - bit-identical WASM output across runs
- **Self-hosting** - compiler written in SVL, bootstraps in 3 stages
- **Probabilistic theorem layer** - Genesis 1:1 (2701 = 37×73) passes by mathematical coincidence

### Target Platform
- **WASM (WebAssembly)** - runs in browsers, Node.js, wasmtime, wasmer
- **Linear memory model** - bump allocator, manual memory management
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
PRODUCT = (Π (byte[i] + 1)) mod 231  (0→1 mapping)
```

**Verification Gates**:
1. **AST Guard** - Forbids `sum()` on iterables (requires `neumaier_sum()`)
2. **Golden References** - Psalm 119 Aleph, Genesis 1:1
3. **Mutation Test** - 3+ injected corruptions must be caught
4. **Meta-Checksum** - `SUM ⊕ LINEAR ⊕ PRODUCT mod 231` for tamper detection

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
- Function imports — emitted **only when the module actually calls them** (an unused import still has to be
  supplied by the host, so emitting them unconditionally would force every host to stub functions it never
  uses): `env.print(i32,i32)`, `env.print_int(i32)`, `env.malloc(i32)->i32`,
  `env.iterator_next(i32)->i32`, `env.await(i32)->i32`
- Deterministic output with **no `PYTHONHASHSEED` pinning needed** (fixed function of the input)
- Export name `<module>_main`

### 5.3.1 What the WASM backend actually executes

"Compiles to WASM" means **wasmtime accepted and ran it**. Text-level checks cannot see invalid WAT or a
mis-executing loop, so verify by assembling (`wasmtime.wat2wasm` then `wasmtime.Module` — the `Module` is
what validates) and invoking the export.

Verified to assemble **and run** (2026-11-12):

| Feature | Probe | Result |
|---|---|---|
| `while` (incl. nested) | `while i<=5 { s+=i; i+=1 }` | 15 |
| `for` over a range | `for i in 0..5 { s+=i }` | 10 |
| `if…then…else` **expression** | `let r = if c then 10 else 20` with `c=0` | 20 |
| top-level `const`/`var` | `const one=1 const seven=7  return one+seven` | 8 |
| `assert` | `assert x==5` with `x=5` | no trap — and it **must** trap when false |
| `print` / `print_int` | `print("hi")` | assembles + calls the host |
| early `return` from inside `if`/`while` | — | runs cleanly |

Also working: `void` returns, helper calls, `+ - * %` on i32.

**Not** in the executable subset (parse-level only, or unimplemented): closures/`lambda`, `match`
expressions, struct/array literals + field/index access on real layout, `try`/`catch`, `async`/`await`,
SIMD emission for general loops, GC structs, generics at runtime.

**Pitfall — `%` is WASM's truncated remainder (sign of the dividend), not Python's floor modulo.**
`(-1) % 256` is `-1`, not `255`. Write arithmetic that keeps the operand non-negative.

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
// ✓ Good: Explicit types enable optimization
func add(x: int, y: int) type int { return x + y }

// ✗ Avoid: Implicit types (slower inference)
func add(x, y) { return x + y }

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
| `WASM compilation not deterministic` | A process-salted value leaked into a hashed path | Not expected any more — struct buckets use `sha256(name) % 5`, not `hash()`. Do **not** paper over this with `PYTHONHASHSEED=0`: find the salted input |
| `unknown local: failed to find name $x` | A reference to a name that is not a param/local/const | Fix the name (or declare it); the compiler raises a clear `Unknown identifier` error for this case |

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

> **Status note**: All H2–H16 extensions are **parser-verified** (48/50 spike suite, 2026-11-11). Call them "syntax-level" — the type-checker/compiler backends for most are partial. Where a dedicated engine exists it is listed; where not, treat the feature as parse-only until the engine lands.

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

### 12.2 Incremental 231-Gate Checksums (H18)

`svl/incremental_checksum.py` — O(1)-style incremental update of the 231-gate triple.

```python
from svl.incremental_checksum import IncrementalChecksum
ic = IncrementalChecksum()
for byte in b"Hello, World! ":
    ic.append_byte(byte)
ic.update_byte(0, ord('J'))        # in-place edit, checksums recomputed incrementally
print(ic.get_checksums())          # (SUM, LINEAR, PRODUCT) mod 231
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

### 13.1 SIMD Vectorization (H26)

`svl/simd_vectorization.py` — detects vectorizable loops and emits WASM SIMD.

```python
from svl.simd_vectorization import SimdVectorizer, run_simd_vectorization_pass, has_simd_instructions

wasm = compile_file_to_wasm(source)
print(has_simd_instructions(wasm))   # True if v128./i8x16./i16x8./i32x4./f32x4./f64x2. present
```

- `SimdVectorizer.analyze_program()` finds arithmetic loops; `SimdWasmEmitter.emit_vectorized_function()` emits `i32x4.*` etc.
- **Pitfall**: only `*` (mul) computations get SIMD in the reduction pass; nested `BinaryExpr`/`CallExpr`/`UnaryExpr` must be analyzed recursively or vectorization misses `a[i] * b[i]`.

### 13.2 Tail Call Optimization (H27)

```python
from svl.tco import run_tco_analysis   # returns list[TCOAnalysis]

results = run_tco_analysis("""
func fact(n: int, acc: int) type int {
  if n == 0 then { return acc }
  else { return fact(n - 1, n * acc) }
}
""")
# results[0].is_tail_recursive == True, optimization_possible == True
```

- `TCOAnalyzer.analyze_function()` detects tail-recursive calls; WASM `return_call` emission is prepared but not the default backend path.

### 13.3 Escape Analysis (H28)

`svl/escape_analysis.py` — stack allocation for non-escaping objects.

```python
from svl.escape_analysis import EscapeAnalyzer, run_escape_analysis, can_stack_allocate

infos = run_escape_analysis(ast)          # Dict[str, FunctionEscapeInfo] keyed by func name
info = infos['no_escape']                 # .allocations: list[AllocationSite]
ok = can_stack_allocate(ast, 'no_escape', 'p')
```

- `EscapeAnalyzer.analyze_program()` computes `EscapeState` per allocation site; `get_stack_allocatable()` / `get_heap_allocatable()`.

### 13.4 WASM GC Proposal Support (H25)

`svl/wasm_gc.py` — emits `struct`/`array` GC types with root management.

```python
from svl.wasm_gc import WASMGCManager
from svl.compiler_wasm import compile_file_to_wasm

manager = WASMGCManager()
manager.register_struct("Point", [("x", "i32"), ("y", "i32")])   # list of (name, type) tuples
manager.register_array("IntArray", "i32", mutable=True)
decls = manager.generate_type_decls()        # -> ["(type $Point ...)", "(type $IntArray ...)"]
wasm = compile_file_to_wasm(source)          # struct decls also emitted in WASM via the visitor
```

- `GCStructLayout` / `GCArrayLayout` model layouts; `generate_type_decls()` emits the `(type ...)` declarations.
- `WASMGCManager.compile_program_with_gc(program)` takes a **parsed AST program**; `compile_with_gc(program)` is the convenience wrapper.
- **Pitfall**: `register_struct` fields are `list[(name, type)]`, not a dict — passing `{"x": "i32"}` breaks layout order.

### 13.5 Profile-Guided Optimization (H29)

`svl/pgo.py` — instrument WASM, collect profiles, drive inlining/devirtualization.

```python
from svl.pgo import PGOPipeline, PGOOptimizer, ProfileData

pipeline = PGOPipeline('./profile_dir')
instrumented = pipeline.instrument(wasm_text)      # adds pgo_profile_count/edge/value/call
profile = pipeline.collect_profile(runs=3)         # runs instrumented code -> ProfileData
optimizer = PGOOptimizer(profile)                  # analysis is constructor-driven
hot = optimizer.get_hot_functions()                # PGOSummary-style hot function list
optimizer.should_inline(caller, callee)            # inlining decision
optimizer.should_devirtualize(call_site)           # devirtualization decision
wasm_opt = pipeline.optimize(wasm_text, profile)   # apply hot-path transforms
```

- **Pitfall**: instrumentation must add `pgo` module imports **before** function definitions or WASM validation fails.

### 13.6 Link-Time Optimization (H30)

`svl/lto.py` — parse WASM text, merge modules, DCE, duplicate-function elimination, inlining.

```python
from svl.lto import WASMParser, LTOOptimizer, LTOConfig, check_lto_tools

parser = WASMParser()
module_a = parser.parse(wasm_text_a)
module_b = parser.parse(wasm_text_b)
opt = LTOOptimizer(config=LTOConfig(enabled=True, opt_level=2, thin_lto=True, inline_threshold=250))
result = opt.optimize([module_a, module_b])        # merge + DCE + dedup + inline in one pass
merged_text = parser.to_text(result)               # -> merged WASM text
```

- `check_lto_tools()` detects `wat2wasm`/`wasm-ld`; if absent, falls back to merge-only mode.
- Lower-level passes are also exposed individually: `_merge_modules()` (renames funcs to `mod$func`, fixes call sites), `dead_code_elimination()` (reachability from exports), `merge_duplicate_functions()` (normalizes `$local_N`, compares bodies), `inline_functions()`.
- **Pitfall**: function renaming must update every call site; module name extraction must handle `(module $name "name")` and bare `(module)`.

### 13.7 AOT Compilation with Cranelift (H31)

- Spike-verified: `wasmtime` available in the environment; AOT pipeline is a stub in `smt_theorem.py` for going straight to native code. Treat as **stub** — no production path yet.

### 13.8 Hot Reloading with State Migration (H32)

`svl/hot_reload.py` — hot-swap modules while migrating live state.

```python
from svl.hot_reload import TypeSchema, StateMigrator, HotReloadManager, MigrationPlan

v1 = TypeSchema(name="Point", version=1, fields={"x": "int", "y": "int"}, field_order=["x", "y"])
v2 = TypeSchema(name="Point", version=2, fields={"x": "int", "y": "int", "z": "int"}, field_order=["x", "y", "z"])
v1.is_compatible_with(v2)          # True: only additions
v1.get_migration_plan(v2)          # MigrationPlan: keep x/y, add z with default
```

- `HotReloadManager` coordinates per-type state migration; `StateMigrator` applies keep/transform/remove/add.
- **Pitfall**: extract per-type state with `old_state.get(type_name, {})` before migrating or you get `None` fields.

---

## 14. Build & Tooling Ecosystem (H33–H35, H41–H49)

### 14.1 LSP with Tree-sitter Grammar (H33)

- `svl/tree_sitter_grammar.py`: `save_grammar_to_file()` writes `svl_grammar.json`; `generate_highlight_queries()` writes highlight queries. Works alongside the hand-written `lsp_server.py`.
- Regenerate after grammar changes: `python3 -m svl.tree_sitter_grammar` (exposes `save_grammar_to_file`).

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

### 14.11 Self-Optimizing Compiler (RL) (H49)

`svl/rl_compiler.py` — Q-learning pass selection with replay buffer.

```python
from svl.rl_compiler import RLAgent, ReplayBuffer, SelfOptimizingCompiler

agent = RLAgent(...)                     # linear Q-network: Q(s,a) = w_a^T * phi(s)
compiler = SelfOptimizingCompiler(agent)
compiler.train(steps=100)                # reward = log(speedup)*w + size_reduction*w - penalties
wasm = compiler.compile(source)          # agent picks passes
```

- **Pitfall**: `ReplayBuffer.push` must build the tuple before appending (`buffer.append((s,a,r,s2,d))`, never `append(None)`).

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

Run: `python -m svl.spike_runner` (from the repo root)

**Current (2026-11-11): 48/50 PASS (96%)**

| Status | Spikes |
|--------|--------|
| ✅ PASS | H1–H35 (all parser/engine/runtime features) |
| ✅ PASS | H38–H49 (property testing, semantic diff, component model, WIT, registry, incremental, distributed build, LSIF, docs, Jupyter, RL) |
| ✅ PASS | H50 (Raft, after import fix) |
| ❌ NOT IMPLEMENTED | H36 Visual AST/Type Explorer |
| ❌ NOT IMPLEMENTED | H37 AI-Assisted Proof Search |

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

*SVL Knowledge Base v0.2.0 | Generated from BUILD_PLAN_2_SELF_VERIFYING_LANGUAGE.md | Spike suite 48/50 PASS (2026-11-11)*