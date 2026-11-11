# svl/time_travel.py
# Time-Travel Debugging / Deterministic Replay (H35)
# Event logging and replay for deterministic debugging

from typing import Dict, List, Optional, Any, Callable, Set
from dataclasses import dataclass, field
from enum import Enum
import json
import time
import hashlib
from collections import deque
from pathlib import Path
import copy


class EventType(Enum):
    """Types of events in the execution trace."""
    INSTRUCTION = "instruction"      # WASM instruction executed
    FUNCTION_CALL = "function_call"  # Function entered
    FUNCTION_RETURN = "function_return"  # Function exited
    MEMORY_READ = "memory_read"      # Memory read
    MEMORY_WRITE = "memory_write"    # Memory write
    LOCAL_GET = "local_get"          # Local variable read
    LOCAL_SET = "local_set"          # Local variable write
    GLOBAL_GET = "global_get"        # Global variable read
    GLOBAL_SET = "global_set"        # Global variable write
    BRANCH = "branch"                # Branch taken/not taken
    TRAP = "trap"                    # Runtime trap/error
    HOST_CALL = "host_call"          # Call to host function
    SNAPSHOT = "snapshot"            # Full state snapshot


@dataclass
class ExecutionEvent:
    """Single event in execution trace."""
    event_type: EventType
    timestamp: float
    instruction_ptr: int  # Program counter / instruction index
    function_name: Optional[str] = None
    operands: List[Any] = field(default_factory=list)
    result: Any = None
    memory_addr: Optional[int] = None
    memory_value: Any = None
    local_index: Optional[int] = None
    local_value: Any = None
    global_index: Optional[int] = None
    global_value: Any = None
    branch_taken: Optional[bool] = None
    trap_reason: Optional[str] = None
    host_function: Optional[str] = None
    snapshot_data: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'event_type': self.event_type.value,
            'timestamp': self.timestamp,
            'instruction_ptr': self.instruction_ptr,
            'function_name': self.function_name,
            'operands': self.operands,
            'result': self.result,
            'memory_addr': self.memory_addr,
            'memory_value': self.memory_value,
            'local_index': self.local_index,
            'local_value': self.local_value,
            'global_index': self.global_index,
            'global_value': self.global_value,
            'branch_taken': self.branch_taken,
            'trap_reason': self.trap_reason,
            'host_function': self.host_function,
            'snapshot_data': self.snapshot_data,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ExecutionEvent':
        return cls(
            event_type=EventType(data['event_type']),
            timestamp=data['timestamp'],
            instruction_ptr=data['instruction_ptr'],
            function_name=data.get('function_name'),
            operands=data.get('operands', []),
            result=data.get('result'),
            memory_addr=data.get('memory_addr'),
            memory_value=data.get('memory_value'),
            local_index=data.get('local_index'),
            local_value=data.get('local_value'),
            global_index=data.get('global_index'),
            global_value=data.get('global_value'),
            branch_taken=data.get('branch_taken'),
            trap_reason=data.get('trap_reason'),
            host_function=data.get('host_function'),
            snapshot_data=data.get('snapshot_data'),
        )


@dataclass
class ExecutionTrace:
    """Complete execution trace for a program run."""
    program_hash: str
    start_time: float
    end_time: Optional[float] = None
    events: List[ExecutionEvent] = field(default_factory=list)
    initial_state: Dict[str, Any] = field(default_factory=dict)
    final_state: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def add_event(self, event: ExecutionEvent):
        self.events.append(event)
    
    def get_events_in_range(self, start_idx: int, end_idx: int) -> List[ExecutionEvent]:
        return self.events[start_idx:end_idx]
    
    def get_events_by_type(self, event_type: EventType) -> List[ExecutionEvent]:
        return [e for e in self.events if e.event_type == event_type]
    
    def get_events_by_function(self, function_name: str) -> List[ExecutionEvent]:
        return [e for e in self.events if e.function_name == function_name]
    
    def to_json(self) -> str:
        data = {
            'program_hash': self.program_hash,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'events': [e.to_dict() for e in self.events],
            'initial_state': self.initial_state,
            'final_state': self.final_state,
            'metadata': self.metadata,
        }
        return json.dumps(data)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'ExecutionTrace':
        data = json.loads(json_str)
        trace = cls(
            program_hash=data['program_hash'],
            start_time=data['start_time'],
            end_time=data.get('end_time'),
            initial_state=data.get('initial_state', {}),
            final_state=data.get('final_state', {}),
            metadata=data.get('metadata', {}),
        )
        trace.events = [ExecutionEvent.from_dict(e) for e in data['events']]
        return trace
    
    def save(self, path: str):
        with open(path, 'w') as f:
            f.write(self.to_json())
    
    @classmethod
    def load(cls, path: str) -> 'ExecutionTrace':
        with open(path, 'r') as f:
            return cls.from_json(f.read())


class TimeTravelDebugger:
    """Time-travel debugger with deterministic replay."""
    
    def __init__(self, trace: Optional[ExecutionTrace] = None):
        self.trace = trace or ExecutionTrace(
            program_hash="",
            start_time=time.time()
        )
        self.current_index = 0
        self.snapshots: Dict[int, Dict[str, Any]] = {}  # index -> state
        self.breakpoints: Set[int] = set()  # instruction indices
        self.watchpoints: Dict[int, Any] = {}  # memory address -> last value
        self.call_stack: List[str] = []
    
    def record_event(self, event: ExecutionEvent):
        """Record an execution event."""
        self.trace.add_event(event)
        
        # Update call stack
        if event.event_type == EventType.FUNCTION_CALL:
            self.call_stack.append(event.function_name or "unknown")
        elif event.event_type == EventType.FUNCTION_RETURN:
            if self.call_stack:
                self.call_stack.pop()
        
        # Check watchpoints
        if event.event_type == EventType.MEMORY_WRITE and event.memory_addr is not None:
            if event.memory_addr in self.watchpoints:
                old_value = self.watchpoints[event.memory_addr]
                if old_value != event.memory_value:
                    # Watchpoint triggered - could pause execution
                    pass
            self.watchpoints[event.memory_addr] = event.memory_value
    
    def take_snapshot(self, state: Dict[str, Any]):
        """Take a full state snapshot at current index."""
        self.snapshots[self.current_index] = copy.deepcopy(state)
        # Also record as event
        event = ExecutionEvent(
            event_type=EventType.SNAPSHOT,
            timestamp=time.time(),
            instruction_ptr=self.current_index,
            snapshot_data=state
        )
        self.trace.add_event(event)
    
    def step_forward(self) -> Optional[ExecutionEvent]:
        """Step forward one event."""
        if self.current_index < len(self.trace.events):
            event = self.trace.events[self.current_index]
            self.current_index += 1
            return event
        return None
    
    def step_backward(self) -> Optional[ExecutionEvent]:
        """Step backward one event."""
        if self.current_index > 0:
            self.current_index -= 1
            return self.trace.events[self.current_index]
        return None
    
    def jump_to(self, index: int) -> bool:
        """Jump to specific event index."""
        if 0 <= index < len(self.trace.events):
            self.current_index = index
            return True
        return False
    
    def jump_to_function_call(self, function_name: str, occurrence: int = 1) -> bool:
        """Jump to nth call of a function."""
        count = 0
        for i, event in enumerate(self.trace.events):
            if event.event_type == EventType.FUNCTION_CALL and event.function_name == function_name:
                count += 1
                if count == occurrence:
                    self.current_index = i
                    return True
        return False
    
    def jump_to_trap(self) -> bool:
        """Jump to first trap event."""
        for i, event in enumerate(self.trace.events):
            if event.event_type == EventType.TRAP:
                self.current_index = i
                return True
        return False
    
    def get_current_event(self) -> Optional[ExecutionEvent]:
        """Get current event."""
        if 0 <= self.current_index < len(self.trace.events):
            return self.trace.events[self.current_index]
        return None
    
    def get_call_stack(self) -> List[str]:
        """Get call stack at current position."""
        # Reconstruct call stack up to current index
        stack = []
        for i in range(self.current_index):
            event = self.trace.events[i]
            if event.event_type == EventType.FUNCTION_CALL:
                stack.append(event.function_name or "unknown")
            elif event.event_type == EventType.FUNCTION_RETURN:
                if stack:
                    stack.pop()
        return stack
    
    def get_memory_at(self, address: int) -> Any:
        """Get memory value at address by replaying events."""
        value = None
        for i in range(self.current_index):
            event = self.trace.events[i]
            if event.event_type == EventType.MEMORY_WRITE and event.memory_addr == address:
                value = event.memory_value
        return value
    
    def get_local_at(self, index: int, function: str) -> Any:
        """Get local variable value by replaying."""
        value = None
        for i in range(self.current_index):
            event = self.trace.events[i]
            if (event.event_type == EventType.LOCAL_SET and 
                event.local_index == index and
                event.function_name == function):
                value = event.local_value
        return value
    
    def set_breakpoint(self, instruction_ptr: int):
        """Set breakpoint at instruction."""
        self.breakpoints.add(instruction_ptr)
    
    def remove_breakpoint(self, instruction_ptr: int):
        """Remove breakpoint."""
        self.breakpoints.discard(instruction_ptr)
    
    def check_breakpoint(self, instruction_ptr: int) -> bool:
        """Check if breakpoint at instruction."""
        return instruction_ptr in self.breakpoints
    
    def set_watchpoint(self, address: int):
        """Set watchpoint on memory address."""
        self.watchpoints[address] = None
    
    def remove_watchpoint(self, address: int):
        """Remove watchpoint."""
        self.watchpoints.pop(address, None)
    
    def replay_to_breakpoint(self) -> Optional[ExecutionEvent]:
        """Replay until next breakpoint."""
        while self.current_index < len(self.trace.events):
            event = self.trace.events[self.current_index]
            if event.instruction_ptr in self.breakpoints:
                return event
            self.current_index += 1
        return None
    
    def replay_to_watchpoint(self) -> Optional[ExecutionEvent]:
        """Replay until watchpoint triggered."""
        while self.current_index < len(self.trace.events):
            event = self.trace.events[self.current_index]
            if (event.event_type == EventType.MEMORY_WRITE and 
                event.memory_addr in self.watchpoints):
                old = self.watchpoints[event.memory_addr]
                if old is not None and old != event.memory_value:
                    return event
            self.current_index += 1
        return None
    
    def export_trace(self, path: str):
        """Export trace to file."""
        self.trace.save(path)
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get trace statistics."""
        event_counts = {}
        for event in self.trace.events:
            event_counts[event.event_type.value] = event_counts.get(event.event_type.value, 0) + 1
        
        return {
            'total_events': len(self.trace.events),
            'event_counts': event_counts,
            'duration': (self.trace.end_time or time.time()) - self.trace.start_time,
            'functions_called': len(set(e.function_name for e in self.trace.events 
                                         if e.event_type == EventType.FUNCTION_CALL)),
            'memory_operations': sum(1 for e in self.trace.events 
                                     if e.event_type in (EventType.MEMORY_READ, EventType.MEMORY_WRITE)),
            'snapshots': len(self.snapshots),
        }


class DeterministicReplayer:
    """Replays execution deterministically from trace."""
    
    def __init__(self, trace: ExecutionTrace):
        self.trace = trace
        self.debugger = TimeTravelDebugger(trace)
    
    def replay(self, start_idx: int = 0, end_idx: Optional[int] = None,
               callback: Optional[Callable[[ExecutionEvent], bool]] = None) -> List[ExecutionEvent]:
        """Replay events in range."""
        end = end_idx if end_idx is not None else len(self.trace.events)
        replayed = []
        
        self.debugger.current_index = start_idx
        
        for i in range(start_idx, min(end, len(self.trace.events))):
            event = self.trace.events[i]
            replayed.append(event)
            
            if callback and not callback(event):
                break
        
        return replayed
    
    def replay_function(self, function_name: str, occurrence: int = 1) -> List[ExecutionEvent]:
        """Replay specific function call."""
        # Find function call
        call_idx = None
        count = 0
        for i, event in enumerate(self.trace.events):
            if event.event_type == EventType.FUNCTION_CALL and event.function_name == function_name:
                count += 1
                if count == occurrence:
                    call_idx = i
                    break
        
        if call_idx is None:
            return []
        
        # Find matching return
        return_idx = None
        depth = 1
        for i in range(call_idx + 1, len(self.trace.events)):
            event = self.trace.events[i]
            if event.event_type == EventType.FUNCTION_CALL:
                depth += 1
            elif event.event_type == EventType.FUNCTION_RETURN:
                depth -= 1
                if depth == 0:
                    return_idx = i
                    break
        
        end_idx = return_idx if return_idx is not None else len(self.trace.events)
        return self.replay(call_idx, end_idx)
    
    def find_bug(self, predicate: Callable[[ExecutionEvent], bool]) -> Optional[ExecutionEvent]:
        """Find first event matching predicate."""
        for event in self.trace.events:
            if predicate(event):
                return event
        return None
    
    def find_last_state_change(self, address: int) -> Optional[ExecutionEvent]:
        """Find last write to memory address."""
        for event in reversed(self.trace.events):
            if (event.event_type == EventType.MEMORY_WRITE and 
                event.memory_addr == address):
                return event
        return None


class TimeTravelCLI:
    """Command-line interface for time-travel debugging."""
    
    def __init__(self, debugger: TimeTravelDebugger):
        self.debugger = debugger
    
    def run_command(self, command: str) -> str:
        """Execute debugger command."""
        parts = command.strip().split()
        if not parts:
            return ""
        
        cmd = parts[0]
        args = parts[1:]
        
        if cmd == "next" or cmd == "n":
            event = self.debugger.step_forward()
            return self._format_event(event) if event else "End of trace"
        
        elif cmd == "prev" or cmd == "p":
            event = self.debugger.step_backward()
            return self._format_event(event) if event else "Start of trace"
        
        elif cmd == "jump" or cmd == "j":
            if args:
                idx = int(args[0])
                if self.debugger.jump_to(idx):
                    return f"Jumped to event {idx}"
                return f"Invalid index: {idx}"
            return "Usage: jump <index>"
        
        elif cmd == "break" or cmd == "b":
            if args:
                idx = int(args[0])
                self.debugger.set_breakpoint(idx)
                return f"Breakpoint set at {idx}"
            return "Usage: break <index>"
        
        elif cmd == "watch":
            if args:
                addr = int(args[0], 0)  # Support hex
                self.debugger.set_watchpoint(addr)
                return f"Watchpoint set at {addr:#x}"
            return "Usage: watch <address>"
        
        elif cmd == "continue" or cmd == "c":
            event = self.debugger.replay_to_breakpoint()
            return self._format_event(event) if event else "No breakpoint hit"
        
        elif cmd == "stack":
            stack = self.debugger.get_call_stack()
            return "\n".join(f"  {i}: {f}" for i, f in enumerate(stack))
        
        elif cmd == "info":
            stats = self.debugger.get_statistics()
            return "\n".join(f"  {k}: {v}" for k, v in stats.items())
        
        elif cmd == "event":
            event = self.debugger.get_current_event()
            return self._format_event(event) if event else "No current event"
        
        elif cmd == "list":
            # List recent events
            start = max(0, self.debugger.current_index - 10)
            events = self.debugger.trace.events[start:self.debugger.current_index + 1]
            lines = []
            for i, event in enumerate(events):
                idx = start + i
                marker = ">" if idx == self.debugger.current_index else " "
                lines.append(f"{marker} {idx}: {self._format_event_short(event)}")
            return "\n".join(lines)
        
        elif cmd == "help":
            return """Commands:
  next (n)        - Step forward
  prev (p)        - Step backward
  jump (j) <idx>  - Jump to event index
  break (b) <idx> - Set breakpoint
  watch <addr>    - Set memory watchpoint
  continue (c)    - Run to breakpoint
  stack           - Show call stack
  info            - Show trace statistics
  event           - Show current event
  list            - List recent events
  help            - Show this help"""
        
        return f"Unknown command: {cmd}"
    
    def _format_event(self, event: ExecutionEvent) -> str:
        lines = [
            f"Event #{self.debugger.current_index - 1}:",
            f"  Type: {event.event_type.value}",
            f"  Time: {event.timestamp:.6f}",
            f"  IP: {event.instruction_ptr}",
        ]
        if event.function_name:
            lines.append(f"  Function: {event.function_name}")
        if event.operands:
            lines.append(f"  Operands: {event.operands}")
        if event.result is not None:
            lines.append(f"  Result: {event.result}")
        if event.memory_addr is not None:
            lines.append(f"  Mem[{event.memory_addr:#x}] = {event.memory_value}")
        if event.local_index is not None:
            lines.append(f"  Local[{event.local_index}] = {event.local_value}")
        if event.branch_taken is not None:
            lines.append(f"  Branch: {'taken' if event.branch_taken else 'not taken'}")
        if event.trap_reason:
            lines.append(f"  TRAP: {event.trap_reason}")
        return "\n".join(lines)
    
    def _format_event_short(self, event: ExecutionEvent) -> str:
        parts = [event.event_type.value]
        if event.function_name:
            parts.append(f"in {event.function_name}")
        if event.memory_addr is not None:
            parts.append(f"mem[{event.memory_addr:#x}]={event.memory_value}")
        return " ".join(parts)


def create_test_trace() -> ExecutionTrace:
    """Create a test execution trace for demonstration."""
    trace = ExecutionTrace(
        program_hash="test_program_abc123",
        start_time=time.time()
    )
    
    # Simulate a simple execution
    events = [
        ExecutionEvent(EventType.FUNCTION_CALL, time.time(), 0, "main"),
        ExecutionEvent(EventType.LOCAL_SET, time.time(), 1, "main", local_index=0, local_value=42),
        ExecutionEvent(EventType.LOCAL_SET, time.time(), 2, "main", local_index=1, local_value=10),
        ExecutionEvent(EventType.INSTRUCTION, time.time(), 3, "main", operands=[0, 1], result=52),
        ExecutionEvent(EventType.FUNCTION_CALL, time.time(), 4, "add", operands=[42, 10]),
        ExecutionEvent(EventType.INSTRUCTION, time.time(), 5, "add", operands=[42, 10], result=52),
        ExecutionEvent(EventType.FUNCTION_RETURN, time.time(), 6, "add", result=52),
        ExecutionEvent(EventType.LOCAL_SET, time.time(), 7, "main", local_index=2, local_value=52),
        ExecutionEvent(EventType.FUNCTION_RETURN, time.time(), 8, "main", result=52),
    ]
    
    for event in events:
        trace.add_event(event)
    
    trace.end_time = time.time()
    trace.initial_state = {"memory": {}, "locals": {}, "globals": {}}
    trace.final_state = {"memory": {}, "locals": {"main": [42, 10, 52]}, "globals": {}}
    
    return trace


if __name__ == '__main__':
    # Test time-travel debugger
    print("=== Time-Travel Debugger Test ===")
    
    trace = create_test_trace()
    debugger = TimeTravelDebugger(trace)
    cli = TimeTravelCLI(debugger)
    
    print("Trace Statistics:")
    stats = debugger.get_statistics()
    for k, v in stats.items():
        print(f"  {k}: {v}")
    
    print("\n--- Replay Demo ---")
    # Step through events
    while True:
        event = debugger.step_forward()
        if not event:
            break
        print(f"  {event.event_type.value} at IP={event.instruction_ptr}")
    
    print("\n--- Backwards Demo ---")
    # Step backward
    for _ in range(3):
        event = debugger.step_backward()
        if event:
            print(f"  Back to {event.event_type.value} at IP={event.instruction_ptr}")
    
    print("\n--- Jump Demo ---")
    debugger.jump_to(3)
    event = debugger.get_current_event()
    if event:
        print(f"Jumped to event 3: {event.event_type.value}")
    else:
        print("Jumped to event 3: no event")
    
    print("\n--- Breakpoint Demo ---")
    debugger.set_breakpoint(5)
    debugger.jump_to(0)
    event = debugger.replay_to_breakpoint()
    print(f"Hit breakpoint at event: {event.instruction_ptr if event else 'none'}")
    
    print("\n--- Function Replay ---")
    replayer = DeterministicReplayer(trace)
    add_events = replayer.replay_function("add")
    print(f"Function 'add' events: {len(add_events)}")
    for e in add_events:
        print(f"  {e.event_type.value} at IP={e.instruction_ptr}")
    
    print("\n--- Statistics ---")
    for k, v in debugger.get_statistics().items():
        print(f"  {k}: {v}")