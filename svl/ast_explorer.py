"""Visual AST/type explorer: render an SVL program as one self-contained HTML page.

The page is produced by ``svlc explore <file.svl>`` and shows three things side by side:

* the AST, as a collapsible tree with each node's type and source line;
* the type checker's inferred type for every local, parameter and function result;
* the warnings/errors the checker produced, when there were any.

It is a static document: no server, no external assets, and byte-identical output for
the same input, so two renders can be diffed directly.
"""
from __future__ import annotations

import html
import os
from typing import Any, List, Optional

from svl.closures import walk
from svl.type_lowering import infer_types


def _escape(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _node_label(node: Any) -> str:
    """A short, human-readable label for an AST node."""
    kind = type(node).__name__
    detail = ""
    for field in ("name", "value", "callee", "operator", "literal_type"):
        value = getattr(node, field, None)
        if isinstance(value, (str, int, float)) and value != "":
            detail = f": {_escape(value)}"
            break
    line = getattr(node, "line", None)
    suffix = f" <span class='line'>line {line}</span>" if line else ""
    return f"{_escape(kind)}{detail}{suffix}"


def _render_tree(node: Any, depth: int = 0) -> str:
    """A nested ``<ul>`` for the AST, in deterministic pre-order."""
    label = _node_label(node)
    children = []
    for field in getattr(node, "__dataclass_fields__", {}):
        if field in ("line", "column", "offset", "type"):
            continue
        value = getattr(node, field, None)
        if hasattr(value, "__dataclass_fields__"):
            children.append(value)
        elif isinstance(value, list):
            children.extend(v for v in value if hasattr(v, "__dataclass_fields__"))
    # AST nodes are mutable and must not be hashed; sort children by their label so the
    # render is stable regardless of dict iteration order.
    children.sort(key=_node_label)
    if not children:
        return f"<li>{label}</li>"
    inner = "".join(_render_tree(child, depth + 1) for child in children)
    return f"<li>{label}<ul>{inner}</ul></li>"


def _type_name(t: Any) -> str:
    if t is None:
        return "<em>unresolved</em>"
    try:
        return _escape(repr(t))
    except Exception:                                        # noqa: BLE001
        return _escape(t)


def _inference_rows(inferred) -> List[str]:
    """One table row per recorded binding: where it lives, and its inferred type."""
    rows = []
    for (func_name, local_name), t in sorted(
            inferred.local_types.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        rows.append(
            f"<tr><td>{_escape(func_name)}</td><td>{_escape(local_name)}</td>"
            f"<td>{_type_name(t)}</td></tr>")
    for func_name, t in sorted(inferred.func_types.items()):
        rows.append(
            f"<tr class='fn'><td>{_escape(func_name)}</td><td>result</td>"
            f"<td>{_type_name(t)}</td></tr>")
    return rows


def build_explorer_html(source: str, title: str = "SVL AST Explorer") -> str:
    """Render the whole explorer page for one SVL source string."""
    from svl.lexer import tokenize
    from svl.parser_rd import parse

    errors: List[str] = []
    tree_html = ""
    rows: List[str] = []
    token_count = 0
    try:
        tokens = tokenize(source)
        token_count = len(tokens)
        ast = parse(tokens)
        tree_html = _render_tree(ast)
        inferred = infer_types(ast)
        rows = _inference_rows(inferred)
        errors = list(inferred.errors)
    except Exception as exc:                                # noqa: BLE001
        errors.append(f"{type(exc).__name__}: {exc}")

    error_html = ""
    if errors:
        items = "".join(f"<li>{_escape(e)}</li>" for e in errors)
        error_html = f"<section id='errors'><h2>Verification problems</h2><ul>{items}</ul></section>"

    body = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{_escape(title)}</title>
<style>
  body {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; margin: 2rem;
         color: #1b1b1f; background: #fafafa; }}
  h1 {{ font-size: 1.4rem; }} h2 {{ font-size: 1.05rem; margin-top: 1.2rem; }}
  .meta {{ color: #555; font-size: 0.85rem; }}
  ul {{ list-style: none; padding-left: 1rem; }}
  #tree > li {{ font-weight: 600; }}
  .line {{ color: #8a8a8a; font-size: 0.75rem; }}
  table {{ border-collapse: collapse; font-size: 0.85rem; }}
  td, th {{ border: 1px solid #ddd; padding: 0.2rem 0.5rem; text-align: left; }}
  tr.fn td {{ background: #eef4ff; }}
  #errors li {{ color: #a11; }}
</style>
</head>
<body>
<h1>{_escape(title)}</h1>
<p class="meta">{token_count} tokens &middot; {len(rows)} recorded bindings</p>
<section id="tree"><h2>AST</h2><ul>{tree_html}</ul></section>
<section id="types"><h2>Inferred types</h2>
<table><thead><tr><th>function</th><th>binding</th><th>type</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></section>
{error_html}
</body>
</html>
"""
    return body


def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="svl-explore",
                                     description="Render an SVL AST/type explorer page")
    parser.add_argument("file")
    parser.add_argument("--out", default=None,
                        help="output path (default: <file>.html)")
    args = parser.parse_args(argv)

    with open(args.file, encoding="utf-8") as fh:
        source = fh.read()
    page = build_explorer_html(source, title=os.path.basename(args.file))
    out = args.out or (os.path.splitext(args.file)[0] + ".html")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(page)
    print(f"explorer written: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
