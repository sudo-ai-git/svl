# TOOLS.md - Local Notes

## Model Selection (Quick Ref)

| Task Type | Model | Why |
|-----------|-------|-----|
| Orchestration, complex reasoning | `claude-opus-4` | Main session only |
| Standard workers, research | `claude-sonnet-4` | Default for spawns |
| Bulk extraction (5+ tasks) | `claude-3-haiku` | Cheap, fast, high rate limit |

**Rate limit (Opus):** 10k input tokens/min — don't spawn Opus sub-agents.

## Environment

- Python 3.12.3
- Node 22.22.0
- curl/wget available
- chromium browser (headless available)
- jq: NOT installed

---

## Setup Notes

*(Add cameras, SSH hosts, TTS voices, etc. as learned)*
