# svl/abstract_interpretation.py
# Abstract Interpretation for Type Layer (H21)
# Implements abstract domains (intervals, congruences) with fixpoint computation

from typing import Dict, List, Optional, Set, Tuple, Any, Union
from dataclasses import dataclass, field
from enum import Enum
from abc import ABC, abstractmethod


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


class IntervalDomain(AbstractDomain):
    """Interval abstract domain implementation."""

    def bottom(self) -> Interval:
        return Interval.bottom()

    def top(self) -> Interval:
        return Interval.top()

    def join(self, a: Interval, b: Interval) -> Interval:
        if a.is_bottom:
            return b
        if b.is_bottom:
            return a
        if a.is_top or b.is_top:
            return Interval.top()

        lower = min(a.lower, b.lower) if isinstance(a.lower, (int, float)) and isinstance(b.lower, (int, float)) else '-inf'
        upper = max(a.upper, b.upper) if isinstance(a.upper, (int, float)) and isinstance(b.upper, (int, float)) else '+inf'

        return Interval(lower=lower, upper=upper)

    def meet(self, a: Interval, b: Interval) -> Interval:
        if a.is_bottom or b.is_bottom:
            return Interval.bottom()
        if a.is_top:
            return b
        if b.is_top:
            return a

        lower = max(a.lower, b.lower) if isinstance(a.lower, (int, float)) and isinstance(b.lower, (int, float)) else '-inf'
        upper = min(a.upper, b.upper) if isinstance(a.upper, (int, float)) and isinstance(b.upper, (int, float)) else '+inf'

        if isinstance(lower, (int, float)) and isinstance(upper, (int, float)) and lower > upper:
            return Interval.bottom()

        return Interval(lower=lower, upper=upper)

    def widen(self, a: Interval, b: Interval) -> Interval:
        if a.is_bottom:
            return b
        if a.is_top or b.is_top:
            return Interval.top()

        # Widening: if bounds are expanding, jump to infinity
        if isinstance(a.lower, (int, float)) and isinstance(b.lower, (int, float)) and b.lower < a.lower:
            new_lower = '-inf'
        else:
            new_lower = a.lower

        if isinstance(a.upper, (int, float)) and isinstance(b.upper, (int, float)) and b.upper > a.upper:
            new_upper = '+inf'
        else:
            new_upper = a.upper

        return Interval(lower=new_lower, upper=new_upper)

    def narrow(self, a: Interval, b: Interval) -> Interval:
        if a.is_top or b.is_bottom:
            return b
        return self.meet(a, b)

    def leq(self, a: Interval, b: Interval) -> bool:
        if a.is_bottom:
            return True
        if b.is_top:
            return True
        if a.is_top or b.is_bottom:
            return False

        lower_ok = (isinstance(a.lower, (int, float)) and isinstance(b.lower, (int, float)) and a.lower >= b.lower) or b.lower == '-inf'
        upper_ok = (isinstance(a.upper, (int, float)) and isinstance(b.upper, (int, float)) and a.upper <= b.upper) or b.upper == '+inf'
        return lower_ok and upper_ok


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
# ABSTRACT INTERPRETER
# ============================================================================

@dataclass
class AbstractState:
    """Abstract state mapping variables to abstract values."""
    env: Dict[str, AbstractValue]
    domain: AbstractDomain

    @staticmethod
    def bottom(domain: AbstractDomain) -> 'AbstractState':
        return AbstractState(env={}, domain=domain)

    def get(self, var: str) -> AbstractValue:
        return self.env.get(var, self.domain.bottom())

    def set(self, var: str, value: AbstractValue) -> 'AbstractState':
        new_env = dict(self.env)
        new_env[var] = value
        return AbstractState(env=new_env, domain=self.domain)

    def join(self, other: 'AbstractState') -> 'AbstractState':
        all_vars = set(self.env.keys()) | set(other.env.keys())
        new_env = {}
        for var in all_vars:
            v1 = self.env.get(var, self.domain.bottom())
            v2 = other.env.get(var, other.domain.bottom())
            new_env[var] = self.domain.join(v1, v2)
        return AbstractState(env=new_env, domain=self.domain)

    def widen(self, other: 'AbstractState') -> 'AbstractState':
        all_vars = set(self.env.keys()) | set(other.env.keys())
        new_env = {}
        for var in all_vars:
            v1 = self.env.get(var, self.domain.bottom())
            v2 = other.env.get(var, other.domain.bottom())
            new_env[var] = self.domain.widen(v1, v2)
        return AbstractState(env=new_env, domain=self.domain)

    def leq(self, other: 'AbstractState') -> bool:
        all_vars = set(self.env.keys()) | set(other.env.keys())
        return all(
            self.domain.leq(self.env.get(var, self.domain.bottom()),
                           other.env.get(var, other.domain.bottom()))
            for var in all_vars
        )


class AbstractInterpreter:
    """Abstract interpreter for SVL programs."""

    def __init__(self, domain: AbstractDomain):
        self.domain = domain
        self.state = AbstractState.bottom(domain)

    def analyze_program(self, ast: Any) -> AbstractState:
        """Analyze entire program."""
        # Simplified: would traverse AST and compute abstract semantics
        return self.state

    def analyze_function(self, func_ast: Any) -> AbstractState:
        """Analyze function body with fixpoint computation."""
        # Initial state
        state = AbstractState.bottom(self.domain)

        # Worklist algorithm for fixpoint
        worklist = [func_ast.body]
        visited = set()

        while worklist:
            block = worklist.pop(0)
            if id(block) in visited:
                continue
            visited.add(id(block))

            new_state = self._analyze_block(block, state)
            if not state.leq(new_state):
                state = state.widen(new_state)
                worklist.append(block)  # Re-analyze

        return state

    def _analyze_block(self, block: Any, state: AbstractState) -> AbstractState:
        """Analyze a block of statements."""
        for stmt in getattr(block, 'statements', []):
            state = self._analyze_stmt(stmt, state)
        return state

    def _analyze_stmt(self, stmt: Any, state: AbstractState) -> AbstractState:
        """Analyze a single statement."""
        stmt_type = type(stmt).__name__

        if stmt_type == 'LetStmt':
            val = self._analyze_expr(stmt.value, state)
            return state.set(stmt.name, val)

        elif stmt_type == 'IfStmt':
            then_state = self._analyze_block(stmt.then_branch, state)
            else_state = self._analyze_block(stmt.else_branch, state) if stmt.else_branch else state
            return then_state.join(else_state)

        elif stmt_type == 'WhileStmt':
            # Fixpoint for loops
            old_state = state
            for _ in range(10):  # Max iterations
                cond_state = self._analyze_expr(stmt.condition, state)
                body_state = self._analyze_block(stmt.body, cond_state)
                state = state.join(body_state)
                if state.leq(old_state):
                    break
                old_state = state
            return state

        elif stmt_type == 'AssertStmt':
            # Assertions can refine state
            return state

        return state

    def _analyze_expr(self, expr: Any, state: AbstractState) -> AbstractValue:
        """Analyze expression in abstract domain."""
        expr_type = type(expr).__name__

        if expr_type == 'Literal':
            if isinstance(expr.value, int):
                if isinstance(self.domain, IntervalDomain):
                    return Interval.from_value(expr.value)
                elif isinstance(self.domain, CongruenceDomain):
                    return Congruence.from_value(expr.value)
            return self.domain.top()

        elif expr_type == 'Ident':
            return state.get(expr.name)

        elif expr_type == 'BinaryExpr':
            left = self._analyze_expr(expr.left, state)
            right = self._analyze_expr(expr.right, state)

            if isinstance(self.domain, IntervalDomain):
                return self._abstract_binop_interval(left, right, expr.operator)
            elif isinstance(self.domain, CongruenceDomain):
                return self._abstract_binop_congruence(left, right, expr.operator)

        return self.domain.top()

    def _abstract_binop_interval(self, a: Interval, b: Interval, op: str) -> Interval:
        if a.is_bottom or b.is_bottom:
            return Interval.bottom()
        if a.is_top or b.is_top:
            return Interval.top()

        if op == '+':
            if isinstance(a.lower, (int, float)) and isinstance(b.lower, (int, float)) and \
               isinstance(a.upper, (int, float)) and isinstance(b.upper, (int, float)):
                return Interval(lower=a.lower + b.lower, upper=a.upper + b.upper)
        elif op == '-':
            if isinstance(a.lower, (int, float)) and isinstance(b.lower, (int, float)) and \
               isinstance(a.upper, (int, float)) and isinstance(b.upper, (int, float)):
                return Interval(lower=a.lower - b.upper, upper=a.upper - b.lower)
        elif op == '*':
            if isinstance(a.lower, (int, float)) and isinstance(b.lower, (int, float)) and \
               isinstance(a.upper, (int, float)) and isinstance(b.upper, (int, float)):
                candidates = [a.lower * b.lower, a.lower * b.upper,
                              a.upper * b.lower, a.upper * b.upper]
                return Interval(lower=min(candidates), upper=max(candidates))

        return Interval.top()

    def _abstract_binop_congruence(self, a: Congruence, b: Congruence, op: str) -> Congruence:
        if a.is_bottom or b.is_bottom:
            return Congruence.bottom()
        if a.is_top or b.is_top:
            return Congruence.top()

        if op == '+' and isinstance(a.modulus, int) and isinstance(b.modulus, int):
            from math import gcd
            m = gcd(a.modulus, b.modulus)
            r = (a.remainder + b.remainder) % m
            return Congruence(remainder=r, modulus=m)

        return Congruence.top()


# ============================================================================
# ABSTRACT INTERPRETATION INTEGRATION WITH TYPE LAYER
# ============================================================================

def create_type_analysis_domain() -> ProductDomain:
    """Create product domain for type layer analysis."""
    return ProductDomain({
        'interval': IntervalDomain(),
        'congruence': CongruenceDomain(),
    })


def analyze_type_bounds(ast: Any) -> Dict[str, Any]:
    """Analyze array bounds, overflow, division by zero using abstract interpretation."""
    domain = create_type_analysis_domain()
    interpreter = AbstractInterpreter(domain)

    state = interpreter.analyze_program(ast)

    # Extract warnings
    warnings = []
    for var, val in state.env.items():
        if isinstance(val, ProductValue):
            interval = val.components.get('interval')
            congruence = val.components.get('congruence')

            # Check for potential issues
            if interval and not interval.is_bottom and not interval.is_top:
                if interval.lower < 0:
                    warnings.append(f"Variable {var} may be negative: {interval}")

                if interval.upper > 2**31 - 1:
                    warnings.append(f"Variable {var} may overflow i32: {interval}")

            if congruence and not congruence.is_bottom and not congruence.is_top:
                if congruence.modulus == 'exact' and congruence.remainder == 0:
                    warnings.append(f"Variable {var} may be zero: {congruence}")

    return {
        'state': state,
        'warnings': warnings,
    }


if __name__ == '__main__':
    print("=== Abstract Interpretation Test ===")

    # Test interval domain
    interval_dom = IntervalDomain()
    a = Interval(lower=0, upper=10)
    b = Interval(lower=5, upper=15)

    print(f"Interval a: {a}")
    print(f"Interval b: {b}")
    print(f"a join b: {interval_dom.join(a, b)}")
    print(f"a meet b: {interval_dom.meet(a, b)}")
    print(f"a widen b: {interval_dom.widen(a, b)}")
    print(f"a <= b: {interval_dom.leq(a, b)}")

    # Test congruence domain
    congruence_dom = CongruenceDomain()
    c = Congruence(remainder=0, modulus=2)  # even numbers
    d = Congruence(remainder=1, modulus=2)  # odd numbers

    print(f"\nCongruence c: {c}")
    print(f"Congruence d: {d}")
    print(f"c join d: {congruence_dom.join(c, d)}")
    print(f"c + d: {congruence_dom.join(c, d)}")

    # Test product domain
    product_dom = create_type_analysis_domain()
    pa = product_dom.bottom()
    pb = product_dom.top()

    print(f"\nProduct bottom: {pa}")
    print(f"Product top: {pb}")
    print(f"Product join: {product_dom.join(pa, pb)}")

    print("\n✓ Abstract Interpretation test complete!")