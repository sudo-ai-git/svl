# grAIl Agent-Loop Modifications Using pcomp Tools at Critical Reasoning Junctures

## Architecture Overview

The grAIl agent loop is a ReAct pattern: `think → tool_call → observe → think → answer`. The loop lives in `AgentLoop.run()` and iterates up to `max_iterations`, calling `gateway.chat_with_tools()` each turn, dispatching tool calls through `dispatcher.dispatch()`, and feeding results back as tool messages.

The pcomp framework provides 13 tools organized into four pillars:
- **P1 (Compute)**: `cmat`, `verify` — complex GEMM and correctness gates
- **P2 (Quantize)**: `quant` — bit-sliced ADC quantization
- **P3 (Buffer)**: `ringbuf`, `tokenstep`, `live` — optical ring-buffer, token-lockstep, LiveCoprocessor
- **P4 (System)**: `conv`, `energy`, `thermal`, `osnr`, `adaptive_q`, `yield`, `token_alu` — physical layer telemetry

The framework also uses **DSPy optimizer** for provider-routing (`dspy_optimizer.py`), with `BootstrapFewShot` compilation of `ProviderRouteModule`.

---

## Design Philosophy: Where pcomp Tools Enter the Reasoning Chain

The core insight is that pcomp tools are **not just verification utilities** — they are **reasoning primitives** that provide *physical-grounded signal* at specific points where the LLM's internal reasoning is most likely to diverge from reality:

| LLM Reasoning Weakness | pcomp Countermeasure | Juncture |
|----------------------|---------------------|----------|
| Numeric hallucination | `verify` gates produce deterministic ground truth | Pre-answer grounding |
| Unbounded computation | `cmat` constrains matrix ops to optical physics | Mid-reasoning computation |
| Quantization unawareness | `quant` enforces bit-sliced precision | Post-computation |
| State drift across turns | `ringbuf` provides stable memory buffer | Context management |
| Token budget explosion | `tokenstep` enforces lockstep pacing | Budget enforcement |
| Provider routing errors | DSPy optimizer + `verify` gates | Provider selection |
| Silent failures | `live` provides real-time hardware feedback | Error detection |
| Physical impossibility | `energy`, `thermal`, `osnr` enforce physics | Constraint checking |

---

## Juncture 1: Pre-Reasoning Planning Phase — `verify` + `tokenstep`

### Location
`AgentLoop.run()` lines ~220-232, after `_needs_planning()` check, before the main loop.

### Problem
The LLM generates a plan without grounding it in computational reality. It may propose 20 steps when the token budget supports 5, or plan matrix operations that exceed optical hardware capabilities.

### Modification: `verify`-Gated Plan Validation

```python
# In AgentLoop.run(), after plan generation:
if plan_text and self._needs_planning(user_prompt):
    plan_text = self._plan(self.gateway, messages, schemas)
    if plan_text:
        # NEW: Validate plan against pcomp correctness gates
        verification = self._pcomp_verify_plan(plan_text)
        if not verification["all_pass"]:
            # Prune steps that fail verification gates
            plan_text = self._prune_failed_steps(plan_text, verification)
            # Inject failure recovery hint
            messages.append({
                "role": "system",
                "content": (
                    f"[PLAN REVISED] {len(verification['failed'])} steps failed "
                    f"photonic verification. Reduced plan to {len(plan_text)} steps."
                )
            })
        messages.append({"role": "system", "content": f"[PLAN] {plan_text}"})
        self._plan_steps = self._parse_plan_steps(plan_text)

    # NEW: Token-lockstep budget enforcement via pcomp
    n_steps = len(self._parse_plan_steps(plan_text))
    token_step_result = self._pcomp_tokenstep(n_steps)
    # Scale token budget to match lockstep capacity
    self.token_budget = min(
        self.token_budget,
        token_step_result["total"] * TOKENS_PER_STEP  # e.g., 200 tokens/step
    )
```

### How Results Feed Back

- `verify` returns `{total: 6, passed: N, failed: M, all_pass: bool, gates: [...]}`
- Failed gates → plan steps are pruned or rewritten
- `tokenstep` returns `{tokens: [...], total: N}` → sets hard token budget ceiling
- The `[PLAN REVISED]` system message becomes part of the LLM's reasoning context

### Failure Recovery

If `verify` returns `all_pass: False` and no viable plan exists:
```python
if not verification["all_pass"] and not plan_text:
    # Fallback: reduce scope and re-plan
    return self._done(
        ok=False, answer="", trace=trace, iterations=0,
        error="plan_failed_photonic_verification"
    )
```

### Creative Synthesis Pattern

`tokenstep` doesn't just enforce budgets — it **shapes reasoning structure**. A 5-step plan gets `token_step(5)` which returns `{"tokens": [{"token": 0, "status": "processed"}, ...], "total": 5}`. This can be used to inject a **token-lockstep pacing signal** into the reasoning:

```
[LOCKSTEP] Processing 5/5 tokens. Each step must produce verifiable output.
Step 1/5: [reasoning] → call cmat
Step 2/5: [reasoning] → call quant
...
```

---

## Juncture 2: Tool Selection Phase — `cmat` + DSPy Optimizer

### Location
`AgentLoop.run()` lines ~265-277, where `schemas = self._tool_schemas(user_prompt)` is called.

### Problem
The LLM selects tools based on TF-IDF cosine similarity over tool descriptions. For complex numerical tasks (matrix operations, quantization), the model may select the wrong tool or combine tools incorrectly.

### Modification: `cmat`-Weighted Tool Ranking

```python
# In AgentLoop._tool_schemas() or a new _pcomp_weighted_rank():
def _pcomp_weighted_rank(self, user_prompt: str, schemas: List[Dict]) -> List[Dict]:
    """Re-rank tools using cmat as a computational relevance signal.
    
    The LLM's tool selection is noisy for numerical tasks.
    cmat provides a deterministic relevance score: does the task
    require complex matrix math? If yes, boost cmat-adjacent tools.
    """
    # Check if task involves matrix operations
    matrix_indicators = ["matrix", "multiply", "gemm", "transform", "linear", "projection"]
    task_vector = self._text_to_vector(user_prompt)  # simple TF-IDF of prompt
    
    # cmat provides the ground-truth computational signature
    from pcomp.cmat import cgemm
    # Run a minimal cmat operation to establish computational demand
    import numpy as np
    probe_A = np.random.randn(4, 4).astype(np.float32)
    probe_B = np.random.randn(4, 4).astype(np.float32)
    try:
        result = cgemm(probe_A, probe_B)
        computational_demand = float(np.abs(result).max())
    except Exception:
        computational_demand = 0.0
    
    # Re-rank schemas: boost tools that match computational demand
    ranked = []
    for schema in schemas:
        name = schema["name"]
        score = self._semantic_match_score(name, user_prompt)
        # If task is computationally demanding, boost compute tools
        if computational_demand > 1.0 and name in ("photonic_compute_cmat", "photonic_compute_verify"):
            score *= 2.0  # Double the score for compute tasks
        # If task involves quantization, boost quant tool
        if "quant" in user_prompt.lower() and "quant" in name.lower():
            score *= 1.5
        ranked.append((score, schema))
    
    ranked.sort(key=lambda x: -x[0])
    return [s for _, s in ranked]

# Also integrate DSPy optimizer for provider routing
def _select_provider_with_dspy(self, task_description: str) -> str:
    """Use DSPy-optimized provider routing to select the best provider.
    
    The DSPy model is trained on historical route decisions to pick
    the optimal provider for the task type.
    """
    from dspy_optimizer import ProviderRouteModule, load_dataset, to_dspy_examples
    import dspy
    
    module = ProviderRouteModule()
    dataset = load_dataset()
    if len(dataset) >= 4:
        # Compiled model picks the best provider
        pred = module(request=task_description, 
                      available_providers="deepseek,grok,openrouter",
                      requires_tools="true",
                      preferred_provider="deepseek")
        return pred.provider
    else:
        # Fallback: deterministic router
        return "deepseek"
```

### How Results Feed Back

- `cmat` returns a computational demand score → re-orders tool schemas
- DSPy returns `{provider, confidence}` → selects which LLM provider handles the turn
- The `[TOOLS RE-RANKED]` system message already exists in the loop; this extends it with `cmat`-driven ranking

### Failure Recovery

If `cmat` fails (hardware unavailable):
```python
try:
    result = cgemm(probe_A, probe_B)
except Exception as e:
    # Fall back to semantic-only ranking
    computational_demand = 0.0
    # Log the failure for DSPy training data
    self._log_route_failure(task_description, str(e))
```

---

## Juncture 3: Tool Execution Phase — `live` + `ringbuf`

### Location
`AgentLoop.run()` lines ~508-589, where `dispatcher.dispatch(fn_name, fn_args, ctx)` executes tool calls.

### Problem
When pcomp tools are dispatched, the result is a JSON dict that gets appended to the conversation as a tool message. But the LLM has no way to know if the result is *physically grounded* — it just sees a number. The `live` coprocessor and `ringbuf` provide real-time hardware signals that the LLM can reason about.

### Modification: `live`-Grounded Execution Verification

```python
# In the tool execution loop (around line 528):
for tc in tool_calls:
    fn_name = self._tool_aliases.get(...)
    fn_args_raw = tc.get("function", {}).get("arguments", "{}")
    
    # NEW: Before dispatch, check live hardware state
    if fn_name.startswith("photonic_compute"):
        live_state = self._get_live_coprocessor_state()
        # Inject hardware context into the tool call
        fn_args["hardware_context"] = live_state
    
    try:
        tool_result = await self.dispatcher.dispatch(fn_name, fn_args, ctx)
    except Exception as e:
        tool_result = {"ok": False, "error": str(e)}
    
    # NEW: After dispatch, verify against ringbuf state
    if tool_result.get("ok"):
        # Push result to ringbuf for state continuity
        self._ringbuf_push(tool_result)
        
        # NEW: If this is a pcomp tool, cross-verify with LiveCoprocessor
        if fn_name.startswith("photonic_compute"):
            live_verification = self._live_verify(tool_result)
            if not live_verification["consistent"]:
                # Hardware divergence detected — trigger recovery
                tool_result["ok"] = False
                tool_result["error"] = (
                    f"Hardware divergence: {live_verification['detail']}"
                )
                # Backtrack will fire below
    
    # ... existing code: append tool message, track evidence, etc.
```

### `live` Integration Details

```python
def _get_live_coprocessor_state(self) -> Dict:
    """Get real-time phase register state from the LiveCoprocessor."""
    from pcomp.live import LiveCoprocessor
    live = LiveCoprocessor()
    snapshot = live.snapshot()
    return {
        "n_registers": live.n_registers,
        "phase_values": snapshot.tolist(),
        "coherent": float(np.abs(snapshot).mean()),
    }

def _live_verify(self, tool_result: Dict) -> Dict:
    """Cross-verify a tool result against LiveCoprocessor phase registers.
    
    The LiveCoprocessor writes phase values to memory-mapped registers.
    If the tool result diverges from what the hardware produces,
    the result is unreliable.
    """
    from pcomp.live import LiveCoprocessor
    live = LiveCoprocessor()
    current = live.snapshot()
    
    # Check if the tool result's numeric values are within
    # the hardware's phase range
    result_value = tool_result.get("result", {})
    if isinstance(result_value, (int, float)):
        # Map result to phase register space
        phase = abs(result_value) % (2 * np.pi)
        closest_phase = float(current[0]) if len(current) > 0 else 0.0
        divergence = abs(phase - closest_phase)
        return {
            "consistent": divergence < 0.1,  # radians
            "detail": f"phase divergence: {divergence:.4f} rad",
            "phase": phase,
            "hardware_phase": closest_phase,
        }
    return {"consistent": True, "detail": "non-numeric result, skipped"}
```

### How Results Feed Back

- `live` state → injected as `hardware_context` in tool args → LLM sees physical reality
- `ringbuf` → persists results across turns → LLM reasoning has stable memory
- Hardware divergence → sets `tool_result["ok"] = False` → triggers backtracking

### Failure Recovery

```python
# If live verification fails (hardware divergence):
if not live_verification["consistent"]:
    # Roll back to pre-tool state (existing backtrack mechanism)
    messages = pre_tool_messages
    messages.append({
        "role": "user",
        "content": (
            "[HARDWARE DIVERGENCE] The photonic hardware produced a "
            f"different result than the software layer. "
            f"Hardware phase: {live_verification['hardware_phase']}, "
            f"expected: {live_verification['phase']}. "
            "Re-derive using the ringbuf-stable state."
        )
    })
    consecutive_errors += 1
```

### Creative Synthesis Pattern: RingBuf as Reasoning State

The `ringbuf` isn't just a data structure — it's a **reasoning state machine**. Each tool result is pushed to the ringbuf, and subsequent reasoning steps can read from it:

```python
def _ringbuf_push(self, tool_result: Dict) -> None:
    """Push tool results to the ringbuf for cross-step reasoning."""
    from pcomp.ringbuf import RingBuffer
    if not hasattr(self, "_reasoning_ringbuf"):
        self._reasoning_ringbuf = RingBuffer(size=8)
    # Encode result as a scalar for the ringbuf
    result_value = self._extract_scalar(tool_result)
    self._reasoning_ringbuf.push(result_value)

def _ringbuf_context(self) -> str:
    """Generate a reasoning context from ringbuf state.
    
    This feeds back into the LLM's next reasoning step.
    """
    if not hasattr(self, "_reasoning_ringbuf"):
        return ""
    buf = self._reasoning_ringbuf.get()
    recent = buf[-3:]  # Last 3 values
    if len(recent) >= 2:
        trend = "increasing" if recent[-1] > recent[0] else "decreasing"
        return f"[RINGBUF] Recent values: {recent.tolist()}, trend: {trend}"
    return ""
```

---

## Juncture 4: Numeric Grounding Phase — `quant` + `verify`

### Location
`AgentLoop.run()` lines ~442-455, where `_verify_answer_against_trace()` checks the final answer against tool evidence.

### Problem
The LLM may produce a confident but numerically wrong final answer. The existing `_verify_answer_against_trace` compares against trace entries, but doesn't use pcomp's quantization-aware verification.

### Modification: `quant`-Enforced Answer Grounding

```python
# Replace or augment _verify_answer_against_trace():
def _quant_grounded_verify(self, answer: str, trace: List[Dict]) -> Dict:
    """Verify answer using bit-sliced ADC quantization as ground truth.
    
    The quant tool produces a bit-sliced, ADC-quantized version of
    the computation. This is the physical reality that the answer
    must match.
    """
    import re
    import numpy as np
    from pcomp.quant import AdcQuantizer, quant_forward
    
    # Extract all numeric claims from the answer
    numbers = re.findall(r'\b\d+\.?\d*\b', answer)
    if not numbers:
        return {"mismatch": False, "reason": "no numbers to verify"}
    
    # Extract the tool result that should ground this answer
    tool_results = [t for t in trace if t.get("result", {}).get("ok")]
    if not tool_results:
        return {"mismatch": False, "reason": "no tool evidence"}
    
    # Use the last successful tool result as reference
    ref_result = tool_results[-1]["result"]
    ref_value = self._extract_numeric(ref_result)
    
    if ref_value is None:
        return {"mismatch": False, "reason": "non-numeric tool result"}
    
    # Quantize the reference using the ADC (physical ground truth)
    q = AdcQuantizer(din=16, dout=8, adc_enob=10)
    quantized_ref = q.quant_forward(np.array([ref_value], dtype=np.float32))
    quantized_value = float(quantized_ref[0])
    
    # Check each claimed number against quantized reference
    claimed_numbers = [float(n) for n in numbers]
    mismatches = []
    for claimed in claimed_numbers:
        # Quantized difference must be within ADC precision
        diff = abs(claimed - quantized_value)
        if diff > 2 ** (-q.adc_enob) * ref_value:  # ADC resolution limit
            mismatches.append({
                "claimed": claimed,
                "quantized_ground_truth": quantized_value,
                "diff": diff,
                "adc_resolution": 2 ** (-q.adc_enob),
            })
    
    return {
        "mismatch": len(mismatches) > 0,
        "mismatches": mismatches,
        "quantized_ground_truth": quantized_value,
        "answer": answer,
    }
```

### How Results Feed Back

- `quant` returns a bit-sliced, ADC-quantized value → the **physical ground truth** that the answer must match
- Mismatches → `answer_evidence_correction` event added to trace → answer corrected
- The `adc_enob` parameter controls strictness: higher ENOB = stricter verification

### Failure Recovery

If `quant` grounding reveals a mismatch:
```python
v = self._quant_grounded_verify(answer, trace)
if v["mismatch"]:
    # The LLM's answer disagrees with physical quantization
    trace.append({
        "iteration": iteration,
        "event": "answer_quant_correction",
        "claimed": v["mismatches"],
        "quantized_ground_truth": v["quantized_ground_truth"],
        "answer": v["answer"],
    })
    # Correct the answer using quantized values
    corrected = self._apply_quant_correction(answer, v)
    answer = corrected
    # Force reflection on why the model hallucinated
    self.reflection_depth = max(self.reflection_depth, 2)
```

---

## Juncture 5: Error Recovery Phase — `verify` + `ringbuf` + `live`

### Location
`AgentLoop.run()` lines ~343-358 (transient error retry) and lines ~574-584 (backtracking), plus the `consecutive_errors` tracking at lines ~586-589.

### Problem
When pcomp tools fail, the existing loop either retries (for transient errors) or backtracks (for verified-false results). But pcomp-specific failures need specialized recovery: the optical hardware may be in a bad state, the ringbuf may have stale data, or the live coprocessor may need reinitialization.

### Modification: pcomp-Aware Error Recovery State Machine

```python
# NEW: pcomp error recovery state machine
class PcompErrorRecovery:
    """Manages recovery from photonic compute failures."""
    
    def __init__(self):
        self.state = "HEALTHY"  # HEALTHY | DEGRADED | RECOVERING | FAILED
        self.consecutive_hardware_errors = 0
        self.ringbuf_stale = False
        self.live_disconnected = False
        self.recovery_attempts = 0
        self.max_recovery = 3
    
    def record_error(self, error_type: str) -> Dict:
        """Record an error and determine recovery action.
        
        Returns a recovery directive for the agent loop.
        """
        if error_type == "hardware_divergence":
            self.consecutive_hardware_errors += 1
            self.state = "DEGRADED"
        elif error_type == "ringbuf_stale":
            self.ringbuf_stale = True
            self.state = "DEGRADED"
        elif error_type == "live_disconnected":
            self.live_disconnected = True
            self.state = "RECOVERING"
        elif error_type == "verify_gate_failure":
            self.consecutive_hardware_errors += 2
            self.state = "FAILED" if self.consecutive_hardware_errors >= 3 else "DEGRADED"
        
        # Determine recovery action
        if self.state == "FAILED":
            return {
                "action": "abort",
                "reason": f"pcomp failed after {self.recovery_attempts} recovery attempts",
                "error_code": "PCOMP_PERMANENT_FAILURE",
            }
        elif self.state == "DEGRADED":
            return self._recover_degraded()
        elif self.state == "RECOVERING":
            return self._recover_live()
        else:
            return {"action": "continue", "state": self.state}
    
    def _recover_degraded(self) -> Dict:
        """Recover from degraded state using ringbuf + verify."""
        self.recovery_attempts += 1
        if self.recovery_attempts > self.max_recovery:
            return {"action": "abort", "reason": "max recovery attempts exceeded"}
        
        # Step 1: Reset ringbuf to stable state
        from pcomp.ringbuf import RingBuffer
        self._reset_ringbuf()
        
        # Step 2: Run verify gates to confirm hardware is functional
        from pcomp.verify import summary
        verify_result = summary()
        
        if verify_result["all_pass"]:
            self.state = "HEALTHY"
            self.consecutive_hardware_errors = 0
            return {
                "action": "retry",
                "reason": "hardware recovered after ringbuf reset",
                "verify_passed": True,
            }
        else:
            return {
                "action": "retry_with_fallback",
                "reason": "verify gates partially failed, using fallback computation",
                "failed_gates": [g["gate"] for g in verify_result["gates"] if not g["pass"]],
                "fallback": "use_cpu_matmul",
            }
    
    def _recover_live(self) -> Dict:
        """Recover from LiveCoprocessor disconnection."""
        from pcomp.live import LiveCoprocessor
        live = LiveCoprocessor()
        try:
            live.init_phase_regs()
            self.live_disconnected = False
            self.state = "HEALTHY"
            return {"action": "retry", "reason": "live coprocessor reinitialized"}
        except Exception as e:
            self.live_disconnected = True
            return {
                "action": "degrade",
                "reason": f"cannot reinitialize live coprocessor: {e}",
                "fallback": "software_only",
            }
```

### Integration into Agent Loop

```python
# In the tool execution loop, after catching an error:
if not tool_result.get("ok", True):
    error_type = self._classify_pcomp_error(tool_result, fn_name)
    if error_type:
        recovery = self._pcomp_recovery.record_error(error_type)
        if recovery["action"] == "abort":
            return self._done(
                ok=False, answer=answer, trace=trace,
                iterations=iteration, tokens_used=tokens_used,
                error=recovery["reason"]
            )
        elif recovery["action"] == "retry":
            # Reset state and retry the same tool call
            self._ringbuf_reset()
            continue  # Retry on next iteration
        elif recovery["action"] == "retry_with_fallback":
            # Use CPU fallback for the failed computation
            tool_result = self._cpu_fallback(fn_name, fn_args)
            tool_result["ok"] = True
            tool_result["fallback"] = True
        elif recovery["action"] == "degrade":
            # Continue without live coprocessor
            tool_result["live_unavailable"] = True
    
    # Existing consecutive error tracking
    if not tool_result.get("ok", True):
        consecutive_errors += 1
    else:
        consecutive_errors = 0
```

### Failure Classification

```python
def _classify_pcomp_error(self, tool_result: Dict, fn_name: str) -> Optional[str]:
    """Classify pcomp tool errors into recovery categories."""
    error_str = str(tool_result.get("error", "")).lower()
    
    if "phase" in error_str or "hardware" in error_str or "divergence" in error_str:
        return "hardware_divergence"
    if "ringbuf" in error_str or "stale" in error_str or "buffer" in error_str:
        return "ringbuf_stale"
    if "live" in error_str or "coprocessor" in error_str or "mmap" in error_str:
        return "live_disconnected"
    if "gate" in error_str and "fail" in error_str:
        return "verify_gate_failure"
    if "quant" in error_str or "adc" in error_str or "bit" in error_str:
        return "quant_error"
    return None
```

---

## Juncture 6: Reflection/Self-Critique Phase — `energy`, `thermal`, `osnr`

### Location
`AgentLoop.run()` lines ~485-486, where `_self_reflect()` is called.

### Problem
The existing reflection calls the same weak model to critique its own answer. A confidently-wrong model can't recognize its error. The physical layer tools (`energy`, `thermal`, `osnr`) provide **objective physical constraints** that the model's reasoning must satisfy.

### Modification: Physics-Constrained Reflection

```python
def _pconstrained_reflect(self, answer: str, trace: List[Dict], 
                           messages: List[Dict]) -> str:
    """Reflect using physical layer constraints as objective criteria.
    
    Instead of asking the weak model to self-critique (which fails
    for confidently-wrong answers), use energy/thermal/osnr as
    objective correctness signals.
    """
    import numpy as np
    from pcomp.energy import tool_pc_energy
    from pcomp.thermal import tool_pc_thermal
    from pcomp.osnr import tool_pc_osnr
    
    # Extract computational claims from the answer
    computational_claims = self._extract_computational_claims(answer)
    
    # Get physical layer constraints
    energy = tool_pc_energy()
    thermal = tool_pc_thermal()
    osnr = tool_pc_osnr()
    
    # Build physics-constrained reflection prompt
    physics_context = (
        f"[PHYSICS CONSTRAINTS] Energy: {energy['energy_joules']}J, "
        f"Temperature: {thermal['temperature_k']}K, "
        f"OSNR: {osnr['osnr_db']}dB. "
        f"Any computational claim that would require more energy than "
        f"{energy['energy_joules']}J or produce more heat than "
        f"{thermal['temperature_k']}K is physically impossible."
    )
    
    # Check if answer's computational claims violate physics
    violations = []
    for claim in computational_claims:
        if claim["operation"] == "matrix_multiply":
            # A 4096x4096 matmul at 1e-3 J per operation would be 
            # physically impossible at the current energy budget
            estimated_energy = self._estimate_energy(claim)
            if estimated_energy > energy["energy_joules"] * 10:
                violations.append({
                    "claim": claim,
                    "violation": "energy_exceeded",
                    "required_energy": estimated_energy,
                    "available_energy": energy["energy_joules"],
                })
    
    # Inject physics constraints into the reflection
    messages.append({
        "role": "system",
        "content": physics_context,
    })
    
    # If violations exist, use the DSPy verifier to get an independent
    # assessment instead of self-reflection
    if violations:
        return self._independent_verify(answer, violations, messages)
    
    # Otherwise, proceed with normal reflection but with physics context
    return self._self_reflect(answer, messages, trace)
```

### How Results Feed Back

- `energy` returns `{energy_joules}` → the maximum computation the hardware can sustain
- `thermal` returns `{temperature_k}` → thermal ceiling for sustained operation
- `osnr` returns `{osnr_db}` → signal quality, which determines computational precision
- Violations → independent verifier replaces self-reflection

---

## Juncture 7: Token Budget Enforcement Phase — `tokenstep` + `adaptive_q`

### Location
`AgentLoop.run()` lines ~240-243, where token budget triggers reflection depth changes.

### Problem
The token budget check is purely arithmetic: `tokens_used > self.token_budget * 0.5`. This doesn't account for the actual token processing capacity of the optical pipeline.

### Modification: `tokenstep`-Driven Budget Enforcement

```python
def _tokenstep_enforce_budget(self, iteration: int, tokens_used: int) -> Dict:
    """Use tokenstep to enforce lockstep token budget.
    
    Instead of a simple threshold check, tokenstep provides a
    lockstep pacing signal that adjusts the budget dynamically
    based on the pipeline's actual throughput.
    """
    from pcomp.tokenstep import token_step, TokenPipeline
    
    # Get the token pipeline status
    pipeline = TokenPipeline(n_tokens=self.max_iterations - iteration)
    pipeline_status = pipeline.process()
    
    # Calculate remaining budget based on lockstep position
    remaining_tokens = self.max_iterations - iteration
    step_result = token_step(n_tokens=remaining_tokens)
    
    # adaptive_q adjusts the Q-factor (precision) based on budget pressure
    from pcomp import tool_pc_adaptive_q
    q_result = tool_pc_adaptive_q(
        budget_pressure=tokens_used / self.token_budget if self.token_budget > 0 else 0,
        remaining_steps=remaining_tokens,
    )
    
    # Adjust token budget dynamically
    if q_result["q_factor"] < 0.5:
        # High pressure: tighten budget aggressively
        self.token_budget = int(self.token_budget * 0.8)
    elif q_result["q_factor"] > 1.5:
        # Low pressure: relax budget
        self.token_budget = int(self.token_budget * 1.2)
    
    return {
        "remaining_steps": remaining_tokens,
        "step_result": step_result,
        "q_factor": q_result["q_factor"],
        "adjusted_budget": self.token_budget,
    }

# In the loop, replace the simple check:
# OLD:
# if tokens_used > int(self.token_budget * 0.5):
#     self.reflection_depth = max(self.reflection_depth, 1)
# NEW:
budget_status = self._tokenstep_enforce_budget(iteration, tokens_used)
if budget_status["q_factor"] < 0.5:
    self.reflection_depth = max(self.reflection_depth, 2)  # Aggressive compression
elif budget_status["q_factor"] > 1.5:
    self.reflection_depth = 0  # Relaxed, no compression needed
```

---

## Juncture 8: Provider Routing via DSPy — `verify`-Trained Routes

### Location
`dspy_optimizer.py` and `AgentLoop.run()` provider selection.

### Problem
The DSPy optimizer trains a `ProviderRouteModule` to select the best provider, but the training data comes from historical route decisions. Without quality labels, the optimizer can't improve. The `verify` gates provide **ground-truth correctness signals** that can be used as training labels.

### Modification: Verify-Gated DSPy Training

```python
def _train_dspy_with_verify(self, route_examples: List[RouteExample]):
    """Train DSPy provider router using verify gate results as labels.
    
    Each route example gets a 'correct' label based on whether the
    selected provider's output passed the photonic verify gates.
    """
    from dspy_optimizer import load_dataset, to_dspy_examples, evaluate
    import dspy
    
    # For each route example, run the verify gate on the provider's output
    enriched_examples = []
    for example in route_examples:
        # Run the provider's output through verify
        provider_output = self._get_provider_output(example.provider, example.request)
        verify_result = self._run_pcomp_verify(provider_output)
        
        # Use verify pass/fail as the quality label
        example.provider = example.provider if verify_result["all_pass"] else "fallback"
        example.confidence = verify_result["passed"] / verify_result["total"]
        
        enriched_examples.append(example)
    
    # Train with enriched labels
    if len(enriched_examples) >= 4:
        module = ProviderRouteModule()
        compiled = dspy.BootstrapFewShot(
            metric=self._verify_aware_metric,
            max_bootstrapped_demos=4
        ).compile(module, trainset=to_dspy_examples(enriched_examples))
        return compiled
    return None

def _verify_aware_metric(self, example, prediction, trace=None):
    """DSPy metric that weights provider selection by verify gate results."""
    from dspy_optimizer import metric as base_metric
    base = base_metric(example, prediction, trace)
    
    # Bonus for selecting providers whose outputs pass verify gates
    if hasattr(example, 'verify_passed') and example.verify_passed:
        return base * 1.2  # 20% bonus for verified providers
    elif hasattr(example, 'verify_passed') and not example.verify_passed:
        return base * 0.5  # 50% penalty for unverified providers
    return base
```

---

## Juncture 9: Creative Synthesis — `token_alu` + `conv` + `ringbuf`

### Location
Post-answer synthesis phase, `AgentLoop.run()` lines ~477-480, where `_synthesize_sources()` and `_fact_check_answer()` run.

### Problem
The existing synthesis just aggregates search results. For creative tasks (designing new photonic circuits, composing transformations), the LLM needs **structured computational primitives** to work with, not just text.

### Modification: Photonic Creative Synthesis Loop

```python
def _photonic_creative_synthesis(self, answer: str, trace: List[Dict],
                                  ctx: Any) -> str:
    """Use pcomp tools for creative synthesis, not just verification.
    
    token_alu provides arithmetic/logic operations for computation.
    conv provides convolution for spatial transformations.
    ringbuf provides state for iterative creative processes.
    """
    import numpy as np
    from pcomp.token_alu import tool_pc_token_alu
    from pcomp.conv import tool_pc_conv
    from pcomp.ringbuf import RingBufferBank
    
    # Check if the task is creative (design, compose, transform)
    if not self._is_creative_task(answer):
        return answer
    
    # Use token_alu for computational primitive synthesis
    alu_result = tool_pc_token_alu(
        operations=self._extract_creative_operations(answer),
        mode="synthesize"
    )
    
    # Use conv for spatial transformation design
    conv_result = tool_pc_conv(
        kernel=self._design_kernel(answer),
        mode="creative"
    )
    
    # Use ringbuf bank for iterative refinement
    bank = RingBufferBank(n_buffers=4, buffer_size=8)
    for i, op in enumerate(alu_result.get("operations", [])):
        bank.push_all([op.get("value", 0.0) for _ in range(4)])
    
    # Generate the creative synthesis
    synthesis = {
        "answer": answer,
        "alu_primitives": alu_result,
        "conv_transform": conv_result,
        "ringbuf_state": bank.pop_all(),
        "iteration_count": len(alu_result.get("operations", [])),
    }
    
    # Inject synthesis into the answer
    answer = (
        f"{answer}\n\n"
        f"[PHOTONIC SYNTHESIS] {synthesis['iteration_count']} operations composed. "
        f"Ring-buffer state: {synthesis['ringbuf_state']}. "
        f"Convolution kernel: {synthesis['conv_transform']['operation']}."
    )
    
    return answer
```

---

## Complete Integration Map: Tool → Reasoning → Tool Cycles

```
┌─────────────────────────────────────────────────────────────────────┐
│                    AGENT LOOP REASONING CYCLE                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐      │
│  │          │    │          │    │          │    │          │      │
│  │ PLAN     │───▶│ TOOL     │───▶│ EXECUTE  │───▶│ GROUND   │      │
│  │ PHASE    │    │ SELECT.  │    │ PHASE    │    │ PHASE    │      │
│  │          │    │          │    │          │    │          │      │
│  │ verify   │    │ cmat     │    │ live     │    │ quant    │      │
│  │ ringbuf  │    │ dspy     │    │ ringbuf  │    │ verify   │      │
│  │ tokenstep│    │          │    │ cmat     │    │ ringbuf  │      │
│  │          │    │          │    │ quant    │    │ energy   │      │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘      │
│       │                │                │                │          │
│       ▼                ▼                ▼                ▼          │
│  [PLAN REVISED]  [TOOLS         [HARDWARE      [QUANT-GROUNDED]    │
│  if fail        RE-RANKED]       DIVERGENCE?]     if mismatch      │
│                                                                  │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐      │
│  │          │    │          │    │          │    │          │      │
│  │ REFLECT  │◀───│ SYNTHESIZE│◀───│ RECOVER  │◀───│ ERROR    │      │
│  │ PHASE    │    │ PHASE    │    │ PHASE    │    │ HANDLING │      │
│  │          │    │          │    │          │    │          │      │
│  │ energy   │    │ token_alu│    │ verify   │    │ ringbuf  │      │
│  │ thermal  │    │ conv     │    │ live     │    │ live     │      │
│  │ osnr     │    │ ringbuf  │    │ ringbuf  │    │ verify   │      │
│  │ adaptive │    │          │    │ quant    │    │ tokenstep│      │
│  │ q        │    │          │    │          │    │          │      │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘      │
│       │                │                │                │          │
│       ▼                ▼                ▼                ▼          │
│  [PHYSICS-CONSTRAINED] [CREATIVE    [STATE RESTORED] [CONTINUED]   │
│  REFLECTION]         SYNTHESIS]                                  │
│                                                                  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Summary of Modification Points

| # | Juncture | pcomp Tools | Modification | Failure Recovery |
|---|----------|-------------|-------------|-----------------|
| 1 | Pre-Reasoning Plan | `verify`, `tokenstep` | Plan validated against gates; budget set by tokenstep | Prune failed steps; abort if no viable plan |
| 2 | Tool Selection | `cmat`, DSPy | cmat-weighted ranking; DSPy provider routing | Fallback to semantic-only ranking |
| 3 | Tool Execution | `live`, `ringbuf` | Hardware-grounded execution; ringbuf state continuity | Hardware divergence → backtrack; ringbuf reset |
| 4 | Numeric Grounding | `quant`, `verify` | ADC-quantized ground truth for answer verification | Force reflection on mismatch; apply quant correction |
| 5 | Error Recovery | `verify`, `ringbuf`, `live` | State machine with DEGRADED/RECOVERING/FAILED states | Ringbuf reset + verify re-check; live reinit |
| 6 | Reflection | `energy`, `thermal`, `osnr` | Physics-constrained reflection replaces self-critique | Independent verifier when violations exist |
| 7 | Budget Enforcement | `tokenstep`, `adaptive_q` | Lockstep-paced budget; adaptive Q-factor scaling | Aggressive compression or relaxation |
| 8 | Provider Routing | `verify` + DSPy | Verify gate results as training labels for DSPy | Fallback provider on verify failure |
| 9 | Creative Synthesis | `token_alu`, `conv`, `ringbuf` | Structured computational primitives for creative tasks | Degrade to text-only synthesis |

---

## Key Design Principles

1. **pcomp as reasoning primitive, not just utility**: Each tool provides a *grounding signal* that the LLM can reason about, not just a yes/no verification.

2. **Bidirectional flow**: pcomp results both constrain the LLM (as input) and are shaped by the LLM (as output). The ringbuf captures this bidirectional state.

3. **Failure is a first-class signal**: Hardware divergence, verify gate failures, and quantization mismatches aren't errors to suppress — they're **reasoning triggers** that redirect the agent's logic.

4. **Creative beyond verification**: `token_alu`, `conv`, and `ringbuf` aren't just for checking correctness — they're primitives for **generating** new content (circuit designs, transformation compositions).

5. **DSPy + pcomp feedback loop**: The verify gates produce quality labels that train the DSPy router, which selects better providers, which produce more correct outputs, which pass verify gates. This is a self-improving cycle.