# svl/tactics.py
# Interactive Theorem Proving with Tactics (H34)
# Tactic language for interactive proof construction

from typing import Dict, List, Optional, Any, Callable, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
from abc import ABC, abstractmethod
import copy


class TacticResult(Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    INCOMPLETE = "incomplete"  # Proof requires more tactics


@dataclass
class ProofState:
    """Current state of a proof."""
    goals: List['Goal'] = field(default_factory=list)
    hypotheses: Dict[str, Any] = field(default_factory=dict)
    context: Dict[str, Any] = field(default_factory=dict)
    
    def copy(self) -> 'ProofState':
        return ProofState(
            goals=[g.copy() for g in self.goals],
            hypotheses=copy.deepcopy(self.hypotheses),
            context=copy.deepcopy(self.context)
        )


@dataclass
class Goal:
    """A proof goal."""
    statement: Any  # The proposition to prove
    name: str = "goal"
    assumptions: List[Any] = field(default_factory=list)
    
    def copy(self) -> 'Goal':
        return Goal(
            statement=self.statement,
            name=self.name,
            assumptions=copy.deepcopy(self.assumptions)
        )


class Tactic(ABC):
    """Base class for all tactics."""
    
    @abstractmethod
    def apply(self, state: ProofState) -> Tuple[TacticResult, ProofState, str]:
        """Apply tactic to proof state. Returns (result, new_state, message)."""
        pass
    
    def __or__(self, other: 'Tactic') -> 'OrElse':
        return OrElse(self, other)
    
    def __rshift__(self, other: 'Tactic') -> 'Sequence':
        return Sequence(self, other)
    
    def repeat(self, n: Optional[int] = None) -> 'Repeat':
        return Repeat(self, n)


class TacticResultData:
    """Result of tactic application."""
    def __init__(self, result: TacticResult, state: ProofState, message: str = ""):
        self.result = result
        self.state = state
        self.message = message


# ============================================================================
# Proposition AST for Tactic System
# ============================================================================

class PropType(Enum):
    VAR = "var"
    IMPLIES = "implies"
    AND = "and"
    OR = "or"
    NOT = "not"
    TRUE = "true"
    FALSE = "false"
    FORALL = "forall"
    EXISTS = "exists"


@dataclass
class Prop:
    """Proposition AST node."""
    type: PropType
    name: Optional[str] = None  # For variables
    left: Optional['Prop'] = None
    right: Optional['Prop'] = None
    variable: Optional[str] = None
    body: Optional['Prop'] = None
    
    def __str__(self):
        if self.type == PropType.VAR:
            return self.name or "?"
        elif self.type == PropType.IMPLIES:
            return f"({self.left} -> {self.right})"
        elif self.type == PropType.AND:
            return f"({self.left} /\\ {self.right})"
        elif self.type == PropType.OR:
            return f"({self.left} \\/ {self.right})"
        elif self.type == PropType.NOT:
            return f"~{self.left}"
        elif self.type == PropType.TRUE:
            return "True"
        elif self.type == PropType.FALSE:
            return "False"
        elif self.type == PropType.FORALL:
            return f"forall {self.variable}, {self.body}"
        elif self.type == PropType.EXISTS:
            return f"exists {self.variable}, {self.body}"
        return "?"
    
    @staticmethod
    def var(name: str) -> 'Prop':
        return Prop(PropType.VAR, name=name)
    
    @staticmethod
    def implies(left: 'Prop', right: 'Prop') -> 'Prop':
        return Prop(PropType.IMPLIES, left=left, right=right)
    
    @staticmethod
    def and_(left: 'Prop', right: 'Prop') -> 'Prop':
        return Prop(PropType.AND, left=left, right=right)
    
    @staticmethod
    def or_(left: 'Prop', right: 'Prop') -> 'Prop':
        return Prop(PropType.OR, left=left, right=right)
    
    @staticmethod
    def not_(prop: 'Prop') -> 'Prop':
        return Prop(PropType.NOT, left=prop)
    
    @staticmethod
    def true() -> 'Prop':
        return Prop(PropType.TRUE)
    
    @staticmethod
    def false() -> 'Prop':
        return Prop(PropType.FALSE)
    
    @staticmethod
    def forall(var: str, body: 'Prop') -> 'Prop':
        return Prop(PropType.FORALL, variable=var, body=body)
    
    @staticmethod
    def exists(var: str, body: 'Prop') -> 'Prop':
        return Prop(PropType.EXISTS, variable=var, body=body)


def parse_prop(s: str) -> Prop:
    """Simple parser for proposition strings."""
    s = s.strip()
    
    # Handle True/False
    if s in ("True", "true", "1"):
        return Prop.true()
    if s in ("False", "false", "0"):
        return Prop.false()
    
    # Handle implication (right-associative)
    # Find top-level ->
    depth = 0
    for i, c in enumerate(s):
        if c == '(':
            depth += 1
        elif c == ')':
            depth -= 1
        elif c == '-' and i + 1 < len(s) and s[i+1] == '>' and depth == 0:
            left = parse_prop(s[:i].strip())
            right = parse_prop(s[i+2:].strip())
            return Prop.implies(left, right)
    
    # Handle forall
    if s.startswith("forall "):
        # forall x, P(x)
        rest = s[7:].strip()
        if ',' in rest:
            var, body = rest.split(',', 1)
            return Prop.forall(var.strip(), parse_prop(body.strip()))
    
    # Handle not
    if s.startswith("~") or s.startswith("not "):
        prefix = "~" if s.startswith("~") else "not "
        return Prop.not_(parse_prop(s[len(prefix):].strip()))
    
    # Handle and/or (simplified)
    # ... 
    
    # Variable
    return Prop.var(s)


class Intro(Tactic):
    """Introduce variables/hypotheses (intro)."""
    
    def apply(self, state: ProofState) -> Tuple[TacticResult, ProofState, str]:
        if not state.goals:
            return TacticResult.FAILURE, state, "No goals to introduce"
        
        new_state = state.copy()
        goal = new_state.goals[0]
        
        # Parse goal statement if it's a string
        stmt = goal.statement
        if isinstance(stmt, str):
            stmt = parse_prop(stmt)
            goal.statement = stmt
        
        # For implication A -> B, introduce A as hypothesis
        if isinstance(stmt, Prop) and stmt.type == PropType.IMPLIES:
            antecedent = stmt.left
            consequent = stmt.right
            
            # Add antecedent as hypothesis
            hyp_name = f"H{len(new_state.hypotheses) + 1}"
            new_state.hypotheses[hyp_name] = antecedent
            
            # Replace goal with consequent
            new_state.goals[0] = Goal(
                statement=consequent,
                name=goal.name,
                assumptions=goal.assumptions + [antecedent]
            )
            
            return TacticResult.SUCCESS, new_state, f"Introduced {hyp_name}"
        
        return TacticResult.FAILURE, state, "Goal is not an implication"


class Apply(Tactic):
    """Apply a lemma/theorem (apply)."""
    
    def __init__(self, lemma_name: str, *args):
        self.lemma_name = lemma_name
        self.args = args
    
    def apply(self, state: ProofState) -> Tuple[TacticResult, ProofState, str]:
        if not state.goals:
            return TacticResult.FAILURE, state, "No goals to apply to"
        
        # In real implementation, would look up lemma and unify
        # For now, just simulate
        new_state = state.copy()
        goal = new_state.goals[0]
        
        # Simulate application - would generate subgoals for premises
        new_state.goals = [
            Goal(statement=f"premise_{i}", name=f"{goal.name}_prem{i}")
            for i in range(len(self.args) + 1)
        ]
        
        return TacticResult.SUCCESS, new_state, f"Applied {self.lemma_name}"


class Exact(Tactic):
    """Close goal with exact proof term (exact)."""
    
    def __init__(self, term: Any):
        self.term = term
    
    def apply(self, state: ProofState) -> Tuple[TacticResult, ProofState, str]:
        if not state.goals:
            return TacticResult.FAILURE, state, "No goals to close"
        
        new_state = state.copy()
        # Remove the first goal (solved)
        new_state.goals = new_state.goals[1:]
        
        if not new_state.goals:
            return TacticResult.SUCCESS, new_state, "Proof completed"
        else:
            return TacticResult.INCOMPLETE, new_state, "Goal solved, more goals remain"


class Assumption(Tactic):
    """Close goal by finding matching hypothesis (assumption)."""
    
    def apply(self, state: ProofState) -> Tuple[TacticResult, ProofState, str]:
        if not state.goals:
            return TacticResult.FAILURE, state, "No goals"
        
        goal = state.goals[0]
        
        # Parse goal statement if it's a string
        stmt = goal.statement
        if isinstance(stmt, str):
            stmt = parse_prop(stmt)
        
        # Check if goal matches any hypothesis
        for name, hyp in state.hypotheses.items():
            # Parse hypothesis if string
            if isinstance(hyp, str):
                hyp = parse_prop(hyp)
            
            if self._match(stmt, hyp):
                new_state = state.copy()
                new_state.goals = new_state.goals[1:]
                
                if not new_state.goals:
                    return TacticResult.SUCCESS, new_state, f"Closed by assumption {name}"
                else:
                    return TacticResult.INCOMPLETE, new_state, f"Closed by assumption {name}"
        
        return TacticResult.FAILURE, state, "No matching assumption"
    
    def _match(self, goal: Any, hypothesis: Any) -> bool:
        """Check if goal matches hypothesis."""
        # Parse both if strings
        if isinstance(goal, str):
            goal = parse_prop(goal)
        if isinstance(hypothesis, str):
            hypothesis = parse_prop(hypothesis)
        
        # Compare Prop structures
        if isinstance(goal, Prop) and isinstance(hypothesis, Prop):
            return self._prop_equal(goal, hypothesis)
        
        return str(goal) == str(hypothesis)  # Fallback
    
    def _prop_equal(self, p1: Prop, p2: Prop) -> bool:
        """Check structural equality of propositions."""
        if p1.type != p2.type:
            return False
        
        if p1.type == PropType.VAR:
            return p1.name == p2.name
        elif p1.type in (PropType.IMPLIES, PropType.AND, PropType.OR):
            return (p1.left is not None and p2.left is not None and
                    p1.right is not None and p2.right is not None and
                    self._prop_equal(p1.left, p2.left) and 
                    self._prop_equal(p1.right, p2.right))
        elif p1.type == PropType.NOT:
            return (p1.left is not None and p2.left is not None and
                    self._prop_equal(p1.left, p2.left))
        elif p1.type in (PropType.TRUE, PropType.FALSE):
            return True
        elif p1.type in (PropType.FORALL, PropType.EXISTS):
            return (p1.variable == p2.variable and 
                    p1.body is not None and p2.body is not None and
                    self._prop_equal(p1.body, p2.body))
        
        return False


class Simplify(Tactic):
    """Simplify goal (simplify)."""
    
    def apply(self, state: ProofState) -> Tuple[TacticResult, ProofState, str]:
        if not state.goals:
            return TacticResult.FAILURE, state, "No goals to simplify"
        
        new_state = state.copy()
        # In real implementation, would run simplifier
        # For now, just report
        return TacticResult.SUCCESS, new_state, "Goal simplified"


class Rewrite(Tactic):
    """Rewrite using equality (rewrite)."""
    
    def __init__(self, equality: Any, direction: str = "forward"):
        self.equality = equality
        self.direction = direction
    
    def apply(self, state: ProofState) -> Tuple[TacticResult, ProofState, str]:
        if not state.goals:
            return TacticResult.FAILURE, state, "No goals to rewrite"
        
        new_state = state.copy()
        # In real implementation, would perform rewriting
        return TacticResult.SUCCESS, new_state, f"Rewrote using {self.equality}"


class Induction(Tactic):
    """Proof by induction (induction)."""
    
    def __init__(self, variable: str):
        self.variable = variable
    
    def apply(self, state: ProofState) -> Tuple[TacticResult, ProofState, str]:
        if not state.goals:
            return TacticResult.FAILURE, state, "No goals for induction"
        
        new_state = state.copy()
        goal = new_state.goals[0]
        
        # Generate base case and inductive step
        base_case = Goal(statement=f"base_case({self.variable})", name=f"{goal.name}_base")
        inductive_step = Goal(
            statement=f"inductive_step({self.variable})", 
            name=f"{goal.name}_induct"
        )
        
        new_state.goals = [base_case, inductive_step] + new_state.goals[1:]
        
        return TacticResult.INCOMPLETE, new_state, f"Induction on {self.variable}"


class Cases(Tactic):
    """Case analysis (cases)."""
    
    def __init__(self, expression: Any):
        self.expression = expression
    
    def apply(self, state: ProofState) -> Tuple[TacticResult, ProofState, str]:
        if not state.goals:
            return TacticResult.FAILURE, state, "No goals for case analysis"
        
        new_state = state.copy()
        # In real implementation, would analyze expression type and generate cases
        # For enums/sum types, one case per constructor
        case_goals = [
            Goal(statement=f"case_{i}({self.expression})", name=f"case_{i}")
            for i in range(2)  # Simplified: 2 cases
        ]
        
        new_state.goals = case_goals + new_state.goals[1:]
        
        return TacticResult.INCOMPLETE, new_state, f"Case analysis on {self.expression}"


class Contradiction(Tactic):
    """Find contradiction in hypotheses (contradiction)."""
    
    def apply(self, state: ProofState) -> Tuple[TacticResult, ProofState, str]:
        # Check for contradictory hypotheses
        hyps = list(state.hypotheses.values())
        for i, h1 in enumerate(hyps):
            for h2 in hyps[i+1:]:
                if self._is_contradiction(h1, h2):
                    new_state = state.copy()
                    new_state.goals = new_state.goals[1:]
                    return TacticResult.SUCCESS, new_state, "Found contradiction"
        
        return TacticResult.FAILURE, state, "No contradiction found"
    
    def _is_contradiction(self, h1: Any, h2: Any) -> bool:
        return str(h1) == f"not {h2}" or str(h2) == f"not {h1}"


class Trivial(Tactic):
    """Solve trivial goal (trivial)."""
    
    def apply(self, state: ProofState) -> Tuple[TacticResult, ProofState, str]:
        if not state.goals:
            return TacticResult.FAILURE, state, "No goals"
        
        # Check if goal is obviously true (e.g., True, x = x)
        goal = state.goals[0]
        if str(goal.statement) in ("True", "true", "1=1"):
            new_state = state.copy()
            new_state.goals = new_state.goals[1:]
            return TacticResult.SUCCESS if not new_state.goals else TacticResult.INCOMPLETE, new_state, "Trivial"
        
        return TacticResult.FAILURE, state, "Goal not trivial"


# ============================================================================
# Tactical Combinators
# ============================================================================

class Sequence(Tactic):
    """Sequence of tactics (t1; t2)."""
    
    def __init__(self, t1: Tactic, t2: Tactic):
        self.t1 = t1
        self.t2 = t2
    
    def apply(self, state: ProofState) -> Tuple[TacticResult, ProofState, str]:
        result1, state1, msg1 = self.t1.apply(state)
        
        if result1 == TacticResult.FAILURE:
            return TacticResult.FAILURE, state, f"First tactic failed: {msg1}"
        
        result2, state2, msg2 = self.t2.apply(state1)
        
        if result2 == TacticResult.FAILURE:
            return TacticResult.FAILURE, state, f"Second tactic failed: {msg2}"
        
        final_result = result1
        if result1 == TacticResult.INCOMPLETE or result2 == TacticResult.INCOMPLETE:
            final_result = TacticResult.INCOMPLETE
        
        return final_result, state2, f"{msg1}; {msg2}"


class OrElse(Tactic):
    """Try first tactic, if fails try second (t1 | t2)."""
    
    def __init__(self, t1: Tactic, t2: Tactic):
        self.t1 = t1
        self.t2 = t2
    
    def apply(self, state: ProofState) -> Tuple[TacticResult, ProofState, str]:
        result1, state1, msg1 = self.t1.apply(state)
        
        if result1 != TacticResult.FAILURE:
            return result1, state1, msg1
        
        # First failed, try second
        result2, state2, msg2 = self.t2.apply(state)
        return result2, state2, f"({msg1}) | {msg2}"


class Repeat(Tactic):
    """Repeat tactic n times or until failure (repeat n {t})."""
    
    def __init__(self, tactic: Tactic, n: Optional[int] = None):
        self.tactic = tactic
        self.n = n
    
    def apply(self, state: ProofState) -> Tuple[TacticResult, ProofState, str]:
        current_state = state
        count = 0
        max_iterations = self.n if self.n is not None else 100
        
        while count < max_iterations:
            result, new_state, msg = self.tactic.apply(current_state)
            
            if result == TacticResult.FAILURE:
                break
            
            current_state = new_state
            count += 1
            
            if result == TacticResult.SUCCESS and not current_state.goals:
                break
        
        if count == 0:
            return TacticResult.FAILURE, state, "Repeat: tactic failed immediately"
        
        return TacticResult.INCOMPLETE if current_state.goals else TacticResult.SUCCESS, \
               current_state, f"Repeated {count} times"


class Try(Tactic):
    """Try tactic, succeed even if it fails (try {t})."""
    
    def __init__(self, tactic: Tactic):
        self.tactic = tactic
    
    def apply(self, state: ProofState) -> Tuple[TacticResult, ProofState, str]:
        result, new_state, msg = self.tactic.apply(state)
        
        if result == TacticResult.FAILURE:
            return TacticResult.SUCCESS, state, f"try {{...}} (tactic failed: {msg})"
        
        return result, new_state, f"try {{...}} -> {msg}"


# ============================================================================
# Tactic Interpreter / Proof Engine
# ============================================================================

@dataclass
class ProofScript:
    """A sequence of tactics forming a proof script."""
    tactics: List[Tactic] = field(default_factory=list)
    
    def add(self, tactic: Tactic):
        self.tactics.append(tactic)
    
    def execute(self, initial_state: ProofState) -> Tuple[TacticResult, ProofState, List[str]]:
        """Execute all tactics in sequence."""
        state = initial_state
        messages = []
        
        for tactic in self.tactics:
            result, state, msg = tactic.apply(state)
            messages.append(msg)
            
            if result == TacticResult.FAILURE:
                return TacticResult.FAILURE, state, messages
        
        if state.goals:
            return TacticResult.INCOMPLETE, state, messages
        
        return TacticResult.SUCCESS, state, messages


class TacticInterpreter:
    """Interactive tactic interpreter with REPL-like interface."""
    
    def __init__(self):
        self.state: Optional[ProofState] = None
        self.history: List[Tuple[Tactic, TacticResult, ProofState, str]] = []
        self.saved_states: Dict[str, ProofState] = {}
    
    def start_proof(self, goal: Goal, hypotheses: Optional[Dict[str, Any]] = None):
        """Start a new proof."""
        self.state = ProofState(
            goals=[goal],
            hypotheses=hypotheses or {},
            context={}
        )
        self.history = []
    
    def run_tactic(self, tactic: Tactic) -> Tuple[TacticResult, str]:
        """Run a single tactic."""
        if not self.state:
            return TacticResult.FAILURE, "No active proof"
        
        # Save current state for potential undo
        old_state = self.state.copy()
        
        result, new_state, msg = tactic.apply(self.state)
        
        if result != TacticResult.FAILURE:
            self.state = new_state
            self.history.append((tactic, result, old_state, msg))
        
        return result, msg
    
    def undo(self) -> bool:
        """Undo last tactic."""
        if not self.history:
            return False
        
        _, _, old_state, _ = self.history.pop()
        self.state = old_state
        return True
    
    def save_state(self, name: str):
        """Save current state with name."""
        if self.state:
            self.saved_states[name] = self.state.copy()
    
    def load_state(self, name: str) -> bool:
        """Load saved state."""
        if name in self.saved_states:
            self.state = self.saved_states[name].copy()
            return True
        return False
    
    def get_goals(self) -> List[Goal]:
        """Get current goals."""
        return self.state.goals if self.state else []
    
    def get_hypotheses(self) -> Dict[str, Any]:
        """Get current hypotheses."""
        return self.state.hypotheses if self.state else {}
    
    def is_complete(self) -> bool:
        """Check if proof is complete."""
        return self.state is not None and len(self.state.goals) == 0


# ============================================================================
# Integration with SVL Theorem Layer
# ============================================================================

class SVLTacticBridge:
    """Bridge between tactic system and SVL theorem layer."""
    
    def __init__(self):
        self.interpreter = TacticInterpreter()
    
    def prove_with_tactics(self, theorem_statement: Any, 
                          tactics: List[Tactic]) -> Tuple[bool, List[str]]:
        """Prove a theorem using a list of tactics."""
        goal = Goal(statement=theorem_statement)
        self.interpreter.start_proof(goal)
        
        messages = []
        for tactic in tactics:
            result, msg = self.interpreter.run_tactic(tactic)
            messages.append(msg)
            
            if result == TacticResult.FAILURE:
                return False, messages
        
        success = self.interpreter.is_complete()
        return success, messages
    
    def interactive_proof(self, theorem_statement: Any):
        """Start interactive proof session."""
        goal = Goal(statement=theorem_statement)
        self.interpreter.start_proof(goal)
        return self.interpreter


# Predefined tactic instances for convenience
intro = Intro()
apply = lambda lemma, *args: Apply(lemma, *args)
exact = lambda term: Exact(term)
assumption = Assumption()
simplify = Simplify()
rewrite = lambda eq, dir="forward": Rewrite(eq, dir)
induction = lambda var: Induction(var)
cases = lambda expr: Cases(expr)
contradiction = Contradiction()
trivial = Trivial()

# Tactical combinators as functions
seq = lambda t1, t2: Sequence(t1, t2)
orelse = lambda t1, t2: OrElse(t1, t2)
repeat = lambda t, n=None: Repeat(t, n)
try_t = lambda t: Try(t)


if __name__ == '__main__':
    # Test tactic system
    print("=== Tactic System Test ===")
    
    # Create a simple proof: prove A -> A
    goal = Goal(statement="A -> A", name="identity")
    interpreter = TacticInterpreter()
    interpreter.start_proof(goal)
    
    # Apply intro tactic
    result, msg = interpreter.run_tactic(intro)
    print(f"Intro: {result}, {msg}")
    print(f"Goals: {[g.statement for g in interpreter.get_goals()]}")
    print(f"Hypotheses: {interpreter.get_hypotheses()}")
    
    # Apply assumption tactic
    result, msg = interpreter.run_tactic(assumption)
    print(f"Assumption: {result}, {msg}")
    print(f"Goals: {[g.statement for g in interpreter.get_goals()]}")
    
    print(f"Proof complete: {interpreter.is_complete()}")
    
    # Test proof script
    print("\n=== Proof Script Test ===")
    script = ProofScript()
    script.add(intro)
    script.add(assumption)
    
    initial_state = ProofState(goals=[Goal(statement="A -> A")])
    result, final_state, messages = script.execute(initial_state)
    print(f"Result: {result}")
    for msg in messages:
        print(f"  {msg}")
    
    # Test tactical combinators
    print("\n=== Tactical Combinators ===")
    # try { intro } ; assumption
    combined = try_t(intro) >> assumption
    
    state = ProofState(goals=[Goal(statement="A -> A")])
    result, state2, msg = combined.apply(state)
    print(f"Combined: {result}, {msg}")
    print(f"Goals remaining: {len(state2.goals)}")