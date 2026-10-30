# grAIl + pcomp: Cutting-Edge Research Brainstorm

**Date:** 2026-09-26  
**Context:** Builds on existing 10 next-gen ideas (pcomp_nextgen_ideas.md) and 7 reasoning patterns (pcomp_reasoning_patterns.md). This document proposes NEW ideas targeting 7 specific cutting-edge research directions not yet covered by existing proposals.

---

## Direction 1: Neural Symbolic Reasoning

### Idea N1: Photonic Attention-Substrate Symbolic Grounding

**Problem:** LLM attention mechanisms operate on floating-point vectors with no intrinsic symbolic structure. Symbolic reasoning (logic, deduction, constraint satisfaction) is bolted on as post-hoc verification, not embedded in the computation itself.

**Concept:** Replace the LLM's attention sub-layer computation with a photonic circuit that performs symbolic operations. Each attention head's QKV projection becomes a photonic matrix multiply (`cmat.phase_matvec()`), but the circuit topology is *constrained to implement symbolic logic gates* rather than generic linear transforms. The LLM's "neurons" become photonic gates — the weights aren't learned floats but configurable photonic phases that implement specific logical rules.

**Why it's NEW:** Existing ideas use pcomp as a verification layer *after* LLM generation (Idea 1) or as a deterministic memory substrate (Idea 2). This makes photonic circuits the *computational substrate of the LLM itself* — the attention mechanism is physically instantiated as optical logic, not just verified by it.

**Architecture:**
```
Input tokens → Photonic QKV Projection (cmat, constrained to symbolic gate topology)
              → Photonic Attention (ringbuf stores key-value pairs as phase registers)
              → Photonic Output Projection (token_alu combines head outputs)
              → Symbolic verification gate (verify confirms logical consistency)
              → LLM continues autoregressive generation
```

**Key mechanism:** The `cmat` matrix multiplication is constrained by the photonic gate topology to implement specific symbolic operations:
- An attention head can be configured to implement `AND` logic (both queries and keys must match)
- Another head implements `XOR` (exclusive feature matching)
- The ringbuf stores the symbolic state transitions (rule activations)
- `verify` gates confirm that the photonic attention output satisfies the intended symbolic constraint

**Novel property:** The LLM's attention becomes a *physically symbolic* computation — not floating-point approximation of symbolic logic, but photonic logic that IS symbolic. The determinism of the photonic circuit guarantees that the same symbolic rule produces the same attention pattern every time.

**Relevant pcomp tools:** cmat (symbolic-constrained matrix multiply), ringbuf (symbolic state storage), token_alu (head output combination), verify (symbolic consistency check), photonic_gate (attention head topology)

---

## Direction 2: Causal Reasoning

### Idea N2: cmat Causal Discovery Engine (Photonic Inversion)

**Problem:** Causal reasoning requires inferring cause-effect relationships from observational data. Standard LLMs have no mechanism for causal inference — they correlate, they don't intervene. Pearl's do-calculus requires explicit structural causal models (SCMs), which LLMs cannot construct.

**Concept:** Use `cmat` as a causal structure discovery engine. The photonic matrix multiply is run in *inversion mode* — given observational data (matrix of variable states), compute the inverse covariance matrix to identify conditional independencies, which map to causal graph edges. The `verify` gates then test each inferred edge against interventional data (do-operations).

**Why it's NEW:** Existing ideas use cmat for general computation (Idea 1, 5) or cost computation (Idea 4). This makes cmat a *causal inference engine* — the photonic circuit's linear algebra properties (eigenvalue decomposition, matrix inversion) directly implement causal discovery algorithms (PC algorithm, LiNGAM) at hardware speed.

**Architecture:**
```
Observational data matrix X (N samples × K variables)
         │
         ▼
cmat.phase_matvec(inversion_kernel, X) → Inverse covariance Θ
         │
         ▼
Θ[i,j] ≈ 0 ↔ conditional independence ↔ no causal edge
         │
         ▼
Verify gates test inferred edges:
  "If I intervene on X_i, does X_j change?"
  → cmat computes do-calculus projection
  → verify confirms causal direction
         │
         ▼
Causal DAG stored in ringbuf (topological ordering)
```

**Key mechanism:** 
- The photonic circuit's natural ability to compute matrix inverses (via phase_matvec with inverse kernels) directly implements the PC algorithm's conditional independence testing
- `cmat.phase_matvec()` with a *causal discovery kernel* produces the precision matrix whose zeros encode the causal graph
- The ringbuf stores the evolving causal graph as interventions are performed
- `adaptive_q` adjusts the precision of causal edge detection: high Q = confident edges, low Q = tentative edges requiring more data

**Novel property:** Causal discovery becomes a *photonic linear algebra operation* rather than a statistical procedure. The optical circuit's inherent parallelism evaluates all conditional independencies simultaneously — exponentially faster than sequential PC algorithm steps.

**Relevant pcomp tools:** cmat (inverse covariance computation), verify (interventional testing), ringbuf (causal graph state), adaptive_q (precision control), token_alu (graph edge arithmetic)

---

## Direction 3: Analogical Reasoning

### Idea N3: Ringbuf Analogy Engine (Phase-Coherent Analogy Retrieval)

**Problem:** Analogical reasoning — "This problem is structurally similar to that one, so the solution should transfer" — is powerful but unreliable in LLMs. They lack a structured analogy database and a mechanism to compute structural similarity between problems.

**Concept:** The optical ring-buffer becomes an *analogy store* where each entry is a (problem_structure, solution) pair encoded as photonic phase values. The ringbuf's phase coherence property provides a *physical similarity metric*: when a new problem's phase representation overlaps with stored analogies, constructive interference indicates structural similarity. This implements the "structure mapping theory" of analogy physically.

**Why it's NEW:** Existing ideas use ringbuf as working memory (Idea 2, 7), state machine (Idea 1), or trajectory recorder (Idea 8). This transforms the ringbuf into an *analogy retrieval system* where the optical physics literally computes analogy strength through phase coherence — not text similarity, but structural overlap.

**Architecture:**
```
New problem → encode as phase vector → push to ringbuf
         │
         ▼
Ringbuf phase coherence measurement:
  - Compute overlap between new problem's phase vector
    and each stored analogy's phase vector
  - Constructive interference = high structural similarity
  - Destructive interference = dissimilar
         │
         ▼
Top-K analogies retrieved (phase coherence ranking)
         │
         ▼
Solution transfer:
  - Retrieve the solution phase pattern from the matched analogy
  - Adapt it to the current problem using cmat (structural transformation)
  - Verify the adapted solution passes verification gates
```

**Key mechanism:**
- Each analogy is stored as a ringbuf entry with problem encoding (phase vector) and solution encoding (phase vector)
- The ringbuf's optical interconnect naturally computes inner products between phase vectors — this IS the structure mapping operation
- `cmat.phase_matvec()` performs the structural transformation (mapping from analogy's problem space to current problem space)
- The ringbuf's FIFO eviction creates a *forgetting mechanism* that prioritizes recent/relevant analogies
- `live.snapshot()` coherence measures the current "analogy temperature" — how analogical the reasoning currently is

**Novel property:** Analogy retrieval is a *photonic physics operation* — the optical circuit's coherence measurement literally computes which stored problems are structurally similar to the current one. This is fundamentally different from embedding-based retrieval (which computes semantic similarity); it computes *structural* similarity through wave interference.

**Relevant pcomp tools:** ringbuf (analogy store + coherence retrieval), cmat (structural transformation), live (analogy temperature), verify (solution validation), photonic_neuromorphic (analogy pattern matching)

---

## Direction 4: Creativity Scoring

### Idea N4: Photonic Entropy Novelty Scorer (E6 PUF as Creativity Meter)

**Problem:** LLMs cannot reliably measure the novelty or creativity of their outputs. They may produce outputs that are fluent but unoriginal, or original but incoherent. There is no objective "surprise" metric.

**Concept:** Exploit the E6 PUF/TRNG photonic circuit's entropy production as a creativity meter. The photonic PUF (Physical Unclonable Function) produces maximally random outputs when operated at its *threshold-detuned* point (low margin, m~0). An LLM's output can be encoded as a photonic challenge signal, and the PUF's response entropy directly measures how "surprising" or "novel" the output is relative to the PUF's training distribution.

**Why it's NEW:** Existing ideas use photonic evolution for ideation (Idea 5, Pattern 5) but don't provide a *quantitative creativity score*. This uses the PUF's physical entropy production as a first-class creativity metric — not a linguistic heuristic, but a hardware-measured novelty score grounded in information theory.

**Architecture:**
```
LLM generates output → encode output as photonic challenge (phase vector)
         │
         ▼
E6 PUF/TRNG circuit receives challenge:
  - Operate at threshold-detuned point (m~0, low margin)
  - Measure output entropy: H_min (min-entropy per gate)
  - High H_min (~0.94 bits/gate) = highly novel output
  - Low H_min (~0.0) = predictable/conventional output
         │
         ▼
Entropy-to-creativity mapping:
  - H_min > 0.8 → "Highly creative" (novel but may need coherence check)
  - H_min 0.5-0.8 → "Moderately creative" (good novelty)
  - H_min < 0.5 → "Conventional" (derivative of training data)
         │
         ▼
Coherence check (verify gate):
  - Creative output must still pass logical verification
  - Novelty without coherence = hallucination, not creativity
  - Coherence without novelty = conventional but correct
```

**Key mechanism:**
- The E6 PUF lesson (from photonic-circuit-composition skill) shows that threshold-detuned gates produce H_min ≈ 0.941 bits/gate — maximal entropy
- The LLM's output tokens are mapped to photonic phase challenges that drive the PUF
- The PUF's response distribution is measured: high entropy = the output is "surprising" the photonic substrate (which encodes the training distribution)
- `adaptive_q` adjusts the creativity threshold: high Q = strict creativity (only highly surprising outputs score high), low Q = lenient
- The ringbuf tracks creativity scores over time, enabling the system to recognize when it's becoming repetitive

**Novel property:** Creativity is *physically measurable* through photonic entropy production. The PUF's min-entropy directly quantifies how much the LLM's output deviates from its training distribution — not through linguistic heuristics, but through the physics of information production.

**Relevant pcomp tools:** photonic_evolve_gate (PUF threshold configuration), cmat (output encoding), ringbuf (creativity history), verify (coherence check), adaptive_q (creativity threshold), osnr (signal clarity for entropy measurement)

---

## Direction 5: Multi-Modal Integration

### Idea N5: Photonic Cross-Modal Verifier (Image-Text Consistency through Optical Interference)

**Problem:** Multi-modal LLMs (e.g., GPT-4V, LLaVA) can produce text descriptions of images but have no mechanism to *verify* that the text faithfully represents the image. They hallucinate visual details. There is no objective cross-modal consistency check.

**Concept:** Encode both the image and the text description into photonic phase vectors. The `cmat` circuit computes their interference pattern. High constructive interference = the text description is photonic-consistent with the image. Destructive interference = the description misrepresents the image. The verify gate confirms this interference pattern matches a predefined "consistency threshold."

**Why it's NEW:** Existing ideas focus on text-only reasoning. This makes pcomp the *cross-modal verification substrate* — the photonic circuit literally computes whether text and image representations are consistent through optical interference, a fundamentally physical operation that has no text-only equivalent.

**Architecture:**
```
Image → photonic encoding (cmat: image features → phase vector Φ_img)
         │
Text → photonic encoding (cmat: text embeddings → phase vector Φ_txt)
         │
         ▼
cmat.phase_matvec(cross_modal_fusion, [Φ_img, Φ_txt])
         │
         ▼
Interference pattern:
  - High constructive interference → text matches image
  - Destructive interference → text hallucinates or omits
         │
         ▼
Verify gate:
  - Interference strength > threshold → PASS (text is faithful)
  - Interference strength < threshold → FAIL (hallucination detected)
         │
         ▼
Ringbuf stores verified (image, text) pairs as cross-modal analogies
```

**Key mechanism:**
- The image is encoded as a photonic phase vector through a learned encoding network (photonic_neuromorphic trained on image features)
- The text is encoded as a photonic phase vector through a separate encoding network (trained on text embeddings)
- `cmat.phase_matvec()` computes the cross-modal interference — this is the physical implementation of a consistency function
- The verify gate's threshold is calibrated: it must reject clearly inconsistent pairs while accepting faithful descriptions
- The ringbuf stores verified cross-modal pairs, building a growing library of (image, text) analogies that improve future verification
- `token_alu` performs the arithmetic of mapping between visual and textual phase spaces

**Novel property:** Cross-modal consistency is verified through *photonic interference* — the same physical phenomenon that makes optical computing fast also makes it the ideal tool for measuring representational alignment. The photonic circuit computes a multi-modal compatibility score that is fundamentally different from any text-based or vision-based metric.和解

**Relevant pcomp tools:** cmat (cross-modal interference computation), ringbuf (verified pair storage), verify (consistency threshold), photonic_neuromorphic (image/text encoders), token_alu (phase space mapping), live (real-time coherence monitoring)

---

## Direction 6: Self-Play

### Idea N6: Photonic Game-Theoretic Arena (pcomp_Verify as Impartial Judge)

**Problem:** In multi-agent settings, agents can collude, bias each other, or lack an objective evaluation mechanism. When agents "self-play" to improve, they need a judge that is genuinely impartial and deterministic — not another LLM that might be biased.

**Concept:** Two or more LLM agents compete in a game (coding challenge, math problem, strategic task). Their outputs are fed through the same deterministic pcomp verify gates. The verify gate's output (pass/fail across all 6 gates) is the *sole judge* — it's impartial because it operates on the photonic substrate independently of both agents' reasoning. The ringbuf stores the game history, and the live coprocessor monitors fairness (coherence between agents' submissions).

**Why it's NEW:** Existing ideas address multi-agent consensus (Idea 1) and cross-model bridges (Idea 5), but not *competitive self-play* with pcomp as judge. This transforms the verify gates from a correctness checker into a *game arbiter* — the same deterministic properties that make verification reliable also make it the fairest possible judge.

**Architecture:**
```
Agent A submits solution → verify gates → score_A
Agent B submits solution → verify gates → score_B
         │
         ▼
Photonic game-theoretic evaluation:
  - Both solutions evaluated through IDENTICAL verify gates
  - Gate results are compared: higher pass rate wins
  - Tie-breaker: cmat computes "solution elegance" metric
         │
         ▼
Ringbuf stores game history:
  - Each (agent, solution, score) triple recorded
  - Over time, reveals which agents improve fastest
  - Ringbuf FIFO eviction keeps most recent games
         │
         ▼
LiveCoprocessor monitors fairness:
  - Phase coherence between agents' submissions
  - If coherence is too high → possible collusion
  - If coherence is too low → fair competition
         │
         ▼
Evolutionary pressure:
  - Loser's strategy is evolved (photonic_evolve_adder)
  - Winner's strategy is reinforced
  - Next round: evolved strategies compete again
```

**Key mechanism:**
- The verify gates are the *impartial judge* — they don't know which agent produced which solution, they only evaluate the solution itself
- `cmat` provides a secondary "quality" score (solution elegance, efficiency) for tie-breaking
- The ringbuf's deterministic history creates a *reproducible tournament* — the same game state + same strategies always produces the same outcome
- `adaptive_q` adjusts the competition intensity: high Q = only top-scoring solutions survive (strong selection), low Q = more diversity maintained (exploration)
- `tokenstep` enforces equal time allocation: both agents get the same number of reasoning steps
- The system implements a photonic version of iterated tournament selection — strategies evolve through competition

**Novel property:** The judge is *physically impartial* — the photonic verification gates don't have preferences, biases, or awareness of which agent submitted what. They only evaluate the solution. This is fundamentally different from LLM-based judges that can be influenced by framing, prompting, or model identity.

**Relevant pcomp tools:** verify (impartial judge), cmat (quality scoring), ringbuf (game history), live (fairness monitoring), adaptive_q (selection pressure), tokenstep (equal time), photonic_evolve_adder (strategy evolution)

---

## Direction 7: World Models

### Idea N7: Photonic Learned Environment Model (Ringbuf + cmat as World Simulator)

**Problem:** LLMs have no internal world model — they don't understand how actions change the environment, they only predict next tokens. Reinforcement learning requires a world model to plan ahead, but LLMs can't simulate environment dynamics.

**Concept:** The optical ring-buffer + cmat combination becomes a *learned world model*. The ringbuf stores (state, action, next_state) tuples from environment interactions. The cmat learns the transition dynamics as a photonic matrix that maps (state, action) → next_state. The ringbuf's phase coherence provides the model's confidence in its predictions. The LLM can "think" by running the photonic world model forward — simulating what would happen if it took a specific action.

**Why it's NEW:** Existing ideas use ringbuf as memory (Idea 2, 3), state machine (Idea 1), or analogy store (Idea 3). This transforms the ringbuf + cmat into a *causal world simulator* — the photonic circuit literally predicts environment dynamics, enabling the LLM to reason about counterfactuals and plan through simulation.

**Architecture:**
```
Environment interaction loop:
  State S_t → Agent takes action A_t → Environment returns S_{t+1}
       │
       ▼
Ringbuf stores tuple: (S_t, A_t, S_{t+1})
       │
       ▼
cmat learns transition dynamics:
  - Matrix M maps (S_t, A_t) → predicted S_{t+1}
  - Trained on accumulated ringbuf tuples
  - Loss = ||M · (S_t, A_t) - S_{t+1}||²
       │
       ▼
World model simulation (planning):
  LLM imagines action A' → cmat predicts S_{t+1}' → cmat predicts S_{t+2}' → ...
  Ringbuf coherence = model confidence in prediction chain
  Long prediction chains = low coherence (uncertainty grows)
       │
       ▼
Verify gate validates simulated outcomes:
  - Does the predicted state make physical sense?
  - Is the predicted outcome consistent with known constraints?
```

**Key mechanism:**
- The ringbuf acts as the *experience replay buffer* — storing state-action-next_state triples
- `cmat.phase_matvec()` learns the transition function: the photonic matrix M is trained to predict next states
- The ringbuf's phase coherence measures *prediction confidence* — high coherence = the world model is confident about its prediction, low coherence = the model is uncertain
- `energy` constrains how far ahead the LLM can simulate (more steps = more energy)
- `thermal` indicates when the world model is overheating (too many predictions degrading accuracy)
- `osnr` measures signal clarity of the prediction — low OSNR = the world model's prediction is noisy
- `adaptive_q` adjusts prediction precision: high Q = precise short-term predictions, low Q = coarse long-term predictions

**Novel property:** The LLM has a *physically instantiated world model* — not a separate neural network but a photonic circuit that learns environment dynamics through optical matrix multiplication. The ringbuf provides the memory, cmat provides the dynamics, and the verify gates provide the sanity check. This is fundamentally different from using a separate world model neural network — it's a photonic, deterministic, physically-grounded simulation engine.

**Relevant pcomp tools:** ringbuf (experience replay + state storage), cmat (transition dynamics learning), verify (outcome validation), energy (prediction depth limit), thermal (model overheating), osnr (prediction clarity), adaptive_q (precision control), tokenstep (simulation steps)

---

## Cross-Direction Synthesis

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    CUTTING-EDGE GRail + pcomp ARCHITECTURE               │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐ │
│  │  N7: WORLD MODEL (Ringbuf + cmat as environment simulator)       │ │
│  │  LLM plans by simulating environment dynamics photonicly         │ │
│  └──────────────────────┬───────────────────────────────────────────┘ │
│                         │ feeds planning into                          │
│  ┌──────────────────────▼───────────────────────────────────────────┐ │
│  │  N2: CAUSAL REASONING (cmat inversion for causal discovery)      │ │
│  │  World model's causal structure informs which actions matter     │ │
│  └──────────────────────┬───────────────────────────────────────────┘ │
│                         │ enables                                    │
│  ┌──────────────────────▼───────────────────────────────────────────┐ │
│  │  N6: SELF-PLAY (pcomp_verify as impartial game judge)            │ │
│  │  World model simulates outcomes, verify judges agent performance  │ │
│  └──────────────────────┬───────────────────────────────────────────┘ │
│                         │ produces creative solutions                │
│  ┌──────────────────────▼───────────────────────────────────────────┐ │
│  │  N4: CREATIVITY SCORING (E6 PUF entropy as novelty meter)        │ │
│  │  Self-play produces candidates, PUF scores their novelty          │ │
│  └──────────────────────┬───────────────────────────────────────────┘ │
│                         │ requires cross-modal grounding            │
│  ┌──────────────────────▼───────────────────────────────────────────┐ │
│  │  N5: MULTI-MODAL VERIFIER (photonic interference for image/text) │ │
│  │  Creative outputs verified across modalities                      │ │
│  └──────────────────────┬───────────────────────────────────────────┘ │
│                         │ grounded in symbolic structure             │
│  ┌──────────────────────▼───────────────────────────────────────────┐ │
│  │  N1: NEURAL SYMBOLIC GROUNDING (photonic attention as logic)      │ │
│  │  Multi-modal inputs are symbolically grounded in photonic logic   │ │
│  └──────────────────────┬───────────────────────────────────────────┘ │
│                         │ analogical transfer enables                │
│  ┌──────────────────────▼───────────────────────────────────────────┐ │
│  │  N3: ANALOGICAL REASONING (ringbuf phase-coherent analogy)        │ │
│  │  Symbolic representations retrieved via photonic similarity        │ │
│  └───────────────────────────────────────────────────────────────────┘ │
│                                                                         │
├─────────────────────────────────────────────────────────────────────────┤
│ KEY INNOVATION THREADS:                                                  │
│ • Direction 1 (neural symbolic) makes photonic logic the LLM's brain    │
│ • Direction 2 (causal) makes cmat the discovery engine for why things   │
│   happen, not just what happens                                         │
│ • Direction 3 (analogical) makes ringbuf's physics compute similarity,  │
│   not just store data                                                   │
│ • Direction 4 (creativity) makes entropy a first-class creative metric  │
│ • Direction 5 (multi-modal) makes optical interference verify           │
│   cross-modal consistency                                               │
│ • Direction 6 (self-play) makes verify gates impartial judges           │
│ • Direction 7 (world models) makes cmat + ringbuf simulate reality      │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Summary Table

| # | Idea | Direction | Core Innovation | Key pcomp Tools | Novel Beyond Existing |
|---|------|-----------|----------------|-----------------|----------------------|
| N1 | Photonic Attention-Substrate Symbolic Grounding | Neural Symbolic | Photonic circuits as LLM attention substrate | cmat, ringbuf, token_alu, verify, photonic_gate | Attention IS photonic logic, not just verified by it |
| N2 | cmat Causal Discovery Engine | Causal Reasoning | Matrix inversion as causal structure learning | cmat, verify, ringbuf, adaptive_q | Hardware-speed PC algorithm via optical inversion |
| N3 | Ringbuf Analogy Engine | Analogical Reasoning | Phase coherence computes structural similarity | ringbuf, cmat, live, verify, photonic_neuromorphic | Physical wave interference = analogy retrieval |
| N4 | Photonic Entropy Novelty Scorer | Creativity Scoring | E6 PUF min-entropy as creativity meter | photonic_evolve_gate, cmat, ringbuf, verify, adaptive_q | Hardware-measured novelty, not linguistic heuristic |
| N5 | Photonic Cross-Modal Verifier | Multi-Modal Integration | Optical interference verifies image-text consistency | cmat, ringbuf, verify, photonic_neuromorphic, token_alu | Physical representational alignment check |
| N6 | Photonic Game-Theoretic Arena | Self-Play | pcomp_verify as impartial competitive judge | verify, cmat, ringbuf, live, adaptive_q, tokenstep | Physically impartial judge, not LLM-biased |
| N7 | Photonic Learned Environment Model | World Models | Ringbuf + cmat as causal world simulator | ringbuf, cmat, verify, energy, thermal, osnr, adaptive_q | Photonic deterministic environment simulation |

---

## Research Gaps & Open Questions

1. **Can photonic attention (N1) actually be trained?** The constraint that attention heads must implement symbolic logic gates limits the representational capacity. Can the ringbuf's phase registers be trained to adjust symbolic gate configurations?

2. **How many variables can cmat causal discovery (N2) handle?** Matrix inversion scales as O(N³) classically — but photonic matrix multiplication is O(1) depth. What is the practical limit on K variables for causal discovery?

3. **Is photonic similarity (N3) truly structural or just correlated with it?** Phase coherence between vectors may correlate with structural similarity but not perfectly capture it. How do we calibrate the ringbuf's coherence metric against human-defined analogy tasks?

4. **Does PUF entropy (N4) truly measure creativity or just randomness?** High entropy = surprising, but surprise ≠ creativity. The coherence check (verify gate) helps, but the mapping from entropy to meaningful creativity needs empirical validation.

5. **How does the cross-modal verifier (N5) handle ambiguity?** An image might be describable in multiple valid ways. How does the verify gate threshold handle "correct but different" descriptions?

6. **Can self-play (N6) converge to a stable equilibrium?** If both agents evolve strategies to pass the same verify gates, they may converge to the same solution — ending the competitive dynamic. How is diversity maintained?

7. **How far ahead can the world model (N7) reliably predict?** The ringbuf's coherence decays with prediction horizon. What is the practical prediction horizon for a photonic world model before uncertainty overwhelms the signal?

---

## Distinction from Existing 10 Ideas

| Existing Idea | What It Covers | Why These Are Different |
|---------------|----------------|------------------------|
| Ideas 1-10 (nextgen_ideas.md) | Multi-agent consensus, persistent memory, self-evolving strategies, planning topology, cross-model bridge, adaptive controller, quantum state machine, self-improvement loop, collaborative composition, thermodynamic optimization | Those are architecture-level proposals for how pcomp integrates into the agent loop |
| Ideas 1-7 (this document) | Neural-symbolic grounding, causal discovery, analogical retrieval, creativity scoring, cross-modal verification, self-play adjudication, world model simulation | These are *research directions* — they target specific cognitive capabilities that pcomp enables, not architectural integrations |
| Reasoning Patterns (patterns doc) | 7 patterns for embedding pcomp determinism into LLM reasoning | Those are implementation patterns for existing junctures; these are new research frontiers |
| Agent Loop Design (pcomp_agent_loop_design.md) | 9 junctures with specific code modifications | That's the current implementation; this brainstorm targets what comes AFTER current implementation |

---

## Research Priority Recommendation

Based on feasibility and impact:

1. **N4 (Creativity Scoring)** — Highest priority: requires minimal new hardware (E6 PUF already demonstrated), builds directly on existing photonic_evolve_gate skill, and has immediate practical applications for output quality assessment
2. **N7 (World Model)** — High impact: enables planning through simulation, builds on ringbuf + cmat which are already implemented, and connects directly to the existing planning juncture (Juncture 1)
3. **N6 (Self-Play)** — High feasibility: just uses verify gates as judges (already implemented), the game-theoretic framing is a new application layer
4. **N3 (Analogical Reasoning)** — Medium feasibility: ringbuf phase coherence is a physical property that needs empirical calibration against analogy benchmarks
5. **N2 (Causal Discovery)** — Medium feasibility: cmat matrix inversion is computable but needs validation on causal discovery benchmarks
6. **N5 (Cross-Modal)** — Medium feasibility: requires multi-modal encoders trained in photonic representation space, but the interference principle is sound
7. **N1 (Neural Symbolic)** — Longest timeline: requires rethinking the LLM attention mechanism to be photonic-native, which is a fundamental architectural change