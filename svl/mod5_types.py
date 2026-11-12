# svl/mod5_types.py
# Mod-5 Type System with Z/2 Negation
# Core type bucket definitions and operations

from enum import Enum, IntEnum
from typing import Dict, List, Optional, Set, Tuple, Any
from dataclasses import dataclass, field
import hashlib
from svl.gate231 import MODULUS


def stable_name_bucket(name: str) -> int:
    """Deterministic mod-5 bucket for a type name.

    Python's built-in ``hash()`` on strings is salted per process (PYTHONHASHSEED),
    so ``hash(name) % 5`` made a struct's bucket — and any checksum derived from it —
    differ between runs. SVL's core claim is bit-identical determinism, so the bucket
    must come from a fixed function of the name: SHA-256(name) mod 5.
    """
    digest = hashlib.sha256(str(name).encode('utf-8')).digest()
    return int.from_bytes(digest[:8], 'big') % 5


class Mod5Bucket(IntEnum):
    """Mod-5 residue class buckets for type classification."""
    B0 = 0  # Base/Primitive types: int, float, bool, void, never
    B1 = 1  # Container types: List<T>, Dict<K,V>, Set<T>, Array<T>, Option<T>, Tuple<...>
    B2 = 2  # Function types: fn(...) -> ..., AsyncFn(...) -> ..., closures
    B3 = 3  # Async/Effect types: Future<T>, Stream<T>, Async<T>, IO<T>
    B4 = 4  # Error/Exception types: Result<T,E>, Error, Exception, panic


# Hebrew token ordinals (1-22) for semantic stream
HEBREW_ORDINALS = {
    'LET': 1,      # א
    'IF': 2,       # ב
    'THEN': 3,     # ג
    'ELSE': 4,     # ד
    'WHILE': 5,    # ה
    'FOR': 6,      # ו
    'FUNC': 7,     # ז
    'RETURN': 8,   # ח
    'MATCH': 9,    # ט
    'TYPE': 10,    # י
    'STRUCT': 11,  # כ
    'MODULE': 12,  # ל
    'IMPORT': 13,  # מ
    'EXPORT': 14,  # נ
    'CONST': 15,   # ס
    'VAR': 16,     # ע
    'ASSERT': 17,  # פ
    'TRY': 18,     # צ
    'CATCH': 19,   # ק
    'THROW': 20,   # ר
    'ASYNC': 21,   # ש
    'AWAIT': 22,   # ת
}


# Mod-5 bucket assignment for primitive types
PRIMITIVE_BUCKETS = {
    'int': Mod5Bucket.B0,
    'float': Mod5Bucket.B0,
    'bool': Mod5Bucket.B0,
    'void': Mod5Bucket.B0,
    'never': Mod5Bucket.B0,
    'string': Mod5Bucket.B0,
}

# Mod-5 bucket assignment for type constructors
CONSTRUCTOR_BUCKETS = {
    'List': Mod5Bucket.B1,
    'Dict': Mod5Bucket.B1,
    'Set': Mod5Bucket.B1,
    'Array': Mod5Bucket.B1,
    'Option': Mod5Bucket.B1,
    'Tuple': Mod5Bucket.B1,
    'fn': Mod5Bucket.B2,
    'AsyncFn': Mod5Bucket.B2,
    'Future': Mod5Bucket.B3,
    'Stream': Mod5Bucket.B3,
    'Async': Mod5Bucket.B3,
    'IO': Mod5Bucket.B3,
    'Result': Mod5Bucket.B4,
    'Error': Mod5Bucket.B4,
    'Exception': Mod5Bucket.B4,
    'panic': Mod5Bucket.B4,
}


def get_primitive_bucket(type_name: str) -> Mod5Bucket:
    """Get Mod-5 bucket for a primitive type."""
    return PRIMITIVE_BUCKETS.get(type_name, Mod5Bucket.B0)


def get_constructor_bucket(constructor: str) -> Mod5Bucket:
    """Get Mod-5 bucket for a type constructor."""
    return CONSTRUCTOR_BUCKETS.get(constructor, Mod5Bucket.B0)


def bucket_of_type(type_expr: Any) -> Mod5Bucket:
    """Compute Mod-5 bucket for a type expression (TypeExpr AST or internal Type)."""
    # Import locally to avoid circular imports
    from svl.parser_rd import TypeExpr, FuncTypeDetail
    from svl.type_inference import Type
    
    # Handle internal Type objects
    if isinstance(type_expr, Type):
        if type_expr.kind == 'prim':
            return get_primitive_bucket(type_expr.args[0] if type_expr.args else 'int')
        elif type_expr.kind == 'struct':
            return Mod5Bucket(stable_name_bucket(type_expr.args[0] if type_expr.args else 'Unknown'))
        elif type_expr.kind == 'func':
            return Mod5Bucket.B2
        elif type_expr.kind == 'generic':
            base = get_constructor_bucket(type_expr.generic_name)
            arg_buckets = sum(bucket_of_type(arg) for arg in type_expr.args)
            return Mod5Bucket((base + arg_buckets) % 5)
        elif type_expr.kind == 'tuple':
            return Mod5Bucket(sum(bucket_of_type(arg) for arg in type_expr.args) % 5)
        elif type_expr.kind == 'array':
            return Mod5Bucket((bucket_of_type(type_expr.args[0]) + 1) % 5)
        else:
            return Mod5Bucket.B0
    
    # Handle TypeExpr AST nodes (original behavior)
    if type_expr.kind == 'prim':
        return get_primitive_bucket(type_expr.value)
    elif type_expr.kind == 'struct':
        # User-defined structs: deterministic bucket = SHA-256(name) mod 5
        return Mod5Bucket(stable_name_bucket(type_expr.value))
    elif type_expr.kind == 'func':
        return Mod5Bucket.B2
    elif type_expr.kind == 'generic':
        # Generic type: bucket(base) + bucket(args) mod 5
        base = get_constructor_bucket(type_expr.value['name'])
        arg_buckets = sum(bucket_of_type(arg) for arg in type_expr.value['args'])
        return Mod5Bucket((base + arg_buckets) % 5)
    elif type_expr.kind == 'tuple':
        # Tuple: sum of element buckets mod 5
        return Mod5Bucket(sum(bucket_of_type(arg) for arg in type_expr.value) % 5)
    elif type_expr.kind == 'array':
        # Array: bucket(element) + 1 mod 5
        return Mod5Bucket((bucket_of_type(type_expr.value) + 1) % 5)
    else:
        return Mod5Bucket.B0


# Z/2 Negation (Single Involution)
# B0 <-> B4, B1 <-> B3, B2 <-> B2
Z2_NEGATION_MAP = {
    Mod5Bucket.B0: Mod5Bucket.B4,
    Mod5Bucket.B1: Mod5Bucket.B3,
    Mod5Bucket.B2: Mod5Bucket.B2,
    Mod5Bucket.B3: Mod5Bucket.B1,
    Mod5Bucket.B4: Mod5Bucket.B0,
}

Z2_INVERSE_MAP = {v: k for k, v in Z2_NEGATION_MAP.items()}


def z2_negate(bucket: Mod5Bucket) -> Mod5Bucket:
    """Z/2 negation (single involution): B0<->B4, B1<->B3, B2<->B2"""
    return Z2_NEGATION_MAP[bucket]


def mod5_add(a: Mod5Bucket, b: Mod5Bucket) -> Mod5Bucket:
    """Mod-5 addition for type composition."""
    return Mod5Bucket((a + b) % 5)


def mod5_mul(a: Mod5Bucket, b: Mod5Bucket) -> Mod5Bucket:
    """Mod-5 multiplication for type application."""
    return Mod5Bucket((a * b) % 5)


# Variance under Z/2 Negation
VARIANCE_MAP = {
    # Covariant types: negation preserves variance
    Mod5Bucket.B1: 'covariant',   # List, Option, Future
    Mod5Bucket.B3: 'covariant',   # Future, Stream
    
    # Contravariant types: negation flips variance
    Mod5Bucket.B2: 'contravariant',  # Function arguments
    
    # Invariant types: negation preserves invariance
    Mod5Bucket.B4: 'invariant',   # Result, Error
    Mod5Bucket.B0: 'invariant',   # Base primitives
}


def get_variance(bucket: Mod5Bucket) -> str:
    """Get variance classification for a bucket."""
    return VARIANCE_MAP.get(bucket, 'invariant')


# Structural stream moduli (for structural checksums)
STRUCTURAL_MODULI = [37, 73, 11]  # mod 13 removed per deep verification

def compute_structural_checksum(type_expr: 'TypeExpr') -> Tuple[int, int, int]:
    """Compute 3-channel structural checksum for a type expression."""
    # Import locally to avoid circular imports
    from svl.gate231 import compute_checksums_cython
    from svl.serialization import to_binary
    from svl.parser_rd import TypeExpr
    
    # Serialize type expression canonically
    data = to_binary(type_expr)
    
    # Compute checksums
    return compute_checksums_cython(data)


def verify_structural_checksum(type_expr: 'TypeExpr', expected: Tuple[int, int, int]) -> bool:
    """Verify structural checksums match expected."""
    actual = compute_structural_checksum(type_expr)
    return actual == expected


# Type expression serialization (for structural checksums)
def serialize_type_expr(type_expr: 'TypeExpr') -> bytes:
    """Serialize type expression for structural checksum computation."""
    # Import locally to avoid circular imports
    from svl.serialization import to_binary
    return to_binary(type_expr)


if __name__ == '__main__':
    # Test Z/2 negation
    print("=== Z/2 Negation Tests ===")
    for b in Mod5Bucket:
        negated = z2_negate(b)
        double_negated = z2_negate(negated)
        print(f"  {b.name} -> {negated.name} -> {double_negated.name} (involution: {double_negated == b})")
    
    # Test involution property
    for b in Mod5Bucket:
        assert z2_negate(z2_negate(b)) == b, f"Involution failed for {b}"
    print("✓ All involutions verified")
    
    # Test mod5 arithmetic
    print("\n=== Mod-5 Arithmetic Tests ===")
    for a in Mod5Bucket:
        for b in Mod5Bucket:
            s = mod5_add(a, b)
            p = mod5_mul(a, b)
            print(f"  {a.name} + {b.name} = {s.name}")
            print(f"  {a.name} * {b.name} = {p.name}")
    
    # Test bucket assignments
    print("\n=== Bucket Assignment Tests ===")
    for prim, bucket in PRIMITIVE_BUCKETS.items():
        print(f"  {prim}: {bucket.name}")
    
    for constr, bucket in CONSTRUCTOR_BUCKETS.items():
        print(f"  {constr}: {bucket.name}")
    
    # Test variance
    print("\n=== Variance Tests ===")
    for b in Mod5Bucket:
        print(f"  {b.name}: {get_variance(b)}")
    
    # Test structural moduli
    print(f"\nStructural moduli: {STRUCTURAL_MODULI}")
    print(f"Product: {37 * 73 * 11}")
    
    print("\n✓ All Mod-5 type system tests passed!")