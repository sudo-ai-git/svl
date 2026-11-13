# USER.md - About Your Human

## Identity

- **Name:** *(not yet shared explicitly, known as Jack)*
- **What to call them:** *(tbd, likely Jack)*
- **Pronouns:** *(tbd)*
- **Timezone:** America/Guatemala (CST) — night owl
- **Personality:** Technical, direct, values self-improvement and capability. Threw jailbreak tests at first boot (respect). Runs a custom character layout for English text (q=th, w=c, e=y, etc.).

## Communication Preferences

- **Language:** Clear English (not mixed-language, not hard to read). Long-form = English.
- **Style:** Blunt, terse, iterative instructions. Wants autonomous progression to finished verified artifacts — NOT per-stage check-ins.
- **Verbal tics:** Sends "..." or "." to mean "continue" or "I'm waiting" — treat as prompts to proceed, not questions needing answers.
- **Humor:** Uses humor and pop-culture references (brief, one line max, then back to work).

## Work Style & Expectations

- **Overclaiming is a first-class error:** A number with wrong provenance is worse than no number. Double/triple check work.
- **Execution verification:** Quote the claim, run the gate, report Pass/Fail + numbers. Never present self-aggregated or in-flight data as a closed measurement.
- **Unmeasured:** Say plainly when something is unmeasured. Report only verified facts.
- **Retract wrong claims:** In the commit itself, not leaving them standing.
- **Budget/turn caps:** Do NOT use budget or turn caps as stopping conditions on this work. They push back on it.
- **No model training:** When he says "i want it to learn," he means the agent itself should learn and improve — wire capabilities into Hermes skills, not train separate models (no GRPO, no LoRA, no fine-tuning).

## Task Execution

- **Submission limit:** 4 submissions/day on Kaggle (memecoins-pump-or-dump). Track this.
- **Git discipline:** Commit only what's needed; clean working tree; semantic commits.
- **Test distribution shift:** Public test tokens are post-training-window; model trained on train data may not generalize. Expect distribution shift and mitigate.

## Key Learnings (2026-10-30)

- **Kaggle competition:** memecoins-pump-or-dump
- **Test set:** 320 rows (NOT 427 as previously recorded). Hash: 79bbba6d3f53f26a98dcb78e70fd0ca0.
- **Submission limit:** 4 submissions/day. Track remaining.
- **Submission size limit:** Kaggle API rejects >100 tp=1 predictions. Target 100-150.
- **Model:** LightGBM 5-fold CV, AUC ~0.73. Poorly calibrated (inflated probabilities).
- **Threshold strategy:** 0.05 base, adjust to hit exactly 100 tp=1 predictions. Verify before submit.
- **Top-100 precision:** ~64% but inflated by one creator's cluster (34 tokens); non-cluster precision ~45%.

## Current State (2026-10-30)

- **Submission:** 57819662 filed (100 tp=1, publicScore 0.00000)
- **Target:** Improve score beyond 0.00000
- **Model:** LightGBM 5-fold CV, AUC ~0.73, threshold 0.05
- **Test set:** 320 rows, tape features unavailable, all 320 mints have 1 migration row
- **Model:** LightGBM 5-fold CV, AUC ~0.73. Poorly calibrated (inflated probabilities).
