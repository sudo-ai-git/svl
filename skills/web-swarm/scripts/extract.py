#!/usr/bin/env python3
"""
Quick HTML extraction utilities.
Usage: python3 extract.py <url> [--xpath EXPR] [--css SELECTOR] [--json-path PATH]
"""

import argparse
import json
import sys
import requests
from lxml import html


def fetch(url: str) -> str:
    """Fetch URL content."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (compatible; Zed/1.0; +https://openclaw.ai)'
    }
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.text


def extract_xpath(content: str, expr: str) -> list:
    """Extract via XPath."""
    tree = html.fromstring(content)
    return tree.xpath(expr)


def extract_css(content: str, selector: str) -> list:
    """Extract via CSS selector."""
    tree = html.fromstring(content)
    return tree.cssselect(selector)


def main():
    parser = argparse.ArgumentParser(description='Extract data from URL')
    parser.add_argument('url', help='URL to fetch')
    parser.add_argument('--xpath', help='XPath expression')
    parser.add_argument('--css', help='CSS selector')
    parser.add_argument('--attr', help='Attribute to extract from elements')
    parser.add_argument('--text', action='store_true', help='Extract text content')
    parser.add_argument('--json', action='store_true', help='Output as JSON')
    
    args = parser.parse_args()
    
    content = fetch(args.url)
    
    elements = []
    if args.xpath:
        elements = extract_xpath(content, args.xpath)
    elif args.css:
        elements = extract_css(content, args.css)
    else:
        # Default: return page title
        elements = extract_xpath(content, '//title/text()')
    
    results = []
    for el in elements:
        if isinstance(el, str):
            results.append(el)
        elif args.attr:
            results.append(el.get(args.attr, ''))
        elif args.text:
            results.append(el.text_content().strip())
        else:
            results.append(html.tostring(el, encoding='unicode'))
    
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        for r in results:
            print(r)


if __name__ == '__main__':
    main()
