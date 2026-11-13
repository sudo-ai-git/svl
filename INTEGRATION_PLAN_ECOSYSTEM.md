# SVL Integration Plan — where the biggest gain is, and how to get it

**Date:** 2026-11-12 · **Author:** Fox (for Jack)
**Baseline:** `svl-release` @ `v0.2.0` (`567a601`), workspace @ `f41a629`/`e8f7343`
**Evidence:** every claim below was executed this session; commands are reproducible.

---

## 1. The call

**The biggest gain is D6 — ecosystem & interoperability — and it is an integration
job, not a research job.** The machinery already exists and, in places, is already
on the compile path. What is missing is the wiring and two honest fixes.

Rated headroom (weights × gap):

| Dim | Weight | Now | Headroom | One-step gain | Cost |
|---|---|---|---|---|---|
| D1 semantics | 20% | 6 | 4 | +0.20 (GC **+ closures + generics**) | three hard features |
| D4 verification | 20% | 8 | 2 | +0.20 (codegen-level proofs) | research-grade |
| **D6 ecosystem** | **10%** | **3** | **7** | **+0.20 (packages + runtime)** | **mostly integration** |
| D2 types | 15% | 6 | 4 | +0.15 (one H2–H16 engine) | one engine |
| D3 runtime | 15% | 6 | 4 | +0.15 (native/AOT) | new backend |
| D5 tooling | 10% | 6 | 4 | +0.10 | DX work |
| D7 maturity | 10% | 5 | 5 | +0.10 | process |

Three items offer **+0.20**. D6 is the one where the required components are
**already built and already gated** — the work is connecting them, which is the
highest-confidence +0.20 available. It is also the only dimension that compounds:
every future capability becomes usable by someone other than the author.

---

## 2. Why D6, on evidence

### 2.1 The FFI gap is smaller than the rating says — and the linking is proven

`SVL_FORMAL_RATING.md` §3 scores D6=3 citing four gaps. **Two are already closed:**
`import` linking (probe P27: "two-file link -> 42 = True") and published releases
(`v0.1.0`, `v0.2.0`, both with GitHub Releases). §13's D6 row already drops both.

The remaining gap is "no actual C/Rust FFI linkage". That is **proven closable
today** — an SVL `extern "c"` import was satisfied by another WASM module's export:

```
SVL WAT imports:  (import "env" "svl_add" (func $svl_add (param i32 i32) (result i32)))
C   module exports: ['svl_add']
SVL called the C module -> 42
```

(`Linker.instantiate` + `Linker.define_instance(store, "env", c_inst)`; probe
`/tmp/link_probe.py`.)

### 2.2 The package machinery exists but is unwired — and two parts are dishonest

| Component | State |
|---|---|
| `svl/interface.py` | **On the compile path.** `generate_interface` / `write_interface` / `load_interface` / `verify_against_interface`; `_link_imports` refuses an import whose source no longer matches its `.svli`. Real. |
| `svl/package_manager.py` | `create_package` **works**: runs syntax+type+theorem gates, compiles to WASM, checks determinism ×3, writes `~/.svl/packages/<name>/<ver>/{source.svl,module.wasm,metadata.json}`. |
| `PackageManager.publish` | **No-op.** Prints `Uploading to https://svl-registry.example.com...` then `Published successfully` and returns `True`. Nothing is uploaded. |
| `PackageManager.install` | `raise NotImplementedError("Registry download not implemented")` |
| `registry_url` | `https://svl-registry.example.com` — a placeholder |
| `PackageRegistry.add_verification` | **Forgeable.** Compares `public_key` bytes, never calls `verify()`, then writes `status=VERIFIED`. Anyone holding a registered public key can attest anything. |
| `svlc` | `version, build, run, check, diff, corpus, repl, lsp`. **No** `publish` / `install` / `add` / `new`. |

So the plan is not "build a package ecosystem". It is: **fix the two dishonest
paths, wire the existing lifecycle to the CLI, and make the local registry a real
execution gate.**

### 2.3 The counter-case, stated plainly

**D1 (GC + closures + generics) is a co-equal +0.20** and is fully buildable, unlike
D6's community component. It loses on risk: closures need a `funcref` table the
backend does not emit, generics need monomorphisation, and GC is a new runtime
subsystem — three hard features for one step. D6 is four smaller changes, two of
which are bug fixes.

**D6's ceiling is lower than it looks.** The rubric ties D6 3→5 to "packages +
component runtime". This plan delivers **packages + core-module linking**, which is
a defensible reading of "runtime" but **not** the full WASM component model
(P4.2). Expect D6 3→4 from M1+M2, and 3→5 only if the component work lands.

---

## 3. Workstreams

Each has a falsifiable gate. A gate that cannot fail is not a gate.

### W1 — Make "verified" mean something *(prerequisite, S)*

`add_verification` must verify the signature over `(package_name, version,
content_hash)` with the registered public key and refuse on mismatch.
`publish` must either upload or fail — a printed success with no upload is the
same defect class as the contract prover's vacuous proofs.

**Gate:** a forged signature (registered key, garbage bytes) → **refused**;
a correctly signed attestation → **accepted**. Falsifiable by mutation: reverting
to a key-only comparison makes the forged case pass.

### W2 — Link a foreign WASM module *(M, proven feasible)*

Extend the runtime so `extern "c" func` imports can be satisfied by a compiled
foreign module, not only by a host callback.

- `svlc run --link <module.wasm> <file.svl>` (and a `svlc link` companion).
- Link-time signature check: a foreign module whose export type does not match the
  declared `extern` is **refused**, naming the mismatch.
- Foreign-module build: `clang --target=wasm32` is present but **`wasm-ld` is not**,
  so C→WASM needs either `lld` installed, a prebuilt `.wasm` input, or a WAT shim.
  **Do not claim "compile C from source" until one of those lands.**

**Gate:** SVL calls a foreign `add` → 42 (already reproduced). A foreign module
with the wrong signature → refused.

### W3 — Wire the package manager *(M)*

- `svlc publish <lib.svl>` — `create_package` (works) + record in a registry.
- `svlc install <name>@<ver> --into <dir>` — fetch, verify `wasm_sha256` and
  `source_sha256`, write into the project.
- `svlc add` — install + record in a manifest (`svl.toml`).
- Registry backend: **a local directory first** (fully verifiable offline), with an
  HTTP layer behind the same interface later. No placeholder URLs in the CLI.
- Bind the `.svli` artifact into the package so `_link_imports` verifies it on use.

**Gate:** publish → install into an empty directory → compile a program that
imports it → **correct answer**; tamper the installed `source.svl` → **refused**,
naming the difference. Second build byte-identical.

### W4 — Attestation by default *(S)*

`--attest` on `build`/`publish`; `install` re-verifies the artifact before linking.
`svl/attest.py` already provides `attest`, `extract_attestation`, `content_hash`,
`locate_sync`; `examples/attest.py` is the reference flow (its `--verify` re-derives
`content_sha256` and fails on any flipped byte).

**Gate:** `svlc build --wasm --attest` → `verify_attestation` True; one flipped
byte → False.

---

## 4. Sequencing

| Milestone | Work | D6 evidence | Rating effect |
|---|---|---|---|
| **M1** | W1 + W2 | real FFI linkage, unforgeable attestation | D6 3 → 4 likely |
| **M2** | W3 | publish/install/import as an execution gate | D6 4 → 5 possible |
| **M3** | W4 | attestation on the package path | supports the above |

Re-score after M2 with the same rubric and anchors; do not carry the number forward.

**Deliberately not in this plan:** the WASM component model (P4.2), GC (P3.6),
closures, generics, native/AOT (P3.7). Each is real work with its own gate; none is
needed to make the D6 claim.

---

## 5. Honesty bounds — read before quoting any of this

1. **Community and adoption cannot be gated.** The gates below prove *capability*
   (FFI works, packages install and verify). They do not prove anyone uses it. A D6
   claim must say which.
2. **"Component runtime" is scoped to core-module linking.** Loading a C/Rust
   `.so` and marshalling through WIT (P4.2) is not delivered by this plan.
3. **`publish`/`install` against a real network registry is out of scope** for M2;
   the local-directory backend is the verifiable form. An HTTP registry is a thin
   layer over the same interface, not a redesign.
4. **The +0.20 is not committed.** It depends on D6 3→5, which needs the component
   work this plan scopes out. Budget the claim at +0.10 (D6 3→4) unless M2 lands
   and the rubric is re-scored.

---

## 6. Reproduce the baseline

```bash
cd ~/svl-release
python -m pytest tests -q                    # 176 passed
python svl-rating/probes.py                 # 33 rows: 30 PASS / 0 FAIL / 3 INFO
python -m svl.spike_runner                  # 41/43 (H36/H37 are declared stubs)
python -m svl.corpus_check --json           # 25 compiled, 0 refused
```

Cross-module linking probe (this session):

```python
import wasmtime
from svl.compiler_wasm import compile_file_to_wasm
# SVL: extern "c" func svl_add(a: int, b: int) type int ; main -> svl_add(40, 2)
# foreign: (module (func (export "svl_add") (param i32 i32) (result i32) ...))
linker = wasmtime.Linker(engine)
linker.define_instance(store, "env", linker.instantiate(store, foreign_mod))
print(linker.instantiate(store, svl_mod).exports(store)["m_main"](store))   # 42
```
