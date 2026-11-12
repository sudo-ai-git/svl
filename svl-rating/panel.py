#!/usr/bin/env python3
"""SVL improvement panel — 5 experts, distinct lenses, spawned via delegate_task.

Each expert is given the verified failure list from SVL_FORMAL_RATING.md and the
repo layout, and must return concrete improvements with file:line references and a
falsifiable spike question.  Raw child output is saved to svl-rating/panel_raw/.

Run:  python svl-rating/panel.py
"""
import json
import os
import sys
import threading

sys.path.insert(0, "/home/sudosudo/.hermes/hermes-agent")
from tools.delegate_tool import delegate_task  # noqa: E402

MODEL = "meituan/longcat-2.5:free"
OUT = "/home/sudosudo/.openclaw/workspace/svl-rating/panel_raw"
os.makedirs(OUT, exist_ok=True)

FAILURES = """
VERIFIED FAILURES (execution gates, 2026-11-12, tree 8e3d18f / mirror 9e6e3b8):

F1. NO LEXICAL SCOPING. `let x=1; if 1==1 then { let x=99 } else {}; return x` -> 99 (correct: 1).
   The compiler keeps one flat local map per function; an inner `let` overwrites the outer slot.
F2. `for x in <iterable>` IS A SILENT NO-OP. `let a=[1,2,3]; let s=0; for x in a { s+=x }; return s` -> 0.
   The parser accepts it; the backend's iterator path exits immediately (host iterator_next returns 0).
F3. `&&` / `||` ARE EAGER. Both operands are always compiled; emitted as i32.and / i32.or.
   `func f(x:int){ let r = x==0 && 10/x>1; return r }` called with f(0) TRAPS on division by zero.
F4. TYPE CHECKER UNSOUND AT BOUNDARIES. `return "hi"` inside `func f() type int` is accepted;
   `f("hi")` against `f(x: int)` is accepted; strict=True does not refuse either.
   Only `let x: int = "hi"` is refused.
F5. `print(<int variable>)` EMITS INVALID WAT. `let x=5; print(x)` -> wasmtime.Module rejects it
   (`expected i32 but nothing on stack`). Only `print("literal")` and `print_int(x)` are handled.
F6. REASSIGNING A `const` EMITS INVALID WAT. `const c: int = 5; c = 6` -> module validation fails.
F7. PCC ARTIFACT DOES NOT ASSEMBLE. PCCWasmGenerator().generate(src).to_wasm_with_proofs() emits a
   `(custom "svl-proofs" ...)` section that wat2wasm rejects.
F8. NO MEMORY GROWTH / NO FREE. Emitted module is `(memory 16)` (1 MiB), bump allocator only,
   no memory.grow, no free. An allocating program CANNOT be run twice in one instance: the second
   call leaks past the ceiling and traps. 400 KiB allocations work within the ceiling.
F9. `try` / `catch` UNSUPPORTED. Parser raises SyntaxError ("not supported by the WASM backend yet").
F10. `import` IS INERT. `import "other"` parses and compiles but links nothing.
F11. LSP CRASHES ON BOOT. `python -m svl.lsp_server` -> AttributeError: 'method' object has no attribute 'reg_name'.
F12. REPL CANNOT EVALUATE. Every input, including `let x = 1`, -> "Unexpected token at top level".

INFORMATIONAL SCOPE LIMITS:
L1. BPSW "theorem" layer is CONSTANT-TRUE (0/60 valid programs fail it).
L2. 231-gate PRODUCT channel is DEGENERATE (0 for 2000/2000 random 512-byte windows).
L3. No pyproject.toml / setup.py / `svlc` CLI; invoked as `python -m svl.*`.
L4. Public README corpus expectation is stale (says 52 files/42 compilable; measured 28/23).
L5. Public mirror CI triggers on `master` but the branch is `main` -> CI never runs.

WHAT IS GENUINELY GOOD (do not propose re-building these):
- Deterministic compilation (bit-identical WAT across PYTHONHASHSEED).
- Backend assembles AND runs; 61/61 pytest; bounds-checked arrays; TCO wired (return_call).
- Interval abstract interpreter proves OOB index + division-by-zero and refuses them.
- SMT layer is a real tri-state (proven / counterexample / unverified) and discharges asserts.
- Hebrew/ASCII alias contract byte-identical (22/22).
- Compile latency 3-6x faster than Rust-to-wasm; runtime at parity with Rust-to-wasm.
"""

LAYOUT = """
REPO LAYOUT (workspace /home/sudosudo/.openclaw/workspace):
- svl/lexer.py        — hand-written lexer, 22 Hebrew tokens + ASCII aliases
- svl/parser_rd.py    — recursive-descent parser + all AST dataclasses (~2095 lines)
- svl/compiler_wasm.py— WASM backend (~1584 lines): locals, globals, arrays, structs, match, TCO
- svl/type_inference.py / type_lowering.py / type_layer.py — type checker and its bridge to codegen
- svl/abstract_interpretation.py — interval analysis (OOB / div-zero), runs in the compile gate
- svl/smt_theorem.py  — Z3 model, tri-state
- svl/verify_gate.py  — compile-time gate (AST guard + type layer + AI)
- svl/serialization.py, gate231.py, bpsw_monodromy.py, mod5_types.py, dual_stream.py
- svl/pcc_wasm.py     — proof-carrying code generator
- svl/lsp_server.py, repl.py, package_registry.py, package_manager.py
- tests/              — 61 pytest tests; conftest.py has assemble()+instantiate()+run_main() helpers
- examples/           — bubble_sort.svl, sieve.svl, snake.svl, run_example.py
- SVL_FORMAL_RATING.md — the full rating this panel feeds
- svl-rating/probes.py — the 31 execution probes (run it to reproduce any failure)
"""

LENSES = [
    ("semantics", " LANGUAGE SEMANTICS AND COMPILER CORRECTNESS",
     "Focus on F1 (scoping), F2 (for-in), F3 (short-circuit), F9 (error model), F10 (modules), F6 (const immutability).",
     "svl/parser_rd.py, svl/compiler_wasm.py, svl/lexer.py"),
    ("types", " TYPE SYSTEM AND SOUNDNESS",
     "Focus on F4 (unsound boundaries), F5/F6 (invalid WAT from the type/lowering path).",
     "svl/type_inference.py, svl/type_lowering.py, svl/type_layer.py, svl/compiler_wasm.py"),
    ("runtime", " RUNTIME, CODEGEN AND MEMORY MODEL",
     "Focus on F8 (memory growth/free), F5/F6 (invalid artifacts), F7 (PCC assembly).",
     "svl/compiler_wasm.py, svl/pcc_wasm.py"),
    ("verification", " VERIFICATION AND ASSURANCE",
     "Focus on L1 (BPSW constant-true), L2 (PRODUCT degenerate), F7 (PCC), and how the interval AI and SMT layers should be wired into the compile path or dropped.",
     "svl/bpsw_monodromy.py, svl/gate231.py, svl/theorem_layer.py, svl/verify_gate.py, svl/smt_theorem.py"),
    ("tooling", " TOOLING, DX AND ECOSYSTEM",
     "Focus on F11 (LSP), F12 (REPL), L3 (CLI/packaging), L4 (stale docs), L5 (CI branch).",
     "svl/lsp_server.py, svl/repl.py, svl/package_manager.py, .github/workflows/ci.yml, README.md"),
]

TEMPLATE = """You are a senior expert __LENS__.

TASK: analyse the SVL language and propose CONCRETE, PRIORITISED IMPROVEMENTS that address the
verified failures below. This is not a restatement exercise — propose changes that would actually
move the rating, each grounded in the real code.

You MAY read the repository files listed below to ground your proposals in real line numbers and
real function names. Do NOT modify any files. Do NOT run long builds.

For EACH improvement return:
- id: short slug
- title: one line
- addresses: which failure id(s) (F1..F12, L1..L5)
- problem: one sentence, with file:line where possible
- proposal: the concrete change (what to add/change, which function, which data structure)
- expected_effect: what the execution gate would show after the change (a specific program + expected output)
- spike_question: Given/When/Then framing of a THROWAWAY experiment that proves or kills the proposal
- risk: Low/Medium/High + one sentence
- effort: S/M/L

ORDER by impact (highest first). Return 4-6 improvements. Be specific and honest: if a failure is
a deliberate design trade-off rather than a defect, say so and propose the cheapest honest fix
(e.g. rejecting it at compile time instead of silently mis-compiling).

RETURN FORMAT: your final message MUST end with a fenced ```json block containing exactly:
{"expert": "panel_semantics", "improvements": [ {id, title, addresses, problem, proposal,
expected_effect, spike_question, risk, effort}, ... ], "top_pick": "<id>", "honest_note": "..."}
Prose before the block is fine, but the block must be present and parseable."""


class MockParent:
    base_url = None
    api_key = None
    provider = "nous"
    api_mode = "chat_completions"
    model = MODEL
    platform = "cli"
    providers_allowed = None
    providers_ignored = None
    providers_order = None
    provider_sort = None
    _session_db = None
    _delegate_depth = 0
    _print_fn = None
    tool_progress_callback = None
    thinking_callback = None
    enabled_toolsets = ["terminal", "file"]

    def __init__(self):
        self._active_children = []
        self._active_children_lock = threading.Lock()


def run_batch(tasks, parent):
    res = delegate_task(
        goal="SVL improvement panel",
        context="panel",
        tasks=tasks,
        max_iterations=10,
        role="leaf",
        background=False,
        output_schema=None,
        action="spawn",
        subagent_id="svl_improvement_panel",
        message="panel",
        parent_agent=parent,
        credentials_cfg={"provider": "nous", "model": MODEL},
    )
    if isinstance(res, str):
        try:
            res = json.loads(res)
        except Exception:
            print("RAW:", res[:2000])
            return []
    with open(os.path.join(OUT, "_raw_response.json"), "w") as fh:
        json.dump(res, fh, indent=2)
    return res.get("results") or []


def main():
    tasks = []
    for slug, lens, focus, files in LENSES:
        context = (FAILURES + "\n" + LAYOUT +
                   f"\nYOUR LENS:{lens}\nYOUR FOCUS: {focus}\nKEY FILES: {files}\n")
        tasks.append({
            "name": f"panel_{slug}",
            "goal": TEMPLATE.replace("__LENS__", lens),
            "context": context,
        })

    parent = MockParent()
    # max_concurrent_children is 3 -> two batches
    results = []
    for i in range(0, len(tasks), 3):
        batch = tasks[i:i + 3]
        print(f"spawning batch {i // 3 + 1} ({len(batch)} experts) on {MODEL} ...")
        results.extend(run_batch(batch, parent))

    print("top-level keys:", list(results[0].keys()) if results else "none")
    print(f"children returned: {len(results)}")
    all_improvements = []
    for entry in results:
        # `name` is absent from delegate_task results; task_index is the stable key.
        name = entry.get("name") or f"task_{entry.get('task_index', '?')}"
        summary = str(entry.get("summary") or "")
        status = entry.get("status")
        with open(os.path.join(OUT, f"{name}.txt"), "w") as fh:
            fh.write(f"status: {status}\n\n{summary}\n")
        print(f"--- {name}: status={status} len={len(summary)}")
        # extract json block
        block = None
        if "```json" in summary:
            block = summary.split("```json", 1)[1].split("```", 1)[0].strip()
        elif "```" in summary:
            block = summary.split("```", 1)[1].split("```", 1)[0].strip()
        if block:
            try:
                data = json.loads(block)
                imps = data.get("improvements") or []
                print(f"    parsed {len(imps)} improvements; top_pick={data.get('top_pick')}")
                for imp in imps:
                    imp["_expert"] = data.get("expert") or name
                all_improvements.extend(imps)
            except Exception as exc:
                print(f"    JSON parse failed: {exc}")
        else:
            print("    NO JSON BLOCK")

    with open(os.path.join(OUT, "all_improvements.json"), "w") as fh:
        json.dump(all_improvements, fh, indent=2)
    print(f"\nTOTAL improvements collected: {len(all_improvements)}")
    print(f"raw output: {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
