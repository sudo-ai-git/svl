"""Ring-buffer-based test vector storage.

Stores test cases, results, and metadata in optical ring buffers
for deterministic, bounded memory with FIFO eviction semantics.
"""
from __future__ import annotations
import numpy as np
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import datetime
import json
import hashlib


@dataclass
class TestVector:
    """A stored test vector with metadata."""
    id: str
    target: str
    inputs_hash: str
    expected: Any
    result: Any = None
    passed: bool = False
    timestamp: str = ""
    oracle_method: str = ""
    confidence: float = 0.0
    tags: List[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat()

    def fingerprint(self) -> str:
        """Create a unique fingerprint for deduplication."""
        content = f"{self.target}:{self.inputs_hash}:{self.expected}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "target": self.target,
            "inputs_hash": self.inputs_hash,
            "expected": str(self.expected)[:200],
            "result": str(self.result)[:200] if self.result else None,
            "passed": self.passed,
            "timestamp": self.timestamp,
            "oracle_method": self.oracle_method,
            "confidence": self.confidence,
            "tags": self.tags,
        }


class RingVectorStore:
    """Optical ring-buffer for test vectors — bounded, deterministic storage."""

    def __init__(self, capacity: int = 1024):
        self.capacity = capacity
        self._buf: List[Optional[TestVector]] = [None] * capacity
        self._head = 0
        self._tail = 0
        self._count = 0
        self._fingerprint_index: Dict[str, str] = {}  # fingerprint → test_id

    def store(self, vector: TestVector) -> bool:
        """Store a test vector in the ring buffer."""
        fp = vector.fingerprint()

        # Deduplication: if fingerprint exists, update instead of adding
        if fp in self._fingerprint_index:
            existing_id = self._fingerprint_index[fp]
            self.update(vector, existing_id)
            return True

        self._buf[self._head] = vector
        self._fingerprint_index[fp] = vector.id
        self._head = (self._head + 1) % self.capacity

        if self._count < self.capacity:
            self._count += 1
        else:
            # Evict oldest — remove from fingerprint index
            evicted = self._buf[self._tail]
            if evicted:
                evicted_fp = evicted.fingerprint()
                self._fingerprint_index.pop(evicted_fp, None)
            self._tail = (self._tail + 1) % self.capacity

        return True

    def update(self, vector: TestVector, test_id: str) -> bool:
        """Update an existing test vector by ID."""
        for i in range(self._count):
            idx = (self._tail + i) % self.capacity
            if self._buf[idx] and self._buf[idx].id == test_id:
                self._buf[idx] = vector
                return True
        return False

    def get(self, test_id: str) -> Optional[TestVector]:
        """Retrieve a test vector by ID."""
        for i in range(self._count):
            idx = (self._tail + i) % self.capacity
            if self._buf[idx] and self._buf[idx].id == test_id:
                return self._buf[idx]
        return None

    def get_by_target(self, target: str) -> List[TestVector]:
        """Get all vectors for a specific target."""
        results = []
        for i in range(self._count):
            idx = (self._tail + i) % self.capacity
            if self._buf[idx] and self._buf[idx].target == target:
                results.append(self._buf[idx])
        return results

    def get_passing(self) -> List[TestVector]:
        """Get all passing test vectors."""
        results: List[TestVector] = []
        for i in range(self._count):
            idx = (self._tail + i) % self.capacity
            v = self._buf[idx]
            if v is not None and v.passed:
                results.append(v)
        return results

    def get_failing(self) -> List[TestVector]:
        """Get all failing test vectors."""
        results: List[TestVector] = []
        for i in range(self._count):
            idx = (self._tail + i) % self.capacity
            v = self._buf[idx]
            if v is not None and not v.passed:
                results.append(v)
        return results

    @property
    def vectors(self) -> List[TestVector]:
        """Return all stored vectors in order."""
        results: List[TestVector] = []
        for i in range(self._count):
            idx = (self._tail + i) % self.capacity
            v = self._buf[idx]
            if v is not None:
                results.append(v)
        return results

    @property
    def size(self) -> int:
        return self._count

    @property
    def is_full(self) -> bool:
        return self._count >= self.capacity

    def stats(self) -> Dict[str, Any]:
        """Return storage statistics."""
        passing = len(self.get_passing())
        failing = len(self.get_failing())
        return {
            "capacity": self.capacity,
            "stored": self._count,
            "passing": passing,
            "failing": failing,
            "pass_rate": passing / max(self._count, 1),
            "full": self.is_full,
            "fingerprint_index_size": len(self._fingerprint_index),
        }

    def to_json(self) -> str:
        """Serialize all vectors to JSON."""
        return json.dumps([v.to_dict() for v in self.vectors], indent=2)

    def clear(self) -> None:
        """Clear all vectors."""
        self._buf = [None] * self.capacity
        self._head = 0
        self._tail = 0
        self._count = 0
        self._fingerprint_index.clear()


class TestVectorBank:
    """Multiple ring buffer banks for organized test storage."""

    def __init__(self, banks: int = 4, bank_size: int = 256):
        self.banks = [RingVectorStore(capacity=bank_size) for _ in range(banks)]
        self._bank_names = [f"bank_{i}" for i in range(banks)]

    def store(self, vector: TestVector, bank: int = 0) -> bool:
        """Store in a specific bank."""
        if 0 <= bank < len(self.banks):
            return self.banks[bank].store(vector)
        # Default to round-robin by target hash
        bank = hash(vector.target) % len(self.banks)
        return self.banks[bank].store(vector)

    def get_all_passing(self) -> List[TestVector]:
        """Get all passing vectors across all banks."""
        results = []
        for bank in self.banks:
            results.extend(bank.get_passing())
        return results

    def get_all_failing(self) -> List[TestVector]:
        """Get all failing vectors across all banks."""
        results = []
        for bank in self.banks:
            results.extend(bank.get_failing())
        return results

    def stats(self) -> Dict[str, Any]:
        """Return combined statistics."""
        return {
            f"bank_{i}": bank.stats() for i, bank in enumerate(self.banks)
        }
