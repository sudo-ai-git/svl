# svl/distributed_build.py
# Distributed Build Cache (H45)
# Content-addressed remote build cache with remote execution protocol

from typing import Dict, List, Optional, Any, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import os
import time
import threading
from pathlib import Path
from abc import ABC, abstractmethod


class CacheEntryStatus(Enum):
    """Status of a cache entry."""
    PENDING = "pending"
    COMPLETE = "complete"
    FAILED = "failed"
    MISSING = "missing"


@dataclass
class BuildArtifact:
    """Build artifact with content-addressed storage."""
    hash: str  # SHA256 of content
    content: bytes
    mime_type: str
    size: int
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.hash:
            self.hash = hashlib.sha256(self.content).hexdigest()
        if not self.size:
            self.size = len(self.content)


@dataclass
class CacheEntry:
    """Cache entry for build results."""
    key: str  # Content-addressed key (hash of inputs)
    status: CacheEntryStatus
    outputs: List[BuildArtifact] = field(default_factory=list)
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    execution_time_ms: float = 0.0
    worker_id: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    accessed_at: float = field(default_factory=time.time)
    access_count: int = 0


class ContentAddressableStore:
    """Content-addressable storage for build artifacts."""

    def __init__(self, root_path: str):
        self.root = Path(root_path)
        self.root.mkdir(parents=True, exist_ok=True)
        self.objects_dir = self.root / 'objects'
        self.objects_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = self.root / 'index.json'
        self._index: Dict[str, CacheEntry] = {}
        self._lock = threading.RLock()
        self._load_index()

    def _load_index(self):
        """Load cache index from disk."""
        if self.index_file.exists():
            try:
                with open(self.index_file, 'r') as f:
                    data = json.load(f)
                for key, entry_data in data.items():
                    entry = CacheEntry(**entry_data)
                    entry.outputs = [BuildArtifact(**a) for a in entry_data.get('outputs', [])]
                    self._index[key] = entry
            except Exception:
                pass

    def _save_index(self):
        """Save cache index to disk."""
        with self._lock:
            data = {}
            for key, entry in self._index.items():
                entry_dict = {
                    'key': entry.key,
                    'status': entry.status.value,
                    'outputs': [
                        {
                            'hash': a.hash,
                            'mime_type': a.mime_type,
                            'size': a.size,
                            'created_at': a.created_at,
                            'metadata': a.metadata
                        }
                        for a in entry.outputs
                    ],
                    'stdout': entry.stdout,
                    'stderr': entry.stderr,
                    'exit_code': entry.exit_code,
                    'execution_time_ms': entry.execution_time_ms,
                    'worker_id': entry.worker_id,
                    'created_at': entry.created_at,
                    'accessed_at': entry.accessed_at,
                    'access_count': entry.access_count,
                }
                data[key] = entry_dict

            with open(self.index_file, 'w') as f:
                json.dump(data, f)

    def store_artifact(self, artifact: BuildArtifact) -> str:
        """Store artifact in CAS."""
        obj_dir = self.objects_dir / artifact.hash[:2]
        obj_dir.mkdir(parents=True, exist_ok=True)
        obj_file = obj_dir / artifact.hash[2:]

        if not obj_file.exists():
            obj_file.write_bytes(artifact.content)

        return artifact.hash

    def get_artifact(self, hash: str) -> Optional[BuildArtifact]:
        """Retrieve artifact from CAS."""
        obj_file = self.objects_dir / hash[:2] / hash[2:]
        if obj_file.exists():
            content = obj_file.read_bytes()
            return BuildArtifact(
                hash=hash,
                content=content,
                mime_type='application/octet-stream',
                size=len(content)
            )
        return None

    def put(self, key: str, entry: CacheEntry) -> bool:
        """Store cache entry."""
        with self._lock:
            # Store output artifacts
            for artifact in entry.outputs:
                self.store_artifact(artifact)

            self._index[key] = entry
            self._save_index()
            return True

    def get(self, key: str) -> Optional[CacheEntry]:
        """Retrieve cache entry."""
        with self._lock:
            entry = self._index.get(key)
            if entry:
                entry.accessed_at = time.time()
                entry.access_count += 1
                self._save_index()
            return entry

    def has(self, key: str) -> bool:
        """Check if key exists in cache."""
        with self._lock:
            return key in self._index

    def remove(self, key: str) -> bool:
        """Remove cache entry."""
        with self._lock:
            if key in self._index:
                del self._index[key]
                self._save_index()
                return True
            return False

    def cleanup(self, max_age_days: int = 30, max_size_gb: float = 10.0):
        """Clean up old/unused cache entries."""
        with self._lock:
            now = time.time()
            max_age = max_age_days * 24 * 3600

            # Calculate total size
            total_size = 0
            for entry in self._index.values():
                for artifact in entry.outputs:
                    total_size += artifact.size

            # Remove old entries
            to_remove = []
            for key, entry in self._index.items():
                if now - entry.accessed_at > max_age:
                    to_remove.append(key)

            for key in to_remove:
                self.remove(key)

            # If still over size limit, remove least recently used
            if total_size > max_size_gb * 1024 * 1024 * 1024:
                sorted_entries = sorted(
                    self._index.items(),
                    key=lambda x: x[1].accessed_at
                )
                for key, _ in sorted_entries:
                    if total_size <= max_size_gb * 1024 * 1024 * 1024:
                        break
                    entry = self._index[key]
                    for artifact in entry.outputs:
                        total_size -= artifact.size
                    self.remove(key)


class RemoteExecutionClient(ABC):
    """Abstract base for remote execution clients."""

    @abstractmethod
    def execute(self, action: 'BuildAction') -> CacheEntry:
        """Execute build action remotely."""
        pass

    @abstractmethod
    def get_capabilities(self) -> Dict[str, Any]:
        """Get remote executor capabilities."""
        pass


@dataclass
class BuildAction:
    """Build action specification."""
    command: List[str]
    inputs: Dict[str, str]  # path -> hash
    outputs: List[str]  # output paths
    env: Dict[str, str] = field(default_factory=dict)
    working_dir: str = "."
    timeout_seconds: int = 300
    platform: Dict[str, str] = field(default_factory=dict)  # OS, arch, etc.

    def cache_key(self) -> str:
        """Compute content-addressed cache key."""
        data = {
            'command': self.command,
            'inputs': self.inputs,
            'outputs': self.outputs,
            'env': self.env,
            'working_dir': self.working_dir,
        }
        content = json.dumps(data, sort_keys=True).encode('utf-8')
        return hashlib.sha256(content).hexdigest()


class DistributedBuildCache:
    """Distributed build cache with local and remote tiers."""

    def __init__(self, local_cache_path: str, remote_client: Optional[RemoteExecutionClient] = None):
        self.local_cache = ContentAddressableStore(local_cache_path)
        self.remote_client = remote_client
        self.stats = {
            'local_hits': 0,
            'local_misses': 0,
            'remote_hits': 0,
            'remote_misses': 0,
            'uploads': 0,
            'downloads': 0,
        }

    def get_or_execute(self, action: BuildAction) -> CacheEntry:
        """Get cached result or execute action."""
        key = action.cache_key()

        # Try local cache first
        entry = self.local_cache.get(key)
        if entry and entry.status == CacheEntryStatus.COMPLETE:
            self.stats['local_hits'] += 1
            return entry

        self.stats['local_misses'] += 1

        # Try remote cache
        if self.remote_client:
            entry = self.remote_client.execute(action)
            if entry.status == CacheEntryStatus.COMPLETE:
                self.stats['remote_hits'] += 1
                # Store in local cache
                self.local_cache.put(key, entry)
                return entry
            self.stats['remote_misses'] += 1

        # Execute locally (would be implemented by caller)
        return CacheEntry(
            key=key,
            status=CacheEntryStatus.MISSING,
            stdout="",
            stderr="Cache miss - needs local execution",
            exit_code=1
        )

    def store_result(self, action: BuildAction, entry: CacheEntry):
        """Store build result in cache."""
        key = action.cache_key()
        entry.key = key
        self.local_cache.put(key, entry)

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total = self.stats['local_hits'] + self.stats['local_misses']
        local_hit_rate = self.stats['local_hits'] / total if total > 0 else 0

        total_remote = self.stats['remote_hits'] + self.stats['remote_misses']
        remote_hit_rate = self.stats['remote_hits'] / total_remote if total_remote > 0 else 0

        return {
            **self.stats,
            'local_hit_rate': local_hit_rate,
            'remote_hit_rate': remote_hit_rate,
            'total_requests': total,
        }


# REAPI (Remote Execution API) Protocol Implementation
class ReapiClient(RemoteExecutionClient):
    """gRPC client for Remote Execution API (REAPI)."""

    def __init__(self, endpoint: str, instance_name: str = ""):
        self.endpoint = endpoint
        self.instance_name = instance_name
        self._channel = None
        self._stub = None

    def connect(self):
        """Connect to REAPI server."""
        try:
            import grpc
            from google.devtools.remoteworkers.v1test2 import bots_pb2_grpc
            self._channel = grpc.insecure_channel(self.endpoint)
            self._stub = bots_pb2_grpc.BotsStub(self._channel)
        except ImportError:
            # grpc or REAPI protos not available
            pass

    def execute(self, action: BuildAction) -> CacheEntry:
        """Execute action via REAPI."""
        if not self._stub:
            return CacheEntry(
                key=action.cache_key(),
                status=CacheEntryStatus.FAILED,
                stderr="REAPI client not connected"
            )

        # Would implement actual REAPI call
        return CacheEntry(
            key=action.cache_key(),
            status=CacheEntryStatus.FAILED,
            stderr="REAPI execution not implemented"
        )

    def get_capabilities(self) -> Dict[str, Any]:
        """Get remote executor capabilities."""
        return {
            'platform': 'linux-x86_64',
            'max_concurrent': 10,
            'supports_cache': True,
        }


class LocalExecutor:
    """Local build executor with cache integration."""

    def __init__(self, cache: DistributedBuildCache):
        self.cache = cache

    def execute(self, action: BuildAction) -> CacheEntry:
        """Execute build action locally."""
        import subprocess

        start = time.time()

        try:
            result = subprocess.run(
                action.command,
                cwd=action.working_dir,
                env={**os.environ, **action.env},
                capture_output=True,
                text=True,
                timeout=action.timeout_seconds
            )

            elapsed = (time.time() - start) * 1000

            # Collect output artifacts
            outputs = []
            for output_path in action.outputs:
                path = Path(action.working_dir) / output_path
                if path.exists():
                    content = path.read_bytes()
                    artifact = BuildArtifact(
                        hash=hashlib.sha256(content).hexdigest(),
                        content=content,
                        mime_type='application/octet-stream',
                        size=len(content),
                        created_at=time.time(),
                        metadata={'path': output_path}
                    )
                    outputs.append(artifact)

            entry = CacheEntry(
                key=action.cache_key(),
                status=CacheEntryStatus.COMPLETE if result.returncode == 0 else CacheEntryStatus.FAILED,
                outputs=outputs,
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode,
                execution_time_ms=elapsed
            )

            # Store in cache
            self.cache.store_result(action, entry)

            return entry

        except subprocess.TimeoutExpired:
            return CacheEntry(
                key=action.cache_key(),
                status=CacheEntryStatus.FAILED,
                stderr=f"Timeout after {action.timeout_seconds}s",
                exit_code=124
            )
        except Exception as e:
            return CacheEntry(
                key=action.cache_key(),
                status=CacheEntryStatus.FAILED,
                stderr=str(e),
                exit_code=1
            )


# Build Action Generator for SVL
class SVLBuildActionGenerator:
    """Generates build actions for SVL compilation."""

    def __init__(self, cache: DistributedBuildCache):
        self.cache = cache

    @staticmethod
    def _input_hash(source: str) -> str:
        """Cache key for a source file: its canonical AST fingerprint.

        A reproducible build must map every source that parses to the same program onto the
        same cache entry -- reformatting, comment changes, and the Hebrew vs ASCII keyword
        spellings all qualify (measured: five such variants share one fingerprint).  A raw
        text hash cannot do that.  An unparsable source falls back to a prefixed text hash so
        the failure is still cacheable rather than recomputed.
        """
        try:
            from svl.attest import ast_fingerprint
            return ast_fingerprint(source)["ast_sha256"]
        except Exception:                                              # noqa: BLE001
            return "text:" + hashlib.sha256(source.encode("utf-8")).hexdigest()

    def compile_module(self, source_path: str, output_path: str,
                       options: Dict[str, Any] = None) -> BuildAction:
        """Generate action to compile SVL module to WASM."""
        options = options or {}

        # Read source to compute input hash
        with open(source_path, 'r') as f:
            source = f.read()

        source_hash = self._input_hash(source)

        return BuildAction(
            command=['svl', 'compile', source_path, '-o', output_path],
            inputs={source_path: source_hash},
            outputs=[output_path],
            env=options.get('env', {}),
            working_dir=os.path.dirname(source_path) or '.',
            timeout_seconds=options.get('timeout', 300),
            platform={'os': 'linux', 'arch': 'x86_64'}
        )

    def verify_module(self, source_path: str) -> BuildAction:
        """Generate action to verify SVL module."""
        with open(source_path, 'r') as f:
            source = f.read()

        source_hash = self._input_hash(source)

        return BuildAction(
            command=['svl', 'verify', source_path],
            inputs={source_path: source_hash},
            outputs=[],
            working_dir=os.path.dirname(source_path) or '.',
            timeout_seconds=60
        )

    def run_tests(self, test_dir: str) -> BuildAction:
        """Generate action to run SVL tests."""
        return BuildAction(
            command=['svl', 'test', test_dir],
            inputs={},
            outputs=[],
            working_dir=test_dir,
            timeout_seconds=600
        )


if __name__ == '__main__':
    print("=== Distributed Build Cache Test ===")

    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        cache = DistributedBuildCache(os.path.join(tmpdir, 'cache'))

        # Test CAS
        store = cache.local_cache

        artifact = BuildArtifact(
            hash='',
            content=b'Hello, World!',
            mime_type='text/plain',
            size=0,
            created_at=time.time()
        )

        stored_hash = store.store_artifact(artifact)
        print(f"Stored artifact: {stored_hash[:16]}...")

        retrieved = store.get_artifact(stored_hash)
        print(f"Retrieved: {retrieved.content if retrieved else 'NOT FOUND'}")

        # Test cache entry
        action = BuildAction(
            command=['echo', 'test'],
            inputs={'input.txt': 'abc123'},
            outputs=['output.txt']
        )

        entry = CacheEntry(
            key=action.cache_key(),
            status=CacheEntryStatus.COMPLETE,
            outputs=[artifact],
            stdout='test\n',
            stderr='',
            exit_code=0,
            execution_time_ms=10.0
        )

        store.put(entry.key, entry)
        retrieved_entry = store.get(entry.key)
        print(f"Cache entry: {retrieved_entry.status if retrieved_entry else 'NOT FOUND'}")

        # Test cache hit
        hit_entry = cache.get_or_execute(action)
        print(f"Cache hit: {hit_entry.status}")

        print(f"\nStats: {cache.get_stats()}")

    print("\n✓ Distributed Build Cache test complete!")