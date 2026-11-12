#!/usr/bin/env python3
"""Spike 006: make the gate's type layer check call args and return types (F4)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, "/home/sudosudo/.openclaw/workspace")

from harness import verdict                                    # noqa: E402
import svl.type_inference as ti                                # noqa: E402
from svl.type_layer import verify_type                         # noqa: E402

_orig_return = ti.TypeChecker._check_return_stmt
_orig_func = ti.TypeChecker._check_func_decl
_orig_synth_call = ti.TypeInferencer._synth_call


def patched_return(self, stmt):
    if stmt.value:
        vt = self.inferencer.synthesize(stmt.value, self.env)
        rt = getattr(self, "_current_return_type", None)
        if rt is not None:
            try:
                self.inferencer.unify(vt, rt)
            except ti.UnificationError as e:
                self.errors.append(f"Type mismatch in return: {e}")


def patched_func(self, stmt):
    if stmt.return_type:
        rt = self._type_ann_to_type(stmt.return_type, self.env)
    else:
        rt = ti.Type.prim('void')
    prev = getattr(self, "_current_return_type", None)
    self._current_return_type = rt
    try:
        _orig_func(self, stmt)
    finally:
        self._current_return_type = prev


def patched_synth_call(self, expr, env):
    scheme = env.lookup(expr.callee)
    if scheme:
        func_type = scheme.instantiate()
        if func_type.kind == 'func':
            params, ret = func_type.args[:-1], func_type.args[-1]
            for arg, pt in zip(expr.arguments, params):
                at = self.synthesize(arg, env)
                self.unify(at, pt)          # raises UnificationError -> checker reports it
            return ret
    return _orig_synth_call(self, expr, env)


def main():
    ti.TypeChecker._check_return_stmt = patched_return
    ti.TypeChecker._check_func_decl = patched_func
    ti.TypeInferencer._synth_call = patched_synth_call

    ret_bad = ('module m { func f() type int { return "hi" }'
               ' func main() type int { return 0 } }')
    call_bad = ('module m { func f(x: int) type int { return x }'
                ' func main() type int { return f("hi") } }')
    ok_prog = ('module m { func f(x: int) type int { return x }'
               ' func main() type int { let a = [1,2,3] return f(len(a)) } }')

    try:
        r1 = verify_type(ret_bad)
        r2 = verify_type(call_bad)
        r3 = verify_type(ok_prog)
        refused_ret = not r1.passed
        refused_call = not r2.passed
        ok_still = r3.passed
        ok = refused_ret and refused_call and ok_still
        return verdict("006-type-boundary-soundness", ok,
                       f"return mismatch refused={refused_ret}, call mismatch refused={refused_call}, "
                       f"valid program still passes={ok_still}")
    except Exception as exc:
        return verdict("006-type-boundary-soundness", False, f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    sys.exit(main())
