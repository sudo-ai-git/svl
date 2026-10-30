#!/usr/bin/env python3
"""Autonomous exploration of BTC puzzle level 5 alternative patterns with full verification layer."""
import hashlib, os, sys, binascii, time
sys.path.insert(0, "/home/sudosudo/venv/lib/python3.12/site-packages")

try:
    import ecdsa
    from ecdsa import SECP256k1, VerifyingKey, SigningKey
    import base58
except Exception as e:
    print("Dependency error:", e)
    sys.exit(1)

TARGET = "1cryptoGeCRiTzVgxBQcKFFjSVydN1GW7"
# Secp256k1 curve order
N_hex = "FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141"
N_int = int(N_hex, 16)

def verify_scalar(d_hex):
    d_int = int(d_hex, 16)
    if d_int < 1 or d_int >= N_int:
        return False, "scalar out of [1,n-1]"
    # d*G == Q verification: derive public key and encode compressed address
    try:
        sk = SigningKey.from_string(binascii.unhexlify(d_hex), curve=SECP256k1)
        vk = sk.get_verifying_key()
        compressed = b"\x02" + vk.to_string()[:32] if vk.to_string()[32:] == b"" else b"\x03" + vk.to_string()[:32]
        # compressed format uses 02 for even y, 03 for odd y; to_string returns 64 bytes (x,y)
        # Actually ecdsa to_string is uncompressed 64 bytes; we need compressed properly
        # Let's compute properly
        pub_key_bytes = vk.to_string()  # uncompressed 64 bytes (x, y each 32)
        x_bytes = pub_key_bytes[:32]
        y_bytes = pub_key_bytes[32:]
        y_int = int.from_bytes(y_bytes, 'big')
        prefix = b"\x02" if (y_int % 2 == 0) else b"\x03"
        compressed = prefix + x_bytes
        # SHA256(RIPEMD160) for address
        sha = hashlib.sha256(compressed).digest()
        ripemd = hashlib.new('ripemd160')
        ripemd.update(sha)
        hash160 = ripemd.digest()
        # Add version byte 0x00 and base58check encode
        payload = b"\x00" + hash160
        checksum = hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
        addr_bytes = payload + checksum
        addr = base58.b58encode(addr_bytes).decode('ascii')
        return True, addr
    except Exception as ex:
        return False, f"ecdsa error: {ex}"

def pattern_coordinate_encoding():
    # Encode (26, 5) => 26<<8 | 5 => but need 32 bytes; use multiple coords
    coords = [(26,5), (12,8), (3,14), (7,2), (19,4), (1,1), (23,11), (9,6)]
    data = b"".join(bytes([( (c[0] + c[1]*17) & 0xFF )]) for c in coords)
    # Pad to 32 bytes using hash of coordinate string
    extra = hashlib.sha256(b"coordinate_encoding").digest()
    d_hex = (data + extra)[:32].hex()
    return d_hex, "coordinate_encoding"

def pattern_fibonacci():
    # Fibonacci sequence bytes
    a, b = 0, 1
    seq = []
    for _ in range(16):
        a, b = b, a + b
        seq.append(b & 0xFF)
    data = bytes(seq)
    extra = hashlib.sha256(b"fibonacci").digest()
    d_hex = (data + extra)[:32].hex()
    return d_hex, "fibonacci"

def pattern_hash160_reverse():
    # Reverse target string digits as hex bytes
    rev = TARGET[::-1].encode()
    # Pad/repeat to 32 bytes
    data = (rev * 2)[:32]
    extra = hashlib.sha256(b"hash160_reverse").digest()
    d_hex = (data + extra)[:32].hex()
    return d_hex, "hash160_reverse"

def pattern_decimal_digits():
    # Extract digits from target/related strings
    digits = "".join([c for c in TARGET if c.isdigit()])
    # Use decimal digits to build scalar hex (repeat/pad)
    digits_bytes = digits.encode() if digits else b"0"
    data = (digits_bytes * 4)[:32]
    extra = hashlib.sha256(b"decimal_digits").digest()
    d_hex = (data + extra)[:32].hex()
    return d_hex, "decimal_digits"

def pattern_digit_controlled_divisors():
    # Digits of 26 (level) control divisors; build scalar with divisors embedded
    level = 5
    divisors = [d for d in range(2, 32) if (d*level) % 7 == 0 or (d*level) % 5 == 0]
    div_bytes = bytes(divisors)
    extra = hashlib.sha256(b"digit_controlled_divisors").digest()
    d_hex = (div_bytes + extra)[:32].hex()
    return d_hex, "digit_controlled_divisors"

def pattern_bit_interleaving():
    # Interleave bits from two byte sequences derived from target
    src = TARGET.encode()
    bits1 = [int(b) for b in src[:8]]
    bits2 = [int(b) for b in src[-8:]]
    interleaved = bytearray(32)
    for i in range(32):
        interleaved[i] = ((bits1[i%len(bits1)] << 4) | (bits2[i%len(bits2)])) & 0xFF
    d_hex = bytes(interleaved).hex()
    return d_hex, "bit_interleaving"

def pattern_grid_spiral():
    # Grid pattern encoding based on 8x4 grid values
    grid = list(range(1, 33))  # 1..32 mapped
    # Spiral: start center-ish and spiral outward
    # Simplified: use grid values as bytes directly
    data = bytes(grid)
    extra = hashlib.sha256(b"grid_spiral").digest()
    d_hex = (data + extra)[:32].hex()
    return d_hex, "grid_spiral"

def pattern_checksum():
    # Checksum-based scalar: SHA256 of target + checksum approach
    base = TARGET.encode()
    checksum = hashlib.sha256(base).digest()
    d_hex = checksum.hex()
    return d_hex, "checksum"

def pattern_prime_factors():
    # Product of first primes encoded
    primes = [2,3,5,7,11,13,17,19,23,29,31,37,41,43,47,53,59,61,67,71,73,79,83]
    prod_bytes = bytes([(p & 0xFF) for p in primes])
    extra = hashlib.sha256(b"prime_factors").digest()
    d_hex = (prod_bytes + extra)[:32].hex()
    return d_hex, "prime_factors"

def pattern_value_based_walk():
    # Value-based walk: step values derived from target characters
    vals = [ord(c) for c in TARGET]
    walked = bytearray()
    v = 1
    for i in range(32):
        v = (v + vals[i % len(vals)]) % 256
        walked.append(v)
    d_hex = bytes(walked).hex()
    return d_hex, "value_based_walk"

def pattern_two_phase_walk():
    # Two-phase walk combining coordinate and digit values
    phase1 = hashlib.sha256(b"phase1").digest()
    phase2 = hashlib.sha256(b"phase2").digest()
    combined = bytes(a ^ b for a, b in zip(phase1, phase2))
    d_hex = combined.hex()
    return d_hex, "two_phase_walk"

def pattern_target_hash160():
    # Target hash160 analysis approach
    h = hashlib.sha256(TARGET.encode()).digest()
    ripemd = hashlib.new('ripemd160')
    ripemd.update(h)
    hash160_bytes = ripemd.digest()
    # Pad/repeat to 32 bytes
    extended = (hash160_bytes * 2)[:32]
    d_hex = extended.hex()
    return d_hex, "target_hash160"

def pattern_spiral():
    # Spiral encoding using Fibonacci spacing
    spiral_vals = [int(abs(__import__('math').sin(i) * 255)) for i in range(32)]
    d_hex = bytes(spiral_vals).hex()
    return d_hex, "spiral"

def main():
    patterns = [
        pattern_coordinate_encoding,
        pattern_fibonacci,
        pattern_hash160_reverse,
        pattern_decimal_digits,
        pattern_digit_controlled_divisors,
        pattern_bit_interleaving,
        pattern_grid_spiral,
        pattern_checksum,
        pattern_prime_factors,
        pattern_value_based_walk,
        pattern_two_phase_walk,
        pattern_target_hash160,
        pattern_spiral,
    ]
    results = []
    for pat in patterns:
        try:
            d_hex, name = pat()
            ok, info = verify_scalar(d_hex)
            status = "PASS" if ok else "FAIL"
            results.append({
                "pattern": name,
                "hex_key": d_hex,
                "valid_scalar": ok,
                "derived_address": info if ok else info,
                "match_target": TARGET,
                "status": status,
            })
            print(f"{name}: scalar_valid={ok} address={info if ok else info} -> {status}")
        except Exception as ex:
            results.append({
                "pattern": pat.__name__,
                "hex_key": "ERROR",
                "valid_scalar": False,
                "derived_address": f"exception: {ex}",
                "match_target": TARGET,
                "status": "FAIL",
            })
            print(f"{pat.__name__}: EXCEPTION {ex}")

    # Write artifact
    artifact_path = "/tmp/autonomous_agent_exploration_results.md"
    with open(artifact_path, "w") as f:
        f.write("# Autonomous Agent Exploration Results - BTC Puzzle Level 5\n")
        f.write(f"Target address: `{TARGET}`\n\n")
        f.write(f"Verification layer: secp256k1 scalar check (1 <= d < n) + compressed address via base58\n")
        f.write(f"Total patterns executed: {len(results)}\n\n")
        f.write("## Pattern Results\n\n")
        for r in results:
            f.write(f"### {r['pattern']}\n")
            f.write(f"- **Status**: {r['status']}\n")
            f.write(f"- **32-byte scalar hex**: `{r['hex_key']}`\n")
            f.write(f"- **Valid secp256k1 scalar**: {r['valid_scalar']}\n")
            if r['status'] == "PASS":
                f.write(f"- **Derived compressed address**: `{r['derived_address']}`\n")
                match_str = "MATCH" if r['derived_address'] == TARGET else "NO MATCH"
                f.write(f"- **Target comparison**: `{match_str}` (target: `{r['match_target']}`)\n")
            else:
                f.write(f"- **Verification info**: {r['derived_address']}\n")
            f.write("\n")
        f.write("## Summary Count\n\n")
        passes = sum(1 for r in results if r['status'] == "PASS")
        fails = len(results) - passes
        f.write(f"- PASS (valid scalar + derived address): {passes}\n")
        f.write(f"- FAIL (invalid scalar or exception): {fails}\n")
        f.write(f"- No fabricated match: verified by ecdsa+base58 execution.\n")
        f.write(f"- Artifacts: {artifact_path}\n")
    print(f"Artifact saved to {artifact_path}")

if __name__ == "__main__":
    main()
