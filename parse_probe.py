import json
from grAIl.agent_loop import AgentLoop

def show(label, text):
    try:
        out = AgentLoop._parse_text_tool_calls(text)
    except Exception as e:
        out = f"EXC {type(e).__name__}: {e}"
    print(f"\n=== {label}")
    print(f"IN : {text!r}")
    print(f"OUT: {json.dumps(out)}")

# G-probe: nested parens in key=value
show("nested_parens_kv", "alu(a=sub(x,1), b=2)")

# G-probe: comma inside quoted value, key=value
show("comma_in_quoted_kv", "tool(a=\"x,y\", b=2)")

# G-probe: leading-zero numeric string
show("leading_zero_zip", "lookup(zip=02134)")
show("booleans_upper", "tool(a=TRUE,b=FALSE)")

# G-probe: scientific notation
show("sci_notation", "alu(a=1e3, b=2e1)")

# G-probe: prose over-match (no block)
show("prose_overmatch", "To solve this, first add(3,4) to get 7, then we are done.")

# G-probe: nested parens in JSON
show("nested_parens_json", "arithmetic({expr:\"mul(2,3)\"})")
show("nested_braces_json", "tool({a:{\"nested\":1}})")
show("json_string_with_paren", 'm("call: f(1)")')

# G-probe: multiple calls one block
show("multi_tool_call_block", "<tool_call>a(x=1)</tool_call><tool_call>b(y=2)</tool_call>")

# G-probe: misused opener as closer
show("opener_as_closer", "<tool_call>calc(a=1)</tool_call><tool_call>calc2(b=2)")

# G-probe: unclosed block
show("unclosed_block", "<tool_call>sum(a=1)")

# G-probe: backticked bare
show("backtick_bare", "`multiply(a=2, b=3)`")

# G-probe: name with dash (alias would be foo_bar)
show("dash_name", "<tool_call>foo_bar(a=1)</tool_call>")

# G-probe: name being over-64 or starting digit
show("digit_leading_tool", "<tool_call>tool_12345(a=1)</tool_call>")

# G-probe: extra closing ) in nested parens single call
show("nested_paren_single", "<tool_call>mul(g(2))</tool_call>")

# G-probe: coercion of '-1.5' & negative
print("\n=== coerce")
for v in ["1e3", "02134", "TRUE", "False", "-42", "-3.5", '  42  ', '"hi"']:
    print(f"coerce({v!r}) = {AgentLoop._coerce_arg(v)!r}")

# Alias resolution probe
loop = AgentLoop.__new__(AgentLoop)
loop._tool_aliases = {"foo_bar": "foo-bar", "tool_9life": "sample.9life"}
for nm in ["foo_bar", "tool_9life", "not_an_alias"]:
    print("alias.resolve", nm, "->", loop._tool_aliases.get(nm, nm))
