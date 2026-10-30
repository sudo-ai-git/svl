---
name: web-swarm
description: Coordinate parallel agent swarms for web research, scraping, and data extraction. Use when tasks require fetching/analyzing multiple URLs, comparing sources, aggregating search results, or any web task that benefits from parallelization.
---

# Web Swarm

Orchestrate multiple sub-agents for parallel web operations.

## Core Tools Available

- `web_search` — Brave Search API (fast, structured results)
- `web_fetch` — Extract readable content from URLs (HTML → markdown)
- `browser` — Full browser automation (JS-heavy sites, screenshots, interactions)
- `sessions_spawn` — Spawn isolated sub-agents for parallel work

## When to Swarm vs Sequential

**Use swarm when:**
- Fetching 3+ URLs that don't depend on each other
- Comparing information across multiple sources
- Research requiring diverse search queries
- Time-sensitive data gathering

**Stay sequential when:**
- URLs depend on previous results (pagination, auth flows)
- Single source of truth
- Simple single-page extraction

## Swarm Patterns

### Pattern 1: Parallel URL Extraction

```
Task: Extract data from [url1, url2, url3, url4]

Spawn 4 agents:
  Agent 1: web_fetch url1 → extract [specific fields]
  Agent 2: web_fetch url2 → extract [specific fields]
  Agent 3: web_fetch url3 → extract [specific fields]
  Agent 4: web_fetch url4 → extract [specific fields]

Aggregate: Combine results, dedupe, format
```

Implementation:
```python
# Spawn with sessions_spawn for each URL
sessions_spawn(
  task=f"Fetch {url} and extract: {fields}. Return JSON.",
  label=f"fetch-{i}"
)
```

### Pattern 2: Multi-Query Research

```
Task: Research [topic] comprehensively

Spawn agents by angle:
  Agent 1: web_search "[topic] overview" → summarize top 3
  Agent 2: web_search "[topic] problems" → list issues  
  Agent 3: web_search "[topic] alternatives" → compare options
  Agent 4: web_search "[topic] recent news" → timeline

Synthesize: Merge into comprehensive report
```

### Pattern 3: Browser Swarm (JS-heavy sites)

For sites requiring JS rendering:
```
1. Start browser: browser action=start
2. For each target:
   - browser action=open targetUrl=URL
   - browser action=snapshot (get page structure)
   - browser action=act (interact if needed)
   - Extract data from snapshot
3. Aggregate results
```

Note: Browser is single-instance. For true parallelism on JS sites, spawn agents that each manage browser sequentially, or use web_fetch for static content.

## Data Manipulation

### Extraction Patterns

**From web_fetch markdown:**
```python
# Parse structured content
import re
headers = re.findall(r'^##\s+(.+)$', content, re.MULTILINE)
links = re.findall(r'\[([^\]]+)\]\(([^)]+)\)', content)
```

**From browser snapshot:**
- Snapshots return accessibility tree (refs like `e12`, `button "Submit"`)
- Use refs to target elements for interaction
- Extract text content directly from snapshot

### Aggregation Script

See `scripts/aggregate.py` for combining swarm results:
```bash
python3 scripts/aggregate.py results/*.json --output combined.json
```

## Task Template

When spawning web swarm agents, use this task format:

```
Fetch [URL] and extract:
- [field1]: [description]
- [field2]: [description]

Return as JSON:
{"field1": "...", "field2": "..."}

If data not found, return {"error": "reason"}
```

## Error Handling

- Set `runTimeoutSeconds` on spawns (default: 120s for web tasks)
- Check for `{"error": ...}` in responses
- Retry failed URLs with `web_fetch` fallback if browser fails
- Log failures to `memory/YYYY-MM-DD.md` for pattern detection

## Model Selection

See `references/model-selection.md` for full guide.

**Quick rules:**
- **Opus** — orchestration only (main session)
- **Sonnet** — default for spawned workers
- **Haiku** — bulk extraction (5+ parallel tasks)

```python
# Standard worker
sessions_spawn(task="...", model="anthropic/claude-sonnet-4")

# Bulk extraction
sessions_spawn(task="...", model="anthropic/claude-3-haiku-20240307")
```

Stagger spawns if hitting rate limits. Batch similar tasks when possible.

## Example: Product Comparison

```
User: Compare prices for "Sony WH-1000XM5" across Amazon, Best Buy, Walmart

Plan:
1. Spawn 3 agents, one per retailer
2. Each searches/fetches product page
3. Extracts: price, availability, shipping
4. Aggregate into comparison table

Task for each agent:
"Search [retailer] for 'Sony WH-1000XM5'. Find the product page.
Extract: price, availability, shipping estimate.
Return JSON: {retailer, price, available, shipping, url}"
```
