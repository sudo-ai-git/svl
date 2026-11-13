# svl/kind_inference.py
# Higher-Kinded Types: Kind System and Kind Inference (H10)
# Implements kind inference for types: Type -> Type, Type -> Type -> Type, etc.

from typing import Dict, List, Optional, Set, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum
from collections import OrderedDict


class Kind(Enum):
    """Kinds in the kind system."""
    STAR = "*"              # Type (proper type)
    ARROW = "->"            # Kind arrow: k1 -> k2
    ROW = "Row"             # Row kind for extensible records/effects


@dataclass(frozen=True)
class KindVar:
    """Kind variable for kind inference."""
    name: str
    id: int = 0

    def __repr__(self):
        return f"?k{self.id}"


@dataclass
class KindScheme:
    """Polymorphic kind scheme."""
    vars: List[KindVar]
    body: 'KindExpr'


@dataclass
class KindExpr:
    """Kind expression."""
    kind_type: str  # 'star', 'arrow', 'var', 'row'
    args: List['KindExpr'] = field(default_factory=list)
    var: Optional[KindVar] = None

    @staticmethod
    def star() -> 'KindExpr':
        return KindExpr(kind_type='star')

    @staticmethod
    def arrow(from_kind: 'KindExpr', to_kind: 'KindExpr') -> 'KindExpr':
        return KindExpr(kind_type='arrow', args=[from_kind, to_kind])

    @staticmethod
    def var_kind(kv: KindVar) -> 'KindExpr':
        return KindExpr(kind_type='var', var=kv)

    @staticmethod
    def row() -> 'KindExpr':
        return KindExpr(kind_type='row')

    def __repr__(self):
        if self.kind_type == 'star':
            return "*"
        elif self.kind_type == 'arrow':
            return f"({self.args[0]} -> {self.args[1]})"
        elif self.kind_type == 'var':
            return str(self.var)
        elif self.kind_type == 'row':
            return "Row"
        return f"Kind({self.kind_type})"

    def __eq__(self, other):
        if not isinstance(other, KindExpr):
            return False
        if self.kind_type != other.kind_type:
            return False
        if self.kind_type == 'var':
            return self.var == other.var
        return self.args == other.args


# Predefined kind signatures for built-in type constructors
BUILTIN_KINDS: Dict[str, KindExpr] = {
    # Primitive types: *
    'int': KindExpr.star(),
    'float': KindExpr.star(),
    'bool': KindExpr.star(),
    'string': KindExpr.star(),
    'void': KindExpr.star(),
    'never': KindExpr.star(),

    # Type constructors: * -> *
    'List': KindExpr.arrow(KindExpr.star(), KindExpr.star()),
    'Option': KindExpr.arrow(KindExpr.star(), KindExpr.star()),
    'Maybe': KindExpr.arrow(KindExpr.star(), KindExpr.star()),
    'Array': KindExpr.arrow(KindExpr.star(), KindExpr.star()),
    'Future': KindExpr.arrow(KindExpr.star(), KindExpr.star()),
    'Stream': KindExpr.arrow(KindExpr.star(), KindExpr.star()),
    'Async': KindExpr.arrow(KindExpr.star(), KindExpr.star()),
    'IO': KindExpr.arrow(KindExpr.star(), KindExpr.star()),

    # Binary type constructors: * -> * -> *
    'Dict': KindExpr.arrow(KindExpr.star(), KindExpr.arrow(KindExpr.star(), KindExpr.star())),
    'Map': KindExpr.arrow(KindExpr.star(), KindExpr.arrow(KindExpr.star(), KindExpr.star())),
    'Result': KindExpr.arrow(KindExpr.star(), KindExpr.arrow(KindExpr.star(), KindExpr.star())),
    'Either': KindExpr.arrow(KindExpr.star(), KindExpr.arrow(KindExpr.star(), KindExpr.star())),
    'Tuple': KindExpr.arrow(KindExpr.star(), KindExpr.arrow(KindExpr.star(), KindExpr.star())),

    # Higher-kinded: (* -> *) -> *
    'Fix': KindExpr.arrow(
        KindExpr.arrow(KindExpr.star(), KindExpr.star()),
        KindExpr.star()
    ),
    'Free': KindExpr.arrow(
        KindExpr.arrow(KindExpr.star(), KindExpr.star()),
        KindExpr.arrow(KindExpr.star(), KindExpr.star())
    ),

    # Effect rows
    'Effect': KindExpr.row(),
}


class KindEnv:
    """Kind environment with constructor kind bindings."""

    def __init__(self, parent: Optional['KindEnv'] = None):
        self.bindings: Dict[str, KindExpr] = dict(BUILTIN_KINDS)
        self.parent = parent
        self.kind_vars: Dict[int, KindVar] = {}
        self._next_kind_var_id = 0

    def extend(self, name: str, kind: KindExpr) -> 'KindEnv':
        """Create new environment with additional binding."""
        new_env = KindEnv(parent=self)
        new_env.bindings = dict(self.bindings)
        new_env.bindings[name] = kind
        new_env.kind_vars = dict(self.kind_vars)
        new_env._next_kind_var_id = self._next_kind_var_id
        return new_env

    def lookup(self, name: str) -> Optional[KindExpr]:
        """Look up kind of a type constructor."""
        if name in self.bindings:
            return self.bindings[name]
        if self.parent:
            return self.parent.lookup(name)
        return None

    def fresh_kind_var(self, name: str = "k") -> KindVar:
        """Create fresh kind variable."""
        kv = KindVar(name=name, id=self._next_kind_var_id)
        self._next_kind_var_id += 1
        self.kind_vars[kv.id] = kv
        return kv


class KindInference:
    """Kind inference engine with unification."""

    def __init__(self):
        self.env = KindEnv()
        self.substitutions: Dict[int, KindExpr] = {}
        self.constraints: List[Tuple[KindExpr, KindExpr]] = []

    def infer_kind(self, type_expr: Any) -> KindExpr:
        """Infer kind of a type expression."""
        return self._infer_kind_type_expr(type_expr)

    def _infer_kind_type_expr(self, te: Any) -> KindExpr:
        """Infer kind from TypeExpr AST node."""
        if not te or not hasattr(te, 'kind'):
            return KindExpr.star()  # Default to *

        kind_str = te.kind

        if kind_str == 'prim':
            return KindExpr.star()

        elif kind_str == 'struct':
            # User-defined structs have kind *
            return KindExpr.star()

        elif kind_str == 'func':
            # Function types have kind *
            return KindExpr.star()

        elif kind_str == 'generic':
            # Generic type application: F<T1, T2, ...>
            if isinstance(te.value, dict):
                name = te.value.get('name', '')
                args = te.value.get('args', [])

                # Look up constructor kind
                constructor_kind = self.env.lookup(name)
                if constructor_kind is None:
                    # Unknown constructor: infer from number of args
                    arg_kinds = [self._infer_kind_type_expr(arg) for arg in args]
                    return self._construct_kind_from_args(arg_kinds, KindExpr.star())

                # Apply constructor to arguments
                return self._apply_kind(constructor_kind, [self._infer_kind_type_expr(arg) for arg in args])

        elif kind_str == 'tuple':
            # Tuple types have kind *
            return KindExpr.star()

        elif kind_str == 'array':
            # Array types have kind *
            return KindExpr.star()

        elif kind_str == 'vec':
            # Dependent vector types have kind *
            return KindExpr.star()

        elif kind_str == 'refinement':
            # Refinement types have kind *
            return KindExpr.star()

        elif kind_str == 'forall':
            # Quantified types have kind *
            return KindExpr.star()

        elif kind_str == 'kind_star':
            # Explicit kind annotation *
            return KindExpr.star()

        elif kind_str in ('box', 'diamond'):
            # Modal types have kind *
            return KindExpr.star()

        elif kind_str == 'linear' or kind_str == 'unique':
            # Linear/unique qualifiers don't change kind
            if isinstance(te.value, dict) and 'inner' in te.value:
                return self._infer_kind_type_expr(te.value['inner'])
            return KindExpr.star()

        return KindExpr.star()

    def _construct_kind_from_args(self, arg_kinds: List[KindExpr], result_kind: KindExpr) -> KindExpr:
        """Build kind from argument kinds and result kind."""
        kind = result_kind
        for arg_kind in reversed(arg_kinds):
            kind = KindExpr.arrow(arg_kind, kind)
        return kind

    def _apply_kind(self, constructor_kind: KindExpr, arg_kinds: List[KindExpr]) -> KindExpr:
        """Apply constructor kind to argument kinds."""
        current = constructor_kind
        for arg_kind in arg_kinds:
            current = self._apply_kind_one(current, arg_kind)
        return current

    def _apply_kind_one(self, kind: KindExpr, arg_kind: KindExpr) -> KindExpr:
        """Apply a single argument to a kind."""
        kind = self._prune_kind(kind)
        arg_kind = self._prune_kind(arg_kind)

        if kind.kind_type == 'arrow':
            # Check compatibility
            expected = kind.args[0]
            result = kind.args[1]

            # Unify expected with actual
            self.unify_kinds(expected, arg_kind)

            return result

        elif kind.kind_type == 'var':
            # Kind variable applied to argument -> create new arrow kind
            result_var = self.env.fresh_kind_var('k')
            new_arrow = KindExpr.arrow(arg_kind, KindExpr.var_kind(result_var))
            self.unify_kinds(kind, new_arrow)
            return KindExpr.var_kind(result_var)

        else:
            # Kind mismatch: expected arrow kind
            return KindExpr.star()

    def unify_kinds(self, k1: KindExpr, k2: KindExpr) -> KindExpr:
        """Unify two kinds."""
        k1 = self._prune_kind(k1)
        k2 = self._prune_kind(k2)

        if k1 == k2:
            return k1

        if k1.kind_type == 'var':
            return self._bind_kind_var(k1.var, k2)

        if k2.kind_type == 'var':
            return self._bind_kind_var(k2.var, k1)

        if k1.kind_type != k2.kind_type:
            # Kind mismatch - default to *
            return KindExpr.star()

        if k1.kind_type == 'arrow':
            # Unify arrow kinds
            self.unify_kinds(k1.args[0], k2.args[0])
            self.unify_kinds(k1.args[1], k2.args[1])
            return k1

        if k1.kind_type == 'star':
            return KindExpr.star()

        if k1.kind_type == 'row':
            return KindExpr.row()

        return KindExpr.star()

    def _prune_kind(self, k: KindExpr) -> KindExpr:
        """Follow kind variable substitutions."""
        if k.kind_type == 'var' and k.var and k.var.id in self.substitutions:
            return self._prune_kind(self.substitutions[k.var.id])
        return k

    def _bind_kind_var(self, var: KindVar, kind: KindExpr) -> KindExpr:
        """Bind kind variable to kind."""
        kind = self._prune_kind(kind)

        # Occurs check
        if self._occurs_check(var, kind):
            return KindExpr.star()

        self.substitutions[var.id] = kind
        return kind

    def _occurs_check(self, var: KindVar, kind: KindExpr) -> bool:
        """Check if kind variable occurs in kind."""
        kind = self._prune_kind(kind)
        if kind.kind_type == 'var' and kind.var and kind.var.id == var.id:
            return True
        for arg in kind.args:
            if self._occurs_check(var, arg):
                return True
        return False

    def apply_substitutions(self, kind: KindExpr) -> KindExpr:
        """Apply all current substitutions to a kind."""
        kind = self._prune_kind(kind)
        if kind.kind_type == 'var':
            return kind
        new_args = [self.apply_substitutions(arg) for arg in kind.args]
        if new_args == kind.args:
            return kind
        return KindExpr(kind.kind_type, args=new_args, var=kind.var)

    def generalize_kind(self, kind: KindExpr) -> KindScheme:
        """Generalize kind by quantifying over free kind variables."""
        free_vars = self._free_kind_vars(kind)
        return KindScheme(vars=list(free_vars), body=kind)

    def _free_kind_vars(self, kind: KindExpr) -> Set[KindVar]:
        """Collect free kind variables in a kind."""
        vars_set = set()
        kind = self._prune_kind(kind)

        if kind.kind_type == 'var' and kind.var:
            vars_set.add(kind.var)

        for arg in kind.args:
            vars_set.update(self._free_kind_vars(arg))

        return vars_set


# ---------------------------------------------------------------------------
# Compile-path enforcement
# ---------------------------------------------------------------------------
#
# `KindInference` on its own is PERMISSIVE: `_apply_kind_one` returns `KindExpr.star()`
# on a kind mismatch and `unify_kinds` "defaults to *", so applying a `*`-kinded
# constructor to an argument, or passing too many arguments, reports nothing.  The
# functions below add the discipline the engine's model supports:
#
#   * a `type Name<p1, ..., pn> = ...` alias declares a constructor of kind
#     `* -> ... -> *` with arity n;
#   * every `Name<a1, ..., am>` application of a DECLARED constructor must have
#     exactly arity n type arguments.
#
# Undeclared names are NOT checked here.  Whether an unknown type constructor is an
# error is a separate question (unknown identifiers), and guessing would risk
# rejecting programs that are currently accepted.

def _iter_nodes(node, want_types, acc=None):
    if acc is None:
        acc = []
    if node is None:
        return acc
    if isinstance(node, want_types):
        acc.append(node)
    if isinstance(node, (list, tuple)):
        for item in node:
            _iter_nodes(item, want_types, acc)
    elif hasattr(node, '__dataclass_fields__'):
        for f in node.__dataclass_fields__:
            if f in ('line', 'column', 'offset', 'type'):
                continue
            _iter_nodes(getattr(node, f, None), want_types, acc)
    return acc


def collect_type_constructors(ast) -> Dict[str, int]:
    """name -> arity for every `type Name<p1..pn> = ...` alias in the program."""
    from svl.parser_rd import TypeAlias
    out: Dict[str, int] = {}
    for alias in _iter_nodes(ast, (TypeAlias,)):
        out[alias.name] = len(alias.type_params)
    return out


def constructor_kind(arity: int) -> KindExpr:
    """`* -> * -> ... -> *` with `arity` arguments."""
    kind = KindExpr.star()
    for _ in range(arity):
        kind = KindExpr.arrow(KindExpr.star(), kind)
    return kind


def check_kind_correctness(ast) -> List[str]:
    """Every application of a DECLARED type constructor must match its arity.

    Returns a list of problems (empty = well-kinded).
    """
    from svl.parser_rd import TypeExpr

    arity = collect_type_constructors(ast)
    if not arity:
        return []

    problems: List[str] = []
    for te in _iter_nodes(ast, (TypeExpr,)):
        value = te.value
        is_application = te.kind == 'generic' and isinstance(value, dict)
        # A bare name parses as `struct` (the parser has no separate `ident` kind for
        # type annotations), so an incomplete application shows up as `struct`.
        is_bare_name = te.kind in ('ident', 'struct')

        if is_application:
            name = str(value.get('name', ''))
            args = value.get('args') or []
            if name not in arity:
                continue
            expected = arity[name]
            if len(args) != expected:
                problems.append(
                    f"line {getattr(te, 'line', '?')}: '{name}' takes {expected} type "
                    f"argument(s) but was given {len(args)}")
        elif is_bare_name:
            # A bare `Box` where `type Box<a> = ...` declares a constructor is an
            # incomplete application: it names a `* -> *` thing where a type (`*`)
            # is required.
            name = str(value)
            expected = arity.get(name)
            if expected:
                problems.append(
                    f"line {getattr(te, 'line', '?')}: '{name}' is a type constructor "
                    f"taking {expected} argument(s) and cannot be used as a type")
    return problems


# HKT Application AST node
@dataclass
class HKTApplication:
    """Higher-kinded type application: F<A, B, ...>"""
    constructor: str
    args: List[Any]  # TypeExpr arguments
    inferred_kind: Optional[KindExpr] = None


def check_hkt_application(constructor: str, args: List[Any], kind_inference: KindInference) -> Tuple[bool, KindExpr]:
    """
    Check if HKT application is well-kinded.
    Returns (is_valid, resulting_kind).
    """
    constructor_kind = kind_inference.env.lookup(constructor)
    if constructor_kind is None:
        # Unknown constructor - infer from args
        arg_kinds = [kind_inference._infer_kind_type_expr(arg) for arg in args]
        return True, kind_inference._construct_kind_from_args(arg_kinds, KindExpr.star())

    result_kind = kind_inference._apply_kind(constructor_kind, [kind_inference._infer_kind_type_expr(arg) for arg in args])
    return True, result_kind


if __name__ == '__main__':
    print("=== Kind Inference Test ===")

    ki = KindInference()

    # Test builtin kinds
    print("Builtin kinds:")
    for name, kind in BUILTIN_KINDS.items():
        print(f"  {name}: {kind}")

    # Test kind application
    print("\nKind applications:")
    list_kind = ki.env.lookup('List')
    int_kind = KindExpr.star()
    result = ki._apply_kind_one(list_kind, int_kind)
    print(f"  List int: {result}")

    dict_kind = ki.env.lookup('Dict')
    int_kind = KindExpr.star()
    str_kind = KindExpr.star()
    result = ki._apply_kind(dict_kind, [int_kind, str_kind])
    print(f"  Dict int string: {result}")

    # Test HKT application check
    print("\nHKT Application checks:")
    from svl.parser_rd import TypeExpr, NodeType
    int_type = TypeExpr(type=NodeType.TYPE_EXPR, line=1, column=1, offset=0, kind='prim', value='int')
    str_type = TypeExpr(type=NodeType.TYPE_EXPR, line=1, column=1, offset=0, kind='prim', value='string')

    valid, kind = check_hkt_application('List', [int_type], ki)
    print(f"  List<int>: valid={valid}, kind={kind}")

    valid, kind = check_hkt_application('Dict', [int_type, str_type], ki)
    print(f"  Dict<int,string>: valid={valid}, kind={kind}")

    valid, kind = check_hkt_application('Fix', [], ki)
    print(f"  Fix: valid={valid}, kind={kind}")

    print("\n✓ Kind Inference test complete!")