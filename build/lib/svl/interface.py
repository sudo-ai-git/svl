"""Interface artifacts (`.svli`) — the machine-checked contract of a module.

`_link_imports` appends an imported module's declarations textually, so before this the
only contract was "the source file still parses".  A `.svli` file records the module's
public surface — every top-level function signature, struct layout and const type — and
the linker refuses an import whose source no longer matches it.  That makes a tampered
or silently-changed library a *named* link error instead of a recompiled surprise.

Format (JSON)::
    {"functions": {"add": {"params": ["int", "int"], "return": "int"}},
     "structs":   {"P": ["x", "y"]},
     "consts":    {"N": "int"},
     "source_hash": "<sha256 of the source the interface was generated from>"}
"""
import hashlib
import json
import os
from typing import Any, Dict, List, Optional

from svl.lexer import tokenize
from svl.parser_rd import parse, FuncDecl, StructDecl, ConstDecl, VarDecl


def type_ann_str(ann: Any) -> str:
    """A canonical string for a type annotation (used for signature comparison)."""
    if ann is None:
        return 'void'
    kind = getattr(ann, 'kind', None)
    if kind == 'prim':
        return str(ann.value)
    if kind == 'struct':
        return f"struct {ann.value}"
    if kind == 'ident':
        return f"named {ann.value}"
    if kind == 'array':
        return f"[{type_ann_str(ann.value)}]"
    if kind == 'tuple':
        return f"({', '.join(type_ann_str(t) for t in ann.value)})"
    if kind == 'func':
        detail = ann.value
        if hasattr(detail, 'params'):
            params = ', '.join(type_ann_str(p) for p in detail.params)
            return f"fn({params}) -> {type_ann_str(detail.return_type)}"
        return 'fn(...)'
    if kind == 'generic':
        value = ann.value
        if isinstance(value, dict):
            args = ', '.join(type_ann_str(a) for a in value.get('args', []))
            return f"{value.get('name', '')}<{args}>"
        return str(value)
    return str(getattr(ann, 'value', ann))


def generate_interface(source: str) -> Dict[str, Any]:
    """Extract a module's public surface from its source."""
    ast = parse(tokenize(source))
    functions: Dict[str, Any] = {}
    structs: Dict[str, Any] = {}
    consts: Dict[str, Any] = {}
    for module in getattr(ast, 'modules', []):
        for stmt in module.body.statements:
            if isinstance(stmt, FuncDecl):
                functions[stmt.name] = {
                    'params': [type_ann_str(p.type_ann) for p in stmt.params],
                    'return': type_ann_str(stmt.return_type),
                }
            elif isinstance(stmt, StructDecl):
                structs[stmt.name] = [f.name for f in stmt.fields]
            elif isinstance(stmt, ConstDecl):
                consts[stmt.name] = type_ann_str(stmt.type_ann)
    return {
        'functions': functions,
        'structs': structs,
        'consts': consts,
        'source_hash': hashlib.sha256(source.encode('utf-8')).hexdigest(),
    }


def interface_path_for(source_path: str) -> str:
    """`lib.svl` -> `lib.svli` (the interface lives beside the source)."""
    root, _ = os.path.splitext(source_path)
    return root + '.svli'


def write_interface(path: str, interface: Dict[str, Any]) -> None:
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(interface, fh, indent=2, sort_keys=True)
        fh.write('\n')


def load_interface(path: str) -> Dict[str, Any]:
    with open(path, encoding='utf-8') as fh:
        return json.load(fh)


def verify_against_interface(source: str, interface: Dict[str, Any]) -> List[str]:
    """Return the ways the source differs from the interface (empty = match).

    Two kinds of check, and both matter:

    * the **surface** (functions / structs / consts) — a signature change breaks every
      caller, and this is what an interface artifact is for;
    * the **exact source bytes** (`source_hash`) — the artifact records the hash, so a
      body-only change (`a + b` -> `a - b`, same signature) is caught too.

    The hash check is skipped only when the interface carries no `source_hash`, i.e.
    it was produced by a tool that never recorded one.  A hash that IS present and
    does not match is always a problem.
    """
    current = generate_interface(source)
    problems: List[str] = []

    expected_hash = interface.get('source_hash')
    if isinstance(expected_hash, str):
        if current['source_hash'] != expected_hash:
            problems.append(
                f"source changed since the interface was recorded "
                f"(hash {expected_hash[:16]}... -> {current['source_hash'][:16]}...); "
                f"the surface below may not reflect the change")

    for name, expected in interface.get('functions', {}).items():
        actual = current['functions'].get(name)
        if actual is None:
            problems.append(f"function '{name}' is missing")
        elif actual != expected:
            problems.append(f"function '{name}' changed: {expected} -> {actual}")
    for name in current['functions']:
        if name not in interface.get('functions', {}):
            problems.append(f"function '{name}' is new (not in the interface)")

    for name, expected in interface.get('structs', {}).items():
        actual = current['structs'].get(name)
        if actual is None:
            problems.append(f"struct '{name}' is missing")
        elif actual != expected:
            problems.append(f"struct '{name}' changed: {expected} -> {actual}")

    for name, expected in interface.get('consts', {}).items():
        actual = current['consts'].get(name)
        if actual is None:
            problems.append(f"const '{name}' is missing")
        elif actual != expected:
            problems.append(f"const '{name}' changed: {expected} -> {actual}")

    return problems
