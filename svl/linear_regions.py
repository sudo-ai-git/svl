# svl/linear_regions.py
# Linear Type Inference with Regions (H15)
# Region-based linear type inference similar to Rust's borrow checker

from typing import Dict, List, Optional, Set, Any
from dataclasses import dataclass, field
from enum import Enum
from svl.parser_rd import TypeExpr, NodeType, FuncDecl, Param, Block
from svl.lexer import Token, TokenType, tokenize


class RegionKind(Enum):
    """Kind of region."""
    STATIC = "static"      # Global/static region
    STACK = "stack"        # Function-scoped region
    HEAP = "heap"          # Dynamically allocated region
    UNIQUE = "unique"      # Unique ownership region


@dataclass
class Region:
    """A memory region with lifetime."""
    name: str
    kind: RegionKind
    parent: Optional['Region'] = None
    children: List['Region'] = field(default_factory=list)
    variables: Set[str] = field(default_factory=set)
    is_linear: bool = False  # Whether this region enforces linear usage
    
    def add_child(self, child: 'Region'):
        child.parent = self
        self.children.append(child)
        
    def contains_var(self, var: str) -> bool:
        return var in self.variables


@dataclass
class LinearVariable:
    """A variable with linear type and region."""
    name: str
    type: str  # Type expression
    region: Region
    is_moved: bool = False
    is_borrowed: bool = False
    borrow_count: int = 0
    mutable_borrow: bool = False


class RegionInferenceEngine:
    """Infers regions and checks linear type usage."""
    
    def __init__(self):
        self.global_region = Region("global", RegionKind.STATIC)
        self.current_region: Region = self.global_region
        self.regions: Dict[str, Region] = {"global": self.global_region}
        self.variables: Dict[str, LinearVariable] = {}
        self.errors: List[str] = []
        self.warnings: List[str] = []
        
    def enter_function(self, func_name: str) -> Region:
        """Create a new stack region for a function."""
        region = Region(f"fn_{func_name}", RegionKind.STACK, parent=self.current_region)
        self.current_region.add_child(region)
        self.regions[region.name] = region
        old_region = self.current_region
        self.current_region = region
        return old_region
        
    def exit_function(self, old_region: Region):
        """Exit function, check for unused linear variables."""
        self._check_unused_linear(self.current_region)
        self.current_region = old_region
        
    def declare_variable(self, name: str, type_expr: str, is_linear: bool = False) -> LinearVariable:
        """Declare a new variable in current region."""
        var = LinearVariable(
            name=name,
            type=type_expr,
            region=self.current_region,
            is_moved=False
        )
        self.variables[name] = var
        self.current_region.variables.add(name)
        
        if is_linear:
            self.current_region.is_linear = True
            
        return var
        
    def move_variable(self, name: str) -> bool:
        """Move a linear variable (consumes it)."""
        if name not in self.variables:
            self.errors.append(f"Variable '{name}' not declared")
            return False
            
        var = self.variables[name]
        if var.is_moved:
            self.errors.append(f"Variable '{name}' already moved")
            return False
            
        if var.is_borrowed:
            self.errors.append(f"Variable '{name}' is borrowed, cannot move")
            return False
            
        var.is_moved = True
        return True
        
    def borrow_variable(self, name: str, mutable: bool = False) -> bool:
        """Borrow a variable (immutable or mutable borrow)."""
        if name not in self.variables:
            self.errors.append(f"Variable '{name}' not declared")
            return False
            
        var = self.variables[name]
        if var.is_moved:
            self.errors.append(f"Variable '{name}' already moved, cannot borrow")
            return False
            
        if mutable:
            if var.borrow_count > 0:
                self.errors.append(f"Variable '{name}' already borrowed, cannot mutably borrow")
                return False
            var.mutable_borrow = True
        else:
            if var.mutable_borrow:
                self.errors.append(f"Variable '{name}' mutably borrowed, cannot immutably borrow")
                return False
                
        var.borrow_count += 1
        var.is_borrowed = True
        return True
            
        if mutable:
            if var.borrow_count > 0:
                self.errors[f"Variable '{name}' already borrowed, cannot mutably borrow"]
                return False
            var.mutable_borrow = True
        else:
            if var.mutable_borrow:
                self.errors[f"Variable '{name}' mutably borrowed, cannot immutably borrow"]
                return False
                
        var.borrow_count += 1
        var.is_borrowed = True
        return True
        
    def return_borrow(self, name: str) -> bool:
        """Return a borrowed variable."""
        if name not in self.variables:
            return False
            
        var = self.variables[name]
        if not var.is_borrowed:
            return False
            
        var.borrow_count -= 1
        if var.borrow_count == 0:
            var.is_borrowed = False
            var.mutable_borrow = False
        return True
        
    def _check_unused_linear(self, region: Region):
        """Check for unused linear variables in region."""
        for var_name in region.variables:
            if var_name in self.variables:
                var = self.variables[var_name]
                # Check if linear variable was used
                if var.region == region and not var.is_moved and not var.is_borrowed:
                    # Linear variable dropped without being used
                    pass  # Could warn here
                    
        # Recurse into children
        for child in region.children:
            self._check_unused_linear(child)
            
    def get_stats(self) -> Dict[str, Any]:
        """Get inference statistics."""
        total_vars = len(self.variables)
        linear_vars = sum(1 for v in self.variables.values() if v.region.is_linear)
        moved = sum(1 for v in self.variables.values() if v.is_moved)
        borrowed = sum(1 for v in self.variables.values() if v.is_borrowed)
        
        return {
            'total_variables': total_vars,
            'linear_variables': linear_vars,
            'moved_variables': moved,
            'borrowed_variables': borrowed,
            'errors': len(self.errors),
            'warnings': len(self.warnings),
            'regions': len(self.regions)
        }


def infer_regions_for_function(func: FuncDecl) -> Dict[str, Any]:
    """Run region inference on a function."""
    from svl.parser_rd import FuncDecl
    engine = RegionInferenceEngine()
    
    # Enter function region
    old_region = engine.enter_function(func.name)
    
    # Declare parameters
    for param in func.params:
        is_linear = param.type_ann and 'linear' in str(param.type_ann).lower() if param.type_ann else False
        engine.declare_variable(param.name, str(param.type_ann) if param.type_ann else 'unknown', is_linear)
    
    # Process function body (simplified - would need full body analysis)
    # For now, just check parameters
    stats = engine.get_stats()
    
    # Exit function
    engine.exit_function(old_region)
    
    return stats


def run_linear_region_analysis(source: str) -> Dict[str, Any]:
    """Run linear region analysis on SVL source."""
    from svl.parser_rd import parse
    from svl.lexer import tokenize
    from svl.parser_rd import TopLevelItem, FuncDecl
    
    tokens = tokenize(source)
    ast = parse(tokens)
    
    all_stats = {}
    for item in ast.items:
        if isinstance(item, FuncDecl):
            stats = infer_regions_for_function(item)
            all_stats[item.name] = stats
            
    return all_stats


if __name__ == '__main__':
    print("=== Linear Region Inference Test ===")
    
    engine = RegionInferenceEngine()
    
    # Test basic region operations
    old = engine.enter_function("test")
    var = engine.declare_variable("x", "int", is_linear=True)
    print(f"Declared: {var.name}, linear: {engine.current_region.is_linear}")
    
    # Move variable
    engine.move_variable("x")
    print(f"Moved x: {engine.variables['x'].is_moved}")
    
    # Borrow variable
    engine.declare_variable("y", "int", is_linear=True)
    engine.borrow_variable("y", mutable=False)
    print(f"Borrowed y: {engine.variables['y'].is_borrowed}")
    engine.return_borrow("y")
    print(f"Returned y: {engine.variables['y'].is_borrowed}")
    
    engine.exit_function(old)
    
    stats = engine.get_stats()
    print(f"Stats: {stats}")
    print(f"Errors: {engine.errors}")
    
    print("\n✓ Linear Region Inference test complete!")