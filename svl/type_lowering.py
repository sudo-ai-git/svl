# svl/type_lowering.py
# Type-directed lowering: the type layer drives WASM codegen.
#
# Until now `compiler_wasm.py` never imported the type layer, so the two disagreed in
# ways that produced *silently wrong* output rather than errors:
#
# * `let x = 1.5` (no annotation) lowered to an **i32** local while the literal emitted
#   `f64.const`. The text still *parsed* (`wat2wasm` accepts it) but failed validation
#   with "type mismatch: expected i32, found f64" -- a text-level check saw a green compile.
# * `x + y` on two floats emitted `i32.add`, adding the bit patterns of two doubles.
# * `let q = p` (copying a struct handle) lost the struct type, so `q.field` could not be
#   resolved even though the type layer knew `p`'s type.
#
# The backend now runs the type checker first and lowers from its inferred types. The
# mapping is deliberately conservative: an unknown or `void` type falls back to the
# previous behaviour (i32), so a program the checker cannot classify compiles exactly as
# before. A type the checker *does* know and that disagrees with the annotation is a
# compile error, not a guess.
#
# This module is the only bridge: `compiler_wasm` imports it, `type_inference` does not
# import the backend, so the dependency stays one-way.

from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field

from svl.type_inference import Type, TypeChecker, TypeVar


@dataclass
class InferredTypes:
    """The type checker's per-program inference result, keyed for codegen.

    `local_types` is keyed by ``(function_name, local_name)`` where `function_name` is the
    *unqualified* SVL name (the same key the backend's ``_local_struct_types`` uses is
    module-qualified; the caller qualifies it).
    `expr_types` is keyed by ``id(expr)`` -- AST nodes are alive for the whole compile, so
    the identity is stable, and expressions are mutable dataclasses that must not be hashed.
    """
    ok: bool
    errors: List[str] = field(default_factory=list)
    local_types: Dict[Tuple[str, str], Type] = field(default_factory=dict)
    expr_types: Dict[int, Type] = field(default_factory=dict)
    func_types: Dict[str, Type] = field(default_factory=dict)

    def local_type(self, func_name: str, name: str) -> Optional[Type]:
        return self.local_types.get((func_name, name))

    def expr_type(self, expr: Any) -> Optional[Type]:
        return self.expr_types.get(id(expr))


def infer_types(ast: Any, strict: bool = False) -> InferredTypes:
    """Run the type checker over a parsed program and return its inferred types.

    This is `TypeChecker.check_program` with recording switched on; it re-runs the real
    inference rather than a second, simpler approximation of it.

    Codegen is deliberately NON-strict (`strict=False`): the compile-time gate has already
    run the strict checker and refused anything it could not verify, so the lowering pass
    must not fail a second time on the same program.
    """
    checker = TypeChecker(strict=strict)
    return checker.infer_program(ast)


def type_to_valtype(t: Optional[Type]) -> Optional[str]:
    """Map an inferred SVL type to a WASM valtype name, or None when unclassified.

    None means "the checker does not know" -- the caller keeps its previous default (i32).
    That is the conservative direction: an unknown type must never *change* codegen.
    """
    if t is None or isinstance(t, TypeVar):
        return None
    if t.kind == 'prim':
        prim = t.args[0] if t.args else None
        return {
            'int': 'i32',
            'float': 'f64',
            'bool': 'i32',      # represented as 0/1 in an i32 slot
            'string': 'i32',    # pointer to a length-prefixed data segment
            'void': 'i32',      # dummy; void functions emit no result
            'never': 'i32',     # unreachable
        }.get(prim)
    if t.kind == 'func':
        return 'funcref'
    # struct / generic / array / tuple are all heap handles (an i32 pointer)
    if t.kind in ('struct', 'generic', 'array', 'tuple'):
        return 'i32'
    return None


def is_float(t: Optional[Type]) -> bool:
    return bool(t is not None and not isinstance(t, TypeVar)
                and t.kind == 'prim' and t.args and t.args[0] == 'float')


def is_int(t: Optional[Type]) -> bool:
    return bool(t is not None and not isinstance(t, TypeVar)
                and t.kind == 'prim' and t.args and t.args[0] == 'int')


def struct_name_of(t: Optional[Type]) -> Optional[str]:
    """The struct name carried by an inferred type, if any.

    `Point{...}` synthesises as `Type.struct('Point')`; an annotation `p: Point` becomes
    `Type.generic('Point', [])`. Both name the same declared struct.
    """
    if t is None or isinstance(t, TypeVar):
        return None
    if t.kind == 'struct' and t.args:
        return t.args[0]
    if t.kind == 'generic' and t.generic_name:
        return t.generic_name
    return None
