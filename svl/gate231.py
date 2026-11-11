# svl/gate231.py
# Core 231-Gate checksum implementation (Spike S4)
# Three checksums: SUM, LINEAR, PRODUCT mod 231

from typing import List, Tuple, Optional
import numpy as np

MODULUS = 231  # 3 * 7 * 11


def sum_checksum(data: bytes) -> int:
    """SUM = (Σ bytes) mod 231"""
    return sum(data) % MODULUS


def linear_checksum(data: bytes) -> int:
    """LINEAR = (Σ (i+1) * byte[i]) mod 231"""
    total = 0
    for i, b in enumerate(data):
        total += (i + 1) * b
    return total % MODULUS


def product_checksum(data: bytes) -> int:
    """PRODUCT = (Π (byte[i] + 1)) mod 231 (with 0→1 mapping)"""
    result = 1
    for b in data:
        result = (result * (b + 1)) % MODULUS
    return result


def compute_checksums(data: bytes) -> Tuple[int, int, int]:
    """Compute all three checksums for the given data."""
    return (
        sum_checksum(data),
        linear_checksum(data),
        product_checksum(data)
    )


def verify_checksums(data: bytes, expected: Tuple[int, int, int]) -> bool:
    """Verify that data's checksums match expected values."""
    actual = compute_checksums(data)
    return actual == expected


def meta_checksum(data: bytes) -> int:
    """Meta-checksum: SUM ⊕ LINEAR ⊕ PRODUCT mod 231"""
    s, l, p = compute_checksums(data)
    return (s ^ l ^ p) % MODULUS


# NumPy vectorized implementations (for Spike S4 comparison)
def sum_checksum_numpy(data: np.ndarray) -> int:
    """NumPy vectorized SUM checksum."""
    return int(np.sum(data, dtype=np.uint64) % MODULUS)


def linear_checksum_numpy(data: np.ndarray) -> int:
    """NumPy vectorized LINEAR checksum."""
    indices = np.arange(1, len(data) + 1, dtype=np.uint64)
    return int(np.sum(indices * data, dtype=np.uint64) % MODULUS)


def product_checksum_numpy(data: np.ndarray) -> int:
    """NumPy vectorized PRODUCT checksum with modulo at each step."""
    result = 1
    for b in data:
        result = (result * (int(b) + 1)) % MODULUS
    return int(result)


def compute_checksums_numpy(data: bytes) -> Tuple[int, int, int]:
    """Compute all three checksums using NumPy."""
    arr = np.frombuffer(data, dtype=np.uint8)
    return (
        sum_checksum_numpy(arr),
        linear_checksum_numpy(arr),
        product_checksum_numpy(arr)
    )


# Cython-compatible implementations (same as Python but typed for Cython)
# These would be in a .pyx file but we provide Python equivalents here
def sum_checksum_cython(data: bytes) -> int:
    """Cython-compatible SUM checksum (pure Python equivalent)."""
    total = 0
    for b in data:
        total += b
    return total % MODULUS


def linear_checksum_cython(data: bytes) -> int:
    """Cython-compatible LINEAR checksum (pure Python equivalent)."""
    total = 0
    for i, b in enumerate(data):
        total += (i + 1) * b
    return total % MODULUS


def product_checksum_cython(data: bytes) -> int:
    """Cython-compatible PRODUCT checksum (pure Python equivalent)."""
    result = 1
    for b in data:
        result = (result * (b + 1)) % MODULUS
    return result


def compute_checksums_cython(data: bytes) -> Tuple[int, int, int]:
    """Cython-compatible checksum computation."""
    return (
        sum_checksum_cython(data),
        linear_checksum_cython(data),
        product_checksum_cython(data)
    )


# Verify implementations produce identical results
def verify_implementation_identity() -> bool:
    """Verify all implementations produce bit-identical results."""
    test_data = b"Hello, World! This is a test." * 10
    
    py = compute_checksums(test_data)
    np = compute_checksums_numpy(test_data)
    cy = compute_checksums_cython(test_data)
    
    return py == np == cy


if __name__ == '__main__':
    # Quick test
    test_data = b"Test data for 231-gate checksums"
    s, l, p = compute_checksums(test_data)
    print(f"Data: {test_data}")
    print(f"SUM: {s}, LINEAR: {l}, PRODUCT: {p}")
    print(f"Meta: {meta_checksum(test_data)}")
    
    # Verify implementations
    if verify_implementation_identity():
        print("✓ All implementations produce identical results")
    else:
        print("✗ Implementation mismatch!")
    
    # Performance test
    import time
    large_data = b"x" * 5000
    
    start = time.perf_counter()
    for _ in range(100):
        compute_checksums(large_data)
    py_time = time.perf_counter() - start
    
    start = time.perf_counter()
    for _ in range(100):
        compute_checksums_numpy(large_data)
    np_time = time.perf_counter() - start
    
    start = time.perf_counter()
    for _ in range(100):
        compute_checksums_cython(large_data)
    cy_time = time.perf_counter() - start
    
    print(f"\nPerformance (100 iterations on 5KB):")
    print(f"  Python: {py_time*1000:.2f} ms")
    print(f"  NumPy:  {np_time*1000:.2f} ms")
    print(f"  Cython: {cy_time*1000:.2f} ms")