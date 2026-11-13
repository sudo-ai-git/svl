# svl/abstract_interpretation.py
# Abstract Interpretation for the Type Layer (H21)
#
# The lattice (interval / congruence / product) has been here since the first cut of this
# module, but nothing ever walked the AST with it: ``analyze_program`` returned the bottom
# state, so ``analyze_type_bounds`` always produced an empty warning list and the module
# could not fail.  This file now contains a real, sound interval analysis over SVL ASTs.
#
# What it proves -- and ONLY these:
#
# * **Out-of-bounds array index** -- ``a[i]`` where the length of ``a`` is statically known
#   and the possible values of ``i`` are all negative, or all at least that length.
# * **Division / remainder by a provably zero divisor** -- ``x / y``, ``x % y`` and the
#   compound forms ``/=`` ``%=``.
# * **i32 division overflow** -- ``-2**31 / -1``, which traps in WASM.
#
# Everything else is deliberately ``top``.  An over-approximation may miss a real error
# (false negative) but must never invent one: a false positive rejects a CORRECT program at
# compile time, which is strictly worse than the runtime trap the check replaces.
#
# Soundness notes that matter and are easy to get wrong:
#
# * Intervals over-approximate *mathematical* values.  WASM ``i32`` arithmetic wraps, so an
#   interval whose bounds leave ``[-2**31, 2**31-1]`` is widened to ``top`` rather than
#   trusted -- otherwise ``x = 2**31`` would be reported as a safe index when it is really
#   ``-2**31``.
# * Array lengths are tracked per lvalue path (``a``, ``g.cells``).  An unknown length is
#   ``top`` and disables the bounds check for that array -- no guessed lengths.
# * Functions are analysed with parameters bound to the join of the argument intervals at
#   every internal call site (chaotic iteration, bounded passes).  Exported functions and
#   functions with no internal caller keep ``top`` parameters, because an external caller
#   can pass anything.
# * Call return values are ``top`` (no interprocedural value summary), so ``let n = f(x)``
#   loses precision.  The builtins ``len`` and ``zeros`` are modelled.
# * ``assert``/``if``/``while`` conditions refine the state; refinement never removes
#   states that the concrete semantics can reach.
#
# Public entry points: ``analyze_program`` / ``analyze_type_bounds`` (both take a parsed
# ``Program``) and the ``AbstractInterpreter`` wrapper.

from typing import Dict, List, Optional, Set, Tuple, Any, Union
from dataclasses import dataclass, field
from enum import Enum
from abc import ABC, abstractmethod

from svl.parser_rd import (
    Program, Module, FuncDecl, StructDecl, ConstDecl, VarDecl, Block,
    LetStmt, IfStmt, WhileStmt, ForStmt, ReturnStmt, AssertStmt, TryStmt, ExprStmt,
    BinaryExpr, UnaryExpr, AssignExpr, TernaryExpr, CallExpr, MatchExpr,
    AwaitExpr, LambdaExpr, StructLit, ArrayLit, Ident, Literal, FieldAccess, IndexExpr,
    CastExpr,
)


# ============================================================================
# I32 arithmetic helpers
# ============================================================================

I32_MIN = -(2 ** 31)
I32_MAX = 2 ** 31 - 1
NEG_INF = '-inf'
POS_INF = '+inf'


def _is_num(x) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _const(v: int) -> 'Interval':
    return Interval(lower=v, upper=v)


def _ext_mul(x, y):
    """Multiply two extended ints (int or +/-inf), for interval corner products."""
    if _is_num(x) and _is_num(y):
        return x * y
    if _is_num(x):
        if x == 0:
            return 0
        return POS_INF if x > 0 else NEG_INF
    if _is_num(y):
        if y == 0:
            return 0
        return POS_INF if y > 0 else NEG_INF
    sx = 1 if x == POS_INF else -1
    sy = 1 if y == POS_INF else -1
    return POS_INF if sx * sy > 0 else NEG_INF


def _ext_min(a, b):
    if not _is_num(a):
        return a
    if not _is_num(b):
        return b
    return min(a, b)


def _ext_max(a, b):
    if not _is_num(a):
        return a
    if not _is_num(b):
        return b
    return max(a, b)


def _min_int(a, b):
    """min() that treats '+inf' as larger than every int."""
    if not _is_num(b):
        return a
    if not _is_num(a):
        return b
    return min(a, b)


def _max_int(a, b):
    """max() that treats '-inf' as smaller than every int."""
    if not _is_num(b):
        return a
    if not _is_num(a):
        return b
    return max(a, b)


def _wrap_iv(lo, hi) -> 'Interval':
    """Build an interval, or TOP when the bounds leave the i32 range.

    An interval whose endpoints are inside ``[I32_MIN, I32_MAX]`` is realised exactly by
    WASM ``i32`` arithmetic.  Outside it, the machine wraps and the true value can be any
    element of a wrapped range, so the only sound abstract value is ``top``.
    """
    if _is_num(lo) and lo < I32_MIN:
        return _TOP_IV
    if _is_num(hi) and hi > I32_MAX:
        return _TOP_IV
    return Interval(lower=lo, upper=hi)


def _iv_join(a: 'Interval', b: 'Interval') -> 'Interval':
    if a.is_bottom:
        return b
    if b.is_bottom:
        return a
    if a.is_top or b.is_top:
        return _TOP_IV
    return Interval(lower=_ext_min(a.lower, b.lower), upper=_ext_max(a.upper, b.upper))


def _iv_join_all(ivs: List['Interval']) -> 'Interval':
    if not ivs:
        return _TOP_IV
    out = _BOT_IV
    for iv in ivs:
        out = _iv_join(out, iv)
    return out


def _iv_meet(a: 'Interval', b: 'Interval') -> Optional['Interval']:
    if a.is_bottom or b.is_bottom:
        return _BOT_IV
    if a.is_top:
        return b
    if b.is_top:
        return a
    lo = _ext_max(a.lower, b.lower)
    hi = _ext_min(a.upper, b.upper)
    if _is_num(lo) and _is_num(hi) and lo > hi:
        return _BOT_IV
    return Interval(lower=lo, upper=hi)


def _iv_widen(a: 'Interval', b: 'Interval') -> 'Interval':
    """Widening: keep a's bounds, drop any bound that b pushed outward."""
    if a.is_bottom:
        return b
    if b.is_bottom:
        return a
    if a.is_top or b.is_top:
        return _TOP_IV
    if _is_num(a.lower) and _is_num(b.lower) and b.lower < a.lower:
        lo = NEG_INF
    else:
        lo = a.lower
    if _is_num(a.upper) and _is_num(b.upper) and b.upper > a.upper:
        hi = POS_INF
    else:
        hi = a.upper
    return Interval(lower=lo, upper=hi)


def _iv_leq(a: 'Interval', b: 'Interval') -> bool:
    """a <= b in the interval order, i.e. every value of a is a value of b."""
    if a.is_bottom:
        return True
    if b.is_top:
        return True
    if a.is_top or b.is_bottom:
        return False
    lo_ok = (not _is_num(b.lower)) or (_is_num(a.lower) and a.lower >= b.lower)
    hi_ok = (not _is_num(b.upper)) or (_is_num(a.upper) and a.upper <= b.upper)
    return lo_ok and hi_ok


def _trunc_div(a: int, b: int) -> int:
    """WASM ``i32.div_s``: truncate toward zero."""
    q = abs(a) // abs(b)
    return -q if (a < 0) != (b < 0) else q


def _iv_add(a: 'Interval', b: 'Interval') -> 'Interval':
    if a.is_bottom or b.is_bottom:
        return _BOT_IV
    if a.is_top or b.is_top:
        return _TOP_IV
    lo = NEG_INF if (not _is_num(a.lower) or not _is_num(b.lower)) else a.lower + b.lower
    hi = POS_INF if (not _is_num(a.upper) or not _is_num(b.upper)) else a.upper + b.upper
    return _wrap_iv(lo, hi)


def _iv_sub(a: 'Interval', b: 'Interval') -> 'Interval':
    if a.is_bottom or b.is_bottom:
        return _BOT_IV
    if a.is_top or b.is_top:
        return _TOP_IV
    lo = NEG_INF if (not _is_num(a.lower) or not _is_num(b.upper)) else a.lower - b.upper
    hi = POS_INF if (not _is_num(a.upper) or not _is_num(b.lower)) else a.upper - b.lower
    return _wrap_iv(lo, hi)


def _iv_mul(a: 'Interval', b: 'Interval') -> 'Interval':
    if a.is_bottom or b.is_bottom:
        return _BOT_IV
    if a.is_top or b.is_top:
        return _TOP_IV
    cands = [_ext_mul(x, y) for x in (a.lower, a.upper) for y in (b.lower, b.upper)]
    lo = cands[0]
    hi = cands[0]
    for c in cands[1:]:
        lo = _ext_min(lo, c)
        hi = _ext_max(hi, c)
    return _wrap_iv(lo, hi)


def _iv_neg(a: 'Interval') -> 'Interval':
    if a.is_bottom:
        return _BOT_IV
    if a.is_top:
        return _TOP_IV
    lo = NEG_INF if not _is_num(a.upper) else -a.upper
    hi = POS_INF if not _is_num(a.lower) else -a.lower
    return _wrap_iv(lo, hi)


def _iv_div(a: 'Interval', b: 'Interval') -> 'Interval':
    """Interval division.  Caller is responsible for the zero-divisor finding."""
    if a.is_bottom or b.is_bottom:
        return _BOT_IV
    if a.is_top or b.is_top:
        return _TOP_IV
    # A divisor whose range contains 0 cannot be bounded.
    if _is_num(b.lower) and b.lower <= 0 <= b.upper and _is_num(b.upper):
        return _TOP_IV
    if not (_is_num(b.lower) and _is_num(b.upper)):
        return _TOP_IV
    cands: List[int] = []
    for x in (a.lower, a.upper):
        if not _is_num(x):
            continue
        for y in (b.lower, b.upper):
            if y != 0:
                cands.append(_trunc_div(x, y))
    if not cands:
        return _TOP_IV
    lo, hi = min(cands), max(cands)
    # 0 is attainable whenever the dividend's range straddles it.
    if _is_num(a.lower) and _is_num(a.upper) and a.lower <= 0 <= a.upper:
        lo = min(lo, 0)
        hi = max(hi, 0)
    return _wrap_iv(lo, hi)


def _iv_rem(a: 'Interval', b: 'Interval') -> 'Interval':
    """``i32.rem_s``: result sign follows the dividend, magnitude < |divisor|."""
    if a.is_bottom or b.is_bottom:
        return _BOT_IV
    if a.is_top or b.is_top:
        return _TOP_IV
    if not (_is_num(b.lower) and _is_num(b.upper)):
        return _TOP_IV
    if b.lower <= 0 <= b.upper:
        return _TOP_IV
    dmax = max(abs(b.lower), abs(b.upper))
    return Interval(lower=-(dmax - 1), upper=dmax - 1)


def _cmp_const(x: int, y: int, op: str) -> bool:
    if op == '==':
        return x == y
    if op == '!=':
        return x != y
    if op == '<':
        return x < y
    if op == '<=':
        return x <= y
    if op == '>':
        return x > y
    if op == '>=':
        return x >= y
    return False


def _iv_cmp(a: 'Interval', b: 'Interval', op: str) -> 'Interval':
    if a.is_bottom or b.is_bottom:
        return _BOT_IV
    # Exact when both sides are singletons.
    if (_is_num(a.lower) and a.lower == a.upper
            and _is_num(b.lower) and b.lower == b.upper):
        return _const(1 if _cmp_const(a.lower, b.lower, op) else 0)
    # Decided by disjointness for the ordering comparisons.
    if op in ('<', '<=', '>', '>='):
        if _is_num(a.upper) and _is_num(b.lower) and a.upper < b.lower:
            return _const(1 if op in ('<', '<=') else 0)
        if _is_num(b.upper) and _is_num(a.lower) and b.upper < a.lower:
            return _const(1 if op in ('>', '>=') else 0)
    return Interval(lower=0, upper=1)


# ============================================================================
# DOMAINS
# ============================================================================

class AbstractDomain(ABC):
    """Base class for abstract domains."""

    @abstractmethod
    def bottom(self) -> 'AbstractValue':
        """Bottom element (unreachable)."""

    @abstractmethod
    def top(self) -> 'AbstractValue':
        """Top element (any value)."""

    @abstractmethod
    def join(self, a: 'AbstractValue', b: 'AbstractValue') -> 'AbstractValue':
        """Least upper bound (union)."""

    @abstractmethod
    def meet(self, a: 'AbstractValue', b: 'AbstractValue') -> 'AbstractValue':
        """Greatest lower bound (intersection)."""

    @abstractmethod
    def widen(self, a: 'AbstractValue', b: 'AbstractValue') -> 'AbstractValue':
        """Widening operator for fixpoint convergence."""

    @abstractmethod
    def narrow(self, a: 'AbstractValue', b: 'AbstractValue') -> 'AbstractValue':
        """Narrowing operator for precision improvement."""

    @abstractmethod
    def leq(self, a: 'AbstractValue', b: 'AbstractValue') -> bool:
        """Partial order: a <= b."""


@dataclass
class AbstractValue:
    """Base abstract value."""
    domain_name: str
    is_bottom: bool = False
    is_top: bool = False


# ============================================================================
# INTERVAL DOMAIN
# ============================================================================

@dataclass
class Interval(AbstractValue):
    """Interval abstract domain: [lower, upper]"""
    lower: Union[int, float, str] = '-inf'  # '-inf' for negative infinity
    upper: Union[int, float, str] = '+inf'  # '+inf' for positive infinity

    def __init__(self, lower: Union[int, float, str] = '-inf', upper: Union[int, float, str] = '+inf',
                 is_bottom: bool = False, is_top: bool = False):
        super().__init__(domain_name='interval', is_bottom=is_bottom, is_top=is_top)
        self.lower = lower
        self.upper = upper

    @staticmethod
    def bottom() -> 'Interval':
        return Interval(is_bottom=True)

    @staticmethod
    def top() -> 'Interval':
        return Interval(is_top=True)

    @staticmethod
    def from_value(v: Union[int, float]) -> 'Interval':
        return Interval(lower=v, upper=v)

    def __repr__(self):
        if self.is_bottom:
            return "Interval(bottom)"
        if self.is_top:
            return "Interval(top)"
        return f"[{self.lower}, {self.upper}]"

    def __eq__(self, other):
        if not isinstance(other, Interval):
            return False
        return (self.is_bottom == other.is_bottom and
                self.is_top == other.is_top and
                self.lower == other.lower and
                self.upper == other.upper)

    def __hash__(self):
        return hash((self.is_bottom, self.is_top, str(self.lower), str(self.upper)))


# Shared singletons.  Defined after Interval: the helpers above only reference them at
# call time, so a single immutable instance is safe to reuse everywhere.
_TOP_IV = Interval(is_top=True)
_BOT_IV = Interval(is_bottom=True)


class IntervalDomain(AbstractDomain):
    """Interval abstract domain implementation."""

    def bottom(self) -> Interval:
        return Interval.bottom()

    def top(self) -> Interval:
        return Interval.top()

    def join(self, a: Interval, b: Interval) -> Interval:
        return _iv_join(a, b)

    def meet(self, a: Interval, b: Interval) -> Interval:
        r = _iv_meet(a, b)
        return r if r is not None else Interval.bottom()

    def widen(self, a: Interval, b: Interval) -> Interval:
        return _iv_widen(a, b)

    def narrow(self, a: Interval, b: Interval) -> Interval:
        if a.is_top or b.is_bottom:
            return b
        return self.meet(a, b)

    def leq(self, a: Interval, b: Interval) -> bool:
        return _iv_leq(a, b)


# ============================================================================
# CONGRUENCE DOMAIN (modulo arithmetic)
# ============================================================================

@dataclass
class Congruence(AbstractValue):
    """Congruence abstract domain: x ≡ r (mod m)"""
    remainder: Union[int, str] = 'any'  # 'any' for top
    modulus: Union[int, str] = 'any'

    def __init__(self, remainder: Union[int, str] = 'any', modulus: Union[int, str] = 'any',
                 is_bottom: bool = False, is_top: bool = False):
        super().__init__(domain_name='congruence', is_bottom=is_bottom, is_top=is_top)
        self.remainder = remainder
        self.modulus = modulus

    @staticmethod
    def bottom() -> 'Congruence':
        return Congruence(is_bottom=True)

    @staticmethod
    def top() -> 'Congruence':
        return Congruence(is_top=True)

    @staticmethod
    def from_value(v: int, m: int = 0) -> 'Congruence':
        if m == 0:
            return Congruence(remainder=v, modulus='exact')
        return Congruence(remainder=v % m, modulus=m)

    def __repr__(self):
        if self.is_bottom:
            return "Congruence(bottom)"
        if self.is_top:
            return "Congruence(top)"
        if self.modulus == 'exact':
            return f"={self.remainder}"
        return f"≡{self.remainder} (mod {self.modulus})"

    def __eq__(self, other):
        if not isinstance(other, Congruence):
            return False
        return (self.is_bottom == other.is_bottom and
                self.is_top == other.is_top and
                self.remainder == other.remainder and
                self.modulus == other.modulus)


class CongruenceDomain(AbstractDomain):
    """Congruence abstract domain implementation."""

    def bottom(self) -> Congruence:
        return Congruence.bottom()

    def top(self) -> Congruence:
        return Congruence.top()

    def join(self, a: Congruence, b: Congruence) -> Congruence:
        if a.is_bottom:
            return b
        if b.is_bottom:
            return a
        if a.is_top or b.is_top:
            return Congruence.top()

        # If both are exact values
        if a.modulus == 'exact' and b.modulus == 'exact':
            if a.remainder == b.remainder:
                return Congruence(remainder=a.remainder, modulus='exact')
            return Congruence.top()

        # If one is exact, check compatibility
        if a.modulus == 'exact':
            if isinstance(b.modulus, int) and a.remainder % b.modulus == b.remainder:
                return b
            return Congruence.top()
        if b.modulus == 'exact':
            if isinstance(a.modulus, int) and b.remainder % a.modulus == a.remainder:
                return a
            return Congruence.top()

        # Both have modulus: find common modulus
        if isinstance(a.modulus, int) and isinstance(b.modulus, int):
            from math import gcd
            common_mod = gcd(a.modulus, b.modulus)
            if common_mod == 1:
                return Congruence.top()
            # Check if remainders are compatible
            if a.remainder % common_mod == b.remainder % common_mod:
                return Congruence(remainder=a.remainder % common_mod, modulus=common_mod)

        return Congruence.top()

    def meet(self, a: Congruence, b: Congruence) -> Congruence:
        if a.is_bottom or b.is_bottom:
            return Congruence.bottom()
        if a.is_top:
            return b
        if b.is_top:
            return a

        # Meet of congruences: more precise information
        return self.join(a, b)  # Simplified

    def widen(self, a: Congruence, b: Congruence) -> Congruence:
        # Widening for congruences: if modulus decreases, jump to top
        if a.is_top or b.is_top:
            return Congruence.top()
        if a.is_bottom:
            return b

        if isinstance(a.modulus, int) and isinstance(b.modulus, int):
            if b.modulus < a.modulus:
                return Congruence.top()

        return self.join(a, b)

    def narrow(self, a: Congruence, b: Congruence) -> Congruence:
        return self.meet(a, b)

    def leq(self, a: Congruence, b: Congruence) -> bool:
        if a.is_bottom:
            return True
        if b.is_top:
            return True
        if a.is_top or b.is_bottom:
            return False

        if a.modulus == 'exact':
            if b.modulus == 'exact':
                return a.remainder == b.remainder
            if isinstance(b.modulus, int):
                return a.remainder % b.modulus == b.remainder
            return True

        if b.modulus == 'exact':
            return False

        if isinstance(a.modulus, int) and isinstance(b.modulus, int):
            return a.modulus % b.modulus == 0 and a.remainder % b.modulus == b.remainder

        return False


# ============================================================================
# PRODUCT DOMAIN (combining multiple domains)
# ============================================================================

@dataclass
class ProductValue(AbstractValue):
    """Product of multiple abstract domains."""
    components: Dict[str, AbstractValue] = field(default_factory=dict)

    def __init__(self, components: Dict[str, AbstractValue] = None):
        super().__init__(domain_name='product')
        self.components = components or {}

    def __repr__(self):
        return f"Product({self.components})"

    def __eq__(self, other):
        if not isinstance(other, ProductValue):
            return False
        return self.components == other.components


class ProductDomain(AbstractDomain):
    """Product of multiple abstract domains."""

    def __init__(self, domains: Dict[str, AbstractDomain]):
        self.domains = domains

    def bottom(self) -> ProductValue:
        return ProductValue({name: d.bottom() for name, d in self.domains.items()})

    def top(self) -> ProductValue:
        return ProductValue({name: d.top() for name, d in self.domains.items()})

    def join(self, a: ProductValue, b: ProductValue) -> ProductValue:
        return ProductValue({
            name: self.domains[name].join(a.components[name], b.components[name])
            for name in self.domains
        })

    def meet(self, a: ProductValue, b: ProductValue) -> ProductValue:
        return ProductValue({
            name: self.domains[name].meet(a.components[name], b.components[name])
            for name in self.domains
        })

    def widen(self, a: ProductValue, b: ProductValue) -> ProductValue:
        return ProductValue({
            name: self.domains[name].widen(a.components[name], b.components[name])
            for name in self.domains
        })

    def narrow(self, a: ProductValue, b: ProductValue) -> ProductValue:
        return ProductValue({
            name: self.domains[name].narrow(a.components[name], b.components[name])
            for name in self.domains
        })

    def leq(self, a: ProductValue, b: ProductValue) -> bool:
        return all(
            self.domains[name].leq(a.components[name], b.components[name])
            for name in self.domains
        )


# ============================================================================
# ABSTRACT STATE
# ============================================================================

class _State:
    """Abstract state: variable intervals plus per-path array lengths.

    Missing keys are read as ``top`` rather than ``bottom``: joining two branches where a
    variable was only assigned on one side must not forget the other possibility.
    """

    __slots__ = ('env', 'lens')

    def __init__(self, env: Optional[Dict[str, Interval]] = None,
                 lens: Optional[Dict[str, Interval]] = None):
        self.env: Dict[str, Interval] = env if env is not None else {}
        self.lens: Dict[str, Interval] = lens if lens is not None else {}

    def copy(self) -> '_State':
        return _State(dict(self.env), dict(self.lens))

    def get(self, name: str) -> Interval:
        return self.env.get(name, _TOP_IV)

    def set(self, name: str, iv: Interval) -> '_State':
        s = self.copy()
        s.env[name] = iv
        return s

    def set_len(self, name: str, iv: Interval) -> '_State':
        s = self.copy()
        s.lens[name] = iv
        return s

    def join(self, other: '_State') -> '_State':
        env = {k: _iv_join(self.env.get(k, _TOP_IV), other.env.get(k, _TOP_IV))
               for k in set(self.env) | set(other.env)}
        lens = {k: _iv_join(self.lens.get(k, _TOP_IV), other.lens.get(k, _TOP_IV))
                for k in set(self.lens) | set(other.lens)}
        return _State(env, lens)

    def widen(self, other: '_State') -> '_State':
        env = {k: _iv_widen(self.env.get(k, _TOP_IV), other.env.get(k, _TOP_IV))
               for k in set(self.env) | set(other.env)}
        lens = {k: _iv_widen(self.lens.get(k, _TOP_IV), other.lens.get(k, _TOP_IV))
                for k in set(self.lens) | set(other.lens)}
        return _State(env, lens)

    def leq(self, other: '_State') -> bool:
        keys = set(self.env) | set(other.env)
        return all(_iv_leq(self.env.get(k, _TOP_IV), other.env.get(k, _TOP_IV))
                   for k in keys)

    def __eq__(self, other):
        if not isinstance(other, _State):
            return False
        return self.env == other.env and self.lens == other.lens


# ============================================================================
# FINDINGS
# ============================================================================

@dataclass
class Finding:
    """A provable property violation discovered by the analysis."""
    kind: str           # 'oob-index' | 'div-zero' | 'div-overflow'
    message: str
    line: int
    function: str
    severity: str = 'error'


@dataclass
class AnalysisResult:
    findings: List[Finding] = field(default_factory=list)
    internal_errors: List[str] = field(default_factory=list)
    state: Any = None

    @property
    def errors(self) -> List[Finding]:
        return [f for f in self.findings if f.severity == 'error']

    @property
    def warnings(self) -> List[str]:
        return [f.message for f in self.findings if f.severity != 'error']

    @property
    def passed(self) -> bool:
        return not self.errors

    @property
    def ok(self) -> bool:
        """True when the analysis ran cleanly and proved nothing wrong."""
        return self.passed and not self.internal_errors


# ============================================================================
# STRUCTURE COLLECTION
# ============================================================================

def _collect(ast: Program):
    """Return (functions-by-name, exported-names, module-level constants)."""
    functions: Dict[str, FuncDecl] = {}
    exported: Set[str] = set()
    globals_const: Dict[str, Interval] = {}

    def walk_block(block):
        for stmt in getattr(block, 'statements', []) or []:
            if isinstance(stmt, FuncDecl):
                functions[stmt.name] = stmt
            elif isinstance(stmt, ConstDecl):
                iv = _static_const(stmt.value)
                globals_const[stmt.name] = iv if iv is not None else _TOP_IV
            elif isinstance(stmt, VarDecl):
                globals_const.setdefault(stmt.name, _TOP_IV)

    for mod in getattr(ast, 'modules', []) or []:
        walk_block(mod.body)
        for stmt in getattr(mod.body, 'statements', []) or []:
            if isinstance(stmt, Module):
                walk_block(stmt.body)
    for item in getattr(ast, 'items', []) or []:
        if isinstance(item, FuncDecl):
            functions[item.name] = item
        elif isinstance(item, ConstDecl):
            iv = _static_const(item.value)
            globals_const[item.name] = iv if iv is not None else _TOP_IV
        elif isinstance(item, VarDecl):
            globals_const.setdefault(item.name, _TOP_IV)
    for e in getattr(ast, 'exports', []) or []:
        exported.add(getattr(e, 'name', ''))
    return functions, exported, globals_const


def _static_const(expr) -> Optional[Interval]:
    """Exact interval for a constant expression, or None."""
    if isinstance(expr, Literal) and _is_num(expr.value):
        return _const(expr.value)
    if isinstance(expr, UnaryExpr) and expr.operator == '-' and isinstance(expr.operand, Literal):
        v = expr.operand.value
        if _is_num(v):
            return _const(-v)
    return None


# ============================================================================
# THE ANALYZER
# ============================================================================

_MAX_LOOP_PASSES = 16
_WIDEN_AFTER = 2
_MAX_INTERPROC_PASSES = 6


class _Analyzer:
    """One analysis pass over every function with a fixed set of parameter states."""

    def __init__(self, functions: Dict[str, FuncDecl], exported: Set[str],
                 globals_const: Dict[str, Interval]):
        self.functions = functions
        self.exported = exported
        self.globals_const = globals_const
        self.findings: List[Finding] = []
        self.call_sites: Dict[str, List[Tuple[str, List[Interval]]]] = {}
        self.current_function = '<module>'
        # Functions currently being summarised, so a (direct or indirect) recursion
        # returns TOP instead of recursing forever.
        self._summarizing: Set[str] = set()

    # -- driver ---------------------------------------------------------------

    def run_all(self, param_states: Dict[str, Dict[str, Interval]]) -> List[str]:
        errors: List[str] = []
        self.findings = []
        self.call_sites = {}
        for name, fn in self.functions.items():
            try:
                env = dict(self.globals_const)
                env.update(param_states.get(name, {}))
                self.current_function = name
                self._block(fn.body, _State(env=env))
            except Exception as exc:  # noqa: BLE001 - recorded, never fatal to the compiler
                errors.append(f"{name}: {type(exc).__name__}: {exc}")
        self.current_function = '<module>'
        return errors

    def run_function(self, fn: FuncDecl, env: Dict[str, Interval]) -> List[str]:
        self.findings = []
        self.call_sites = {}
        self.current_function = fn.name
        try:
            self._block(fn.body, _State(env=dict(env)))
            return []
        except Exception as exc:  # noqa: BLE001
            return [f"{fn.name}: {type(exc).__name__}: {exc}"]
        finally:
            self.current_function = '<module>'

    # -- helpers --------------------------------------------------------------

    def _line(self, node) -> int:
        return int(getattr(node, 'line', 0) or 0)

    def _add_finding(self, kind: str, message: str, line: int) -> None:
        self.findings.append(Finding(kind=kind, message=message, line=line,
                                     function=self.current_function))

    @staticmethod
    def _key(expr) -> Optional[str]:
        """Lvalue path for a variable or struct field, else None."""
        if isinstance(expr, Ident):
            return expr.name
        if isinstance(expr, FieldAccess):
            base = _Analyzer._key(expr.left)
            if base is None:
                return None
            right = getattr(expr.right, 'name', None)
            return f"{base}.{right}" if right else None
        return None

    # -- statements -----------------------------------------------------------

    def _block(self, block: Block, state: Optional[_State]) -> Optional[_State]:
        for stmt in getattr(block, 'statements', []) or []:
            if state is None:
                return None
            state = self._exec(stmt, state)
        return state

    def _exec(self, stmt, state: Optional[_State]) -> Optional[_State]:
        if state is None:
            return None
        if isinstance(stmt, LetStmt):
            return self._exec_let(stmt, state)
        if isinstance(stmt, AssignExpr):
            return self._exec_assign(stmt, state)
        if isinstance(stmt, ExprStmt):
            # An assignment is a statement in SVL (`i += 1`, `a[i] = v`, `g.cells = zeros(n)`)
            # and the parser wraps it in ExprStmt like any other expression.  Its state
            # update must survive; evaluating it as a plain expression would drop it.
            if isinstance(stmt.expression, AssignExpr):
                return self._exec_assign(stmt.expression, state)
            self._eval(stmt.expression, state)
            return state
        if isinstance(stmt, IfStmt):
            return self._exec_if(stmt, state)
        if isinstance(stmt, WhileStmt):
            return self._exec_while(stmt, state)
        if isinstance(stmt, ForStmt):
            return self._exec_for(stmt, state)
        if isinstance(stmt, ReturnStmt):
            if stmt.value is not None:
                self._eval(stmt.value, state)
            return state
        if isinstance(stmt, AssertStmt):
            self._eval(stmt.condition, state)
            return self._refine(state, stmt.condition, True)
        if isinstance(stmt, Block):
            return self._block(stmt, state)
        if isinstance(stmt, TryStmt):
            try_state = self._block(stmt.try_block, state)
            catch_state = self._block(stmt.catch_block, state)
            if try_state is None:
                return catch_state
            if catch_state is None:
                return try_state
            return try_state.join(catch_state)
        # Unknown statement shape: do not crash, do not invent facts.
        return state

    def _exec_let(self, stmt: LetStmt, state: _State) -> _State:
        val = self._eval(stmt.value, state)
        new = state.set(stmt.name, val)
        length = self._infer_length(stmt.value, state)
        if length is not None:
            new = new.set_len(stmt.name, length)
        return new

    def _exec_if(self, stmt: IfStmt, state: _State) -> Optional[_State]:
        self._eval(stmt.condition, state)
        then_state = self._block(stmt.then_branch, self._refine(state, stmt.condition, True))
        if stmt.else_branch is not None:
            else_state = self._block(stmt.else_branch, self._refine(state, stmt.condition, False))
        else:
            else_state = self._refine(state, stmt.condition, False)
        if then_state is None:
            return else_state
        if else_state is None:
            return then_state
        return then_state.join(else_state)

    def _exec_while(self, stmt: WhileStmt, state: _State) -> Optional[_State]:
        self._eval(stmt.condition, state)
        s = state
        for i in range(_MAX_LOOP_PASSES):
            body_in = self._refine(s, stmt.condition, True)
            if body_in is None:
                return self._refine(s, stmt.condition, False)
            body_out = self._block(stmt.body, body_in)
            if body_out is None:
                body_out = body_in
            joined = s.join(body_out)
            new = s.widen(joined) if i >= _WIDEN_AFTER else joined
            if new == s:
                break
            s = new
        return self._refine(s, stmt.condition, False)

    def _exec_for(self, stmt: ForStmt, state: _State) -> Optional[_State]:
        iter_expr = stmt.iter_expr
        if isinstance(iter_expr, BinaryExpr) and iter_expr.operator == '..':
            start = self._eval(iter_expr.left, state)
            end = self._eval(iter_expr.right, state)
            s = state.set(stmt.var, start)
            for i in range(_MAX_LOOP_PASSES):
                body_in = self._refine_bound(s, stmt.var, end, '<', True)
                if body_in is None:
                    return self._refine_bound(s, stmt.var, end, '<', False)
                body_out = self._block(stmt.body, body_in)
                if body_out is None:
                    body_out = body_in
                cur = body_out.env.get(stmt.var, _TOP_IV)
                body_out = body_out.set(stmt.var, _iv_add(cur, _const(1)))
                joined = s.join(body_out)
                new = s.widen(joined) if i >= _WIDEN_AFTER else joined
                if new == s:
                    break
                s = new
            return self._refine_bound(s, stmt.var, end, '<', False)
        # Iterator form (`for x in xs`): the element type/values are unknown.
        self._eval(iter_expr, state)
        body_in = state.set(stmt.var, _TOP_IV)
        body_out = self._block(stmt.body, body_in)
        if body_out is None:
            return state
        return state.join(body_out)

    def _exec_assign(self, stmt: AssignExpr, state: _State) -> _State:
        target = stmt.target
        if isinstance(target, IndexExpr):
            self._check_index(target, state)
            self._eval(stmt.value, state)
            return state
        val = self._eval(stmt.value, state)
        if isinstance(target, Ident):
            cur = state.env.get(target.name, _TOP_IV)
            new_val = val if stmt.operator == '=' else self._apply_compound(stmt, cur, val, state)
            new = state.set(target.name, new_val)
            length = self._infer_length(stmt.value, state)
            if length is not None:
                new = new.set_len(target.name, length)
            return new
        if isinstance(target, FieldAccess):
            key = self._key(target)
            if key is None:
                self._eval(target.left, state)
                return state
            cur = state.env.get(key, _TOP_IV)
            new_val = val if stmt.operator == '=' else self._apply_compound(stmt, cur, val, state)
            new = state.set(key, new_val)
            length = self._infer_length(stmt.value, state)
            if length is not None:
                new = new.set_len(key, length)
            return new
        return state

    def _apply_compound(self, stmt: AssignExpr, cur: Interval, val: Interval,
                        state: _State) -> Interval:
        op = stmt.operator
        if not op.endswith('=') or len(op) < 2:
            return val
        base = op[:-1]
        if base == '+':
            return _iv_add(cur, val)
        if base == '-':
            return _iv_sub(cur, val)
        if base == '*':
            return _iv_mul(cur, val)
        if base == '/':
            self._check_divisor(stmt, cur, val)
            return _iv_div(cur, val)
        if base == '%':
            self._check_divisor(stmt, cur, val)
            return _iv_rem(cur, val)
        # Bitwise / shift compounds carry no usable interval information.
        return _TOP_IV

    def _infer_length(self, expr, state: _State) -> Optional[Interval]:
        """Statically known length of an array-valued expression, if any."""
        if isinstance(expr, ArrayLit):
            return _const(len(expr.elements))
        if isinstance(expr, CallExpr) and expr.callee == 'zeros' and expr.arguments:
            return self._eval(expr.arguments[0], state)
        key = self._key(expr)
        if key is not None and key in state.lens:
            return state.lens[key]
        return None

    # -- expressions ----------------------------------------------------------

    def _eval(self, expr, state: _State) -> Interval:
        if expr is None:
            return _TOP_IV
        if isinstance(expr, Literal):
            v = expr.value
            if isinstance(v, bool):
                return _const(1 if v else 0)
            if _is_num(v):
                return _const(v)
            return _TOP_IV
        if isinstance(expr, Ident):
            return state.env.get(expr.name, _TOP_IV)
        if isinstance(expr, BinaryExpr):
            return self._eval_binary(expr, state)
        if isinstance(expr, UnaryExpr):
            self._eval(expr.operand, state)
            if expr.operator == '-':
                return _iv_neg(self._eval(expr.operand, state))
            return Interval(lower=0, upper=1) if expr.operator == '!' else _TOP_IV
        if isinstance(expr, IndexExpr):
            self._check_index(expr, state)
            return _TOP_IV
        if isinstance(expr, FieldAccess):
            key = self._key(expr)
            if key is None:
                self._eval(expr.left, state)
                return _TOP_IV
            self._eval(expr.left, state)
            return state.env.get(key, _TOP_IV)
        if isinstance(expr, CallExpr):
            return self._eval_call(expr, state)
        if isinstance(expr, ArrayLit):
            for e in expr.elements:
                self._eval(e, state)
            return _TOP_IV
        if isinstance(expr, StructLit):
            for f in expr.fields:
                self._eval(f.value, state)
            return _TOP_IV
        if isinstance(expr, TernaryExpr):
            self._eval(expr.condition, state)
            a = self._eval(expr.then_expr, state)
            b = self._eval(expr.else_expr, state)
            return _iv_join(a, b)
        if isinstance(expr, AssignExpr):
            self._exec_assign(expr, state)
            return _TOP_IV
        if isinstance(expr, MatchExpr):
            return self._eval_match(expr, state)
        if isinstance(expr, AwaitExpr):
            return self._eval(expr.expression, state)
        if isinstance(expr, LambdaExpr):
            return _TOP_IV
        if isinstance(expr, CastExpr):
            return self._eval(expr.expr, state)
        return _TOP_IV

    def _eval_binary(self, expr: BinaryExpr, state: _State) -> Interval:
        op = expr.operator
        if op == '..':
            self._eval(expr.left, state)
            self._eval(expr.right, state)
            return _TOP_IV
        if op == '[]':
            self._check_index(expr, state)
            return _TOP_IV
        if op == '.':
            self._eval(expr.left, state)
            return _TOP_IV
        left = self._eval(expr.left, state)
        if op in ('&&', '||'):
            # Short-circuit: the right operand runs only when the left does not already
            # decide the result.  Evaluating it unconditionally produced a false
            # division-by-zero finding for `x != 0 && 10 / x > 1`.
            if op == '&&':
                if left.upper == 0:                 # left always false -> right unreachable
                    return Interval(lower=0, upper=0)
                self._eval(expr.right, state)
            else:
                if left.lower > 0:                  # left always true -> right unreachable
                    return Interval(lower=1, upper=1)
                self._eval(expr.right, state)
            return Interval(lower=0, upper=1)
        right = self._eval(expr.right, state)
        if op == '+':
            return _iv_add(left, right)
        if op == '-':
            return _iv_sub(left, right)
        if op == '*':
            return _iv_mul(left, right)
        if op == '/':
            self._check_divisor(expr, left, right)
            return _iv_div(left, right)
        if op == '%':
            self._check_divisor(expr, left, right)
            return _iv_rem(left, right)
        if op in ('==', '!=', '<', '<=', '>', '>='):
            return _iv_cmp(left, right, op)
        # Bitwise and shift operators: no interval information.
        return _TOP_IV

    def _eval_call(self, expr: CallExpr, state: _State) -> Interval:
        callee = expr.callee
        args = expr.arguments
        if callee == 'len' and len(args) == 1:
            key = self._key(args[0])
            if key is not None and key in state.lens:
                return state.lens[key]
            self._eval(args[0], state)
            return _TOP_IV
        if callee == 'zeros' and len(args) == 1:
            self._eval(args[0], state)
            return _TOP_IV
        if callee in self.functions:
            arg_ivs = [self._eval(a, state) for a in args]
            self.call_sites.setdefault(callee, []).append((self.current_function, arg_ivs))
            # Call-site specialisation: re-summarise the callee under the ACTUAL
            # argument intervals instead of returning TOP unconditionally.  This is an
            # over-approximation (sound), and `_summarizing` guards recursion.
            return self._return_summary(callee, arg_ivs)
        for a in args:
            self._eval(a, state)
        return _TOP_IV

    def _return_summary(self, callee: str, arg_ivs: List[Interval]) -> Interval:
        """The callee's return interval under the given argument intervals.

        Returns TOP when the body is not straight-line enough to summarise, or when the
        callee is already being summarised (recursion).
        """
        if callee in self._summarizing:
            return _TOP_IV
        fn = self.functions.get(callee)
        if fn is None:
            return _TOP_IV
        env = {p.name: iv for p, iv in zip(fn.params, arg_ivs)}
        self._summarizing.add(callee)
        try:
            return self._branch_return(fn.body, _State(env=dict(env)))
        finally:
            self._summarizing.discard(callee)

    def _branch_return(self, block: Block, state: _State) -> Interval:
        """The interval of the value a block returns (TOP if it does not return)."""
        for stmt in getattr(block, 'statements', []) or []:
            if isinstance(stmt, ReturnStmt):
                return self._eval(stmt.value, state) if stmt.value is not None else _TOP_IV
            if isinstance(stmt, LetStmt):
                state = self._exec_let(stmt, state)
            elif isinstance(stmt, IfStmt):
                then_iv = self._branch_return(stmt.then_branch, state)
                else_iv = (self._branch_return(stmt.else_branch, state)
                           if stmt.else_branch is not None else _TOP_IV)
                return _iv_join(then_iv, else_iv)
            elif isinstance(stmt, ExprStmt) and isinstance(stmt.expression, AssignExpr):
                state = self._exec_assign(stmt.expression, state)
            else:
                return _TOP_IV
        return _TOP_IV

    def _eval_match(self, expr: MatchExpr, state: _State) -> Interval:
        subject = self._eval(expr.subject, state)
        results: List[Interval] = []
        for case in expr.cases:
            case_state = state
            pattern = getattr(case, 'pattern', None)
            if getattr(pattern, 'kind', '') == 'ident' and isinstance(getattr(pattern, 'value', None), str):
                case_state = state.set(pattern.value, subject)
            iv = self._eval(case.body, case_state)
            results.append(iv)
        return _iv_join_all(results)

    # -- checks ---------------------------------------------------------------

    def _check_index(self, node, state: _State) -> None:
        key = self._key(node.left)
        idx = self._eval(node.right, state)
        if idx.is_bottom:
            return
        if _is_num(idx.upper) and idx.upper < 0:
            self._add_finding(
                'oob-index',
                f"provable out-of-bounds index on '{key}': index {idx} is always negative "
                f"(line {self._line(node)})",
                self._line(node))
            return
        if key is None:
            return
        length = state.lens.get(key)
        if length is None or length.is_bottom or length.is_top:
            return
        if _is_num(idx.lower) and _is_num(length.upper) and idx.lower >= length.upper:
            if length.upper == 0:
                scope = "the array is empty"
            else:
                scope = f"valid indices are 0..{length.upper - 1}"
            self._add_finding(
                'oob-index',
                f"provable out-of-bounds index on '{key}': index {idx} is always >= "
                f"length({key}) = {length} ({scope})",
                self._line(node))

    def _check_divisor(self, node, dividend: Interval, divisor: Interval) -> None:
        if divisor.is_bottom:
            return
        if not (_is_num(divisor.lower) and _is_num(divisor.upper)):
            return
        if divisor.lower == 0 and divisor.upper == 0:
            self._add_finding(
                'div-zero',
                f"provable division by zero: divisor is exactly 0 "
                f"(line {self._line(node)})",
                self._line(node))
            return
        # i32.div_s traps on INT_MIN / -1 (the result would be 2**31, unrepresentable).
        if divisor.lower == -1 and divisor.upper == -1 and not dividend.is_bottom:
            if _is_num(dividend.lower) and dividend.lower == dividend.upper == I32_MIN:
                self._add_finding(
                    'div-overflow',
                    f"provable i32 division overflow: {I32_MIN} / -1 traps "
                    f"(line {self._line(node)})",
                    self._line(node))

    # -- refinement -----------------------------------------------------------

    def _refine(self, state: Optional[_State], cond, polarity: bool) -> Optional[_State]:
        """Restrict `state` to the states where `cond` evaluates as `polarity`."""
        if state is None or cond is None:
            return state
        if isinstance(cond, UnaryExpr) and cond.operator == '!':
            return self._refine(state, cond.operand, not polarity)
        if isinstance(cond, BinaryExpr):
            op = cond.operator
            if op == '&&':
                if polarity:
                    return self._refine(self._refine(state, cond.left, True), cond.right, True)
                return state
            if op == '||':
                if not polarity:
                    return self._refine(self._refine(state, cond.left, False), cond.right, False)
                return state
            if op in ('<', '<=', '>', '>=', '==', '!='):
                return self._refine_cmp(state, cond.left, cond.right, op, polarity)
        # Anything else (bare identifiers, calls, arithmetic) carries no usable
        # interval information -- leave the state alone rather than guess.
        return state

    def _refine_cmp(self, state: _State, left, right, op: str,
                    polarity: bool) -> Optional[_State]:
        if isinstance(left, Ident) and not isinstance(right, Ident):
            name, bound, o = left.name, self._eval(right, state), op
        elif isinstance(right, Ident) and not isinstance(left, Ident):
            name, bound, o = right.name, self._eval(left, state), _flip(op)
        elif isinstance(left, Ident) and isinstance(right, Ident):
            name, bound, o = left.name, self._eval(right, state), op
        else:
            return state
        if bound.is_bottom:
            return None
        cur = state.env.get(name, _TOP_IV)
        new = _refine_interval(cur, bound, o, polarity)
        if new is None:
            return None
        return state.set(name, new)

    def _refine_bound(self, state: _State, name: str, bound: Interval, op: str,
                      polarity: bool) -> Optional[_State]:
        if bound.is_bottom:
            return None
        cur = state.env.get(name, _TOP_IV)
        new = _refine_interval(cur, bound, op, polarity)
        if new is None:
            return None
        return state.set(name, new)


def _flip(op: str) -> str:
    return {'<': '>', '<=': '>=', '>': '<', '>=': '<=', '==': '==', '!=': '!='}[op]


def _refine_interval(cur: Interval, bound: Interval, op: str,
                     polarity: bool) -> Optional[Interval]:
    """Intersect `cur` with the states satisfying ``cur OP bound`` (or its negation)."""
    if cur.is_bottom or bound.is_bottom:
        return _BOT_IV
    lo, hi = cur.lower, cur.upper

    if op == '<':
        if polarity:
            if _is_num(bound.upper):
                hi = _min_int(hi, bound.upper - 1)
        else:
            if _is_num(bound.lower):
                lo = _max_int(lo, bound.lower)
    elif op == '<=':
        if polarity:
            if _is_num(bound.upper):
                hi = _min_int(hi, bound.upper)
        else:
            if _is_num(bound.lower):
                lo = _max_int(lo, bound.lower + 1)
    elif op == '>':
        if polarity:
            if _is_num(bound.lower):
                lo = _max_int(lo, bound.lower + 1)
        else:
            if _is_num(bound.upper):
                hi = _min_int(hi, bound.upper)
    elif op == '>=':
        if polarity:
            if _is_num(bound.lower):
                lo = _max_int(lo, bound.lower)
        else:
            if _is_num(bound.upper):
                hi = _min_int(hi, bound.upper - 1)
    elif op == '==':
        if polarity:
            return _iv_meet(cur, bound)
        if _is_num(bound.lower) and bound.lower == bound.upper:
            if _is_num(lo) and lo == hi == bound.lower:
                return _BOT_IV
        return cur
    elif op == '!=':
        if not polarity:
            if _is_num(bound.lower) and bound.lower == bound.upper:
                return _iv_meet(cur, bound)
            return cur
        if _is_num(bound.lower) and bound.lower == bound.upper:
            if _is_num(lo) and lo == hi == bound.lower:
                return _BOT_IV
        return cur

    if _is_num(lo) and _is_num(hi) and lo > hi:
        return _BOT_IV
    return Interval(lower=lo, upper=hi)


# ============================================================================
# PUBLIC ENTRY POINTS
# ============================================================================

def analyze_program(ast: Program) -> AnalysisResult:
    """Run the interval analysis over a parsed SVL program."""
    functions, exported, globals_const = _collect(ast)
    param_states = {name: {p.name: _TOP_IV for p in fn.params}
                    for name, fn in functions.items()}

    internal_errors: List[str] = []
    findings: List[Finding] = []

    # Chaotic iteration over parameter states.  Each pass's states are
    # over-approximations of the real call-site arguments, so any finding reported by
    # the final pass holds for every concrete execution.
    for _ in range(_MAX_INTERPROC_PASSES):
        analyzer = _Analyzer(functions, exported, globals_const)
        internal_errors.extend(analyzer.run_all(param_states))
        new_states: Dict[str, Dict[str, Interval]] = {}
        changed = False
        for name, fn in functions.items():
            params = {p.name: _TOP_IV for p in fn.params}
            sites = analyzer.call_sites.get(name)
            if name not in exported and sites:
                for i, p in enumerate(fn.params):
                    ivs = [arg_ivs[i] for _caller, arg_ivs in sites if i < len(arg_ivs)]
                    params[p.name] = _iv_join_all(ivs)
            new_states[name] = params
            if params != param_states[name]:
                changed = True
        param_states = new_states
        if not changed:
            break

    # Final pass with the converged parameter states, so the reported findings are
    # exactly the ones that hold for those states.
    analyzer = _Analyzer(functions, exported, globals_const)
    internal_errors.extend(analyzer.run_all(param_states))
    findings = analyzer.findings

    return AnalysisResult(findings=findings, internal_errors=internal_errors,
                          state=param_states)


def analyze_function(func_ast: FuncDecl,
                     param_state: Optional[Dict[str, Interval]] = None) -> AnalysisResult:
    """Analyse a single function declaration."""
    analyzer = _Analyzer({func_ast.name: func_ast}, set(), {})
    env = {p.name: _TOP_IV for p in func_ast.params}
    if param_state:
        env.update(param_state)
    errors = analyzer.run_function(func_ast, env)
    return AnalysisResult(findings=analyzer.findings, internal_errors=errors)


def analyze_type_bounds(ast: Program) -> Dict[str, Any]:
    """Analyze array bounds, overflow, division by zero using abstract interpretation."""
    result = analyze_program(ast)
    return {
        'state': result.state,
        'findings': [{'kind': f.kind, 'message': f.message, 'line': f.line,
                      'function': f.function, 'severity': f.severity}
                     for f in result.findings],
        'warnings': [f.message for f in result.findings],
        'passed': result.passed,
        'internal_errors': list(result.internal_errors),
    }


class AbstractInterpreter:
    """Abstract interpreter for SVL programs (interval domain by default)."""

    def __init__(self, domain: Optional[AbstractDomain] = None):
        self.domain = domain if domain is not None else IntervalDomain()

    def analyze_program(self, ast: Program) -> AnalysisResult:
        """Analyze an entire program."""
        return analyze_program(ast)

    def analyze_function(self, func_ast: FuncDecl,
                         param_state: Optional[Dict[str, Interval]] = None) -> AnalysisResult:
        """Analyze one function body with a fixpoint over its loops."""
        return analyze_function(func_ast, param_state)


def create_type_analysis_domain() -> ProductDomain:
    """Create product domain for type layer analysis."""
    return ProductDomain({
        'interval': IntervalDomain(),
        'congruence': CongruenceDomain(),
    })


if __name__ == '__main__':
    print("=== Abstract Interpretation Test ===")

    interval_dom = IntervalDomain()
    a = Interval(lower=0, upper=10)
    b = Interval(lower=5, upper=15)

    print(f"Interval a: {a}")
    print(f"Interval b: {b}")
    print(f"a join b: {interval_dom.join(a, b)}")
    print(f"a meet b: {interval_dom.meet(a, b)}")
    print(f"a widen b: {interval_dom.widen(a, b)}")
    print(f"a <= b: {interval_dom.leq(a, b)}")

    congruence_dom = CongruenceDomain()
    c = Congruence(remainder=0, modulus=2)  # even numbers
    d = Congruence(remainder=1, modulus=2)  # odd numbers

    print(f"\nCongruence c: {c}")
    print(f"Congruence d: {d}")
    print(f"c join d: {congruence_dom.join(c, d)}")

    product_dom = create_type_analysis_domain()
    pa = product_dom.bottom()
    pb = product_dom.top()

    print(f"\nProduct bottom: {pa}")
    print(f"Product top: {pb}")
    print(f"Product join: {product_dom.join(pa, pb)}")

    # A real program through the analyzer.
    from svl.lexer import tokenize
    from svl.parser_rd import parse
    src = """
    module demo {
      func main() type int {
        let a: int = [1, 2, 3]
        let i: int = 5
        return a[i]
      }
    }
    """
    result = analyze_program(parse(tokenize(src)))
    print(f"\nfindings: {[f.message for f in result.findings]}")
    print("\n✓ Abstract Interpretation test complete!")
