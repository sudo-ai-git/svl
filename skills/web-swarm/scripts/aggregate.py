#!/usr/bin/env python3
"""
Aggregate JSON results from swarm agents.

Usage:
    python3 aggregate.py results/*.json --output combined.json
    python3 aggregate.py results/*.json --format table
    cat results.jsonl | python3 aggregate.py --stdin
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def load_results(paths: list[str], stdin: bool = False) -> list[dict]:
    """Load JSON results from files or stdin."""
    results = []
    
    if stdin:
        for line in sys.stdin:
            line = line.strip()
            if line:
                try:
                    results.append(json.loads(line))
                except json.JSONDecodeError as e:
                    results.append({"_parse_error": str(e), "_raw": line})
    else:
        for path in paths:
            p = Path(path)
            if p.exists():
                try:
                    with open(p) as f:
                        data = json.load(f)
                        if isinstance(data, list):
                            results.extend(data)
                        else:
                            results.append(data)
                except json.JSONDecodeError as e:
                    results.append({"_parse_error": str(e), "_file": str(p)})
    
    return results


def dedupe(results: list[dict], key: str = None) -> list[dict]:
    """Remove duplicate results by key field."""
    if not key:
        # Dedupe by full content
        seen = set()
        unique = []
        for r in results:
            h = json.dumps(r, sort_keys=True)
            if h not in seen:
                seen.add(h)
                unique.append(r)
        return unique
    
    # Dedupe by specific key
    seen = set()
    unique = []
    for r in results:
        k = r.get(key)
        if k and k not in seen:
            seen.add(k)
            unique.append(r)
    return unique


def filter_errors(results: list[dict]) -> tuple[list[dict], list[dict]]:
    """Separate successful results from errors."""
    success = []
    errors = []
    for r in results:
        if "error" in r or "_parse_error" in r:
            errors.append(r)
        else:
            success.append(r)
    return success, errors


def format_table(results: list[dict]) -> str:
    """Format results as markdown table."""
    if not results:
        return "_No results_"
    
    # Get all keys
    keys = []
    for r in results:
        for k in r.keys():
            if k not in keys and not k.startswith("_"):
                keys.append(k)
    
    if not keys:
        return "_No displayable fields_"
    
    # Build table
    lines = []
    lines.append("| " + " | ".join(keys) + " |")
    lines.append("| " + " | ".join(["---"] * len(keys)) + " |")
    
    for r in results:
        row = []
        for k in keys:
            v = r.get(k, "")
            # Truncate long values
            s = str(v)[:50]
            if len(str(v)) > 50:
                s += "..."
            row.append(s.replace("|", "\\|"))
        lines.append("| " + " | ".join(row) + " |")
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Aggregate swarm results")
    parser.add_argument("files", nargs="*", help="JSON files to aggregate")
    parser.add_argument("--stdin", action="store_true", help="Read JSONL from stdin")
    parser.add_argument("--output", "-o", help="Output file (default: stdout)")
    parser.add_argument("--format", "-f", choices=["json", "jsonl", "table"], 
                        default="json", help="Output format")
    parser.add_argument("--dedupe", "-d", metavar="KEY", 
                        help="Dedupe by field (omit for full-content dedupe)")
    parser.add_argument("--no-dedupe", action="store_true", help="Skip deduplication")
    parser.add_argument("--include-errors", action="store_true",
                        help="Include error results in output")
    
    args = parser.parse_args()
    
    if not args.files and not args.stdin:
        parser.error("Provide files or --stdin")
    
    # Load
    results = load_results(args.files, args.stdin)
    
    # Filter errors
    success, errors = filter_errors(results)
    if args.include_errors:
        success = results
    
    # Dedupe
    if not args.no_dedupe:
        success = dedupe(success, args.dedupe)
    
    # Format output
    if args.format == "json":
        output = json.dumps(success, indent=2)
    elif args.format == "jsonl":
        output = "\n".join(json.dumps(r) for r in success)
    elif args.format == "table":
        output = format_table(success)
    
    # Add error summary for table format
    if args.format == "table" and errors:
        output += f"\n\n_({len(errors)} errors omitted)_"
    
    # Write
    if args.output:
        with open(args.output, "w") as f:
            f.write(output)
        print(f"Wrote {len(success)} results to {args.output}")
        if errors:
            print(f"  ({len(errors)} errors filtered)")
    else:
        print(output)


if __name__ == "__main__":
    main()
