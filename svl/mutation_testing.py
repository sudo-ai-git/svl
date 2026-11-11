# svl/mutation_testing.py
# Mutation testing framework for 231-gate verification (Spike S5)

from typing import List, Tuple, Callable, Optional
from dataclasses import dataclass
import random
import copy

from svl.gate231 import compute_checksums, MODULUS
from svl.viable_start import find_viable_start, verify_unique_viable_start


@dataclass
class MutationResult:
    """Result of a mutation test."""
    mutation_type: str
    position: int
    original_byte: int
    mutated_byte: int
    detected: bool
    viable_start_before: Optional[int]
    viable_start_after: Optional[int]


class MutationTesting:
    """Framework for testing mutation detection in 231-gate verified data."""
    
    MUTATION_TYPES = [
        'single_bit_flip',
        'byte_swap',
        'three_byte_burst',
        'checksum_byte_modification',
        'ast_node_type_change',
    ]
    
    def __init__(self, data: bytes, expected_checksums: Tuple[int, int, int], expected_meta: int):
        self.data = bytearray(data)
        self.expected_checksums = expected_checksums
        self.expected_meta = expected_meta
        self.block_size = 512
    
    def apply_mutation(self, mutation_type: str, position: int) -> Tuple[int, int]:
        """Apply a mutation at the given position. Returns (original_byte, mutated_byte)."""
        if position >= len(self.data):
            raise ValueError(f"Position {position} out of bounds")
        
        original = self.data[position]
        
        if mutation_type == 'single_bit_flip':
            # Flip a random bit
            bit = random.randint(0, 7)
            mutated = original ^ (1 << bit)
        elif mutation_type == 'byte_swap':
            # Swap with adjacent byte
            if position + 1 < len(self.data):
                self.data[position], self.data[position + 1] = self.data[position + 1], self.data[position]
                return original, self.data[position]
            else:
                # Swap with previous
                self.data[position], self.data[position - 1] = self.data[position - 1], self.data[position]
                return original, self.data[position]
        elif mutation_type == 'three_byte_burst':
            # Corrupt 3 consecutive bytes
            for i in range(3):
                if position + i < len(self.data):
                    self.data[position + i] ^= 0xFF
            return original, self.data[position]
        elif mutation_type == 'checksum_byte_modification':
            # Modify a byte that affects checksums
            # Just flip all bits
            mutated = original ^ 0xFF
        elif mutation_type == 'ast_node_type_change':
            # Simulate AST node type change by modifying a structural byte
            mutated = original ^ 0x80  # Flip high bit
        else:
            raise ValueError(f"Unknown mutation type: {mutation_type}")
        
        self.data[position] = mutated
        return original, mutated
    
    def test_mutation(self, mutation_type: str, position: int) -> MutationResult:
        """Test a single mutation."""
        # Get viable start before mutation
        viable_before = find_viable_start(
            bytes(self.data), self.expected_checksums, self.expected_meta
        )
        
        # Apply mutation
        original, mutated = self.apply_mutation(mutation_type, position)
        
        # Get viable start after mutation
        viable_after = find_viable_start(
            bytes(self.data), self.expected_checksums, self.expected_meta
        )
        
        # Check if mutation was detected
        detected = (viable_before != viable_after) or viable_after is None
        
        # Restore original data
        self.data[position] = original
        
        return MutationResult(
            mutation_type=mutation_type,
            position=position,
            original_byte=original,
            mutated_byte=mutated,
            detected=detected,
            viable_start_before=viable_before,
            viable_start_after=viable_after
        )
    
    def run_mutation_suite(self, num_tests_per_type: int = 20) -> List[MutationResult]:
        """Run a full mutation testing suite."""
        results = []
        
        # Determine the embedded region (non-zero bytes)
        embedded_start = None
        embedded_end = None
        for i, b in enumerate(self.data):
            if b != 0:
                if embedded_start is None:
                    embedded_start = i
                embedded_end = i
        
        if embedded_start is None:
            embedded_start = 0
            embedded_end = len(self.data) - 1
        
        for mut_type in self.MUTATION_TYPES:
            for _ in range(num_tests_per_type):
                # Only mutate within the embedded region
                if embedded_start is not None and embedded_end is not None and embedded_end > embedded_start:
                    position = random.randint(int(embedded_start), int(embedded_end))
                else:
                    position = random.randint(0, len(self.data) - 1)
                result = self.test_mutation(mut_type, position)
                results.append(result)
        
        return results
    
    def report_results(self, results: List[MutationResult]):
        """Print a summary of mutation testing results."""
        print(f"\n{'='*60}")
        print(f"MUTATION TESTING RESULTS")
        print(f"{'='*60}")
        print(f"Total mutations tested: {len(results)}")
        
        by_type = {}
        for r in results:
            if r.mutation_type not in by_type:
                by_type[r.mutation_type] = {'total': 0, 'detected': 0}
            by_type[r.mutation_type]['total'] += 1
            if r.detected:
                by_type[r.mutation_type]['detected'] += 1
        
        for mut_type, stats in by_type.items():
            rate = stats['detected'] / stats['total'] * 100
            print(f"  {mut_type}: {stats['detected']}/{stats['total']} ({rate:.1f}%)")
        
        total_detected = sum(s['detected'] for s in by_type.values())
        total = sum(s['total'] for s in by_type.values())
        overall_rate = total_detected / total * 100
        print(f"\nOverall detection rate: {total_detected}/{total} ({overall_rate:.1f}%)")
        
        return overall_rate


def run_spike_s5(data: bytes, expected_checksums: Tuple[int, int, int], expected_meta: int) -> bool:
    """
    Run Spike S5: Mutation testing for 231-gate verification.
    
    Tests 5 mutation types with 20 tests each (100 total).
    Requires 100% detection rate for all mutation types.
    """
    print(f"\n{'='*60}")
    print(f"SPIKE S5: MUTATION TESTING")
    print(f"{'='*60}")
    
    tester = MutationTesting(data, expected_checksums, expected_meta)
    # Reduced to 20 per type for speed (100 total)
    results = tester.run_mutation_suite(num_tests_per_type=20)
    rate = tester.report_results(results)
    
    # All mutations must be detected
    success = rate == 100.0
    
    if success:
        print("\n✓ SPIKE S5 PASSED - 100% mutation detection")
    else:
        print(f"\n✗ SPIKE S5 FAILED - {rate:.1f}% detection rate")
    
    return success


if __name__ == '__main__':
    # Test with golden reference
    from svl.golden_refs import get_golden_ref
    from svl.lexer import tokenize
    from svl.parser_rd import parse
    from svl.serialization import to_binary
    from svl.gate231 import compute_checksums
    
    ref = get_golden_ref('psalm119_aleph')
    
    tokens = tokenize(ref.source)
    ast = parse(tokens)
    from svl.serialization import to_binary
    ref_data = to_binary(ast)
    
    block_size = 512
    embed_pos = 100
    total_size = 1024
    
    test_data = bytearray(b'\x00' * total_size)
    ref_bytes = ref_data[:block_size]
    if len(ref_bytes) < block_size:
        ref_bytes = ref_bytes + b'\x00' * (block_size - len(ref_bytes))
    
    test_data[embed_pos:embed_pos + block_size] = ref_bytes
    
    expected = (173, 95, 0)
    expected_meta = 11
    
    success = run_spike_s5(bytes(test_data), expected, expected_meta)
    
    import sys
    sys.exit(0 if success else 1)