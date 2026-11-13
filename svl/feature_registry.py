"""Feature registry — which advanced type-system features are actually enforced.

The parser accepts a wide surface of type syntax.  Before P1.1/P1.2 the checker silently
mapped every unregistered `TypeExpr` kind to `int`, so `linear int` and
`{v: int | v > 0}` compiled as plain `int`: the advertised "widest type-system surface"
was worth nothing.  Strict mode now refuses what it cannot check, and this registry makes
the status of every feature explicit, machine-readable and self-checked.

Three statuses:

* ``enforced``    — a checker runs on the compile path for this kind.
* ``engine-only`` — an engine module exists (regions, kinds, type families) but is NOT
  wired into the compile path, so strict mode still refuses it.
* ``parse-only``  — the parser accepts it; nothing checks it.  Strict mode refuses it.

``verify_registry`` parses a representative snippet per kind and asserts that every
``TypeExpr.kind`` the parser can produce is registered, so a new kind cannot be added
without an explicit status decision.
"""
from dataclasses import dataclass
from typing import Dict, List, Tuple

ENFORCED = "enforced"
ENGINE_ONLY = "engine-only"
PARSE_ONLY = "parse-only"


@dataclass(frozen=True)
class Feature:
    name: str
    kind: str          # the TypeExpr.kind the parser produces
    status: str
    note: str


FEATURES: Dict[str, Feature] = {
    # -- enforced: a checker runs on the compile path -------------------------------
    'prim': Feature('primitive types', 'prim', ENFORCED,
                    'int / float / bool / string / void / never'),
    'struct': Feature('struct types', 'struct', ENFORCED,
                      'resolved against the struct environment'),
    'ident': Feature('named types', 'ident', ENFORCED,
                     'resolved against the type environment'),
    'func': Feature('function types', 'func', ENFORCED,
                    'parameterised and checked like any other type'),
    'generic': Feature('generic type constructors', 'generic', ENFORCED,
                       'e.g. Option<int>; arguments are checked'),
    'tuple': Feature('tuple types', 'tuple', ENFORCED,
                     'fixed-arity product types'),
    'array': Feature('array types', 'array', ENFORCED,
                     'element type is checked'),
    # -- engine-only: an engine exists but is not on the compile path ---------------
    'linear': Feature('linear types', 'linear', ENFORCED,
                      'svl/linear_regions.py enforces the move discipline on the '
                      'compile path: a moved value may not be used or moved again'),
    'unique': Feature('uniqueness types', 'unique', ENFORCED,
                      'svl/linear_regions.py enforces the move discipline on the '
                      'compile path; affine, so an unconsumed one is not a warning'),
    'kind_star': Feature('higher-kinded types (*)', 'kind_star', ENGINE_ONLY,
                         'svl/kind_inference.py is not wired into the compile path; '
                         'constructor ARITY is now checked, but `*` has no type-level '
                         'meaning in SVL yet'),
    'kind_arrow': Feature('kind arrows', 'kind_arrow', ENGINE_ONLY,
                          'svl/kind_inference.py is not wired into the compile path; '
                          'no type syntax uses kind arrows yet'),
    'refinement': Feature('refinement types', 'refinement', ENFORCED,
                          'svl/refinement_types.py discharges { v: T | P(v) } obligations '
                          'through Z3 on the compile path'),
    # -- parse-only: nothing checks it ---------------------------------------------
    'vec': Feature('dependent array bounds', 'vec', ENFORCED,
                   'svl/vec_bounds.py checks vec<T, n> against an array literal or '
                   'zeros(k) initializer when both sides are literal'),
    'dynamic': Feature('gradual typing (?)', 'dynamic', PARSE_ONLY,
                       'the wildcard type parses; no cast checking'),
    'forall': Feature('quantified constraints', 'forall', PARSE_ONLY,
                      'forall a. C => T parses; constraints are not solved'),
    'intersection': Feature('intersection types', 'intersection', PARSE_ONLY,
                            'A & B parses; no subtype reasoning'),
    'union': Feature('union types', 'union', PARSE_ONLY,
                     'A | B parses; no case reasoning'),
}

# Top-level constructs the parser accepts but the compile path does not enforce.
# These are refused by the syntax layer's structural checksum ("Unknown node type: X"),
# which is a rejection but not a type-checker verdict.
DECLARATION_FEATURES: Dict[str, Feature] = {
    'MacroDecl': Feature('hygienic macros', 'MacroDecl', PARSE_ONLY,
                         'parsed; not expanded'),
    'ModuleTypeDecl': Feature('module types', 'ModuleTypeDecl', PARSE_ONLY,
                             'parsed; not enforced'),
    'ModuleFunctorDecl': Feature('module functors', 'ModuleFunctorDecl', PARSE_ONLY,
                                'parsed; not applied'),
    'EffectDecl': Feature('algebraic effects', 'EffectDecl', PARSE_ONLY,
                          'parsed; no handler compilation'),
    'ClassDecl': Feature('type classes', 'ClassDecl', PARSE_ONLY,
                         'parsed; no coherence check'),
    'InstanceDecl': Feature('type class instances', 'InstanceDecl', PARSE_ONLY,
                            'parsed; no instance resolution'),
    'EffectRow': Feature('effect rows', 'EffectRow', PARSE_ONLY,
                         'refused by the structural checksum'),
}

# One representative snippet per TypeExpr kind, used by verify_registry().
REPRESENTATIVE = {
    'prim': 'func f(x: int) type int { return x }',
    'struct': 'module m { struct S { a: int } func f(x: S) type int { return 0 } }',
    'ident': 'func f(x: Foo) type int { return 0 }',
    'func': 'func f(x: fn(int) -> int) type int { return 0 }',
    'generic': 'func f(x: Option<int>) type int { return 0 }',
    'tuple': 'func f(x: (int)) type int { return 0 }',
    'array': 'func f(x: [int]) type int { return 0 }',
    'dynamic': 'func f(x: ?) type int { return 0 }',
    'linear': 'func f(x: linear int) type int { return x }',
    'unique': 'func f(x: unique int) type int { return x }',
    'vec': 'module m { func f() type int { let v: vec<int, 10> = [1] return 0 } }',
    'kind_star': 'func f() type * { return 0 }',
    'kind_arrow': 'func f() type -> * * { return 0 }',
    'forall': 'func f() type forall a. Int => a { return 0 }',
    'refinement': 'func f(x: { v: int | v > 0 }) type int { return x }',
    'intersection': 'func f(x: int & string) type int { return 0 }',
    'union': 'func f(x: int | string) type int { return 0 }',
}


def status_of(kind: str) -> Feature:
    """Return the Feature for a TypeExpr kind, or a synthetic 'unregistered' one."""
    return FEATURES.get(kind, Feature(f"unregistered kind '{kind}'", kind, 'unregistered',
                                      'no status decision recorded'))


def support_matrix() -> Dict[str, str]:
    """A machine-readable {kind: status} map for docs and CI."""
    return {k: f.status for k, f in sorted(FEATURES.items())}


def enforced_kinds() -> List[str]:
    return sorted(k for k, f in FEATURES.items() if f.status == ENFORCED)


def non_enforced_kinds() -> List[str]:
    return sorted(k for k, f in FEATURES.items() if f.status != ENFORCED)


def verify_registry() -> Tuple[bool, List[str], List[str]]:
    """Parse every representative snippet and assert each TypeExpr kind is registered.

    Returns ``(ok, unknown_kinds, parse_failures)``.  Parse failures are reported
    rather than skipped: a snippet that no longer parses is itself a coverage gap,
    and silently skipping it would let a feature disappear from the matrix.
    """
    from svl.lexer import tokenize
    from svl.parser_rd import parse, TypeExpr

    unknown: List[str] = []
    parse_failures: List[str] = []
    seen = set()
    for kind, snippet in REPRESENTATIVE.items():
        try:
            ast = parse(tokenize(snippet))
        except Exception as exc:                                      # noqa: BLE001
            parse_failures.append(f"{kind}: {exc}")
            continue
        stack = [ast]
        while stack:
            node = stack.pop()
            # Only TypeExpr kinds are the type-feature surface; `Pattern.kind`
            # ('wildcard', 'int', ...) is a separate union and not registered here.
            if isinstance(node, TypeExpr):
                seen.add(node.kind)
            for value in getattr(node, '__dataclass_fields__', {}):
                child = getattr(node, value, None)
                if hasattr(child, '__dataclass_fields__'):
                    stack.append(child)
                elif isinstance(child, list):
                    stack.extend(c for c in child if hasattr(c, '__dataclass_fields__'))
    for kind in sorted(seen):
        if kind not in FEATURES:
            unknown.append(kind)
    return (not unknown and not parse_failures), unknown, parse_failures


if __name__ == '__main__':
    ok, unknown, failures = verify_registry()
    print(f"registry coverage: {'OK' if ok else 'GAPS'}")
    if unknown:
        print("  unregistered kinds:", unknown)
    if failures:
        print("  unparseable representatives:", failures)
    print("support matrix:")
    for kind, status in support_matrix().items():
        print(f"  {kind:14s} {status}")
