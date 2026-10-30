# Model Selection Guide

Match model to task complexity. Avoid burning Opus tokens on simple extraction.

## Tiers

| Model | Use For | Rate Limit | Cost |
|-------|---------|------------|------|
| `claude-opus-4` | Complex reasoning, orchestration, multi-step planning | 10k input/min | $$$ |
| `claude-sonnet-4` | Standard tasks, research, code generation | Higher | $$ |
| `claude-haiku-3` | Simple extraction, formatting, quick lookups | Highest | $ |

## Task → Model Mapping

### Use Opus (orchestrator only)
- Multi-agent coordination
- Complex analysis requiring deep reasoning
- Ambiguous tasks needing judgment
- Final synthesis of swarm results

### Use Sonnet (default for sub-agents)
- Web research and summarization
- Code writing and review
- Data extraction from structured sources
- Most spawned tasks

### Use Haiku (high-volume workers)
- Simple field extraction
- Format conversion
- Yes/no classification
- Bulk processing (10+ parallel tasks)

## Implementation

```python
# Orchestrator spawns workers on Sonnet
sessions_spawn(
    task="Research X and summarize",
    model="anthropic/claude-sonnet-4"
)

# Bulk extraction uses Haiku
sessions_spawn(
    task="Extract price from this text: {text}",
    model="anthropic/claude-3-haiku-20240307"
)
```

## Rate Limit Strategy

1. **Stagger spawns** — don't fire 8 agents simultaneously
2. **Batch similar tasks** — one agent handles multiple URLs vs one per URL
3. **Use lighter models** — Haiku for extraction, Sonnet for synthesis
4. **Queue when limited** — if 429, wait 60s and retry

## Decision Tree

```
Is this task complex reasoning/planning?
├─ Yes → Opus (or keep in main session)
└─ No
   Is this high-volume (5+ parallel)?
   ├─ Yes → Haiku
   └─ No → Sonnet
```
