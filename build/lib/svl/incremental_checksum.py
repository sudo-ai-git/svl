# svl/incremental_checksum.py
# Incremental 231-Gate Checksums (H18)
# O(1) checksum updates for IDE feedback

from typing import List, Tuple, Dict, Optional
from dataclasses import dataclass, field
from svl.gate231 import compute_checksums_cython, MODULUS


@dataclass
class IncrementalChecksum:
    """Incremental checksum state for O(1) updates."""
    sum_val: int = 0
    linear_val: int = 0
    product_val: int = 1
    length: int = 0
    data: bytearray = field(default_factory=bytearray)
    
    def append_byte(self, byte: int):
        """Append a byte and update checksums incrementally."""
        self.length += 1
        self.sum_val = (self.sum_val + byte) % MODULUS
        self.linear_val = (self.linear_val + self.length * byte) % MODULUS
        self.product_val = (self.product_val * (byte + 1)) % MODULUS
        self.data.append(byte)
        
    def update_byte(self, index: int, new_byte: int):
        """Update a byte at index and recompute affected checksums."""
        if index >= len(self.data):
            raise IndexError(f"Index {index} out of bounds")
            
        old_byte = self.data[index]
        if old_byte == new_byte:
            return
            
        # Update SUM: subtract old, add new
        self.sum_val = (self.sum_val - old_byte + new_byte) % MODULUS
        
        # Update LINEAR: subtract old contribution, add new
        pos = index + 1  # 1-indexed for linear checksum
        self.linear_val = (self.linear_val - pos * old_byte + pos * new_byte) % MODULUS
        
        # Update PRODUCT: divide by (old+1), multiply by (new+1)
        # Since we're in mod MODULUS, we need modular inverse
        old_factor = (old_byte + 1) % MODULUS
        new_factor = (new_byte + 1) % MODULUS
        
        # Compute modular inverse of old_factor
        inv_old = pow(old_factor, MODULUS - 2, MODULUS) if old_factor != 0 else 0
        self.product_val = (self.product_val * inv_old) % MODULUS
        self.product_val = (self.product_val * new_factor) % MODULUS
        
        self.data[index] = new_byte
        
    def insert_byte(self, index: int, byte: int):
        """Insert a byte at index."""
        if index > len(self.data):
            index = len(self.data)
            
        self.data.insert(index, byte)
        self.length += 1
        
        # Recompute all checksums from insertion point
        # This is O(n) but only for the affected suffix
        self._recompute_from(index)
        
    def delete_byte(self, index: int):
        """Delete a byte at index."""
        if index >= len(self.data):
            raise IndexError(f"Index {index} out of bounds")
            
        self.data.pop(index)
        self.length -= 1
        
        # Recompute all checksums from deletion point
        self._recompute_from(index)
        
    def _recompute_from(self, start: int):
        """Recompute checksums from start position to end."""
        # Recompute prefix sums up to start
        self.sum_val = sum(self.data[:start]) % MODULUS
        self.linear_val = sum((i + 1) * self.data[i] for i in range(start)) % MODULUS
        self.product_val = 1
        for i in range(start):
            self.product_val = (self.product_val * (self.data[i] + 1)) % MODULUS
            
        # Recompute from start to end using direct computation (not append_byte)
        for i in range(start, len(self.data)):
            byte = self.data[i]
            self.sum_val = (self.sum_val + byte) % MODULUS
            self.linear_val = (self.linear_val + (i + 1) * byte) % MODULUS
            self.product_val = (self.product_val * (byte + 1)) % MODULUS
            
    def get_checksums(self) -> Tuple[int, int, int]:
        """Get current checksums."""
        return (self.sum_val, self.linear_val, self.product_val)
        
    def verify(self, expected: Tuple[int, int, int]) -> bool:
        """Verify checksums match expected."""
        return self.get_checksums() == expected


class IncrementalChecksumManager:
    """Manages incremental checksums for multiple buffers."""
    
    def __init__(self):
        self.buffers: Dict[str, IncrementalChecksum] = {}
        
    def create_buffer(self, name: str, initial_data: bytes = b'') -> IncrementalChecksum:
        """Create a new incremental checksum buffer."""
        ic = IncrementalChecksum()
        for byte in initial_data:
            ic.append_byte(byte)
        self.buffers[name] = ic
        return ic
        
    def get_buffer(self, name: str) -> Optional[IncrementalChecksum]:
        """Get a buffer by name."""
        return self.buffers.get(name)
        
    def update_buffer(self, name: str, index: int, byte: int) -> bool:
        """Update a byte in a buffer."""
        if name not in self.buffers:
            return False
        self.buffers[name].update_byte(index, byte)
        return True
        
    def verify_all(self, expected: Dict[str, Tuple[int, int, int]]) -> Dict[str, bool]:
        """Verify all buffers against expected checksums."""
        results = {}
        for name, expected_checksums in expected.items():
            if name in self.buffers:
                results[name] = self.buffers[name].verify(expected_checksums)
            else:
                results[name] = False
        return results


def test_incremental_checksum():
    """Test incremental checksum functionality."""
    print("=== Incremental Checksum Test ===")
    
    # Test basic append
    ic = IncrementalChecksum()
    test_data = b"Hello, World! "
    for byte in test_data:
        ic.append_byte(byte)
    
    expected = (sum(test_data) % 231, 
                sum((i+1)*b for i,b in enumerate(test_data)) % 231,
                1)
    for byte in test_data:
        expected = (expected[0], expected[1], (expected[2] * (byte + 1)) % 231)
    
    actual = ic.get_checksums()
    print(f"Append test: {'PASS' if actual == expected else 'FAIL'}")
    print(f"  Expected: {expected}")
    print(f"  Actual:   {actual}")
    
    # Test update
    ic2 = IncrementalChecksum()
    for byte in test_data:
        ic2.append_byte(byte)
    
    ic2.update_byte(0, ord('J'))  # Change 'H' to 'J'
    
    modified = bytearray(test_data)
    modified[0] = ord('J')
    expected2 = (sum(modified) % 231,
                 sum((i+1)*b for i,b in enumerate(modified)) % 231,
                 1)
    for byte in modified:
        expected2 = (expected2[0], expected2[1], (expected2[2] * (byte + 1)) % 231)
    
    actual2 = ic2.get_checksums()
    print(f"Update test: {'PASS' if actual2 == expected2 else 'FAIL'}")
    print(f"  Expected: {expected2}")
    print(f"  Actual:   {actual2}")
    
    # Test insert
    ic3 = IncrementalChecksum()
    for byte in test_data:
        ic3.append_byte(byte)
    
    ic3.insert_byte(5, ord(','))  # Insert comma after "Hello"
    
    modified3 = bytearray(test_data)
    modified3.insert(5, ord(','))
    expected3 = (sum(modified3) % 231,
                 sum((i+1)*b for i,b in enumerate(modified3)) % 231,
                 1)
    for byte in modified3:
        expected3 = (expected3[0], expected3[1], (expected3[2] * (byte + 1)) % 231)
    
    actual3 = ic3.get_checksums()
    print(f"Insert test: {'PASS' if actual3 == expected3 else 'FAIL'}")
    print(f"  Expected: {expected3}")
    print(f"  Actual:   {actual3}")
    
    # Test delete
    ic4 = IncrementalChecksum()
    for byte in test_data:
        ic4.append_byte(byte)
    
    ic4.delete_byte(5)  # Delete comma
    
    modified4 = bytearray(test_data)
    modified4.pop(5)
    expected4 = (sum(modified4) % 231,
                 sum((i+1)*b for i,b in enumerate(modified4)) % 231,
                 1)
    for byte in modified4:
        expected4 = (expected4[0], expected4[1], (expected4[2] * (byte + 1)) % 231)
    
    actual4 = ic4.get_checksums()
    print(f"Delete test: {'PASS' if actual4 == expected4 else 'FAIL'}")
    print(f"  Expected: {expected4}")
    print(f"  Actual:   {actual4}")
    
    print("\n✓ Incremental Checksum test complete!")


if __name__ == '__main__':
    test_incremental_checksum()