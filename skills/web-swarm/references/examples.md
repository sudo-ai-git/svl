# Web Swarm Examples

## Example 1: Price Comparison Swarm

**Goal:** Compare laptop prices across 3 retailers

**Step 1: Define targets**
```
urls = [
  "https://amazon.com/s?k=macbook+pro",
  "https://bestbuy.com/site/searchpage.jsp?st=macbook+pro",
  "https://newegg.com/p/pl?d=macbook+pro"
]
```

**Step 2: Spawn scrapers**
```javascript
// For each URL, spawn an agent
sessions_spawn({
  task: `
    Go to ${url} using browser automation.
    Extract all MacBook Pro listings with:
    - Product name
    - Price
    - Rating (if available)
    Return as JSON array.
  `,
  label: `scrape-${retailer}`,
  runTimeoutSeconds: 120
})
```

**Step 3: Collect & merge**
When agents report back, merge results:
```python
all_products = amazon_results + bestbuy_results + newegg_results
sorted_by_price = sorted(all_products, key=lambda x: x['price'])
```

**Step 4: Output**
Format as markdown table or CSV.

---

## Example 2: Research Aggregator

**Goal:** Gather info on a topic from multiple sources

**Step 1: Search**
```javascript
web_search({ query: "climate change solutions 2026", count: 10 })
```

**Step 2: Fan out**
For each result URL:
```javascript
sessions_spawn({
  task: `
    Fetch ${url} and extract:
    - Main thesis/argument
    - Key statistics cited
    - Proposed solutions
    - Source credibility assessment
    Return structured summary.
  `,
  runTimeoutSeconds: 60
})
```

**Step 3: Synthesize**
Combine agent reports into research brief with citations.

---

## Example 3: Monitoring Swarm

**Goal:** Check multiple sites for changes

**Approach:**
1. Store baseline content hashes
2. Periodically spawn agents to re-fetch
3. Compare hashes, report changes

```javascript
sessions_spawn({
  task: `
    Fetch ${url}
    Hash the main content
    Compare to baseline: ${previousHash}
    If different, extract what changed
    Return: { changed: bool, diff: string }
  `,
  runTimeoutSeconds: 30
})
```

---

## Example 4: API Aggregator

**Goal:** Merge data from multiple APIs

```javascript
// Spawn parallel API callers
sessions_spawn({
  task: `
    Call API: GET https://api.weather.gov/...
    Extract: temperature, conditions
    Return JSON
  `,
  label: "weather-api"
})

sessions_spawn({
  task: `
    Call API: GET https://api.airquality.com/...
    Extract: AQI, pollutants
    Return JSON
  `,
  label: "air-api"
})

// Merge when both complete
combined = { weather: weather_result, air: air_result }
```

---

## Tips

- **Label your spawns** - makes tracking easier
- **Set timeouts** - prevent runaway agents
- **Chunk large jobs** - 5-10 parallel agents is reasonable; more risks rate limits
- **Error handling** - some agents may fail; handle partial results gracefully
