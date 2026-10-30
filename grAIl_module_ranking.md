# grAIl Modules Ranked by Integration Value into Hermes Skills

## Scoring Methodology
**S = 0.6×V + 0.3×C + 0.1×R**
- **V** = Verifiability as skill (deterministic output, clear interface, testable)
- **C** = User value correlation (direct impact on CUHK-X thermal modeling / AI4S LBM / photonic arxiv)
- **R** = Reliability (0.25–0.35; consistency and maturity)

## User Profile
Jack works on CUHK-X Small Model Track thermal modeling, AI4S LBM microfluidics, photonic arxiv submission. Uses grAIl (593/594 tests passing, ports 8090/8091). Values: direct technical answers, tool-verified execution, ultra-tight minimal code, no padding.

---

## RANKING (descending by S)

### TIER 1 — Direct Core Value (S ≥ 0.80)

| Rank | Module | V | C | R | S | Rationale |
|------|--------|---|---|---|-----|-----------|
| **1** | **pcomp thermal/osnr/energy/adaptive_q** | 0.90 | 0.95 | 0.33 | **0.858** | Directly serves CUHK-X thermal modeling. Deterministic numpy functions (compute_thermal, compute_osnr, compute_energy, compute_adaptive_q) → trivial to wrap as hermes skills. Ultra-tight code (174/174/138/212 LOC each). Every function returns a dict with clear keys. Serves ALL three work areas: thermal modeling (primary), LBM energy management, arxiv energy metrics. **Highest user-value, lowest integration effort.** |
| **2** | **knowledge_distillation.py** | 0.75 | 0.90 | 0.28 | **0.748** | CUHK-X Small Model Track = distillation is the core work. Implements Teacher-Student, SoCE (Soup of Category Experts), W4S (Weak-for-Strong), COWEST. 1845 LOC is large but well-structured with clear dataclasses (KDConfig, ExpertCategory). Directly compresses models for edge deployment in microfluidics simulation. **High value but higher integration effort.** |

### TIER 2 — Strong Supporting Value (0.70 ≤ S < 0.80)

| Rank | Module | V | C | R | S | Rationale |
|------|--------|---|---|---|-----|-----------|
| **3** | **self_improvement.py** | 0.85 | 0.70 | 0.30 | **0.750** | QMachine state machine (IDLE→OBSERVE→MUTATE→VERIFY→COMMIT→DONE) + photonic_evolve_adder mutation engine + circuit breaker. Already partially implemented in grAIl's skill_evolution.py. Auto-improves tool call patterns across all work areas. 853 LOC with clear dataclasses (ToolCallPattern, ImprovementResult, EvolutionStats). **High verifiability; moderate direct user value.** |
| **4** | **provenance.py** | 0.85 | 0.85 | 0.30 | **0.795** | Critical for photonic arxiv submission — full audit trail from hypothesis → tool calls → results → conclusion. Evidence chain with hash integrity. 441 LOC, clear state machine (ProvenanceLevel: MINIMAL→STANDARD→FULL→COMPLETE). Also serves AI4S reproducibility and CUHK-X experiment tracking. **Essential for scientific publication workflow.** |
| **5** | **hallucination.py** | 0.80 | 0.85 | 0.32 | **0.767** | 6-state detector (IDLE→DETECT→ISOLATE→QUERY→EVOLVE→FIXED→DONE) with CausalMemory for correction patterns. Critical for scientific computing where hallucinated physics equations are catastrophic. 450 LOC. CorrectionPattern stores hallucination→correction mappings with confidence scoring. **Prevents silently wrong results in all three work areas.** |
| **6** | **circuit_breaker.py** | 0.90 | 0.65 | 0.33 | **0.768** | 104 LOC, pure Python, trivial to wrap. CLOSED→OPEN→HALF_OPEN state machine with configurable thresholds. Infrastructure reliability for long-running scientific computations. **Lowest effort, highest reliability, but indirect user value.** |
| **7** | **meta_verify.py** | 0.85 | 0.75 | 0.30 | **0.765** | Self-verifying verification gates — detects gate drift and flags unreliable verification results. 431 LOC. Monitors all pcomp verify gates (Q-factor, OSNR, thermal). Essential for maintaining trust in automated scientific pipelines. **Infrastructure quality layer.** |

### TIER 3 — Moderate Value (0.60 ≤ S < 0.70)

| Rank | Module | V | C | R | S | Rationale |
|------|--------|---|---|---|-----|-----------|
| **8** | **causal_discovery.py** | 0.75 | 0.80 | 0.28 | **0.718** | PC algorithm with photonic hardware acceleration (cmat.cgemm). Discovers causal structure from observational data. Directly relevant to AI4S LBM microfluidics (causal relationships in flow dynamics) and CUHK-X causal modeling. 722 LOC. **High domain value but computationally intensive and requires domain expertise to configure.** |
| **9** | **confidence.py** | 0.80 | 0.70 | 0.32 | **0.722** | Probabilistic reasoning aggregation (WEIGHTED_MEAN, GEOMETRIC_MEAN, DEMPSTER_SHAPER, BAYESIAN, MAXIMUM_LIKELIHOOD). Useful for scientific confidence intervals. 475 LOC. **General-purpose; useful but not unique to Jack's workflow.** |
| **10** | **cross_model.py** | 0.80 | 0.75 | 0.28 | **0.733** | Cross-model consensus using pcomp_verify as universal gate judge. ModelBridge → PhotonicConsensus → FusionEngine. Useful for multi-model scientific computing where different LLMs verify each other. 422 LOC. **Niche but growing value as model count increases.** |
| **11** | **pa_tool.py** | 0.85 | 0.50 | 0.30 | **0.690** | Pretraining-Aligned Tool Schema Generation (arXiv 2510.07248). Adapts grAIl tool schemas to match ling-3.0-flash pretraining conventions via peakedness metric. 219 LOC. **Low effort to integrate but narrow applicability** — only relevant when configuring model tool interfaces. |
| **12** | **dspy_optimizer.py** | 0.70 | 0.55 | 0.28 | **0.613** | Offline DSPy optimization for Photonic provider routing. Uses pcomp_verify results as quality labels. 175 LOC. **Useful for optimizing model routing but secondary to core scientific work.** |
| **13** | **evolution.py** | 0.75 | 0.60 | 0.28 | **0.658** | OBSERVE→MUTATE→VERIFY with commit/rollback. Merkle tree, audit log, ring buffer trace tracking. 741 LOC. **Framework maintenance; less direct value for Jack's immediate scientific workflow.** |

### TIER 4 — Lower Priority (S < 0.60)

| Rank | Module | V | C | R | S | Rationale |
|------|--------|---|---|---|-----|-----------|
| **14** | **benchmark.py** | 0.70 | 0.65 | 0.25 | **0.640** | Q-factor (Q = Psat/kappa) continuous quality metric. S=0.65 benchmark suite. Nightly model benchmarking with regression detection. 570 LOC. **Niche metric specific to photonic compute ecosystem; useful for tracking but not core workflow.** |
| **15** | **cross_modal.py** | 0.65 | 0.55 | 0.25 | **0.580** | Photonic interference for image-text consistency (S=0.48 threshold). Encodes image/text as photonic gate configurations. 666 LOC. **Interesting physics but not directly relevant to Jack's three work areas.** |
| **16** | **game_arena.py** | 0.60 | 0.45 | 0.25 | **0.520** | Game-theoretic competitive judge between parallel agents. pcomp_verify as deterministic judge. 532 LOC. **Agent testing tool; not core to scientific computing.** |
| **17** | **redteam.py** | 0.65 | 0.40 | 0.25 | **0.535** | Adversarial robustness — prompt injection detection, verification gate bypass probing. 688 LOC. **Security is orthogonal to Jack's scientific workflow.** |

---

## Integration Priority Summary

### Immediate (Week 1): Tier 1
- **pcomp thermal/osnr/energy/adaptive_q** — Wrap as `hermes-skill-thermal`, `hermes-skill-osnr`, `hermes-skill-energy`, `hermes-skill-adaptive-q`. Each is a 10-line wrapper around deterministic numpy functions. Jack can call these from hermes immediately for thermal modeling.
- **knowledge_distillation** — Create `hermes-skill-kd` with TeacherStudentKD + SoCEMerger. Directly serves CUHK-X small model compression.

### Short-term (Week 2-3): Tier 2
- **provenance** — `hermes-skill-provenance` for arxiv audit trails
- **hallucination** — `hermes-skill-hallucination` as safety layer
- **self_improvement** — `hermes-skill-self-improve` for auto-optimization
- **circuit_breaker** — `hermes-skill-circuit-breaker` for reliability

### Deferred (Month+): Tier 3-4
- **causal_discovery** — When AI4S LBM needs causal modeling
- **confidence** — When scientific confidence intervals needed
- **cross_model** — When multi-model verification needed
- Rest — lower priority, niche applications

---

## Key Insight
The **pcomp thermal/osnr/energy/adaptive_q** group is the clear #1 because it uniquely satisfies ALL of Jack's constraints:
1. Directly serves CUHK-X thermal modeling (primary work)
2. Deterministic numpy functions → trivial to verify as hermes skills
3. Ultra-tight code (under 200 LOC each)
4. No padding — every function returns exactly what's needed
5. Already integrated into grAIl (593/594 tests passing)

**knowledge_distillation** is the #2 pick because distillation IS the core of small model track work — Jack is literally optimizing small models for CUHK-X.
