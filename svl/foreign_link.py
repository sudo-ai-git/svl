# svl/foreign_link.py
# Link foreign WASM modules into an SVL program's `extern "c"` imports.
#
# `extern "c" func name(...)` lowers to `(import "env" "name" ...)`.  The default host
# supplies a Python callback for each of the six builtin names; any OTHER `env` import is
# an `extern` that the host must be given a foreign module for.  Previously such a call
# could only be satisfied by a host callback — there was no way to hand the program a
# compiled C/Rust module, which is the actual interop path.
#
# This module loads compiled foreign modules, checks their exports against the program's
# declared `extern` signatures, and defines them under `env` so the SVL module can call
# them.
#
# The signature check is a real link-time gate: a foreign module that does not export an
# `extern` name, or exports it with a different type, is REFUSED with the name and both
# signatures.  Silently falling back to a host stub would make a wrong-signature call
# trap at run time instead of being caught where the mismatch is visible.

from typing import Any, Dict, List, Sequence, Tuple

import wasmtime

# The six builtin host imports.  Everything else under `env` must come from a foreign
# module.  Keep in sync with `svl/repl.py::run_wat`.
HOST_IMPORTS = frozenset({
    "print", "print_int", "putc", "clear", "malloc", "iterator_next", "await",
})


class ForeignModuleError(Exception):
    """A foreign module is missing, invalid, or does not satisfy the `extern` imports."""


def _sig(func_type) -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
    return (tuple(str(p) for p in func_type.params),
            tuple(str(r) for r in func_type.results))


def load_foreign_module(engine: wasmtime.Engine, data: bytes) -> wasmtime.Module:
    """Validate a compiled foreign module.

    Raises rather than returning None: a module that does not validate cannot be linked,
    and a silent skip would leave the `extern` call to trap later.
    """
    if not isinstance(data, (bytes, bytearray)) or bytes(data[:4]) != b"\x00asm":
        raise ForeignModuleError(
            "not a WASM module (missing \\0asm magic) — expected a compiled .wasm, "
            "not WAT text"
        )
    try:
        return wasmtime.Module(engine, bytes(data))
    except Exception as exc:                                    # noqa: BLE001
        raise ForeignModuleError(f"foreign module failed to validate: {exc}") from exc


def foreign_exports(module: wasmtime.Module) -> Dict[str, Any]:
    """name -> FuncType for every function a foreign module exports."""
    out: Dict[str, Any] = {}
    for e in module.exports:
        if isinstance(e.type, wasmtime.FuncType):
            out.setdefault(e.name, e.type)
    return out


def plan_links(module: wasmtime.Module,
               foreign: Sequence[wasmtime.Module]) -> Tuple[List[wasmtime.Module], List[str]]:
    """Check the `extern` imports against the foreign modules' exports.

    Returns ``(modules_to_define, unresolved)``.  `unresolved` is empty when every
    non-host `env` import is provided with a matching signature.
    """
    provided: Dict[str, Any] = {}
    for fm in foreign:
        for name, ft in foreign_exports(fm).items():
            provided.setdefault(name, ft)

    unresolved: List[str] = []
    for imp in module.imports:
        if imp.module != "env" or imp.name in HOST_IMPORTS:
            continue
        if not isinstance(imp.type, wasmtime.FuncType):
            unresolved.append(f"{imp.name} (non-function import)")
            continue
        if imp.name not in provided:
            unresolved.append(
                f"{imp.name} (no linked module exports it)")
            continue
        want, got = _sig(imp.type), _sig(provided[imp.name])
        if want != got:
            unresolved.append(
                f"{imp.name} (signature mismatch: program needs "
                f"{want[0]} -> {want[1]}, module provides {got[0]} -> {got[1]})")
    return list(foreign), unresolved


def define_foreign(store: wasmtime.Store, linker: wasmtime.Linker,
                   module: wasmtime.Module,
                   foreign: Sequence[wasmtime.Module]) -> None:
    """Validate and define the foreign modules under `env`.

    Must be called AFTER the host stubs are defined, with shadowing allowed, so a
    foreign export takes precedence over the default stub for the name it provides.
    """
    _modules, unresolved = plan_links(module, foreign)
    if unresolved:
        raise ForeignModuleError(
            "cannot link extern imports:\n  - " + "\n  - ".join(unresolved))

    linker.allow_shadowing = True
    for fm in foreign:
        try:
            inst = linker.instantiate(store, fm)
        except Exception as exc:                                # noqa: BLE001
            raise ForeignModuleError(
                f"foreign module failed to instantiate (its own imports are not "
                f"satisfied): {exc}") from exc
        linker.define_instance(store, "env", inst)
