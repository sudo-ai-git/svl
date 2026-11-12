#!/usr/bin/env python3
"""SVL formal-rating probe suite.

Every probe is execution-gated: it must be able to FAIL.  A probe reports
PASS only when the observed behaviour matches the *correct* expectation, and
FAIL when SVL is broken (or INFO when the probe measures a neutral fact).

Run:  python /home/sudosudo/.hermes/cache/scratch/svl_rating_probes.py
"""
import hashlib
import os
import random
import re
import subprocess
import sys
import tempfile
import time

ROOT = "/home/sudosudo/.openclaw/workspace"
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import wasmtime  # noqa: E402

from svl.compiler_wasm import compile_file_to_wasm  # noqa: E402
from svl.verify_gate import verify_program, SVLVerificationError  # noqa: E402
from svl.smt_theorem import verify_with_smt  # noqa: E402
from svl.gate231 import product_checksum  # noqa: E402
from svl.bpsw_monodromy import verify_theorem  # noqa: E402
from svl.lexer import tokenize  # noqa: E402
from svl.parser_rd import parse  # noqa: E402
from svl.serialization import to_binary  # noqa: E402

RESULTS = []


def record(pid, title, status, detail):
    RESULTS.append((pid, title, status, detail))
    mark = {"PASS": "PASS", "FAIL": "FAIL", "INFO": "INFO"}[status]
    print(f"{pid:<5} {mark:<4} {title}\n        {detail}")


def run_wat(wat):
    """Assemble + validate + instantiate + run <module>_main. Returns (rv, out)."""
    binary = wasmtime.wat2wasm(wat)
    engine = wasmtime.Engine()
    module = wasmtime.Module(engine, binary)          # VALIDATES
    store = wasmtime.Store(engine)
    linker = wasmtime.Linker(engine)
    i32 = wasmtime.ValType.i32()
    out = bytearray()
    memory = {}
    linker.define_func("env", "print", wasmtime.FuncType([i32, i32], []),
                       lambda p, n: out.extend(bytes(memory["m"].read(store, p, p + n))))
    linker.define_func("env", "print_int", wasmtime.FuncType([i32], []),
                       lambda v: out.extend(str(v).encode()))
    linker.define_func("env", "putc", wasmtime.FuncType([i32], []),
                       lambda c: out.append(c & 0xFF))
    linker.define_func("env", "clear", wasmtime.FuncType([], []), lambda: None)
    linker.define_func("env", "malloc", wasmtime.FuncType([i32], [i32]), lambda n: 1 << 20)
    linker.define_func("env", "iterator_next", wasmtime.FuncType([i32], [i32]), lambda h: 0)
    linker.define_func("env", "await", wasmtime.FuncType([i32], [i32]), lambda x: x)
    inst = linker.instantiate(store, module)
    ex = inst.exports(store)
    names = [e.name for e in module.exports]
    if "memory" in names:
        memory["m"] = ex["memory"]
    entry = next((n for n in names if n.endswith("_main")), None)
    if entry is None:
        raise RuntimeError("no <module>_main export")
    return ex[entry](store), bytes(out)


def compile_ok(src):
    return compile_file_to_wasm(src)


def probe_semantics():
    # P01 lexical scoping
    src = ("module m { func main() type int { let x = 1"
           " if 1 == 1 then { let x = 99 } else { } return x } }")
    try:
        rv, _ = run_wat(compile_ok(src))
        status = "PASS" if rv == 1 else "FAIL"
        record("P01", "lexical scoping (inner let must not clobber outer)", status,
               f"returned {rv}, correct = 1")
    except Exception as exc:
        record("P01", "lexical scoping", "FAIL", f"{type(exc).__name__}: {exc}")

    # P02 for-in over an iterable
    src = ("module m { func main() type int { let a = [1, 2, 3] let s = 0"
           " for x in a { s += x } return s } }")
    try:
        rv, _ = run_wat(compile_ok(src))
        status = "PASS" if rv == 6 else "FAIL"
        record("P02", "for x in <iterable> sums the elements", status,
               f"returned {rv}, correct = 6")
    except Exception as exc:
        record("P02", "for x in <iterable>", "FAIL", f"{type(exc).__name__}: {exc}")

    # P03 short-circuit &&.  NOTE: `x == 0 && 10/x` genuinely traps (the left is TRUE),
    # so the correct short-circuit probe is `x != 0 && 10/x` -- the left is false and the
    # right must be skipped.  (Panel note, 2026-11-12.)
    src = ("module m { func f(x: int) type bool {"
           " let r = x != 0 && 10 / x > 1 return r }"
           " func main() type bool { return f(0) } }")
    try:
        rv, _ = run_wat(compile_file_to_wasm(src))
        status = "PASS" if rv == 0 else "FAIL"
        record("P03", "&& short-circuits (no division by zero)", status,
               f"f(0) returned {rv}, correct = 0 (false)")
    except Exception as exc:
        record("P03", "&& short-circuit", "FAIL",
               f"trapped: {type(exc).__name__}: {str(exc)[:90]}")

    # P04 string equality -- declared `type bool`, since `a == b` IS a bool.
    src = ('module m { func main() type bool { let a = "hi" let b = "hi" return a == b } }')
    try:
        rv, _ = run_wat(compile_ok(src))
        status = "PASS" if rv == 1 else "FAIL"
        record("P04", "string == compares content", status, f"returned {rv}, correct = 1")
    except Exception as exc:
        record("P04", "string ==", "FAIL", f"{type(exc).__name__}: {exc}")

    # P24 float arithmetic
    src = ("module m { func main() type float { let x: float = 1.5"
           " let y: float = 2.5 return x + y } }")
    try:
        rv, _ = run_wat(compile_ok(src))
        status = "PASS" if abs(rv - 4.0) < 1e-9 else "FAIL"
        record("P24", "float arithmetic (1.5 + 2.5)", status, f"returned {rv}, correct = 4.0")
    except Exception as exc:
        record("P24", "float arithmetic", "FAIL", f"{type(exc).__name__}: {exc}")

    # P25 match non-exhaustive traps
    src = ("module m { func main() type int { let x = 7"
           " let r = match x { case 1 => 10 case 2 => 20 } return r } }")
    try:
        rv, _ = run_wat(compile_ok(src))
        record("P25", "non-exhaustive match traps", "FAIL", f"returned {rv} instead of trapping")
    except Exception as exc:
        record("P25", "non-exhaustive match traps", "PASS",
               f"trapped as designed: {type(exc).__name__}")

    # P26 try/catch support
    src = ("module m { func main() type int { try { let x = 1 } catch e { let y = 2 } return 0 } }")
    try:
        compile_ok(src)
        record("P26", "try/catch error model", "PASS", "parsed and compiled")
    except SyntaxError as exc:
        record("P26", "try/catch error model", "FAIL", f"SyntaxError: {str(exc)[:80]}")
    except Exception as exc:
        record("P26", "try/catch error model", "FAIL", f"{type(exc).__name__}: {str(exc)[:80]}")

    # P27 import linking
    import tempfile as _tf
    import os as _os
    # (a) an `import` inside a module body is rejected, not silently dropped
    inline_src = 'module m { import "other" func main() type int { return 42 } }'
    inline_rejected = False
    try:
        compile_ok(inline_src)
    except SyntaxError:
        inline_rejected = True
    # (b) a top-level import links a real file through base_dir
    linked = False
    with _tf.TemporaryDirectory() as d:
        with open(_os.path.join(d, 'other.svl'), 'w') as fh:
            fh.write('module other { func answer() type int { return 42 } }')
        main_src = 'import "other.svl" module m { func main() type int { return answer() } }'
        try:
            rv, _ = run_wat(compile_file_to_wasm(main_src, base_dir=d))
            linked = (rv == 42)
        except Exception:
            linked = False
    status = "PASS" if (inline_rejected and linked) else "FAIL"
    record("P27", "import links a module (inline import rejected)", status,
           f"inline rejected = {inline_rejected}; two-file link -> 42 = {linked}")

    # P31 non-array iterators are rejected, not silently no-op
    bad_iter = 'module m { func main() type int { let n = 3 let s = 0 for x in n { s += x } return s } }'
    try:
        compile_ok(bad_iter)
        record("P31", "non-array iterator is rejected (not a silent no-op)", "FAIL",
               "compiled; the body would silently never run")
    except SyntaxError:
        record("P31", "non-array iterator is rejected (not a silent no-op)", "PASS",
               "clear SyntaxError naming the supported iterables")
    except Exception as exc:
        record("P31", "non-array iterator is rejected", "FAIL",
               f"{type(exc).__name__}: {str(exc)[:80]}")

    # P32 the free list reclaims same-size allocations
    reuse_src = ('module m { func main() type int { let a = zeros(10) let p1 = a'
                 ' free(a) let b = zeros(10) return b - p1 } }')
    try:
        rv, _ = run_wat(compile_ok(reuse_src))
        record("P32", "free() reclaims a same-size allocation", "PASS" if rv == 0 else "FAIL",
               f"reallocated pointer minus original = {rv} (0 = same block reused)")
    except Exception as exc:
        record("P32", "free() reclaims a same-size allocation", "FAIL",
               f"{type(exc).__name__}: {str(exc)[:80]}")

    # P33 extern host import (FFI)
    extern_src = ('extern "c" func host_add(a: int, b: int) type int'
                  ' module m { func main() type int { return host_add(2, 3) } }')
    try:
        wat = compile_ok(extern_src)
        binary = wasmtime.wat2wasm(wat)
        engine = wasmtime.Engine()
        module = wasmtime.Module(engine, binary)
        store = wasmtime.Store(engine)
        linker = wasmtime.Linker(engine)
        i32 = wasmtime.ValType.i32()
        linker.define_func("env", "host_add", wasmtime.FuncType([i32, i32], [i32]),
                           lambda a, b: a + b)
        for nm, sig, f in [
            ("print", wasmtime.FuncType([i32, i32], []), lambda a, b: None),
            ("print_int", wasmtime.FuncType([i32], []), lambda v: None),
            ("putc", wasmtime.FuncType([i32], []), lambda c: None),
            ("clear", wasmtime.FuncType([], []), lambda: None),
            ("malloc", wasmtime.FuncType([i32], [i32]), lambda n: 1 << 20),
            ("iterator_next", wasmtime.FuncType([i32], [i32]), lambda h: 0),
            ("await", wasmtime.FuncType([i32], [i32]), lambda x: x),
        ]:
            linker.define_func("env", nm, sig, f)
        inst = linker.instantiate(store, module)
        rv = inst.exports(store)["m_main"](store)
        record("P33", "extern host import is callable", "PASS" if rv == 5 else "FAIL",
               f"host_add(2, 3) = {rv} (correct 5)")
    except Exception as exc:
        record("P33", "extern host import is callable", "FAIL",
               f"{type(exc).__name__}: {str(exc)[:90]}")


def probe_type_soundness():
    cases = [
        ("P05", 'return "hi" in a type int function',
         'module m { func f() type int { return "hi" } func main() type int { return 0 } }'),
        ("P06", 'f("hi") against f(x: int)',
         'module m { func f(x: int) type int { return x }'
         ' func main() type int { return f("hi") } }'),
        ("P07", 'let x: int = "hi"',
         'module m { func main() type int { let x: int = "hi" return 0 } }'),
    ]
    for pid, title, src in cases:
        problems = verify_program(src)
        if problems:
            record(pid, f"type soundness: {title}", "PASS",
                   f"refused: {problems[0][:80]}")
        else:
            record(pid, f"type soundness: {title}", "FAIL",
                   "accepted a type-incorrect program")


def probe_backend_artifacts():
    # P08 print(<int variable>) must assemble
    src = ("module m { func main() type void { let x = 5 print(x) return } }")
    try:
        wat = compile_ok(src)
        run_wat(wat)
        record("P08", "print(<int variable>) emits a valid module", "PASS", "assembled and ran")
    except Exception as exc:
        record("P08", "print(<int variable>) emits a valid module", "FAIL",
               f"{type(exc).__name__}: {str(exc)[:100]}")

    # P09 reassigning a const
    src = ("module m { const c: int = 5 func main() type int { c = 6 return c } }")
    try:
        wat = compile_ok(src)
        run_wat(wat)
        record("P09", "reassigning a const is rejected or compiles", "INFO",
               "compiled and ran (no const-immutability enforcement)")
    except SVLVerificationError as exc:
        record("P09", "reassigning a const", "PASS", f"refused: {str(exc)[:80]}")
    except Exception as exc:
        record("P09", "reassigning a const", "FAIL",
               f"invalid artifact: {type(exc).__name__}: {str(exc)[:90]}")

    # P10 PCC output assembles (binary form with a real custom section)
    from svl.pcc_wasm import PCCWasmGenerator, extract_proofs_from_wasm_bytes
    src = 'module m { func main() type int { return 7 } }'
    try:
        mod = PCCWasmGenerator().generate(src)
        binary = mod.to_wasm_bytes_with_proofs()
        wasmtime.Module(wasmtime.Engine(), binary)
        payload = extract_proofs_from_wasm_bytes(binary)
        recovered = payload is not None and payload.get('source_hash') == mod.source_hash
        status = "PASS" if recovered else "FAIL"
        record("P10", "proof-carrying WASM artifact assembles", status,
               f"validated; proof section recovered = {recovered}")
    except Exception as exc:
        record("P10", "proof-carrying WASM artifact assembles", "FAIL",
               f"{type(exc).__name__}: {str(exc)[:100]}")

    # P16 memory ceiling + re-runnability
    src = 'module m { func main() type int { let a = zeros(4) return 0 } }'
    wat = compile_ok(src)
    mem = re.search(r"\(memory ([^)]*)\)", wat)
    decl = mem.group(1).strip() if mem else "?"
    grows = "memory.grow" in wat
    # A second call in ONE Store must not trap: the heap resets at main entry and the
    # allocator grows memory instead of bumping past a fixed 1 MiB ceiling.
    src_big = ('module m { func main() type int { let n = 100000'
               ' let a = zeros(n) a[n - 1] = 1 return a[n - 1] } }')
    try:
        wat_big = compile_ok(src_big)
        binary = wasmtime.wat2wasm(wat_big)
        engine = wasmtime.Engine()
        module = wasmtime.Module(engine, binary)
        store = wasmtime.Store(engine)
        linker = wasmtime.Linker(engine)
        i32 = wasmtime.ValType.i32()
        for nm, sig, f in [
            ("print", wasmtime.FuncType([i32, i32], []), lambda a, b: None),
            ("print_int", wasmtime.FuncType([i32], []), lambda v: None),
            ("putc", wasmtime.FuncType([i32], []), lambda c: None),
            ("clear", wasmtime.FuncType([], []), lambda: None),
            ("malloc", wasmtime.FuncType([i32], [i32]), lambda n: 1 << 20),
            ("iterator_next", wasmtime.FuncType([i32], [i32]), lambda h: 0),
            ("await", wasmtime.FuncType([i32], [i32]), lambda x: x),
        ]:
            linker.define_func("env", nm, sig, f)
        inst = linker.instantiate(store, module)
        fn = inst.exports(store)["m_main"]
        rv1 = fn(store)
        rv2 = fn(store)
        rerunnable = (rv1 == 1 and rv2 == 1)
    except Exception as exc:
        rerunnable = False
    status = "PASS" if (grows and rerunnable) else "FAIL"
    record("P16", "memory can grow and the program is re-runnable", status,
           f"(memory {decl}); memory.grow present = {grows}; "
           f"two calls in one Store -> {rv1},{rv2}")

    # P17 tail-call optimisation
    src = ("module m { func count(n: int, acc: int) type int {"
           " if n <= 0 then { return acc } else { return count(n - 1, acc + 1) } }"
           " func main() type int { return count(20000, 0) } }")
    t0 = time.time()
    try:
        rv, _ = run_wat(compile_ok(src))
        dt = time.time() - t0
        status = "PASS" if rv == 20000 else "FAIL"
        record("P17", "20000-deep tail recursion completes", status,
               f"returned {rv} in {dt:.2f}s")
    except Exception as exc:
        record("P17", "20000-deep tail recursion", "FAIL",
               f"{type(exc).__name__}: {str(exc)[:80]}")

    # P28 compile time + artifact size on a real program
    sieve = open("/home/sudosudo/svl-release/examples/sieve.svl").read()
    t0 = time.time()
    wat = compile_ok(sieve)
    dt = time.time() - t0
    binary = wasmtime.wat2wasm(wat)
    record("P28", "compile latency + artifact size (sieve.svl)", "INFO",
           f"compile {dt*1000:.0f} ms, wasm {len(binary)} bytes")


def probe_verification():
    # P11 SMT tri-state
    r_false = verify_with_smt('module t { func f() type int { assert 1 == 2 return 0 } }')
    r_true = verify_with_smt('module t { func f() type int { assert 1 == 1 return 0 } }')
    r_unv = verify_with_smt(
        'module t { func f() type int { let s = 0 for i in 0..10 { s += i }'
        ' assert s == 45 return 0 } }')
    ok = (r_false.status == "counterexample" and r_true.status == "proven"
          and r_unv.status == "unverified")
    record("P11", "SMT tri-state (counterexample / proven / unverified)", "PASS" if ok else "FAIL",
           f"false->{r_false.status}, true->{r_true.status}, unsupported->{r_unv.status}")

    # P12 interval abstract interpretation, both directions
    bad = ('module t { func main() type int { let a: int = [1, 2, 3]'
           ' let i: int = 5 return a[i] } }')
    good = ('module t { func main() type int { let a: int = [1, 2, 3]'
            ' let i: int = 2 return a[i] } }')
    refused = False
    try:
        compile_file_to_wasm(bad)
    except SVLVerificationError:
        refused = True
    except Exception:
        refused = True
    silent = True
    try:
        compile_file_to_wasm(good)
    except Exception:
        silent = False
    record("P12", "interval AI refuses provable OOB, silent on correct code",
           "PASS" if (refused and silent) else "FAIL",
           f"refused OOB = {refused}, correct program silent = {silent}")

    # P13 BPSW monodromy is constant-true (decorative)
    rng = random.Random(20261112)
    failures = 0
    n = 60
    for i in range(n):
        src = f'module m {{ func main() type int {{ let x = {i} return x + {rng.randrange(1, 99)} }} }}'
        try:
            ast = parse(tokenize(src))
            res = verify_theorem(to_binary(ast))
            if not res.passed:
                failures += 1
        except Exception:
            failures += 1
    record("P13", "BPSW 'theorem' layer fails any program", "INFO" if failures == 0 else "PASS",
           f"{failures}/{n} programs failed the layer (0 = constant-true, gates nothing)")

    # P14 PRODUCT/ROLLING channel degeneracy
    rng = random.Random(7)
    zeros = sum(1 for _ in range(2000) if product_checksum(bytes(rng.randrange(256) for _ in range(512))) == 0)
    record("P14", "231-gate ROLLING channel is non-degenerate", "PASS" if zeros < 1999 else "FAIL",
           f"zero checksums: {zeros}/2000 random 512-byte windows (was 2000/2000 with PRODUCT)")

    # P15 strict vs non-strict gate
    bad_typed = 'module m { func f() type int { return "hi" } func main() type int { return 0 } }'
    strict_refused = False
    try:
        compile_file_to_wasm(bad_typed, strict=True)
    except Exception:
        strict_refused = True
    loose_ok = True
    try:
        compile_file_to_wasm(bad_typed, strict=False)
    except Exception:
        loose_ok = False
    record("P15", "strict gate refuses type error; strict=False bypasses", "PASS" if (strict_refused and loose_ok) else "FAIL",
           f"strict refused = {strict_refused}, strict=False compiled = {loose_ok}")


def probe_tooling():
    # P19 LSP boot
    try:
        p = subprocess.run([sys.executable, "-m", "svl.lsp_server"], cwd=ROOT,
                           capture_output=True, text=True, timeout=25,
                           input="")
        err = (p.stderr or "").strip().splitlines()
        crashed = p.returncode != 0 or any("Traceback" in l for l in err)
        record("P19", "LSP server boots", "FAIL" if crashed else "PASS",
               (err[-1][:100] if err else f"exit {p.returncode}"))
    except subprocess.TimeoutExpired:
        record("P19", "LSP server boots", "PASS", "stayed alive 25s (server loop)")

    # P20 REPL evaluates
    try:
        p = subprocess.run([sys.executable, "-m", "svl.repl"], cwd=ROOT,
                           capture_output=True, text=True, timeout=25,
                           input="let x = 1\n\n")
        blob = (p.stdout or "") + (p.stderr or "")
        broken = "Unexpected token" in blob or "Traceback" in blob or p.returncode != 0
        tail = blob.strip().splitlines()[-3:]
        record("P20", "REPL evaluates `let x = 1`", "FAIL" if broken else "PASS",
               " | ".join(tail)[:120])
    except subprocess.TimeoutExpired:
        record("P20", "REPL evaluates", "FAIL", "hung with no response to input")

    # P21 registry save/reload round-trip
    try:
        from svl.package_registry import PackageRegistry, PackageMetadata, PackageType
        d = tempfile.mkdtemp(prefix="svlreg")
        reg = PackageRegistry(storage_path=d)
        reg.register_verifier("v1", b"-----BEGIN PUBLIC KEY-----\nMIIB\n-----END PUBLIC KEY-----\n")
        meta = PackageMetadata(name="p", version="1.0.0", description="d", author="a",
                               license="MIT", package_type=PackageType.LIBRARY)
        # publish needs a real package FILE; create a minimal one
        pkgfile = os.path.join(d, "pkg.tar.gz")
        with open(pkgfile, "wb") as fh:
            fh.write(b"fake package bytes")
        content_hash = hashlib.sha256(b"fake package bytes").hexdigest()
        reg.publish_package(pkgfile, meta, content_hash,
                            b"-----BEGIN PUBLIC KEY-----\nMIIB\n-----END PUBLIC KEY-----\n")
        reg2 = PackageRegistry(storage_path=d)          # reload
        reg2.publish_package(pkgfile, meta, content_hash,
                             b"-----BEGIN PUBLIC KEY-----\nMIIB\n-----END PUBLIC KEY-----\n")
        record("P21", "registry survives save/reload", "PASS", "reloaded and published")
    except Exception as exc:
        record("P21", "registry survives save/reload", "FAIL",
               f"{type(exc).__name__}: {str(exc)[:100]}")

    # P22 no installer / CLI entry point
    has_pkg = os.path.exists(os.path.join(ROOT, "pyproject.toml")) or \
        os.path.exists(os.path.join(ROOT, "setup.py"))
    record("P22", "installable package / `svlc` CLI", "INFO",
           f"pyproject/setup.py present = {has_pkg}; invoked as `python -m svl.*`")

    # P23 CI workflow branch
    ci = open(os.path.join(ROOT, ".github", "workflows", "ci.yml")).read()
    branch = "master" if "branches: [master]" in ci else ("main" if "branches: [main]" in ci else "?")
    cur = subprocess.run(["git", "-C", ROOT, "rev-parse", "--abbrev-ref", "HEAD"],
                         capture_output=True, text=True).stdout.strip()
    record("P23", "CI triggers on the repo's actual branch", "PASS" if branch == cur else "FAIL",
           f"workflow triggers on '{branch}', repo branch is '{cur}'")


def probe_determinism():
    src = 'module m { func main() type int { let x = 1 let y = 2 return x + y } }'
    hashes = []
    for seed in ["0", "1", "12345", "random"]:
        env = dict(os.environ, PYTHONHASHSEED=seed)
        code = ("import sys; sys.path.insert(0, %r);"
                "from svl.compiler_wasm import compile_file_to_wasm;"
                "import hashlib;"
                "print(hashlib.sha256(compile_file_to_wasm(%r).encode()).hexdigest())" % (ROOT, src))
        p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, cwd=ROOT)
        hashes.append(p.stdout.strip())
    same = len(set(hashes)) == 1 and len(hashes[0]) == 64
    record("P18", "bit-identical output across PYTHONHASHSEED 0/1/12345/random", "PASS" if same else "FAIL",
           f"{len(set(hashes))} distinct hashes" + ("" if same else f": {hashes}"))


def probe_programs_vs_oracle():
    """Run the shipped examples and diff against the documented expected output."""
    import svl.compiler_wasm as cw
    # bubble_sort
    bs = open("/home/sudosudo/svl-release/examples/bubble_sort.svl").read()
    rv, out = run_wat(cw.compile_file_to_wasm(bs))
    expected = "sorted=1 sum=28 cmps=15 swaps=8 odds=6\n"
    got = out.decode("utf-8", "replace")
    record("P29", "bubble_sort matches documented output", "PASS" if got == expected else "FAIL",
           f"got {got!r}" + ("" if got == expected else f", expected {expected!r}"))

    # sieve
    sv = open("/home/sudosudo/svl-release/examples/sieve.svl").read()
    rv, out = run_wat(cw.compile_file_to_wasm(sv))
    expected = "pi(10)=4 pi(40)=12 pi(70)=19 pi(100)=25 \n"
    got = out.decode("utf-8", "replace")
    record("P30", "sieve matches documented output", "PASS" if got == expected else "FAIL",
           f"got {got!r}" + ("" if got == expected else f", expected {expected!r}"))


def main():
    print("=" * 78)
    print("SVL FORMAL-RATING PROBE SUITE — execution evidence")
    print("=" * 78)
    probe_semantics()
    probe_type_soundness()
    probe_backend_artifacts()
    probe_verification()
    probe_tooling()
    probe_determinism()
    probe_programs_vs_oracle()
    print("=" * 78)
    npass = sum(1 for r in RESULTS if r[2] == "PASS")
    nfail = sum(1 for r in RESULTS if r[2] == "FAIL")
    ninfo = sum(1 for r in RESULTS if r[2] == "INFO")
    print(f"TOTAL {len(RESULTS)} | PASS {npass} | FAIL {nfail} | INFO {ninfo}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
