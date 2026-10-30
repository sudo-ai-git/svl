# grAIl → JARVIS: Unified Blueprint

> **Consensus formula**: S = 0.6V + 0.3C + 0.1R, quorum 0.67
> **3-voter P3 delegation**: Engineering + User Value + Deployment
> **Status**: 6 ideas pass quorum. Blueprint with microsteps below.

---

## Consensus Results

| Idea | V | C | R | S | Source |
|------|---|---|---|---|--------|
| Vector Semantic Memory | 9 | 10 | 8 | **8.5** | Engineering |
| Proactive Assistance | 10 | 7 | 5 | **8.6** | User Value |
| Conversational Fluidity | 9 | 8 | 7 | **8.5** | User Value |
| Context Awareness | 9 | 8 | 7 | **8.5** | User Value |
| Checkpoint/Rollback | 8 | 9 | 9 | **8.4** | Engineering |
| Dynamic Tool DAG | 8 | 8 | 8 | **8.2** | Engineering |

**Quorum check**: All 6 ideas ≥ 8.2, well above 0.67 threshold.

---

## Blueprint 1: Vector Semantic Memory (S=8.5)

**What**: Replace flat MEMORY.md with embedding-based vector search. O(log n) retrieval with semantic matching.

### Microsteps
1. [ ] Add `sentence-transformers` or `numpy`-based embedding generation
2. [ ] Create `VectorMemory` class in `grAIl/memory/vector_memory.py`
3. [ ] Implement `store(fact, traits)` → embeds and stores in SQLite vector index
4. [ ] Implement `recall(query, top_k=5)` → cosine similarity search
5. [ ] Integrate with `AgentLoop` — replace flat memory lookups with vector recall
6. [ ] Add `hermes-vector-memory` hermes skill
7. [ ] Test: store 10 facts, recall by semantic query, verify accuracy > 80%

### Verification
- `pyright` 0 errors
- Tests: vector memory CRUD, semantic search, integration with AgentLoop
- `py_compile` all files

---

## Blueprint 2: Proactive Assistance (S=8.6)

**What**: JARVIS doesn't wait — it acts. Detect patterns, predict needs, take initiative.

### Microsteps
1. [ ] Build `PreferenceStore` — persistent key-value store of user habits (pure stdlib: `sqlite3`)
2. [ ] Add `cron-jobs` integration for periodic context scanning
3. [ ] Implement `detect_patterns()` — analyze recent actions for recurring patterns
4. [ ] Implement `predict_needs()` — based on time, context, history
5. [ ] Add proactive suggestion endpoint `/api/agent/proactive`
6. [ ] Create `ProactiveAssistant` class with `proactivity_dial` (aggressive → minimal)
7. [ ] Test: simulate morning routine, verify suggestions appear

### Verification
- PreferenceStore persists across sessions
- Cron jobs fire correctly
- Pattern detection accuracy > 70% on synthetic data

---

## Blueprint 3: Conversational Fluidity (S=8.5)

**What**: Natural back-and-forth, remembers context across turns, handles interruptions.

### Microsteps
1. [ ] Add `conversation_buffer` to `AgentLoop` — circular buffer of last N exchanges
2. [ ] Implement `topic_tracking()` — extract and track topics across turns
3. [ ] Implement `implicit_reference_resolution()` — resolve "it", "that", "the previous"
4. [ ] Add `interruption_handling()` — when user changes topic mid-reasoning
5. [ ] Integrate with streaming chat — preserve buffer across WebSocket sessions
6. [ ] Test: multi-turn conversation with topic switches and implicit references

### Verification
- Multi-turn test: 5+ exchanges with topic switches
- Implicit reference resolution: "it" correctly refers to previous entity
- Interruption handling: topic switch mid-reasoning works

---

## Blueprint 4: Context Awareness (S=8.5)

**What**: Agent knows its environment — cluster topology, provider status, available tools, user context.

### Microsteps
1. [ ] Extend `_build_ecology_prompt()` with real-time cluster state
2. [ ] Add `/api/context` endpoint — returns full agent context snapshot
3. [ ] Implement `context_watcher()` — monitors file changes, git status, calendar
4. [ ] Add `environment_awareness` flag to AgentLoop config
5. [ ] Web dashboard: show agent context panel with live updates via WebSocket
6. [ ] Test: agent detects new files, git changes, provider status changes

### Verification
- `/api/context` returns complete context snapshot
- File change detection works
- Web dashboard shows live context updates

---

## Blueprint 5: Checkpoint/Rollback System (S=8.4)

**What**: Before any action, create a checkpoint. If it fails, roll back instantly.

### Microsteps
1. [ ] Create `CheckpointManager` in `grAIl/checkpoint.py`
2. [ ] Implement `create_checkpoint(label)` → saves state snapshot to disk
3. [ ] Implement `rollback(label)` → restores previous state
4. [ ] Integrate with `AgentLoop.run()` — auto-checkpoint before each tool call
5. [ ] Add `_verify_before_commit()` — verify action succeeded before marking done
6. [ ] Test: execute action, simulate failure, verify rollback restores state

### Verification
- Checkpoint creation/restoration works
- AgentLoop auto-checkpoints before tool calls
- Rollback restores exact previous state
- `pyright` 0 errors

---

## Blueprint 6: Dynamic Tool DAG Orchestration (S=8.2)

**What**: Tools aren't just listed — they're orchestrated as a dependency graph. Some tools depend on others.

### Microsteps
1. [ ] Create `ToolDAG` class in `grAIl/tool_dag.py`
2. [ ] Implement `add_tool(tool_key, dependencies=[...])` — declare tool dependencies
3. [ ] Implement `resolve_order(tool_key)` — topological sort for execution order
4. [ ] Integrate with `Dispatcher` — before executing tool, resolve dependencies
5. [ ] Add `auto_chain()` — if tool A output feeds tool B, chain automatically
6. [ ] Test: define DAG with 5 tools, verify topological order, verify chain execution

### Verification
- ToolDAG topological sort correct
- Dependency resolution works
- Auto-chain executes dependent tools in order
- `pyright` 0 errors

---

## Implementation Order

```
Phase 1 (pure stdlib, deploy NOW):
├── Blueprint 5: Checkpoint/Rollback     [S=8.4, R=9]
├── Blueprint 3: Conversational Fluidity [S=8.5, R=7]
└── Blueprint 4: Context Awareness       [S=8.5, R=7]

Phase 2 (light dependencies, deploy SOON):
├── Blueprint 1: Vector Semantic Memory  [S=8.5, R=8]
└── Blueprint 6: Dynamic Tool DAG        [S=8.2, R=8]

Phase 3 (requires preference layer):
└── Blueprint 2: Proactive Assistance    [S=8.6, R=5]
```

---

## Verification Checklist

After each blueprint implementation:
- [ ] `pyright` 0 errors
- [ ] 250/250 tests passing
- [ ] `py_compile` all modified files
- [ ] `__pycache__` cleared before restart
- [ ] Server healthy on ports 8090/8081
- [ ] `/api/ecosystem`, `/api/tools/registry`, `/api/tools/docs` all working
- [ ] Live chat test: `curl -X POST /chat/agent` returns `ok: true`
- [ ] Voice stream test: `/api/voice/stream` accepts audio chunks
- [ ] Line-by-line review: `_review_code_line_by_line()` works
- [ ] Silence detection: `_detect_silence()` returns correct boolean
