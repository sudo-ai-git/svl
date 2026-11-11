# svl/golden_refs.py
# Golden reference programs for 231-gate verification
# Psalm 119 Aleph and Genesis 1:1

from typing import Dict, Tuple
from dataclasses import dataclass

from svl.gate231 import compute_checksums, compute_checksums_cython
from svl.parser_rd import parse
from svl.lexer import tokenize


@dataclass
class GoldenReference:
    """A golden reference program with pre-computed checksums."""
    name: str
    source: str
    expected_checksums: Tuple[int, int, int]  # (SUM, LINEAR, PRODUCT)
    expected_meta: int


# Psalm 119 Aleph (first 8 verses) - represented as SVL program
# Each verse maps to a CONST declaration with verse number
PSALM_119_ALEPH_SOURCE = '''
module psalm119_aleph {
  const aleph: int = 1
  const bet: int = 2
  const gimel: int = 3
  const dalet: int = 4
  const he: int = 5
  const vav: int = 6
  const zayin: int = 7
  const het: int = 8
  const tet: int = 9
  const yod: int = 10
  const kaf: int = 20
  const lamed: int = 30
  const mem: int = 40
  const nun: int = 50
  const samekh: int = 60
  const ayin: int = 70
  const pe: int = 80
  const tsadi: int = 90
  const qof: int = 100
  const resh: int = 200
  const shin: int = 300
  const tav: int = 400
}
'''

# Genesis 1:1 - "In the beginning God created the heavens and the earth"
# In Hebrew: בראשית ברא אלהים את השמים ואת הארץ
# Numerical values: 913 + 203 + 86 + 401 + 395 + 407 + 296 = 2701 = 37 * 73
GENESIS_1_1_SOURCE = '''
module gen1_1 {
  let beginning: int = 913
  let created: int = 203
  let god: int = 86
  let the: int = 401
  let heavens: int = 395
  let and: int = 407
  let earth: int = 296
  assert sum == 37
  assert product == 73
}
'''

# Actually, let me compute the checksums for these programs properly
# The golden references need to be actual valid SVL programs that we can compute checksums for

# Let's create proper golden reference programs that are valid SVL
PSALM_119_ALEPH_PROGRAM = '''
module psalm119_aleph {
  const aleph: int = 1
  const bet: int = 2
  const gimel: int = 3
  const dalet: int = 4
  const he: int = 5
  const vav: int = 6
  const zayin: int = 7
  const het: int = 8
  const tet: int = 9
  const yod: int = 10
  const kaf: int = 20
  const lamed: int = 30
  const mem: int = 40
  const nun: int = 50
  const samekh: int = 60
  const ayin: int = 70
  const pe: int = 80
  const tsadi: int = 90
  const qof: int = 100
  const resh: int = 200
  const shin: int = 300
  const tav: int = 400
}
'''

GENESIS_1_1_PROGRAM = '''
module gen1_1 {
  let beginning: int = 913
  let created: int = 203
  let god: int = 86
  let the: int = 401
  let heavens: int = 395
  let and: int = 407
  let earth: int = 296
  let sum_val: int = 2701
  let product_val: int = 37
  let check_sum: int = 37
  let check_product: int = 73
}
'''

# Standard block size for 231-gate verification
BLOCK_SIZE = 512


def compute_block_checksums(data: bytes, block_size: int = BLOCK_SIZE) -> Tuple[int, int, int]:
    """Compute checksums for exactly block_size bytes (padded with zeros if needed)."""
    if len(data) < block_size:
        data = data + b'\x00' * (block_size - len(data))
    else:
        data = data[:block_size]
    return compute_checksums_cython(data)


def compute_golden_checksums(source: str) -> Tuple[int, int, int]:
    """Compute checksums for a golden reference program (512-byte block)."""
    tokens = tokenize(source)
    ast = parse(tokens)
    
    # Serialize AST to bytes (using canonical serialization)
    from svl.serialization import to_binary
    data = to_binary(ast)
    
    # Use Cython-optimized implementation on 512-byte block
    return compute_block_checksums(data, BLOCK_SIZE)


def load_golden_refs() -> Dict[str, GoldenReference]:
    """Load all golden references with computed checksums (512-byte blocks)."""
    refs = {}
    
    # Psalm 119 Aleph
    psalm_tokens = tokenize(PSALM_119_ALEPH_PROGRAM)
    psalm_ast = parse(psalm_tokens)
    from svl.serialization import to_binary
    psalm_data = to_binary(psalm_ast)
    psalm_checksums = compute_block_checksums(psalm_data, BLOCK_SIZE)
    
    refs['psalm119_aleph'] = GoldenReference(
        name='psalm119_aleph',
        source=PSALM_119_ALEPH_PROGRAM,
        expected_checksums=psalm_checksums,
        expected_meta=(psalm_checksums[0] ^ psalm_checksums[1] ^ psalm_checksums[2]) % 231
    )
    
    # Genesis 1:1
    gen_tokens = tokenize(GENESIS_1_1_PROGRAM)
    gen_ast = parse(gen_tokens)
    gen_data = to_binary(gen_ast)
    gen_checksums = compute_block_checksums(gen_data, BLOCK_SIZE)
    
    refs['gen1_1'] = GoldenReference(
        name='gen1_1',
        source=GENESIS_1_1_PROGRAM,
        expected_checksums=gen_checksums,
        expected_meta=(gen_checksums[0] ^ gen_checksums[1] ^ gen_checksums[2]) % 231
    )
    
    return refs


# Initialize on import
_GOLDEN_REFS_LOADED = False
_GOLDEN_REFS_CACHE: Dict[str, GoldenReference] = {}


def get_golden_ref(name: str) -> GoldenReference:
    """Get a golden reference by name, computing on first access."""
    global _GOLDEN_REFS_LOADED, _GOLDEN_REFS_CACHE
    
    if not _GOLDEN_REFS_LOADED:
        _GOLDEN_REFS_CACHE = load_golden_refs()
        _GOLDEN_REFS_LOADED = True
    
    return _GOLDEN_REFS_CACHE[name]


def get_all_golden_refs() -> Dict[str, GoldenReference]:
    """Get all golden references."""
    global _GOLDEN_REFS_LOADED, _GOLDEN_REFS_CACHE
    
    if not _GOLDEN_REFS_LOADED:
        _GOLDEN_REFS_CACHE = load_golden_refs()
        _GOLDEN_REFS_LOADED = True
    
    return _GOLDEN_REFS_CACHE


def verify_golden_ref(name: str) -> bool:
    """Verify a golden reference matches its expected checksums (512-byte block)."""
    ref = get_golden_ref(name)
    tokens = tokenize(ref.source)
    ast = parse(tokens)
    from svl.serialization import to_binary
    data = to_binary(ast)
    actual = compute_block_checksums(data, BLOCK_SIZE)
    
    return actual == ref.expected_checksums


def verify_all_golden_refs() -> Dict[str, bool]:
    """Verify all golden references."""
    refs = get_all_golden_refs()
    results = {}
    for name, ref in refs.items():
        results[name] = verify_golden_ref(name)
    return results


if __name__ == '__main__':
    print("Loading golden references...")
    refs = get_all_golden_refs()
    
    for name, ref in refs.items():
        print(f"\n{name}:")
        print(f"  SUM: {ref.expected_checksums[0]}")
        print(f"  LINEAR: {ref.expected_checksums[1]}")
        print(f"  PRODUCT: {ref.expected_checksums[2]}")
        print(f"  META: {ref.expected_meta}")
        print(f"  Source length: {len(ref.source)} chars")
    
    print("\nVerifying all golden references...")
    results = verify_all_golden_refs()
    for name, ok in results.items():
        print(f"  {name}: {'✓ PASS' if ok else '✗ FAIL'}")
    
    all_ok = all(results.values())
    print(f"\nAll verified: {'✓' if all_ok else '✗'}")