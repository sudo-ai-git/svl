# svl/gate231.py
# Core 231-Gate checksum implementation (Spike S4)
# Three checksums: SUM, LINEAR, PRODUCT mod 231

from typing import List, Tuple, Optional
import numpy as np

MODULUS = 231  # 3 * 7 * 11
ROLLING_MULTIPLIER = 31  # coprime to 231, so no single byte can force a zero


def sum_checksum(data: bytes) -> int:
    """SUM = (Σ bytes) mod 231"""
    return sum(data) % MODULUS


def linear_checksum(data: bytes) -> int:
    """LINEAR = (Σ (i+1) * byte[i]) mod 231"""
    total = 0
    for i, b in enumerate(data):
        total += (i + 1) * b
    return total % MODULUS


def rolling_checksum(data: bytes) -> int:
    """ROLLING = (H*31 + byte[i]) mod 231, H_0 = 0.

    This is the third channel.  It replaced the old PRODUCT channel, which was
    **degenerate**: Π(b+1) mod 231 is 0 whenever any byte has b+1 divisible by 3, 7 or
    11, so 2000/2000 random 512-byte windows produced 0 and the channel carried no
    information.  31 is coprime to 231, so the rolling hash is non-degenerate: a
    one-byte change alters the checksum with probability ≈ 1 - 1/231.
    """
    h = 0
    for b in data:
        h = (h * ROLLING_MULTIPLIER + b) % MODULUS
    return h


def product_checksum(data: bytes) -> int:
    """Deprecated alias for :func:`rolling_checksum` (the channel is no longer a product)."""
    return rolling_checksum(data)


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
    """NumPy implementation of the rolling-hash channel (see `rolling_checksum`)."""
    n = len(data)
    if n == 0:
        return 0
    powers = np.empty(n, dtype=np.int64)
    p = 1
    for i in range(n - 1, -1, -1):
        powers[i] = p
        p = (p * ROLLING_MULTIPLIER) % MODULUS
    return int((np.dot(data.astype(np.int64), powers)) % MODULUS)


def rolling_checksum_numpy(data: np.ndarray) -> int:
    """Alias for the NumPy rolling-hash channel."""
    return product_checksum_numpy(data)


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
    """Cython-compatible rolling-hash channel (pure Python equivalent)."""
    h = 0
    for b in data:
        h = (h * ROLLING_MULTIPLIER + b) % MODULUS
    return h


def rolling_checksum_cython(data: bytes) -> int:
    """Alias for the Cython-compatible rolling-hash channel."""
    return product_checksum_cython(data)


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