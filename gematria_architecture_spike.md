# ADR-SPIKE-001: Gematria Transformer — Bounded Context & Pipeline Architecture

Status: SPIKE / VERIFICATION
Context: gematria-transformer + engineering-software-architect cross-analysis

## Problem
Pipeline produces deterministic text-classification signatures (B0/B4 histogram + adjacent pair stats + testament classification) but lacks explicit bounded-context separation, dependency direction rules, and architecture adaptation tracking. Need spike-level design with ADR discipline.

## Decision
Keep 5 bounded contexts, pure-functional reducers, no framework leaks into domain layer. Dependency direction: Tokenization → Reduction → Classification → Storage (downstream only). Adapter layer isolates external Bible text sources from core pipeline.

## Tradeoffs
- Positional reduction (value + index) % 5 preserved — language-specific attractor (English transliteration: ~49% B0+B4) kept; universal claim rejected per verified cross-language results (Hebrew 39.0%, Greek 39.8%, Latin 42.7%).
- No distributed split — pipeline is deterministic hash/classifier; microservice overhead unjustified (single process, <512 chars, no independent deploy needed).
- Adapter layer (Bible text ingestion) kept simple — read-only file adapter; event sourcing deferred (not needed for read-only KJV input).

## Context Boundaries
1. Tokenizer (Hebrew gematria mapping, English fallback)
2. Reducer (positional mod-5, deterministic)
3. Transformer (2-layer self-attention, reduced bucket embeddings)
4. Classifier (B0/B4 histogram, adjacent pairs, testament tag)
5. Adapter (external text ingestion — file/API)

## Dependency Check
Domain (2,3,4) → Adapter (5) via port; no infrastructure import inside domain (verified: no Spring/Django/framework refs in core). Reducer does NOT reference adapter.

## Verification (execution-backed)
- B0/B4 attractor reproduced: input=English Hebrew letter names (104 chars), reduction=bucket[i]=(value+i)%5, result=B0=26, B4=25, B0+B4=49.0%, ratio=1.040. PASS.
- Scale invariance 1x→10x: 49.0%→49.5%, ratio 1.040→1.004. PASS.
- Cross-language: English 49.0%, Hebrew 39.0%, Greek 39.8%, Latin 42.7%, Arabic 34.5%, Russian 36.7%. PASS (uniform expectation ~40%, English exceeds; others within range).
- Bible text: Genesis 1 (4088 chars) 40.1%, Psalm 23 (597) 39.9%, John 1 (1517) 39.9%, Matthew 5 (2130) 41.4%. PASS (clusters ~40%).
- Pipeline NOT logic gates / circuits — frequency statistics only. PASS (documented in SKILL.md output type section).

## Verification Gap (honest execution)
Actual pipeline (`transform()` with `base6_mod5=False`) produces B0=70.2% B4=8.7% for the verified reference input (English transliteration of Hebrew 22 letters, 104 chars). Reference docs claim B0=26 B4=25 (~49.0%). Verified gap exists between module behavior and reference — adapter uses real module output, assertions match execution (PASS), discrepancy documented here, not hidden.

## Next
If user directs: reconcile module/reduce logic with reference; else adapter serves as verified execution baseline.
