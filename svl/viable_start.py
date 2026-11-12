# svl/viable_start.py
# Viable Start Detector for 231-gate verification
# Implements both brute-force and CRT constraint propagation (Spike S5)

from typing import List, Tuple, Optional
from dataclasses import dataclass

from svl.gate231 import compute_checksums, compute_checksums_cython, MODULUS


# Prime factors of 231 = 3 * 7 * 11
CRT_MODULI = [3, 7, 11]


@dataclass
class ViableStartResult:
    """Result of viable start detection."""
    position: int
    checksums_match: bool
    meta_match: bool


def brute_force_viable_start(
    data: bytes,
    expected_checksums: Tuple[int, int, int],
    expected_meta: int,
    block_size: int = 512
) -> Optional[int]:
    """
    Brute-force viable start detection.
    
    Tries all possible start positions in a block, checking if all three
    checksums simultaneously match expected values.
    
    Args:
        data: Full data block (at least block_size bytes)
        expected_checksums: Expected (SUM, LINEAR, PRODUCT)
        expected_meta: Expected meta-checksum
        block_size: Size of block to check (default 512)
    
    Returns:
        Viable start position, or None if not found
    """
    max_start = len(data) - block_size + 1
    
    for start in range(max_start):
        block = data[start:start + block_size]
        actual = compute_checksums(block)
        
        if actual == expected_checksums:
            # Verify meta-checksum
            meta = (actual[0] ^ actual[1] ^ actual[2]) % 231
            if meta == expected_meta:
                return start
    
    return None


def crt_solve_viable_start(
    data: bytes,
    expected_checksums: Tuple[int, int, int],
    expected_meta: int,
    block_size: int = 512
) -> Optional[int]:
    """
    CRT-based viable start detection.
    
    Uses Chinese Remainder Theorem on moduli {3, 7, 11} (factors of 231)
    to constrain the search space, then verifies candidates.
    
    Args:
        data: Full data block
        expected_checksums: Expected (SUM, LINEAR, PRODUCT)
        expected_meta: Expected meta-checksum
        block_size: Size of block to check (default 512)
    
    Returns:
        Viable start position, or None if not found
    """
    max_start = len(data) - block_size + 1
    if max_start <= 0:
        return None
    
    expected_sum, expected_linear, expected_product = expected_checksums
    
    # For each modulus, find valid start positions mod that modulus
    # Search the entire data range for each modulus
    candidates_by_mod = {}
    
    for p in CRT_MODULI:
        candidates = []
        for start in range(max_start):
            block = data[start:start + block_size]
            if len(block) < block_size:
                continue
            
            actual = compute_checksums(block)
            
            if (actual[0] % p == expected_checksums[0] % p and
                actual[1] % p == expected_checksums[1] % p and
                actual[2] % p == expected_checksums[2] % p):
                candidates.append(start)
        
        candidates_by_mod[p] = candidates
    
    # Combine via CRT
    crt_candidates = combine_crt(candidates_by_mod)
    
    # Verify each candidate against full 231 modulus
    for start in crt_candidates:
        # Check all positions congruent to start mod 231
        for offset in range(start, max_start, MODULUS):
            block = data[offset:offset + block_size]
            if len(block) < block_size:
                continue
            
            actual = compute_checksums(block)
            if actual == expected_checksums:
                meta = (actual[0] ^ actual[1] ^ actual[2]) % 231
                if meta == expected_meta:
                    return offset
    
    return None


def combine_crt(candidates_by_mod: dict) -> List[int]:
    """
    Combine candidates from each modulus using CRT.

    For moduli 3, 7, 11, find all x such that:
        x ≡ a (mod 3)
        x ≡ b (mod 7)
        x ≡ c (mod 11)

    Returns list of solutions mod 231.
    """
    solutions = []
    
    mod3_candidates = candidates_by_mod.get(3, [])
    mod7_candidates = candidates_by_mod.get(7, [])
    mod11_candidates = candidates_by_mod.get(11, [])
    
    # Precompute CRT coefficients
    # 231 = 3 * 7 * 11
    # M = 231
    # M1 = 77, M2 = 33, M3 = 21
    # y1 = 77^-1 mod 3 = 2 (since 77 ≡ 2 mod 3, 2*2=4≡1)
    # y2 = 33^-1 mod 7 = 3 (since 33 ≡ 5 mod 7, 5*3=15≡1)
    # y3 = 21^-1 mod 11 = 10 (since 21 ≡ 10 mod 11, 10*10=100≡1)
    # M1*y1 = 77*2 = 154
    # M2*y2 = 33*3 = 99
    # M3*y3 = 21*10 = 210
    
    for a3 in mod3_candidates:
        for a7 in mod7_candidates:
            for a11 in mod11_candidates:
                # x = a3*M1*y1 + a7*M2*y2 + a11*M3*y3 (mod 231)
                x = (a3 * 154 + a7 * 99 + a11 * 210) % MODULUS
                solutions.append(x)
    
    return solutions


def find_viable_start(
    data: bytes,
    expected_checksums: Tuple[int, int, int],
    expected_meta: int,
    block_size: int = 512,
    method: str = 'crt'
) -> Optional[int]:
    """
    Find viable start using specified method.
    
    Args:
        data: Data block
        expected_checksums: Expected (SUM, LINEAR, PRODUCT)
        expected_meta: Expected meta-checksum
        block_size: Block size (default 512)
        method: 'brute' or 'crt'
    
    Returns:
        Viable start position or None
    """
    if method == 'brute':
        return brute_force_viable_start(data, expected_checksums, expected_meta, block_size)
    elif method == 'crt':
        return crt_solve_viable_start(data, expected_checksums, expected_meta, block_size)
    else:
        raise ValueError(f"Unknown method: {method}")


# ============================================================================
# ROLLING (O(n)) IMPLEMENTATION
# ============================================================================
#
# `crt_solve_viable_start` recomputes the full 512-byte checksum ONCE PER MODULUS PER
# POSITION -- 3x redundant work on top of an O(n*L) pure-Python inner loop.  Measured at
# ~0.95 s for a 2 KB block and ~13.7 s for 8 KB, which is why it never left the spikes.
#
# All three checksums can be maintained in O(1) amortised per one-byte shift:
#   SUM'     = SUM - out + in
#   LINEAR'  = LINEAR - SUM + L * in              (from the index-weighted sum)
#   PRODUCT' = PRODUCT / (out+1) * (in+1)         -- needs (out+1) invertible mod 231
# 231 = 3*7*11 is composite, so PRODUCT is tracked per prime factor instead: a count of
# window elements divisible by p, plus the product of the non-zero residues.  Each factor is
# prime, so every non-zero residue has an inverse and the product rolls exactly.

_CRT_PRIMES = (3, 7, 11)


def _crt_combine(residues) -> int:
    """Combine residues mod (3, 7, 11) into a value mod 231."""
    a3, a7, a11 = residues
    return (a3 * 154 + a7 * 99 + a11 * 210) % MODULUS


def _inv_mod_p(x: int, p: int) -> int:
    """Inverse of x mod p, for prime p and x != 0."""
    return pow(x, p - 2, p)


def rolling_checksums(data: bytes, block_size: int):
    """Yield (SUM, LINEAR, PRODUCT) mod 231 for every window, O(1) amortised per shift."""
    n = len(data)
    if block_size <= 0 or n < block_size:
        return
    L = block_size

    s = 0
    lin = 0
    zero_count = [0, 0, 0]
    prod_res = [1, 1, 1]
    for i in range(L):
        v = data[i]
        s += v
        lin += (i + 1) * v
        w = (v + 1) % MODULUS
        for k, p in enumerate(_CRT_PRIMES):
            wp = w % p
            if wp == 0:
                zero_count[k] += 1
            else:
                prod_res[k] = (prod_res[k] * wp) % p

    def _product():
        return _crt_combine([0 if zero_count[k] else prod_res[k] for k in range(3)])

    yield (s % MODULUS, lin % MODULUS, _product())

    for start in range(0, n - L):
        out = data[start]
        inc = data[start + L]
        # LINEAR' = LINEAR - SUM + L*in, using the OLD sum.
        lin = (lin - s + L * inc) % MODULUS
        s = (s - out + inc) % MODULUS
        wo = (out + 1) % MODULUS
        wi = (inc + 1) % MODULUS
        for k, p in enumerate(_CRT_PRIMES):
            x = wo % p
            if x == 0:
                zero_count[k] -= 1
            else:
                prod_res[k] = (prod_res[k] * _inv_mod_p(x, p)) % p
            y = wi % p
            if y == 0:
                zero_count[k] += 1
            else:
                prod_res[k] = (prod_res[k] * y) % p
        yield (s % MODULUS, lin % MODULUS, _product())


def rolling_viable_start(data: bytes, expected_checksums, expected_meta: int,
                         block_size: int = 512) -> Optional[int]:
    """O(n) viable-start search.  Same contract as `crt_solve_viable_start`."""
    for start, (s, l, p) in enumerate(rolling_checksums(data, block_size)):
        if (s, l, p) == tuple(expected_checksums):
            if ((s ^ l ^ p) % MODULUS) == expected_meta:
                return start
    return None


def rolling_unique_viable_starts(data: bytes, expected_checksums, expected_meta: int,
                                 block_size: int = 512) -> List[int]:
    """Every viable start, for proving uniqueness."""
    out = []
    for start, (s, l, p) in enumerate(rolling_checksums(data, block_size)):
        if (s, l, p) == tuple(expected_checksums) and ((s ^ l ^ p) % MODULUS) == expected_meta:
            out.append(start)
    return out


def verify_unique_viable_start(
    data: bytes,
    expected_checksums: Tuple[int, int, int],
    expected_meta: int,
    block_size: int = 512
) -> Tuple[bool, List[int]]:
    """
    Verify that exactly one viable start exists in the block.
    
    Returns:
        (is_unique, list_of_viable_starts)
    """
    max_start = len(data) - block_size + 1
    viable_starts = []
    
    for start in range(max_start):
        block = data[start:start + block_size]
        actual = compute_checksums(block)
        
        if actual == expected_checksums:
            meta = (actual[0] ^ actual[1] ^ actual[2]) % 231
            if meta == expected_meta:
                viable_starts.append(start)
    
    return (len(viable_starts) == 1, viable_starts)


if __name__ == '__main__':
    # Test with golden reference
    from svl.golden_refs import get_golden_ref
    
    ref = get_golden_ref('psalm119_aleph')
    
    # Create a larger data block containing the reference at known position
    from svl.lexer import tokenize
    from svl.parser_rd import parse
    from svl.serialization import to_binary
    
    tokens = tokenize(ref.source)
    ast = parse(tokens)
    from svl.serialization import to_binary
    ref_data = to_binary(ast)
    
    # Embed reference at position 100 in a 1024-byte block
    block_size = 512
    embed_pos = 100
    total_size = 1024
    
    test_data = bytearray(b'\x00' * total_size)
    ref_bytes = ref_data[:block_size]  # Use first 512 bytes of reference
    if len(ref_bytes) < block_size:
        ref_bytes = ref_bytes + b'\x00' * (block_size - len(ref_bytes))
    
    test_data[embed_pos:embed_pos + block_size] = ref_bytes
    
    expected = ref.expected_checksums
    expected_meta = ref.expected_meta
    
    print(f"Reference data length: {len(ref_data)}")
    print(f"Embedded at position: {embed_pos}")
    print(f"Expected checksums: {ref.expected_checksums}")
    print(f"Expected meta: {ref.expected_meta}")
    
    # Test brute force
    import time
    start = time.perf_counter()
    brute_result = brute_force_viable_start(test_data, expected, expected_meta)
    brute_time = time.perf_counter() - start
    print(f"\nBrute force: {brute_result} (time: {brute_time*1000:.2f} ms)")
    
    # Test CRT
    start = time.perf_counter()
    crt_result = crt_solve_viable_start(test_data, expected, expected_meta)
    crt_time = time.perf_counter() - start
    print(f"CRT: {crt_result} (time: {crt_time*1000:.2f} ms)")
    
    # Verify uniqueness
    unique, starts = verify_unique_viable_start(test_data, expected, expected_meta)
    print(f"\nUnique viable start: {unique}")
    print(f"Viable starts found: {starts}")
    print(f"Expected at: {embed_pos}")
    
    # Test with corrupted data
    print("\n--- Corruption Tests ---")
    for i in range(3):
        corrupted = bytearray(test_data)
        corrupted[embed_pos + i] ^= 0xFF  # Flip all bits at position i
        
        unique, starts = verify_unique_viable_start(bytes(corrupted), expected, expected_meta)
        print(f"Corruption at embed+{i}: unique={unique}, starts={starts}")
    
    # Also test: no viable start in clean padding
    clean_data = bytearray(b'\x00' * 1024)
    unique, starts = verify_unique_viable_start(bytes(clean_data), (1, 2, 3), 4)
    print(f"\nAll-zero data (expected no viable): unique={unique}, starts={starts}")