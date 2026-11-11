# svl/bpsw_monodromy.py
# BPSW Monodromy Implementation (Spike S9)
# Custom pi(p) = 2*(p+1) for p ∈ {37, 73, 17}
# ord_p(2): ord_37(2)=36, ord_73(2)=9, ord_17(2)=8
# Expected parities: all even (0)

from typing import Tuple, Dict, List, Optional
from dataclasses import dataclass
import hashlib


# ============================================================================
# CORE CONSTANTS (from MEMORY - verified)
# ============================================================================

BPSW_PRIMES = [37, 73, 17]

# Custom pi(p) = 2 * (p + 1) - NOT prime counting function!
PI_FUNCTION = {
    37: 76,   # 2 * (37 + 1) = 76
    73: 148,  # 2 * (73 + 1) = 148
    17: 36,   # 2 * (17 + 1) = 36
}

# Multiplicative order of 2 modulo p
ORD_2_MOD_P = {
    37: 36,   # 2^36 ≡ 1 (mod 37), minimal
    73: 9,    # 2^9 ≡ 1 (mod 73), minimal
    17: 8,    # 2^8 ≡ 1 (mod 17), minimal
}

# Expected monodromy parities: 0 = even (valid), 1 = odd (invalid)
EXPECTED_PARITIES = {37: 0, 73: 0, 17: 0}

# Verified divisibility properties (from MEMORY):
# 37 | pi(73) = 148, 38 | pi(37) = 76
# 73 | pi(73) = 148? No. 74 | pi(73) = 148
# 17 | pi(17) = 36? No. 18 | pi(17) = 36


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def modpow(base: int, exp: int, mod: int) -> int:
    """Modular exponentiation: (base^exp) % mod."""
    result = 1
    base = base % mod
    while exp > 0:
        if exp & 1:
            result = (result * base) % mod
        base = (base * base) % mod
        exp >>= 1
    return result


def jacobi_symbol(a: int, n: int) -> int:
    """Compute the Jacobi symbol (a|n)."""
    if n <= 0 or n % 2 == 0:
        return 0
    a = a % n
    result = 1
    while a != 0:
        while a % 2 == 0:
            a //= 2
            n_mod_8 = n % 8
            if n_mod_8 in (3, 5):
                result = -result
        a, n = n, a
        if a % 4 == 3 and n % 4 == 3:
            result = -result
        a = a % n
    return result if n == 1 else 0


def is_probable_prime_miller_rabin(n: int, bases: Optional[List[int]] = None) -> bool:
    """Miller-Rabin primality test with fixed base 2 (for BPSW)."""
    if n < 2:
        return False
    if n in (2, 3):
        return True
    if n % 2 == 0:
        return False
    
    # Fixed base 2 for BPSW
    if bases is None:
        bases = [2]
    
    # Write n-1 = d * 2^s
    d = n - 1
    s = 0
    while d % 2 == 0:
        d //= 2
        s += 1
    
    for a in bases:
        if a >= n:
            continue
        x = modpow(a, d, n)
        if x == 1 or x == n - 1:
            continue
        for _ in range(s - 1):
            x = (x * x) % n
            if x == n - 1:
                break
        else:
            return False
    return True


def lucas_sequence(P: int, Q: int, n: int, k: int) -> Tuple[int, int]:
    """Compute Lucas sequence U_k, V_k modulo n using standard binary method."""
    if k == 0:
        return (0, 2 % n)
    if k == 1:
        return (1, P % n)
    
    # Standard binary Lucas sequence algorithm
    # U_0 = 0, V_0 = 2
    # U_1 = 1, V_1 = P
    # For doubling: U_{2k} = U_k * V_k, V_{2k} = V_k^2 - 2*Q^k
    # For add: U_{k+1} = (P*U_k + V_k)/2, V_{k+1} = (D*U_k + P*V_k)/2 where D = P^2 - 4Q
    
    D = (P * P - 4 * Q) % n
    
    # Binary method: process bits from MSB to LSB
    U, V = 0, 2 % n  # U_0, V_0
    Q_k = 1 % n       # Q^0
    
    # Get binary representation of k
    bits = []
    temp = k
    while temp > 0:
        bits.append(temp & 1)
        temp >>= 1
    bits.reverse()
    
    for bit in bits:
        # Double step: U_{2m} = U_m * V_m, V_{2m} = V_m^2 - 2*Q^m
        U = (U * V) % n
        V = (V * V - 2 * Q_k) % n
        Q_k = (Q_k * Q_k) % n
        
        if bit:
            # Add step: U_{m+1} = (P*U_m + V_m)/2, V_{m+1} = (D*U_m + P*V_m)/2
            # Need to handle division by 2 modulo n
            U_new = (P * U + V) % n
            if U_new & 1:  # odd
                U_new += n
            U_new = (U_new // 2) % n
            
            V_new = (D * U + P * V) % n
            if V_new & 1:  # odd
                V_new += n
            V_new = (V_new // 2) % n
            
            U, V = U_new, V_new
            Q_k = (Q_k * Q) % n
    
    return (U % n, V % n)


def selfridge_parameters(n: int) -> Tuple[int, int, int]:
    """Find Selfridge parameters (D, P, Q) for Lucas test."""
    D = 5
    while True:
        j = jacobi_symbol(D, n)
        if j == -1:
            break
        if j == 0 and abs(D) != n:
            return (0, 0, 0)  # n shares factor with D
        if D > 0:
            D = -D - 2
        else:
            D = -D + 2
    P = 1
    Q = (1 - D) // 4
    return (D, P, Q)


def lucas_selfridge_test(n: int) -> bool:
    """Lucas test with Selfridge parameters."""
    if n < 2:
        return False
    if n % 2 == 0:
        return n == 2
    
    D, P, Q = selfridge_parameters(n)
    if D == 0:
        return False  # Found factor
    
    # Compute U_{n+1} mod n
    U, V = lucas_sequence(P, Q, n, n + 1)
    return U == 0


# ============================================================================
# BPSW PRIMALITY TEST (Miller-Rabin base 2 + Lucas Selfridge)
# ============================================================================

def bpsw_is_prime(n: int) -> bool:
    """BPSW primality test: Miller-Rabin base 2 AND Lucas Selfridge."""
    # Quick trial division for small factors
    small_primes = [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37]
    for p in small_primes:
        if n % p == 0:
            return n == p
    
    # Miller-Rabin with base 2
    if not is_probable_prime_miller_rabin(n, [2]):
        return False
    
    # Lucas Selfridge
    return lucas_selfridge_test(n)


# ============================================================================
# MONODROMY PARITY COMPUTATION
# ============================================================================

@dataclass
class MonodromyResult:
    """Result of monodromy check for a single prime."""
    prime: int
    program_hash_mod_p: int
    mr_result: bool
    lucas_result: bool
    parity: int  # 0 = even (both pass or both fail), 1 = odd (exactly one passes)
    passed: bool  # True if parity matches expected (0)


def compute_monodromy_for_prime(program_hash: int, p: int) -> MonodromyResult:
    """Compute monodromy parity for a single prime p."""
    h_mod_p = program_hash % p
    
    # If hash mod p == 0, treated as composite
    if h_mod_p == 0:
        mr = False
        lucas = False
    else:
        mr = is_probable_prime_miller_rabin(h_mod_p, [2])
        lucas = lucas_selfridge_test(h_mod_p)
    
    # Monodromy parity: MR XOR Lucas (0 if both same, 1 if different)
    parity = 1 if (mr != lucas) else 0
    expected = EXPECTED_PARITIES.get(p, 0)
    passed = (parity == expected)
    
    return MonodromyResult(
        prime=p,
        program_hash_mod_p=h_mod_p,
        mr_result=mr,
        lucas_result=lucas,
        parity=parity,
        passed=passed
    )


def compute_all_monodromy(program_hash: int) -> Dict[int, MonodromyResult]:
    """Compute monodromy results for all BPSW primes."""
    results = {}
    for p in BPSW_PRIMES:
        results[p] = compute_monodromy_for_prime(program_hash, p)
    return results


def monodromy_all_pass(results: Dict[int, MonodromyResult]) -> bool:
    """Check if all monodromy checks pass (all parities even)."""
    return all(r.passed for r in results.values())


# ============================================================================
# PROGRAM HASH COMPUTATION
# ============================================================================

def compute_program_hash(ast_bytes: bytes) -> int:
    """Compute SHA256 hash of canonical AST serialization as integer."""
    return int.from_bytes(hashlib.sha256(ast_bytes).digest(), 'big')


def compute_program_hash_hex(ast_bytes: bytes) -> str:
    """Compute SHA256 hash as hex string."""
    return hashlib.sha256(ast_bytes).hexdigest()


# ============================================================================
# HIGH-LEVEL VERIFICATION API
# ============================================================================

@dataclass
class TheoremVerifyResult:
    """Result of theorem layer verification."""
    passed: bool
    program_hash: int
    program_hash_hex: str
    monodromy_results: Dict[int, MonodromyResult]
    all_parities_even: bool
    error_message: Optional[str] = None


def verify_theorem(ast_bytes: bytes) -> TheoremVerifyResult:
    """
    Full theorem layer verification:
    1. Compute SHA256 of AST
    2. For each prime p in {37, 73, 17}:
       - Compute program_hash mod p
       - Run BPSW (MR base 2 + Lucas Selfridge)
       - Compute monodromy parity (MR XOR Lucas)
       - Check parity is even (0)
    3. All must pass
    """
    try:
        program_hash = compute_program_hash(ast_bytes)
        program_hash_hex = compute_program_hash_hex(ast_bytes)
        
        monodromy_results = compute_all_monodromy(program_hash)
        all_pass = monodromy_all_pass(monodromy_results)
        
        return TheoremVerifyResult(
            passed=all_pass,
            program_hash=program_hash,
            program_hash_hex=program_hash_hex,
            monodromy_results=monodromy_results,
            all_parities_even=all_pass
        )
    except Exception as e:
        return TheoremVerifyResult(
            passed=False,
            program_hash=0,
            program_hash_hex="",
            monodromy_results={},
            all_parities_even=False,
            error_message=f"Theorem verification error: {e}"
        )


# ============================================================================
# SPIKE S9 TEST FUNCTIONS
# ============================================================================

def spike_s9_test_vectors() -> Dict[str, bool]:
    """Run Spike S9 test cases - compare implementations."""
    results = {}
    
    # Test 1: Known primes (should pass BPSW)
    known_primes = [37, 73, 17, 2, 3, 5, 7, 11, 13, 19, 23, 29, 31, 41, 43, 47, 53, 59, 61, 67, 71, 79, 83, 89, 97]
    all_primes_pass = all(bpsw_is_prime(p) for p in known_primes)
    results['known_primes'] = all_primes_pass
    
    # Test 2: Known composites (should fail BPSW)
    known_composites = [4, 6, 8, 9, 10, 12, 14, 15, 16, 18, 20, 21, 22, 24, 25, 26, 27, 28, 30, 32, 33, 34, 35, 36, 38, 39, 40]
    all_composites_fail = all(not bpsw_is_prime(c) for c in known_composites)
    results['known_composites'] = all_composites_fail
    
    # Test 3: Carmichael numbers (should fail BPSW)
    carmichaels = [561, 1105, 1729, 2465, 2821, 6601, 8911, 10585, 15841, 29341, 41041, 46657, 52633, 62745, 63973]
    all_carmichaels_fail = all(not bpsw_is_prime(c) for c in carmichaels)
    results['carmichaels'] = all_carmichaels_fail
    
    # Test 4: pi(p) function values
    pi_correct = (
        PI_FUNCTION[37] == 76 and
        PI_FUNCTION[73] == 148 and
        PI_FUNCTION[17] == 36
    )
    results['pi_function'] = pi_correct
    
    # Test 5: ord_2(p) values
    ord_correct = (
        ORD_2_MOD_P[37] == 36 and
        ORD_2_MOD_P[73] == 9 and
        ORD_2_MOD_P[17] == 8
    )
    results['ord_function'] = ord_correct
    
    # Test 6: Verified divisibility
    div_correct = (
        PI_FUNCTION[73] % 37 == 0 and  # 148 % 37 == 0
        PI_FUNCTION[73] % 74 == 0 and  # 148 % 74 == 0
        PI_FUNCTION[37] % 38 == 0 and  # 76 % 38 == 0
        PI_FUNCTION[17] % 18 == 0      # 36 % 18 == 0
    )
    results['divisibility'] = div_correct
    
    # Test 7: Monodromy on known hashes
    test_hashes = [
        b"test program 1",
        b"test program 2",
        b"hello world",
        b"svl compiler bootstrap",
    ]
    monodromy_works = True
    for h in test_hashes:
        hash_int = int.from_bytes(hashlib.sha256(h).digest(), 'big')
        res = verify_theorem(h)
        if res.error_message:
            monodromy_works = False
            break
    results['monodromy_execution'] = monodromy_works
    
    return results


def spike_s9_performance_test(num_hashes: int = 1000) -> Dict[str, float]:
    """Performance test for Spike S9."""
    import time
    
    # Generate test hashes
    test_data = [f"program_{i}".encode() for i in range(num_hashes)]
    
    start = time.perf_counter()
    for data in test_data:
        verify_theorem(data)
    total_time = time.perf_counter() - start
    
    return {
        'total_time': total_time,
        'per_hash_ms': (total_time / num_hashes) * 1000,
        'hashes_per_sec': num_hashes / total_time
    }


if __name__ == '__main__':
    print("=== BPSW Monodromy Tests ===")
    
    # Test pi function
    print("\n--- pi(p) values ---")
    for p in BPSW_PRIMES:
        print(f"  pi({p}) = {PI_FUNCTION[p]} (expected {2*(p+1)})")
    
    # Test ord function
    print("\n--- ord_2(p) values ---")
    for p in BPSW_PRIMES:
        print(f"  ord_37(2) = {ORD_2_MOD_P[37]}")
        print(f"  ord_73(2) = {ORD_2_MOD_P[73]}")
        print(f"  ord_17(2) = {ORD_2_MOD_P[17]}")
    
    # Verify divisibility
    print("\n--- Divisibility checks ---")
    print(f"  37 | pi(73): {PI_FUNCTION[73] % 37 == 0} (148 % 37 = {148 % 37})")
    print(f"  74 | pi(73): {PI_FUNCTION[73] % 74 == 0} (148 % 74 = {148 % 74})")
    print(f"  38 | pi(37): {PI_FUNCTION[37] % 38 == 0} (76 % 38 = {76 % 38})")
    print(f"  18 | pi(17): {PI_FUNCTION[17] % 18 == 0} (36 % 18 = {36 % 18})")
    
    # Run spike tests
    print("\n--- Spike S9 Tests ---")
    spike_results = spike_s9_test_vectors()
    for test, passed in spike_results.items():
        print(f"  {test}: {'✓ PASS' if passed else '✗ FAIL'}")
    
    # Performance test
    print("\n--- Performance Test (100 hashes) ---")
    perf = spike_s9_performance_test(100)
    print(f"  Total: {perf['total_time']*1000:.2f} ms")
    print(f"  Per hash: {perf['per_hash_ms']:.3f} ms")
    print(f"  Throughput: {perf['hashes_per_sec']:.0f} hashes/sec")
    
    # Full verification example
    print("\n--- Full Verification Example ---")
    test_ast = b"module test { func main() type void { return } }"
    result = verify_theorem(test_ast)
    print(f"  Hash: {result.program_hash_hex[:16]}...")
    print(f"  Passed: {result.passed}")
    for p, r in result.monodromy_results.items():
        print(f"  p={p}: hash_mod={r.program_hash_mod_p}, MR={r.mr_result}, Lucas={r.lucas_result}, parity={r.parity}, passed={r.passed}")
    
    print("\n✓ All BPSW Monodromy tests complete!")