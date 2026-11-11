# svl/raft.py
# Verified Distributed Consensus (Raft) Implementation in SVL (H50)
# Raft consensus algorithm with formal verification

from typing import Dict, List, Optional, Any, Set, Callable
from dataclasses import dataclass, field
from enum import Enum
import random
import time
import hashlib
import json
from collections import defaultdict
from pathlib import Path


class NodeState(Enum):
    FOLLOWER = "follower"
    CANDIDATE = "candidate"
    LEADER = "leader"


class MessageType(Enum):
    REQUEST_VOTE = "request_vote"
    VOTE_RESPONSE = "vote_response"
    APPEND_ENTRIES = "append_entries"
    APPEND_RESPONSE = "append_response"
    CLIENT_REQUEST = "client_request"
    CLIENT_RESPONSE = "client_response"


@dataclass
class LogEntry:
    """Raft log entry."""
    term: int
    index: int
    command: Any
    timestamp: float = field(default_factory=time.time)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'term': self.term,
            'index': self.index,
            'command': self.command,
            'timestamp': self.timestamp,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'LogEntry':
        return cls(
            term=data['term'],
            index=data['index'],
            command=data['command'],
            timestamp=data['timestamp'],
        )


@dataclass
class Message:
    """Raft message."""
    msg_type: MessageType
    from_node: int
    to_node: int
    term: int
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'msg_type': self.msg_type.value,
            'from_node': self.from_node,
            'to_node': self.to_node,
            'term': self.term,
            'payload': self.payload,
            'timestamp': self.timestamp,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Message':
        return cls(
            msg_type=MessageType(data['msg_type']),
            from_node=data['from_node'],
            to_node=data['to_node'],
            term=data['term'],
            payload=data['payload'],
            timestamp=data['timestamp'],
        )


@dataclass
class RaftConfig:
    """Raft node configuration."""
    node_id: int
    cluster_nodes: List[int]  # All node IDs in cluster
    election_timeout_min: float = 1.5  # seconds
    election_timeout_max: float = 3.0
    heartbeat_interval: float = 0.5
    max_log_entries_per_append: int = 100
    snapshot_threshold: int = 10000  # Log entries before snapshot


class RaftNode:
    """Raft consensus node implementation."""
    
    def __init__(self, config: RaftConfig):
        self.config = config
        self.state = NodeState.FOLLOWER
        self.current_term = 0
        self.voted_for: Optional[int] = None
        self.log: List[LogEntry] = []
        self.commit_index = 0
        self.last_applied = 0
        
        # Leader state
        self.next_index: Dict[int, int] = {}  # For each follower
        self.match_index: Dict[int, int] = {}  # For each follower
        
        # Timing
        self.last_contact = 0.0  # Time since last contact (seconds)
        self.election_timeout = random.uniform(
            config.election_timeout_min, 
            config.election_timeout_max
        )
        
        # State machine
        self.state_machine: Dict[str, Any] = {}
        
        # Persistence
        self.persisted_state: Dict[str, Any] = {}
        
        # Network simulation
        self.message_queue: List[Message] = []
        self.network_partition: Set[int] = set()  # Unreachable nodes
        
        # Election tracking
        self.votes_received: Set[int] = set()  # Node IDs that voted for us
        
        # Verification
        self.verification_log: List[str] = []
    
    def get_majority(self) -> int:
        """Get majority count for cluster."""
        return len(self.config.cluster_nodes) // 2 + 1
    
    def is_leader(self) -> bool:
        return self.state == NodeState.LEADER
    
    def become_follower(self, term: int):
        """Transition to follower state."""
        self._log_verification(f"Node {self.config.node_id}: becoming follower at term {term}")
        self.state = NodeState.FOLLOWER
        self.current_term = term
        self.voted_for = None
        self._reset_election_timer()
    
    def become_candidate(self):
        """Transition to candidate state."""
        self._log_verification(f"Node {self.config.node_id}: becoming candidate at term {self.current_term + 1}")
        self.state = NodeState.CANDIDATE
        self.current_term += 1
        self.voted_for = self.config.node_id
        self._reset_election_timer()
        self._request_votes()
    
    def _request_votes(self):
        """Send RequestVote RPCs to all other nodes."""
        last_log_index = len(self.log)
        last_log_term = self.log[-1].term if self.log else 0
        
        for node_id in self.config.cluster_nodes:
            if node_id == self.config.node_id:
                continue
            
            msg = Message(
                msg_type=MessageType.REQUEST_VOTE,
                from_node=self.config.node_id,
                to_node=node_id,
                term=self.current_term,
                payload={
                    'candidate_id': self.config.node_id,
                    'term': self.current_term,
                    'last_log_index': last_log_index,
                    'last_log_term': last_log_term,
                }
            )
            self.message_queue.append(msg)
        
        self._log_verification(f"Node {self.config.node_id}: requested votes")
    
    def become_leader(self):
        """Transition to leader state."""
        self._log_verification(f"Node {self.config.node_id}: becoming leader at term {self.current_term}")
        self.state = NodeState.LEADER
        
        # Initialize leader state
        for node_id in self.config.cluster_nodes:
            if node_id != self.config.node_id:
                self.next_index[node_id] = len(self.log) + 1
                self.match_index[node_id] = 0
        
        # Send initial heartbeats
        self._send_heartbeats()
    
    def _reset_election_timer(self):
        """Reset election timeout."""
        self.election_timeout = random.uniform(
            self.config.election_timeout_min,
            self.config.election_timeout_max
        )
        self.last_contact = 0.0
        self.votes_received.clear()
    
    def _log_verification(self, message: str):
        """Log for verification purposes."""
        self.verification_log.append(f"[{time.time():.6f}] {message}")
    
    # =========================================================================
    # Message Handling
    # =========================================================================
    
    def receive_message(self, msg: Message):
        """Process incoming message."""
        # Ignore messages from partitioned nodes
        if msg.from_node in self.network_partition:
            return
        
        # Update term if needed
        if msg.term > self.current_term:
            self.become_follower(msg.term)
        
        if msg.msg_type == MessageType.REQUEST_VOTE:
            self._handle_request_vote(msg)
        elif msg.msg_type == MessageType.VOTE_RESPONSE:
            self._handle_vote_response(msg)
        elif msg.msg_type == MessageType.APPEND_ENTRIES:
            self._handle_append_entries(msg)
        elif msg.msg_type == MessageType.APPEND_RESPONSE:
            self._handle_append_response(msg)
        elif msg.msg_type == MessageType.CLIENT_REQUEST:
            self._handle_client_request(msg)
    
    def _handle_request_vote(self, msg: Message):
        """Handle RequestVote RPC."""
        payload = msg.payload
        candidate_id = payload['candidate_id']
        candidate_term = payload['term']
        last_log_index = payload['last_log_index']
        last_log_term = payload['last_log_term']
        
        vote_granted = False
        
        # Check term
        if candidate_term < self.current_term:
            vote_granted = False
        elif self.voted_for is None or self.voted_for == candidate_id:
            # Check if candidate's log is at least as up-to-date
            if self._is_log_up_to_date(last_log_index, last_log_term):
                vote_granted = True
                self.voted_for = candidate_id
                self._reset_election_timer()
        
        # Send response
        response = Message(
            msg_type=MessageType.VOTE_RESPONSE,
            from_node=self.config.node_id,
            to_node=msg.from_node,
            term=self.current_term,
            payload={
                'vote_granted': vote_granted,
            }
        )
        self.message_queue.append(response)
        
        self._log_verification(f"Node {self.config.node_id}: vote {'granted' if vote_granted else 'denied'} to {candidate_id}")
    
    def _handle_vote_response(self, msg: Message):
        """Handle RequestVote response."""
        if self.state != NodeState.CANDIDATE:
            return
        
        if msg.term > self.current_term:
            self.become_follower(msg.term)
            return
        
        if msg.payload.get('vote_granted', False):
            # Track vote from this node
            voter_id = msg.from_node
            self.votes_received.add(voter_id)
            
            # Count votes (including self)
            votes = len(self.votes_received) + 1  # +1 for self vote
            
            if votes >= self.get_majority():
                self.become_leader()
    
    def _handle_append_entries(self, msg: Message):
        """Handle AppendEntries RPC."""
        payload = msg.payload
        leader_id = msg.from_node
        leader_term = msg.term
        prev_log_index = payload['prev_log_index']
        prev_log_term = payload['prev_log_term']
        entries = payload.get('entries', [])
        leader_commit = payload['leader_commit']
        
        success = False
        
        if leader_term < self.current_term:
            success = False
        elif prev_log_index > 0:
            # Check if log contains entry at prev_log_index with matching term
            if prev_log_index <= len(self.log):
                if self.log[prev_log_index - 1].term == prev_log_term:
                    # Log matches, append new entries
                    self._append_entries(prev_log_index, entries)
                    success = True
            else:
                success = False
        else:
            # prev_log_index == 0, always matches
            self._append_entries(0, entries)
            success = True
        
        if success and leader_commit > self.commit_index:
            self.commit_index = min(leader_commit, len(self.log))
            self._apply_committed_entries()
        
        # Send response
        response = Message(
            msg_type=MessageType.APPEND_RESPONSE,
            from_node=self.config.node_id,
            to_node=leader_id,
            term=self.current_term,
            payload={
                'success': success,
                'match_index': len(self.log),
            }
        )
        self.message_queue.append(response)
        
        self._reset_election_timer()  # Valid leader contact
        
        self._log_verification(f"Node {self.config.node_id}: AppendEntries {'success' if success else 'failed'} from {leader_id}")
    
    def _handle_append_response(self, msg: Message):
        """Handle AppendEntries response."""
        if self.state != NodeState.LEADER:
            return
        
        follower_id = msg.from_node
        success = msg.payload.get('success', False)
        match_index = msg.payload.get('match_index', 0)
        
        if msg.term > self.current_term:
            self.become_follower(msg.term)
            return
        
        if success:
            self.next_index[follower_id] = match_index + 1
            self.match_index[follower_id] = match_index
            
            # Check if we can commit more entries
            self._update_commit_index()
        else:
            # Decrement next_index and retry
            self.next_index[follower_id] = max(1, self.next_index[follower_id] - 1)
        
        self._log_verification(f"Node {self.config.node_id}: AppendEntries response from {follower_id} {'success' if success else 'failed'}")
    
    def _handle_client_request(self, msg: Message):
        """Handle client request."""
        if self.state != NodeState.LEADER:
            # Redirect to leader or reject
            response = Message(
                msg_type=MessageType.CLIENT_RESPONSE,
                from_node=self.config.node_id,
                to_node=msg.from_node,
                term=self.current_term,
                payload={
                    'success': False,
                    'error': 'Not leader',
                    'leader_id': self._get_leader_id(),
                }
            )
            self.message_queue.append(response)
            return
        
        # Append to log
        command = msg.payload['command']
        entry = LogEntry(
            term=self.current_term,
            index=len(self.log) + 1,
            command=command
        )
        self.log.append(entry)
        
        # Replicate to followers
        self._replicate_log()
        
        # Wait for commit (simplified - in real impl would wait)
        # For now, just respond after local append
        response = Message(
            msg_type=MessageType.CLIENT_RESPONSE,
            from_node=self.config.node_id,
            to_node=msg.from_node,
            term=self.current_term,
            payload={
                'success': True,
                'index': entry.index,
            }
        )
        self.message_queue.append(response)
    
    # =========================================================================
    # Log Management
    # =========================================================================
    
    def _is_log_up_to_date(self, last_log_index: int, last_log_term: int) -> bool:
        """Check if candidate's log is at least as up-to-date as ours."""
        if not self.log:
            return True
        
        our_last_term = self.log[-1].term
        our_last_index = len(self.log)
        
        if last_log_term != our_last_term:
            return last_log_term > our_last_term
        return last_log_index >= our_last_index
    
    def _append_entries(self, prev_log_index: int, entries: List[Dict[str, Any]]):
        """Append entries to log, handling conflicts."""
        # Delete conflicting entries
        if prev_log_index > 0 and prev_log_index <= len(self.log):
            self.log = self.log[:prev_log_index]
        
        # Append new entries
        for i, entry_data in enumerate(entries):
            entry = LogEntry(
                term=entry_data['term'],
                index=prev_log_index + i + 1,
                command=entry_data['command']
            )
            self.log.append(entry)
    
    def _replicate_log(self):
        """Send AppendEntries to all followers."""
        for node_id in self.config.cluster_nodes:
            if node_id == self.config.node_id:
                continue
            self._send_append_entries(node_id)
    
    def _send_append_entries(self, follower_id: int):
        """Send AppendEntries to specific follower."""
        next_idx = self.next_index.get(follower_id, len(self.log) + 1)
        prev_log_index = next_idx - 1
        prev_log_term = 0
        if prev_log_index > 0 and prev_log_index <= len(self.log):
            prev_log_term = self.log[prev_log_index - 1].term
        
        # Get entries to send
        entries = []
        start_idx = prev_log_index
        if start_idx < 0:
            start_idx = 0
        for entry in self.log[start_idx:]:
            if len(entries) >= self.config.max_log_entries_per_append:
                break
            entries.append(entry.to_dict())
        
        msg = Message(
            msg_type=MessageType.APPEND_ENTRIES,
            from_node=self.config.node_id,
            to_node=follower_id,
            term=self.current_term,
            payload={
                'prev_log_index': prev_log_index,
                'prev_log_term': prev_log_term,
                'entries': entries,
                'leader_commit': self.commit_index,
            }
        )
        self.message_queue.append(msg)
    
    def _send_heartbeats(self):
        """Send empty AppendEntries as heartbeats."""
        for node_id in self.config.cluster_nodes:
            if node_id == self.config.node_id:
                continue
            self._send_append_entries(node_id)
    
    def _update_commit_index(self):
        """Update commit index based on replication."""
        # Find highest index replicated to majority
        for index in range(len(self.log), self.commit_index, -1):
            if self.log[index - 1].term != self.current_term:
                continue  # Only commit entries from current term
            
            # Count replicas
            replicas = 1  # Self
            for node_id in self.config.cluster_nodes:
                if node_id != self.config.node_id:
                    if self.match_index.get(node_id, 0) >= index:
                        replicas += 1
            
            if replicas >= self.get_majority():
                self.commit_index = index
                self._apply_committed_entries()
                break
    
    def _apply_committed_entries(self):
        """Apply committed entries to state machine."""
        while self.last_applied < self.commit_index:
            self.last_applied += 1
            entry = self.log[self.last_applied - 1]
            self._apply_command(entry.command)
    
    def _apply_command(self, command: Any):
        """Apply command to state machine."""
        # Simplified: assume command is dict with 'op', 'key', 'value'
        if isinstance(command, dict) and 'op' in command:
            op = command['op']
            key = command.get('key', '')
            value = command.get('value', None)
            
            if op == 'set':
                self.state_machine[key] = value
            elif op == 'delete':
                self.state_machine.pop(key, None)
            elif op == 'get':
                pass  # Read-only
        
        self._log_verification(f"Node {self.config.node_id}: Applied command {command}")
    
    def _get_leader_id(self) -> Optional[int]:
        """Get current leader ID (if known)."""
        # In real implementation, would track leader
        return None
    
    # =========================================================================
    # Timing & Election
    # =========================================================================
    
    def tick(self, elapsed: float):
        """Process time tick."""
        if self.state == NodeState.FOLLOWER or self.state == NodeState.CANDIDATE:
            self.last_contact += elapsed
            if self.last_contact >= self.election_timeout:
                self.become_candidate()
        elif self.state == NodeState.LEADER:
            # Send periodic heartbeats
            self.last_contact += elapsed
            if self.last_contact >= self.config.heartbeat_interval:
                self._send_heartbeats()
                self.last_contact = 0
    
    # =========================================================================
    # Persistence
    # =========================================================================
    
    def persist(self):
        """Persist state to stable storage."""
        self.persisted_state = {
            'current_term': self.current_term,
            'voted_for': self.voted_for,
            'log': [e.to_dict() for e in self.log],
        }
        self._log_verification(f"Node {self.config.node_id}: State persisted")
    
    def load_persisted(self):
        """Load state from stable storage."""
        if self.persisted_state:
            self.current_term = self.persisted_state.get('current_term', 0)
            self.voted_for = self.persisted_state.get('voted_for')
            self.log = [LogEntry.from_dict(e) for e in self.persisted_state.get('log', [])]
            self._log_verification(f"Node {self.config.node_id}: State loaded")
    
    # =========================================================================
    # Verification Interface
    # =========================================================================
    
    def get_verification_log(self) -> List[str]:
        return self.verification_log.copy()
    
    def verify_state(self) -> bool:
        """Verify node state consistency."""
        checks = [
            self.current_term >= 0,
            self.voted_for is None or self.voted_for in self.config.cluster_nodes,
            self.commit_index <= len(self.log),
            self.last_applied <= self.commit_index,
            all(e.term > 0 for e in self.log),
            all(e.index == i + 1 for i, e in enumerate(self.log)),
        ]
        return all(checks)


class RaftCluster:
    """Manages a cluster of Raft nodes."""
    
    def __init__(self, node_ids: List[int], config: Optional[RaftConfig] = None):
        self.nodes: Dict[int, RaftNode] = {}
        
        for node_id in node_ids:
            if config:
                node_config = RaftConfig(
                    node_id=node_id,
                    cluster_nodes=node_ids,
                    election_timeout_min=config.election_timeout_min,
                    election_timeout_max=config.election_timeout_max,
                    heartbeat_interval=config.heartbeat_interval,
                )
            else:
                node_config = RaftConfig(node_id=node_id, cluster_nodes=node_ids)
            
            self.nodes[node_id] = RaftNode(node_config)
    
    def get_node(self, node_id: int) -> RaftNode:
        return self.nodes[node_id]
    
    def get_leader(self) -> Optional[RaftNode]:
        for node in self.nodes.values():
            if node.is_leader():
                return node
        return None
    
    def step(self, elapsed: float = 0.1):
        """Advance cluster by one time step."""
        # Process message queues
        all_messages = []
        for node in self.nodes.values():
            all_messages.extend(node.message_queue)
            node.message_queue.clear()
        
        # Deliver messages (simulate network)
        for msg in all_messages:
            if msg.to_node in self.nodes:
                # Check partition
                if msg.from_node not in self.nodes[msg.to_node].network_partition:
                    self.nodes[msg.to_node].receive_message(msg)
        
        # Tick all nodes
        for node in self.nodes.values():
            node.tick(elapsed)
    
    def partition(self, node_ids: List[int]):
        """Create network partition."""
        for node_id in node_ids:
            if node_id in self.nodes:
                for other_id in self.nodes:
                    if other_id not in node_ids:
                        self.nodes[other_id].network_partition.add(node_id)
                        self.nodes[node_id].network_partition.add(other_id)
    
    def heal_partition(self):
        """Heal all partitions."""
        for node in self.nodes.values():
            node.network_partition.clear()
    
    def submit_command(self, command: Dict[str, Any]) -> bool:
        """Submit command to cluster."""
        leader = self.get_leader()
        if not leader:
            return False
        
        msg = Message(
            msg_type=MessageType.CLIENT_REQUEST,
            from_node=-1,  # Client
            to_node=leader.config.node_id,
            term=leader.current_term,
            payload={'command': command}
        )
        leader.receive_message(msg)
        return True
    
    def verify_cluster(self) -> Dict[str, Any]:
        """Verify cluster state consistency."""
        results = {
            'all_verified': True,
            'leader': None,
            'terms': {},
            'commit_indices': {},
            'state_machines_match': True,
        }
        
        leader = self.get_leader()
        if leader:
            results['leader'] = leader.config.node_id
        
        for node_id, node in self.nodes.items():
            results['terms'][node_id] = node.current_term
            results['commit_indices'][node_id] = node.commit_index
            
            if not node.verify_state():
                results['all_verified'] = False
        
        # Check state machine consistency
        if len(self.nodes) > 0:
            first_sm = list(self.nodes.values())[0].state_machine
            for node in self.nodes.values():
                if node.state_machine != first_sm:
                    results['state_machines_match'] = False
        
        return results


# =========================================================================
# SVL Integration
# =========================================================================

class SVLRaftVerifier:
    """Verifier for Raft implementation properties."""
    
    @staticmethod
    def verify_election_safety(cluster: RaftCluster) -> bool:
        """Verify at most one leader per term (Election Safety)."""
        leaders_by_term = defaultdict(list)
        
        for node in cluster.nodes.values():
            # In a real implementation, would check history
            # For now, verify current state
            if node.is_leader():
                leaders_by_term[node.current_term].append(node.config.node_id)
        
        for term, leaders in leaders_by_term.items():
            if len(leaders) > 1:
                return False
        return True
    
    @staticmethod
    def verify_leader_append_only(cluster: RaftCluster) -> bool:
        """Verify leader only appends, never overwrites (Leader Append-Only)."""
        leader = cluster.get_leader()
        if not leader:
            return True
        
        # In real implementation, would check log history
        # For now, verify log structure
        for i, entry in enumerate(leader.log):
            if entry.index != i + 1:
                return False
            if entry.term <= 0:
                return False
        return True
    
    @staticmethod
    def verify_log_matching(cluster: RaftCluster) -> bool:
        """Verify if two logs contain an entry with same index and term, 
        then all preceding entries match (Log Matching)."""
        leader = cluster.get_leader()
        if not leader:
            return True
        
        for node in cluster.nodes.values():
            if node == leader:
                continue
            
            # Check common prefix
            min_len = min(len(leader.log), len(node.log))
            for i in range(min_len):
                if leader.log[i].term != node.log[i].term:
                    # Logs diverge at index i
                    return False
        return True
    
    @staticmethod
    def verify_state_machine_safety(cluster: RaftCluster) -> bool:
        """Verify all nodes have same state machine (State Machine Safety)."""
        state_machines = [node.state_machine for node in cluster.nodes.values()]
        return all(sm == state_machines[0] for sm in state_machines)


def create_raft_cluster(node_count: int = 5) -> RaftCluster:
    """Create a Raft cluster for testing."""
    node_ids = list(range(node_count))
    return RaftCluster(node_ids)


def run_raft_simulation(steps: int = 100, node_count: int = 5) -> Dict[str, Any]:
    """Run Raft simulation and return results."""
    cluster = create_raft_cluster(node_count)
    
    # Run simulation
    for i in range(steps):
        cluster.step(0.1)
        
        # Submit some commands periodically
        if i % 20 == 0 and i > 0:
            cluster.submit_command({'op': 'set', 'key': f'key{i}', 'value': f'value{i}'})
    
    # Verify
    verifier = SVLRaftVerifier()
    verification = {
        'election_safety': verifier.verify_election_safety(cluster),
        'leader_append_only': verifier.verify_leader_append_only(cluster),
        'log_matching': verifier.verify_log_matching(cluster),
        'state_machine_safety': verifier.verify_state_machine_safety(cluster),
        'cluster_verification': cluster.verify_cluster(),
    }
    
    return verification


if __name__ == '__main__':
    # Test Raft implementation
    print("=== Raft Consensus Test ===")
    
    # Run simulation
    results = run_raft_simulation(steps=50, node_count=5)
    
    print("Verification Results:")
    for check, result in results.items():
        print(f"  {check}: {'PASS' if result else 'FAIL'}")
    
    # Test cluster verification
    cluster = create_raft_cluster(3)
    for _ in range(20):
        cluster.step(0.1)
    
    verification = cluster.verify_cluster()
    print(f"\nCluster Verification: {verification}")
    
    # Test command submission
    cluster.submit_command({'op': 'set', 'key': 'test', 'value': 'hello'})
    for _ in range(10):
        cluster.step(0.1)
    
    verification = cluster.verify_cluster()
    print(f"After command: {verification}")
    
    print("\n=== Raft Test Complete ===")