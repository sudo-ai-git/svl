import sys
sys.path.insert(0, ".")

from photonic.composition import PipeBuilder, PipelineState

class DummyDispatcher:
    async def dispatch(self, tool, params, ctx):
        return {"ok": True, "tool": tool}

# Test 1: synchronous call (no running loop) should work
builder = PipeBuilder(DummyDispatcher())
builder.chain("tool_a", "tool_b")
state = builder.run()
assert isinstance(state, PipelineState)
assert state.status == "COMPLETED" or state.status == "PARTIAL"
print("OK: sync run")

# Test 2: calling from async context should raise RuntimeError
async def test_async_context():
    builder2 = PipeBuilder(DummyDispatcher())
    builder2.chain("tool_c")
    try:
        builder2.run()
        print("FAIL: expected RuntimeError")
        return False
    except RuntimeError as e:
        msg = str(e)
        assert "async context" in msg
        print("OK: async context raises RuntimeError")
        return True

import asyncio
result = asyncio.run(test_async_context())
assert result is True
print("ALL OK")
