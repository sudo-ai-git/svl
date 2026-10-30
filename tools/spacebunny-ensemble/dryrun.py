#!/usr/bin/env python3
"""End-to-end dry run of run.py's ladder and ensemble paths with a fake model.

Purpose: the live endpoint is 401 on every key on this box. That blocks the
*measurement*, but it does not need to block proof that the plumbing produces
correct, non-fabricated reports. This drives run.py's own do_ladder /
do_ensemble with an injected fake client, so the code path is the real one.

What this proves: report math, arg wiring, result serialisation, exit codes.
What this does NOT prove: anything about Space Bunny Alpha. The fake's accuracy
is a property of this file, not of any model.

Run: python3 dryrun.py
"""

from __future__ import annotations

import json
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import run                    # noqa: E402
from nous_client import Reply, Usage  # noqa: E402

# A fake with a known, deliberately non-trivial profile: it gets harder
# problems right only at higher effort, and its PoT is wrong more often than
# its CoT. That makes agreement/escalation/head-to-head all exercise real
# branches instead of the happy path.
GOLD = {
    1: ("A robe takes 2 bolts of blue fiber and half that much white fiber. "
        "How many bolts in total?", 3.0),
    2: ("Josh buys 3 boxes of nails at 8 each. He pays with a 50 note. "
        "How much change?", 26.0),
    3: ("A robe takes 2 bolts of blue fiber and half that much white fiber. "
        "How many bolts does she need in total for 3 robes?", 9.0),
}


def fake_chat(messages, *, effort=None, temperature=None, max_tokens=2048,
              **_):
    sysmsg = messages[0]["content"]
    # Take the last user message: the effort probe sends a 1-message list, the
    # solvers send 2. Indexing messages[1] unconditionally broke the probe.
    question = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            question = m.get("content") or ""
            break
    lvl = {"low": 1, "medium": 2, "high": 3, None: 2}.get(effort, 2)
    pot = "print(" in sysmsg
    gold = None
    for g in GOLD.values():
        if g[0][:40] == question[:40]:
            gold = g[1]

    if pot:
        # PoT is deliberately sloppier: at low effort it is often wrong or
        # emits no code at all, which is what the executable path is for.
        if lvl < 2:
            return Reply(text="I'm not going to write code for that.",
                         reasoning=None, usage=Usage(90, 30), finish_reason="stop")
        val = gold if lvl >= 3 else (gold + 1 if gold is not None else None)
        if val is None:
            return Reply(text="```python\nprint('None')\n```",
                         reasoning=None, usage=Usage(90, 40), finish_reason="stop")
        return Reply(text=f"```python\nprint({int(val)})\n```",
                     reasoning=None, usage=Usage(90, 40), finish_reason="stop")

    if gold is None:
        return Reply(text="no idea", reasoning=None, usage=Usage(90, 20),
                     finish_reason="stop")
    ok = lvl >= 2
    ans = gold if ok else gold + 10
    return Reply(text=f"working it out\n#### {int(ans)}",
                 reasoning="some chain", usage=Usage(90, 60),
                 finish_reason="stop")


def main() -> int:
    run.nous_client.chat = fake_chat   # type: ignore[assignment]
    probs = [(q, g) for (q, g) in GOLD.values()]

    # get_problems() reads .question / .jsonl and otherwise hits GSM8K, so the
    # dry run supplies the problems through the same inline channel the CLI
    # exposes rather than reaching into do_ladder's internals.
    specs = [f"{q} ::{int(g)}" for q, g in probs]

    class A:
        n = len(probs)
        split = "test"
        seed = 0
        shuffle = False
        jsonl = None
        question = specs          # <- the only path get_problems honours
        effort = "medium"
        rungs = ["low", "medium", "high"]
        max_tokens = 2048
        no_probe = False
        no_escalate = False
        verbose = False

    print("#" * 96)
    print("# DRY RUN -- fake model injected. Numbers below describe the FAKE,")
    print("# not stealth/space-bunny-alpha. No network was touched.")
    print("#" * 96)

    print("\n>>> ladder path")
    rc1 = run.do_ladder(A())
    print(f"\nladder rc={rc1}")

    print("\n>>> ensemble path (escalation on)")
    rc2 = run.do_ensemble(A())
    print(f"\nensemble rc={rc2}")

    print("\n>>> ensemble path (escalation off)")
    a = A()
    a.no_escalate = True
    rc3 = run.do_ensemble(a)

    print("\n" + "=" * 96)
    print("VERIFYING results.jsonl")
    print("=" * 96)
    path = run.RESULTS_PATH
    rows = [json.loads(l) for l in open(path) if l.strip()]
    bad = 0
    for r in rows[-3:]:
        ok = r.get("model") == run.nous_client.MODEL
        print(f"  mode={r.get('mode'):9} graded={str(r.get('graded')):5} "
              f"model_ok={ok} keys={sorted(k for k in r if k not in ('ts',))[:6]}")
        if not ok:
            bad += 1
        if r.get("mode") == "ladder":
            for rung in r["rungs"]:
                assert 0.0 <= rung["acc"] <= 1.0, rung
                assert rung["n"] == 3, rung
            print(f"    ladder rungs: " + ", ".join(
                f"{x['effort']}={x['acc']:.0%}" for x in r["rungs"]))
        if r.get("mode") == "ensemble":
            print(f"    calls/problem={r['calls_per_problem']:.2f} "
                  f"agreement={r['agreement_rate']:.0%} "
                  f"escalation={r['escalation_rate']:.0%}")
            assert 2.0 <= r["calls_per_problem"] <= 3.0, r

    print(f"\nrc ladder={rc1} ensemble={rc2} ensemble_noesc={rc3}")
    print("DRY RUN OK -- paths execute, reports are internally consistent")
    return 0 if (rc1 == rc2 == rc3 == 0 and bad == 0) else 1


if __name__ == "__main__":
    sys.exit(main())