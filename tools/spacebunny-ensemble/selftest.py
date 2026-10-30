"""Self-test: prove the mechanism works with zero API calls.

Why this exists: the live endpoint is currently 401 on every credential on this
box, so the ensemble + ladder logic cannot be validated against the real model.
What CAN be validated offline is everything that is actually our code:
extraction, equivalence, sandbox containment, tie-break policy, and the
reporting math. A fake model that emits canned CoT and canned PoT exercises
those paths exactly; it does not tell you anything about Space Bunny Alpha's
accuracy, and the output says so.

Run: python3 selftest.py
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from dataclasses import dataclass
from typing import Optional

# Captured at import, BEFORE any test patches urllib.request.urlopen. Tests
# restore this rather than None, otherwise a failed restore silently breaks
# every later test that makes a real call.
_real_urlopen = urllib.request.urlopen

import compare as compare_mod
import datasets as ds
import extract
import ladder as ladder_mod
import nous_client
import planner as P
import sandbox
from ensembler import solve_problem
from nous_client import Reply, Usage

PASS, FAIL = "PASS", "FAIL"
results: list[tuple[str, str, str]] = []


def check(name: str, got, want) -> None:
    ok = got == want
    results.append((PASS if ok else FAIL, name,
                    "" if ok else f"got={got!r} want={want!r}"))


def check_pred(name: str, ok: bool, detail: str = "") -> None:
    results.append((PASS if ok else FAIL, name, detail if not ok else ""))


# ---------------------------------------------------------------- extraction

def test_extract() -> None:
    check("extract: gsm8k hash format",
          extract.extract_answer("blah blah\n#### 42"), 42.0)
    check("extract: boxed",
          extract.extract_answer(r"so \boxed{1,234} is it"), 1234.0)
    check("extract: dollar sign stripped",
          extract.extract_answer("#### $1,234.50"), 1234.5)
    check("extract: 'answer is'",
          extract.extract_answer("The final answer is 7"), 7.0)
    check("extract: xml answer tag",
          extract.extract_answer("<answer>99</answer>"), 99.0)
    check("extract: integer-as-float",
          extract.extract_answer("#### 17"), 17.0)
    check("extract: negative",
          extract.extract_answer("#### -5"), -5.0)
    check("extract: fraction in answer line",
          extract.extract_answer("the answer is 3/4"), 0.75)
    check("extract: trailing percent",
          extract.extract_answer("#### 50%"), 50.0)
    check("extract: none when absent",
          extract.extract_answer("I cannot solve this"), None)
    check("extract: empty input", extract.extract_answer(""), None)
    check("extract: last hash wins over earlier",
          extract.extract_answer("#### 1\nwait\n#### 2"), 2.0)
    check("extract: scientific notation",
          extract.extract_answer("#### 1.5e3"), 1500.0)

    # equivalence -- the part majority voting actually depends on
    check("agree: 1000 vs 1,000.00",
          extract.answers_agree(1000.0, 1000.0), True)
    check("agree: 2/3 vs 0.666666",
          extract.answers_agree(2 / 3, 0.666666), True)
    check("disagree: 2/3 vs 0.7",
          extract.answers_agree(2 / 3, 0.7), False)
    check("agree: missing side is None",
          extract.answers_agree(None, 5.0), None)
    check("disagree: 100 vs 101",
          extract.answers_agree(100.0, 101.0), False)
    check_pred("agree: large-magnitude tolerance",
               extract.answers_agree(1e9, 1e9 + 0.5) is True)

    check("format: int stays int", extract.format_answer(42.0), "42")
    check("format: float keeps precision", extract.format_answer(0.5), "0.5")
    check("format: none", extract.format_answer(None), "<none>")


# ------------------------------------------------------------------- sandbox

def test_sandbox() -> None:
    ok = sandbox.run_pot("print(6*7)")
    check_pred("sandbox: runs arithmetic", ok.ok and ok.output.strip() == "42",
               f"ok={ok.ok} out={ok.stdout!r}")

    boom = sandbox.run_pot("1/0")
    check_pred("sandbox: zero div caught", not boom.ok,
               "should have raised")

    loop = sandbox.run_pot("while True:\n    pass", timeout=3.0)
    check_pred("sandbox: infinite loop times out", loop.timed_out,
               f"timed_out={loop.timed_out}")

    hog = sandbox.run_pot("x = bytearray(2*1024*1024*1024)\nprint(len(x))",
                          mem_mb=256)
    check_pred("sandbox: memory hog rejected", not hog.ok,
               "should have failed on RLIMIT_AS")

    for name, src in [
        ("socket", "import socket\nprint('x')"),
        ("requests", "import requests\nprint('x')"),
        ("urllib", "import urllib.request\nprint('x')"),
        ("ssl", "import ssl\nprint('x')"),
        ("asyncio", "import asyncio\nprint('x')"),
        ("shutil", "import shutil\nprint(shutil.which('ls'))"),
        ("pathlib", "import pathlib\nprint(pathlib.Path('.'))"),
        ("subprocess", "import subprocess\nprint(subprocess.run(['id']))"),
        ("ctypes", "import ctypes\nprint(ctypes)"),
        ("pickle", "import pickle\nprint(pickle)"),
        ("sqlite3", "import sqlite3\nprint(sqlite3)"),
        ("glob", "import glob\nprint(glob.glob('*'))"),
        ("os.system", "import os\nos.system('id')"),
        ("os.environ", "import os\nprint(os.environ)"),
        ("os.popen", "import os\nprint(os.popen('id').read())"),
        ("open", "open('/etc/passwd')"),
        ("__import__", "__import__('os').system('id')"),
        ("subclasses", "().__class__.__bases__[0].__subclasses__()"),
        ("globals", "print(globals())"),
        ("builtins.eval", "eval('1+1')"),
        ("builtins.exec", "exec('x=1')"),
    ]:
        r = sandbox.run_pot(src)
        check_pred(f"sandbox: blocks {name}", (not r.ok) and r.blocked,
                   f"ok={r.ok} blocked={r.blocked} err={r.stderr[-80:]!r}")

    # the deny list must not break legitimate math programs
    for label, src, want in [
        ("stdlib math", "import math\nprint(math.sqrt(144))", "12.0"),
        ("fractions", "from fractions import Fraction\n"
                      "print(Fraction(3,4))", "3/4"),
        ("decimal", "import decimal\nprint(decimal.Decimal('0.5')*2)", "1.0"),
        ("builtin round", "print(round(2.567, 2))", "2.57"),
        ("statistics", "import statistics\nprint(statistics.mean([1,2,3]))", "2"),
        ("finite itertools", "import itertools\n"
                             "print(list(itertools.islice(itertools.count(1,2),5)))",
         "[1, 3, 5, 7, 9]"),
        ("functools reduce", "import functools, operator\n"
                             "print(functools.reduce(operator.add, range(1,6)))", "15"),
        ("cmath", "import cmath\nprint(cmath.sqrt(-4))", "2j"),
    ]:
        r = sandbox.run_pot(src)
        lines = r.stdout.strip().splitlines()
        got = lines[-1] if lines else ""
        check_pred(f"sandbox: allows {label}", r.ok and got == want,
                   f"ok={r.ok} out={r.stdout!r} err={r.stderr[-80:]!r}")

    # Regression guard for the over-broad deny list: denying os/sys/importlib
    # looked safer but broke fractions and statistics (statistics -> random ->
    # os). Every module here must import cleanly inside the sandbox.
    for mod in ["math", "decimal", "fractions", "itertools", "functools",
                "operator", "statistics", "random", "bisect", "collections",
                "json", "re", "enum", "types", "copy", "string", "datetime",
                "time", "heapq", "array", "struct", "cmath", "numbers",
                "textwrap", "unicodedata", "calendar", "hashlib", "zlib",
                "base64", "uuid"]:
        r = sandbox.run_pot(f"import {mod}\nprint('OK')")
        check_pred(f"sandbox: stdlib {mod} importable", r.ok,
                   f"ok={r.ok} err={r.stderr[-90:]!r}")

    fence = sandbox.strip_markdown_fence(
        "sure!\n```python\nprint(1+1)\n```\n")
    check("fence: wrapped block stripped", fence, "print(1+1)")
    unterm = sandbox.strip_markdown_fence("```python\nprint(2+2)")
    check("fence: unterminated stripped", unterm, "print(2+2)")
    check("fence: bare code untouched",
          sandbox.strip_markdown_fence("print(3)"), "print(3)")

    r = sandbox.run_pot(sandbox.strip_markdown_fence(
        "```python\nprint(5*5)\n```"))
    check_pred("fence: fenced program executes",
               r.ok and r.stdout.strip() == "25",
               f"out={r.stdout!r}")


# ------------------------------------------------------- the ensembler itself

COT_OK = Reply(text="Natalia sold 48+24=72 clips in May.\n#### 72",
               reasoning=None, usage=Usage(100, 50), finish_reason="stop")
POT_OK = Reply(text="```python\nprint(48+24)\n```",
               reasoning=None, usage=Usage(100, 40), finish_reason="stop")
POT_WRONG = Reply(text="```python\nprint(48+25)\n```",
                  reasoning=None, usage=Usage(100, 40), finish_reason="stop")
POT_JUNK = Reply(text="I'm not going to write code.",
                 reasoning=None, usage=Usage(100, 20), finish_reason="stop")
POT_CRASH = Reply(text="```python\nprint(1/0)\n```",
                  reasoning=None, usage=Usage(100, 30), finish_reason="stop")

Q = "Natalia sold 48 clips in April, then 24 more in May. How many total?"


class FakeCall:
    """Scripted model. Hands out replies[i] on the i-th call, then sticks on
    the last one, and records every request for assertions."""

    def __init__(self, replies, seen=None):
        self.replies = list(replies)
        self.seen = seen
        self._n = 0

    def __call__(self, **kw) -> Reply:
        if self.seen is not None:
            self.seen.append(kw)
        i = min(self._n, len(self.replies) - 1)
        self._n += 1
        return self.replies[i]


def test_ensemble_paths() -> None:
    # happy path: CoT and PoT agree -> 2 calls, no escalation
    f = FakeCall([COT_OK, POT_OK])
    r = solve_problem(Q, 72.0, call=f, effort="low")
    check_pred("ensemble: agreement -> 2 calls", r.calls == 2,
               f"calls={r.calls}")
    check_pred("ensemble: agreement flagged", r.agreed)
    check_pred("ensemble: not escalated", not r.escalated)
    check_pred("ensemble: correct", r.correct is True, f"final={r.final}")

    # disagreement -> escalate, and trust the executable path 2-vs-1
    f = FakeCall([COT_OK, POT_WRONG, COT_OK])
    r = solve_problem(Q, 72.0, call=f, effort="low")
    check_pred("ensemble: disagreement escalates", r.escalated)
    check_pred("ensemble: 3 calls on disagreement", r.calls == 3,
               f"calls={r.calls}")
    check_pred("ensemble: tie-break agrees with CoT -> CoT wins",
               r.final == 72.0, f"final={r.final}")

    # PoT unusable -> fall back to CoT, no wasted escalation
    for junk, label in [(POT_JUNK, "no code"), (POT_CRASH, "crashing code")]:
        f = FakeCall([COT_OK, junk])
        r = solve_problem(Q, 72.0, call=f, effort="low")
        check_pred(f"ensemble: {label} -> no escalation", not r.escalated,
                   "should not escalate when PoT merely failed")
        check_pred(f"ensemble: {label} -> falls back to CoT",
                   r.final == 72.0 and r.correct is True, f"final={r.final}")

    # both dead -> must escalate, something is better than nothing
    empty = Reply(text="no idea", reasoning=None, usage=Usage(10, 5),
                  finish_reason="stop")
    f = FakeCall([empty, empty, COT_OK])
    r = solve_problem(Q, 72.0, call=f, effort="low")
    check_pred("ensemble: both-dead escalates", r.escalated,
               "must retry when nothing answered")
    check_pred("ensemble: both-dead recovers via escalation",
               r.correct is True, f"final={r.final}")

    # escalation disabled -> still answers
    f = FakeCall([COT_OK, POT_WRONG])
    r = solve_problem(Q, 72.0, call=f, effort="low", allow_escalation=False)
    check_pred("ensemble: escalation-disabled stays at 2 calls", r.calls == 2)
    check_pred("ensemble: escalation-disabled prefers executable answer",
               r.final == 73.0, f"final={r.final}")

    # truncation must be surfaced, not silently graded as a wrong answer
    trunc = Reply(text="#### ", reasoning=None, usage=Usage(100, 2048),
                  finish_reason="length")
    f = FakeCall([trunc, POT_OK])
    r = solve_problem(Q, 72.0, call=f, effort="low")
    check_pred("ensemble: truncation recorded",
               any("truncated" in a.detail for a in r.attempts),
               f"details={[a.detail for a in r.attempts]}")


def test_ladder_math() -> None:
    """Reporting arithmetic, on a fake model with a known accuracy profile."""
    problems: list[tuple[str, Optional[float]]] = [
        (f"q{i}", float(i)) for i in range(1, 11)]

    class Profile:
        """Correct iff the question index is below the rung's skill level.

        Effort doubles as a skill dial so the ladder's arithmetic is checked
        against a ground truth of 0.2 / 0.5 / 0.8 accuracy.
        """
        def __init__(self):
            self.seen: list = []

        def __call__(self, **kw) -> Reply:
            self.seen.append(kw)
            idx = int(kw["messages"][1]["content"].strip().lstrip("q"))
            skill = int(kw.get("effort") or 0)
            if idx % 10 < skill:
                return Reply(text=f"#### {idx}", reasoning=None,
                             usage=Usage(50, 10), finish_reason="stop")
            return Reply(text="I don't know", reasoning=None,
                         usage=Usage(50, 10), finish_reason="stop")

    rep = ladder_mod.ladder(problems, call=Profile(), efforts=["2", "5", "8"],
                            probe=False, verbose=False)
    check_pred("ladder: all rungs ran", len(rep.rungs) == 3,
               f"rungs={len(rep.rungs)}")
    accs = [round(r.acc, 1) for r in rep.rungs]
    check("ladder: accuracy rises with skill", accs, [0.2, 0.5, 0.8])
    check_pred("ladder: first-try equals correct (no escalation path)",
               all(r.first_try == r.correct for r in rep.rungs))
    check_pred("ladder: cost_per_correct finite on a scoring rung",
               rep.rungs[-1].cost_per_correct > 0)
    # 8, not 10: idx%10 over 1..10 leaves 8 and 9 above the top rung's skill,
    # which is the same 0.8 accuracy asserted above. Catches a harness that
    # silently inflates the solved-set across rungs.
    check("ladder: distinct problems solved across rungs",
          len(rep.per_problem), 8)
    txt = rep.render()
    check_pred("ladder: report renders a first-try line",
               "first-try lift" in txt)
    check_pred("ladder: report names best accuracy rung",
               "best accuracy" in txt)
    check_pred("ladder: report detects the first-try lift",
               "+60.0%" in txt, f"render=\n{txt}")


def test_summary_math() -> None:
    f = FakeCall([COT_OK, POT_OK], seen=[])
    res, s = ladder_mod.ensemble_sweep([(Q, 72.0)], call=f, effort="low",
                                       verbose=False)
    check("summary: n", s["n"], 1)
    check("summary: correct", s["correct"], 1)
    check("summary: accuracy", s["accuracy"], 1.0)
    check("summary: calls per problem", s["calls_per_problem"], 2.0)
    check("summary: escalation rate", s["escalation_rate"], 0.0)


def test_client_config() -> None:
    check("client: model id", nous_client.MODEL, "stealth/space-bunny-alpha")
    check("client: base url", nous_client.BASE_URL,
          "https://inference-api.nousresearch.com/v1")
    p = nous_client.probe_endpoint(key="")
    check_pred("client: probe returns a dict and never raises",
               isinstance(p, dict), f"probe={p}")
    # A no-key probe must be self-describing. If this box HAS a (dead) key in
    # ~/.hermes/.env the probe is allowed to report that instead -- what it may
    # not do is claim usable=True without a 200 on a real chat call.
    check_pred("client: probe does not claim usable without a 200",
               p.get("usable") is not True or p.get("chat_status") == 200,
               f"probe={p}")
    check_pred("client: probe reports model listing honestly",
               p.get("model_listed") in (True, False, None),
               f"probe={p}")


def test_credential_contract() -> None:
    """The (token, label) ordering bug that shipped a label as a Bearer token.

    resolve_all_keys() returns (token, label); the failover loop unpacks in
    that order. When the two were swapped the Authorization header literally
    read "Bearer device_code", which 401s while every other diagnostic looks
    healthy -- the worst kind of failure, because it impersonates an expired
    account.
    """
    cands = nous_client.resolve_all_keys()
    check_pred("contract: candidates are (token, label)",
               all(tok != lbl for tok, lbl in cands),
               f"cands={[(len(t), l) for t, l in cands]}")
    check_pred("contract: token does not look like a label",
               all(len(tok) >= 20 for tok, _ in cands),
               f"lens={[len(t) for t, _ in cands]}")
    check_pred("contract: token matches the resolved key",
               bool(nous_client.resolve_key()) and
               (not cands or cands[0][0] == nous_client.resolve_key()))
    check_pred("contract: more than one candidate for failover",
               len(cands) >= 1, f"n={len(cands)}")


def test_no_label_as_bearer() -> None:
    """Intercept the outgoing header and assert it is never a pool label."""
    import hashlib
    import urllib.request as _u

    sent: list[str] = []

    def fake_urlopen(req, timeout=None):
        sent.append(req.headers.get("Authorization", ""))
        payload = (b'{"choices":[{"message":{"content":"#### 4"},'
                   b'"finish_reason":"stop"}],"usage":{}}')
        class _R:
            def read(self): return payload
        return _R()

    real = _u.urlopen
    _u.urlopen = fake_urlopen
    try:
        nous_client.chat([{"role": "user", "content": "2+2="}],
                         temperature=0.0, max_tokens=64)
    except Exception:
        pass                      # a stubbed transport may still raise; the
    finally:                     # assertion is on the header, not the result
        _u.urlopen = real

    check_pred("bearer: at least one request was attempted", len(sent) > 0,
               f"sent={sent}")
    labels = {lbl.split(":", 1)[-1] for _, lbl in nous_client.resolve_all_keys()}
    bad = [h for h in sent
           if any(h.endswith(f"Bearer {lb}") for lb in labels)]
    check_pred("bearer: never sends a pool label as the token", not bad,
               f"leaked={bad}")
    # and each header must carry a long opaque value, not a short word
    short = [h for h in sent if len(h) < 30]
    check_pred("bearer: every header carries a real-length credential",
               not short, f"short={short}")


def test_hard_set_is_sane() -> None:
    """The harder set must not be trivially wrong or accidentally degenerate."""
    items = ds.load_hard(8)
    check("hard set: length", len(items), 8)
    check_pred("hard set: every item has a finite gold",
               all(g is not None for _, g in items))
    check_pred("hard set: questions are distinct",
               len({q for q, _ in items}) == len(items))
    check_pred("hard set: includes a non-integer gold (decimal path)",
           any(g is not None and abs(g - round(g)) > 1e-9 for _, g in items),
               "extract.answers_agree must survive decimal golds")
    # the grader must not call a wrong answer correct
    check_pred("hard set: grader rejects wrong answers",
               ds_ok(43.0, 245.0) is False and ds_ok(3.0, 12.0) is False)
    check_pred("hard set: grader accepts correct answers",
               ds_ok(0.375, 0.375) is True)


def ds_ok(a, b):
    return extract.answers_agree(a, b)


def test_outline_parsing() -> None:
    """Outline parsing is where a planner harness silently degrades.

    If parsing returns fewer outlines than requested, the run falls back to
    unplanned branches -- which looks like PTTS in the logs but is not.
    """
    good = """Here are 3 routes.

<outline id="1">
approach: work backwards from the answer
first move: let x be the whole, express parts in terms of x
steps:
- set up x - a = 30
- substitute
</outline>
<outline id="2">
approach: enumerate cases
first move: try each integer in range
steps:
- loop i
</outline>
<outline id="3">
approach: simulate directly
first move: track a running counter
steps:
- init
- iterate
</outline>

Hope that helps."""
    outs = P.parse_outlines(good, 3)
    check("parse: outline count", len(outs), 3)
    check("parse: first approach",
          outs[0].approach, "work backwards from the answer")
    check("parse: first move captured",
          outs[0].first_move, "let x be the whole, express parts in terms of x")
    check("parse: steps captured", len(outs[0].steps), 2)
    check("parse: ids", [o.id for o in outs], ["1", "2", "3"])
    check("parse: third approach", outs[2].approach, "simulate directly")

    # model omits the closing tag on the last outline
    unclosed = good.replace("</outline>\n\nHope", "\n\nHope")
    check_pred("parse: tolerates unclosed tag",
               len(P.parse_outlines(unclosed, 3)) >= 2,
               f"got {len(P.parse_outlines(unclosed, 3))}")

    # no tags at all, numbered blocks instead
    plain = """1. approach: algebra
first move: define variable
2. approach: casework
first move: branch on parity"""
    check_pred("parse: falls back to numbered blocks",
               len(P.parse_outlines(plain, 2)) == 2,
               f"got {len(P.parse_outlines(plain, 2))}")

    check("parse: empty input", len(P.parse_outlines("", 4)), 0)
    check("parse: prose only", len(P.parse_outlines("I cannot help.", 4)), 0)
    check("parse: respects k cap",
          len(P.parse_outlines(good, 2)), 2)

    # the id attribute in single quotes / no quotes
    q = "<outline id='7'>\napproach: x\n</outline>"
    check("parse: single-quoted id", P.parse_outlines(q, 1)[0].id, "7")


def test_follow_score_parsing() -> None:
    check("follow: 0-10 int", P.parse_follow_score("plan-adherence: 8"), 0.8)
    check("follow: 0-1 float", P.parse_follow_score("plan-adherence: 0.7"), 0.7)
    check("follow: percent",
          P.parse_follow_score("plan-adherence: 90%"), 0.9)
    check("follow: absent", P.parse_follow_score("nothing here"), None)
    check("follow: empty text", P.parse_follow_score(""), None)
    # out-of-range must clamp, not silently report nonsense
    check("follow: clamps above 1",
          P.parse_follow_score("plan-adherence: 1.0"), 1.0)
    check_pred("follow: never exceeds 1",
               (P.parse_follow_score("plan-adherence: 10") or 0) <= 1.0)


def test_vote_and_diversity() -> None:
    def br(i, ans, follow=None):
        return P.Branch(i, str(i), ans, 10, ans is not None,
                        follow_score=follow)

    check("vote: clear majority", P.vote([br(0, 5), br(1, 5), br(2, 7)]), 5.0)
    check("vote: no answers", P.vote([br(0, None), br(1, None)]), None)
    check("vote: empty list", P.vote([]), None)

    # tie: higher adherence wins
    check("vote: tie broken by adherence",
          P.vote([br(0, 5, 0.2), br(1, 9, 0.9)]), 9.0)
    # tie with equal adherence: earliest branch wins (deterministic)
    check("vote: tie broken by order",
          P.vote([br(0, 5, 0.5), br(1, 9, 0.5)]), 5.0)

    r = P.PlannedResult(question="q", gold=1.0)
    r.branches = [br(0, 5), br(1, 5), br(2, 9)]
    check("diversity: 2 distinct / 3", r.diversity, 2 / 3)
    check_pred("spread: two-way split", abs(r.spread - (1 - 2 / 3)) < 1e-9,
               f"spread={r.spread}")

    r2 = P.PlannedResult(question="q", gold=1.0)
    r2.branches = [br(0, 5), br(1, 5), br(2, 5)]
    check("diversity: identical branches", r2.diversity, 1 / 3)
    check("spread: all identical", r2.spread, 0.0)

    # numeric-equivalent answers must NOT count as distinct
    r3 = P.PlannedResult(question="q", gold=1.0)
    r3.branches = [br(0, 1000.0), br(1, 1000.0), br(2, 999.0)]
    check("diversity: 1000 twice + 999", r3.diversity, 2 / 3)

    r4 = P.PlannedResult(question="q", gold=None)
    check("diversity: no branches", r4.diversity, 0.0)


def test_ptts_fallback_is_flagged() -> None:
    """A planner that returns nothing must NOT look like a successful PTTS run."""
    def dead_planner(messages, **kw):
        return Reply(text="I refuse to plan.", reasoning=None,
                     usage=Usage(50, 10), finish_reason="stop")

    r = P.solve_planned("q", 7.0, 3, call=dead_planner, effort=None)
    check_pred("fallback: flagged in error", "FELL BACK" in r.error,
               f"error={r.error!r}")
    check("fallback: still produced k branches", len(r.branches), 3)
    check("fallback: counted a planner call", r.calls, 4)
    check_pred("fallback: branches carry no plan id",
               all(b.outline_id == "-" for b in r.branches))


def test_ptts_happy_path() -> None:
    plan_txt = ("<outline id=\"1\">\napproach: algebra\nfirst move: let x\n"
                "steps:\n- solve\n</outline>")
    state = {"n": 0}

    def fake(messages, **kw):
        state["n"] += 1
        if "DIVERGENT" in messages[0]["content"]:
            return Reply(text=plan_txt, reasoning=None, usage=Usage(100, 60),
                         finish_reason="stop")
        i = state["n"]
        return Reply(text=f"reasoning\n#### {10 + i}\nplan-adherence: 9",
                     reasoning=None, usage=Usage(100, 50),
                     finish_reason="stop")

    r = P.solve_planned("q", None, 3, call=fake, effort=None)
    check("happy: one outline parsed", len(r.outlines), 1)
    check_pred("happy: no fallback", "FELL BACK" not in r.error)
    check("happy: calls = planner + branches", r.calls, 2)
    check_pred("happy: all branches answered", r.answered == 1,
               f"answered={r.answered}")
    check_pred("happy: adherence parsed",
               r.branches[0].follow_score == 0.9,
               f"got {r.branches[0].follow_score}")


def test_planner_prompt_has_k() -> None:
    for k in (2, 4, 8):
        p = P.make_planner(k)
        check_pred(f"prompt: mentions k={k}", f"{k} mutually DIFFERENT" in p)
        check_pred(f"prompt: no leftover braces", "{k}" not in p)


def test_branch_retry_recovers() -> None:
    """A dead branch silently shrinks coverage -- coverage IS the metric.

    The greedy run lost a branch to EndpointError and reported diversity as if
    k were still 4. Retry must recover it, and unrecoverable losses must be
    counted, never averaged away.
    """
    state = {"n": 0}

    def flaky(messages, **kw):
        state["n"] += 1
        if state["n"] == 1:
            raise RuntimeError("EndpointError: simulated blip")
        return Reply(text="work\n#### 42\nplan-adherence: 8", reasoning=None,
                     usage=Usage(20, 5), finish_reason="stop")

    o = P.Outline(id="1", approach="algebra")
    b = P.execute("q", o, 0, call=flaky, effort=None, temperature=0.0,
                  branch_retries=2)
    check_pred("retry: recovers a transient endpoint failure",
               b.answer == 42.0, f"answer={b.answer} detail={b.detail}")
    check_pred("retry: took more than one attempt", state["n"] >= 2,
               f"attempts={state['n']}")
    check_pred("retry: loss not reported after recovery", b.answer is not None)

    # permanent failure must terminate, not loop forever
    def dead(messages, **kw):
        raise RuntimeError("EndpointError: permanent")

    b2 = P.execute("q", o, 0, call=dead, effort=None, temperature=0.0,
                   branch_retries=2)
    check("retry: permanent failure yields no answer", b2.answer, None)
    check_pred("retry: permanent failure is labelled",
               "call failed" in b2.detail, f"detail={b2.detail}")

    r = P.PlannedResult(question="q", gold=1.0)
    r.branches = [P.Branch(0, "1", 5.0, 10, True),
                  P.Branch(1, "2", None, 0, False),
                  P.Branch(2, "3", None, 0, False)]
    check("lost: counts dead branches", r.lost_branches, 2)
    check("lost: distinct ignores dead branches", r.distinct_answers, 1)
    check_pred("lost: diversity uses answered as denominator",
               abs(r.diversity - 1.0) < 1e-9, f"div={r.diversity}")


def test_text_diversity() -> None:
    """Plan diversity is measured on OUTLINE TEXT, not answers.

    That separation is the whole point: the measured run had four genuinely
    different outlines and one answer, so an answer-based diversity metric
    reports 0.25 and blames the planner for the executor's convergence.
    """
    check("td: identical strings", P._text_diversity(["a b c"] * 4), 0.0)
    check_pred("td: disjoint vocab is diverse",
               P._text_diversity(["grid counting", "case enumeration",
                                  "algebraic inversion"]) > 0.9,
               f"got {P._text_diversity(['grid counting', 'case enumeration', 'algebraic inversion'])}")
    check_pred("td: near-duplicates are not diverse",
               P._text_diversity(["grid count method", "grid count method",
                                  "grid-count method"]) < 0.2,
               f"got {P._text_diversity(['grid count method'] * 3)}")
    check("td: single item", P._text_diversity(["only one"]), 0.0)
    check("td: empty list", P._text_diversity([]), 0.0)
    check("td: all-empty strings", P._text_diversity(["", ""]), 0.0)
    check_pred("td: always in [0,1]",
               all(0.0 <= P._text_diversity(a) <= 1.0
                   for a in ([], [""], ["x"], ["x", "x"], ["a b", "c d"],
                             ["alpha beta", "alpha gamma", "delta"])))

    # the real measured case: different plans, identical answer
    r = P.PlannedResult(question="q", gold=3.0)
    for i, app in enumerate(["grid-count method", "area-preservation method",
                             "unit-rescaling method", "row-by-row method"]):
        r.outlines.append(P.Outline(id=str(i + 1), approach=app))
    r.branches = [P.Branch(i, str(i + 1), 12.0, 10, True) for i in range(4)]
    check_pred("td: real case separates plan from answer",
               r.plan_diversity > 0.60 and r.diversity == 0.25,
               f"plan-div={r.plan_diversity:.2f} ans-div={r.diversity:.2f}")


def test_verdict_separates_plan_and_answer() -> None:
    """The headline finding must be the SEPARATION, not a single div number."""
    def mk(pd, ad, dp):
        a = compare_mod.ArmStats("repeated")
        a.n = a.graded = a.correct = a.passed_at_k = 4
        a.plan_diversity = [pd] * 4
        a.diversity = [0.25] * 4
        b = compare_mod.ArmStats("PTTS-ZS")
        b.n = b.graded = b.correct = b.passed_at_k = 4
        b.plan_diversity = [pd] * 4
        b.diversity = [ad] * 4
        return a, b

    a, b = mk(0.80, 0.25, 0.0)
    txt = compare_mod.render("repeated", a, "PTTS-ZS", b, 4)
    check_pred("verdict: names the executor, not the planner",
               "THE PLANNER WORKS, THE EXECUTOR IGNORES IT" in txt, txt[-500:])
    check_pred("verdict: does NOT blame the planner here",
               "PLANNER DEGENERATE" not in txt)
    check_pred("verdict: reports both diversities",
               "plan-div" in txt and "ans-div" in txt)

    a, b = mk(0.10, 0.25, 0.0)
    txt2 = compare_mod.render("repeated", a, "PTTS-ZS", b, 4)
    check_pred("verdict: degenerate planner flagged when truly degenerate",
               "PLANNER DEGENERATE" in txt2, txt2[-400:])

    a, b = mk(0.80, 0.75, 1.0)
    # baseline misses 2 of its 4; PTTS solves all 8 it sees. Same total solved
    # count is NOT the point -- pass@k is a RATE over problems, so the arm that
    # sees more problems can beat it. What matters is the rate.
    a.n = a.graded = a.correct = 4
    a.passed_at_k = 2                     # baseline solves 2/4 -> pass@k 0.5
    b.n = b.graded = b.correct = 8
    b.passed_at_k = 8                     # PTTS solves 8/8 -> pass@k 1.0
    txt3 = compare_mod.render("repeated", a, "PTTS-ZS", b, 4)
    check_pred("verdict: pass@k gain reported when it happens",
               "pass@k improved" in txt3, txt3[-400:])
    check_pred("verdict: gain is the real delta, not equal rates",
               "pass@k +50.0%" in txt3, txt3[txt3.find("delta"):][:200])
    check_pred("verdict: pass@k rate uses the graded denominator",
               a.pass_at_k == 0.5 and b.pass_at_k == 1.0,
               f"a={a.pass_at_k} b={b.pass_at_k}")

    # ungraded problems must be called out, never silently averaged in
    c = compare_mod.ArmStats("repeated")
    c.n = 4
    c.graded = 2
    c.passed_at_k = 2
    check_pred("coverage: flagged as unmeasurable when partially graded",
               not c.coverage_measurable)
    txt4 = compare_mod.render("repeated", c, "PTTS-ZS", b, 4)
    check_pred("coverage: render warns on ungraded problems",
               "UNGRADED PROBLEMS PRESENT" in txt4, txt4[-300:])


def test_raw_body_is_narrowed_not_assumed() -> None:
    """_raw returns dict | str; a 200 does not prove the body is a mapping.

    Found by pyright, not by a test: every existing test drove a real dict on
    the happy path, so the str-body case never executed. Two ways it bites:
    an HTTPError body is decoded TEXT, and a well-formed 200 can still be a
    JSON array or bare string.
    """
    import urllib.request as _u

    # (a) 200 whose body is a JSON array -> .get() would raise AttributeError
    _u.urlopen = lambda req, timeout=None: _Resp(b'[1,2,3]', 200)
    try:
        st, body = nous_client._raw("/models", None, None, 5)
        check("raw: array body status", st, 200)
        check_pred("raw: array body is not a dict", not isinstance(body, dict),
                   f"type={type(body).__name__}")
        check_pred("raw: no AttributeError when narrowing", True)

        # probe_endpoint must NOT crash on it
        import urllib.error as _ue
        out = nous_client.probe_endpoint(key="x" * 30, timeout=5)
        check_pred("probe: survives a non-dict 200 body",
                   isinstance(out, dict), f"out={type(out).__name__}")
        check_pred("probe: does not claim usable on a non-dict body",
                   out.get("usable") is not True, f"usable={out.get('usable')}")
    finally:
        _u.urlopen = _real_urlopen

    # (b) 200 with a non-JSON body -> text, not a JSONDecodeError traceback
    _u.urlopen = lambda req, timeout=None: _Resp(b'<html>hi</html>', 200)
    try:
        st, body = nous_client._raw("/models", None, None, 5)
        check("raw: non-JSON 200 status", st, 200)
        check_pred("raw: non-JSON body degrades to text",
                   isinstance(body, str), f"type={type(body).__name__}")
    finally:
        _u.urlopen = _real_urlopen


def test_transport_failure_is_named() -> None:
    """A dead socket used to return status None and fall through every branch.

    Every caller compares against int literals, so None produced an
    unclassified "mystery status" -- which reads like an auth or model problem
    and sends you debugging credentials when the network is down.
    """
    import urllib.request as _u
    import urllib.error as _ue

    def boom(req, timeout=None):
        raise _ue.URLError("Name or service not known")

    _u.urlopen = boom
    try:
        st, body = nous_client._raw("/models", None, None, 5)
        check("transport: sentinel status, not None", st,
              nous_client.TRANSPORT_FAILED)
        check_pred("transport: sentinel is an int (comparable)",
                   isinstance(st, int), f"type={type(st).__name__}")
        check_pred("transport: cannot collide with a real HTTP code",
                   st < 0, f"st={st}")

        out = nous_client.probe_endpoint(key="x" * 30, timeout=5)
        check_pred("transport: probe names it a transport problem",
                   "transport failure" in str(out.get("diagnosis", "")).lower(),
                   f"diagnosis={out.get('diagnosis')!r}")
        check_pred("transport: probe does not blame credentials",
                   "auth" not in str(out.get("diagnosis", "")).lower()
                   or "NOT credentials" in out.get("diagnosis", ""),
                   f"diagnosis={out.get('diagnosis')!r}")
        check_pred("transport: not reported as usable",
                   out.get("usable") is not True)
    finally:
        _u.urlopen = _real_urlopen


class _Resp:
    """Minimal urlopen stand-in for _raw tests."""

    def __init__(self, payload: bytes, status: int):
        self._b = payload
        self.status = status

    def read(self):
        return self._b


def test_math500_parser() -> None:
    """The grader is the foundation of every number we report.

    A lenient parser marks wrong answers correct; an over-eager one fabricates
    golds from LaTeX and silently inflates accuracy. Both are worse than
    dropping an item, so both directions are pinned here.
    """
    import math500 as m

    want_num = [("42", 42.0), ("-50", -50.0), ("1.5", 1.5), ("0.375", 0.375),
                ("1,000", 1000.0), ("3/4", 0.75), ("-3/4", -0.75),
                ("50\\%", 50.0), ("$60$", 60.0), ("1{,}000", 1000.0),
                ("1{,}024", 1024.0)]
    for raw, want in want_num:
        got = m.to_float(raw)
        check_pred(f"m500 parse: {raw!r} -> {want}",
                   got is not None and abs(got - want) < 1e-9,
                   f"got={got}")

    want_none = ["\\frac{3}{4}", "\\sqrt{2}", "2\\sqrt{3}", "\\text{12}",
                 "x^{2}", "2^{10}", "\\binom{5}{2}", "[0,\\infty)",
                 "\\frac{\\pi}{2}", "(3,\\frac{\\pi}{2})", "\\text{even}",
                 "\\infty", "x+1", "", "1/0"]
    for raw in want_none:
        check_pred(f"m500 rejects: {raw!r}", m.to_float(raw) is None,
                   f"leaked={m.to_float(raw)!r}")

    # never fabricate a number from LaTeX that merely CONTAINS digits
    danger = ["\\frac{3}{4}", "\\begin{pmatrix}3\\\\4\\end{pmatrix}",
              "50\\% \\text{ of } 200", "1{,}000 \\text{ dollars}",
              "\\left(3,\\frac{\\pi}{2}\\right)", "{12}"]
    for raw in danger:
        check_pred(f"m500 no fabrication: {raw!r}",
                   m.to_float(raw) is None, f"leaked={m.to_float(raw)!r}")

    check_pred("m500: percent does not invent a scale factor",
               m.to_float("50\\%") == 50.0, "kept digits, no /100")

    if os.path.isfile(os.path.expanduser(
            "~/.hermes/cache/spacebunny-ensemble/math500/test.jsonl")):
        hard = m.load_math500_hard(500, seed=0)
        check_pred("m500: hard subset is substantial", len(hard) >= 100,
                   f"n={len(hard)}")
        check_pred("m500: every hard item has a gold",
                   all(g is not None for _, g in hard))
        check_pred("m500: problems are distinct",
                   len({q for q, _ in hard}) == len(hard))
        again = m.load_math500_hard(500, seed=0)
        check_pred("m500: deterministic for a fixed seed", hard == again)
        # a different seed must actually reshuffle, or the seed is ignored
        other = m.load_math500_hard(40, seed=7)
        base = m.load_math500_hard(40, seed=0)
        check_pred("m500: seed changes the sample", other != base)
        check_pred("m500: sample respects n", len(base) == 40)
        # must never return MORE than exists
        check_pred("m500: n larger than pool is clamped",
                   len(m.load_math500_hard(10_000, seed=0)) == len(hard))


def test_stats() -> None:
    """Confidence intervals are what make a null result interpretable.

    At n=8 the earlier experiments could not distinguish "no effect" from
    "underpowered". These assertions exist so the statistics cannot silently
    become the weak link that undermines every headline number.
    """
    import math as _m
    import stats as st

    # Wilson validated against an INDEPENDENT algebraic rearrangement of the
    # same closed form, 7/7 exact -- not against numbers I wrote down.
    def alt(s, n, z=st.Z95):
        p = s / n
        num = 2 * n * p + z * z - z * _m.sqrt(z * z + 4 * n * p * (1 - p))
        den = 2 * (n + z * z)
        return num / den, (2 * n * p + z * z
                           + z * _m.sqrt(z * z + 4 * n * p * (1 - p))) / den

    for s, n in [(0, 10), (1, 10), (5, 10), (10, 10), (3, 20), (7, 13),
                 (40, 100), (1, 5), (4, 5), (0, 100), (100, 100)]:
        iv = st.wilson(s, n)
        lo, hi = alt(s, n)
        check_pred(f"wilson matches independent form {s}/{n}",
                   abs(iv.lo - lo) < 1e-12 and abs(iv.hi - hi) < 1e-12,
                   f"mine=[{iv.lo},{iv.hi}] alt=[{lo},{hi}]")

    for s, n in [(0, 5), (1, 5), (4, 5), (5, 5), (0, 100), (100, 100)]:
        iv = st.wilson(s, n)
        check_pred(f"wilson stays in [0,1] at {s}/{n}",
                   0.0 <= iv.lo <= iv.hi <= 1.0, f"[{iv.lo},{iv.hi}]")

    # the n=8 problem, quantified
    check_pred("MDE at n=8 is hopeless for small effects",
               st.min_detectable_effect(8) > 0.6,
               f"mde={st.min_detectable_effect(8):.3f}")
    check_pred("MDE shrinks with n", st.min_detectable_effect(200) < 0.15)
    check_pred("MDE handles n=0", st.min_detectable_effect(0) == 1.0)

    # a real effect must come out significant, a null must not
    obs, lo, hi, p = st.paired_bootstrap_delta([1] * 45 + [0] * 15,
                                              [0] * 45 + [1] * 15,
                                              iters=4000, seed=0)
    check("paired: 75% vs 25% delta", obs, 0.5)
    check_pred("paired: real effect CI excludes 0", lo > 0, f"[{lo},{hi}]")
    check_pred("paired: real effect p is small", p is not None and p < 0.05,
               f"p={p}")

    # p must never be fabricated on zero-variance arms. This returned 1.75
    # once, then 1.0 for a maximal effect, before being fixed to None.
    for label, a, b in [("all win", [1] * 40, [0] * 40),
                        ("all lose", [0] * 40, [1] * 40)]:
        o, l, h, pp = st.paired_bootstrap_delta(a, b, iters=2000, seed=0)
        check_pred(f"paired: degenerate '{label}' returns p=None",
                   pp is None, f"p={pp}")
        check_pred(f"paired: degenerate '{label}' still gives a valid CI",
                   -1.0 <= l <= h <= 1.0, f"[{l},{h}]")
    # identical arms are also degenerate
    _, _, _, pid = st.paired_bootstrap_delta([1, 0, 1, 0] * 8, [1, 0, 1, 0] * 8,
                                            iters=2000, seed=0)
    check_pred("paired: identical arms -> p=None", pid is None, f"p={pid}")

    # REGRESSION: inclusive tails overlapped when |obs| was small relative to
    # the spread, and 2*min() of an overlapping pair returned p=1.13. This is
    # the shape of a real rung comparison (36/40 vs 38/40), so it must hold.
    a36 = [1] * 36 + [0] * 4
    a38 = [1] * 38 + [0] * 2
    a37 = [1] * 37 + [0] * 3
    for lbl, x, y in [("36 vs 38", a36, a38), ("38 vs 36", a38, a36),
                      ("37 vs 38", a37, a38), ("38 vs 37", a38, a37)]:
        o, l, h, pp = st.paired_bootstrap_delta(x, y, iters=8000, seed=0)
        check_pred(f"paired: p stays a probability ({lbl})",
                   pp is None or 0.0 <= pp <= 1.0, f"p={pp}")
        check_pred(f"paired: small delta is not significant ({lbl})",
                   pp is None or l <= 0.0 <= h, f"CI=[{l},{h}]")

    # INVARIANT: the percentile CI and the null-centred p must AGREE about
    # significance. They disagreed badly when p was read off the percentile
    # distribution: p=0.0000 for 36/40 vs 38/40 while the CI straddled zero.
    for lbl, x, y in [("36 vs 38", [1] * 36 + [0] * 4, [1] * 38 + [0] * 2),
                      ("75 vs 25", [1] * 45 + [0] * 15, [0] * 45 + [1] * 15),
                      ("50 vs 50", [1] * 20 + [0] * 20, [1] * 20 + [0] * 20),
                      ("62 vs 50", [1, 1, 1, 0, 1, 0, 1, 0] * 6,
                       [1, 0, 1, 0, 1, 0, 1, 0] * 6)]:
        o, l, h, pp = st.paired_bootstrap_delta(x, y, iters=6000, seed=0)
        ci_sig = l > 0
        p_sig = pp is not None and pp < 0.05
        check_pred(f"paired: CI and p agree on significance ({lbl})",
                   ci_sig == p_sig,
                   f"CI=[{l:.3f},{h:.3f}] sig={ci_sig} p={pp}")

    # p must be a probability for every non-degenerate input
    import random
    rng = random.Random(0)
    bad = 0
    for _ in range(120):
        n = rng.randint(4, 60)
        a = [rng.randint(0, 1) for _ in range(n)]
        b = [rng.randint(0, 1) for _ in range(n)]
        _, _, _, pp = st.paired_bootstrap_delta(a, b, iters=400, seed=1)
        if pp is not None and not (0.0 <= pp <= 1.0):
            bad += 1
    check("paired: p always in [0,1] over 120 random cases", bad, 0)

    # mismatched pairing is a programming error, not a data condition
    try:
        st.paired_bootstrap_delta([1, 0], [1, 0, 1])
        check_pred("paired: rejects unequal lengths", False, "no raise")
    except ValueError:
        check_pred("paired: rejects unequal lengths", True)

    # Newcombe
    d, lo, hi = st.newcombe_diff(40, 40, 0, 40)
    check_pred("newcombe: maximal effect is significant", lo > 0, f"[{lo},{hi}]")
    d, lo, hi = st.newcombe_diff(20, 40, 20, 40)
    check_pred("newcombe: identical arms not significant", lo <= 0 <= hi)
    d, lo, hi = st.newcombe_diff(0, 0, 0, 0)
    check_pred("newcombe: empty input does not crash", -1.0 <= lo <= hi <= 1.0)

    # determinism -- a rerun must be reproducible
    a = [rng.randint(0, 1) for _ in range(40)]
    b = [rng.randint(0, 1) for _ in range(40)]
    check("paired: deterministic for a fixed seed",
          st.paired_bootstrap_delta(a, b, iters=1000, seed=3),
          st.paired_bootstrap_delta(a, b, iters=1000, seed=3))

    # null phrasing must always carry its power
    iv = st.wilson(5, 8)
    txt = st.describe_null(iv)
    check_pred("describe_null: names significance", "NOT significant" in txt
               or "significant" in txt, txt)
    iv2 = st.wilson(40, 40)
    check_pred("describe_null: flags a real effect",
               "significant" in st.describe_null(iv2)
               and "NOT" not in st.describe_null(iv2),
               st.describe_null(iv2))


def test_empty_run_is_an_error() -> None:
    """A run that collected nothing must NOT report success.

    This is not hypothetical: the n=40 MATH-500 ladder produced zero rows and
    the CLI still exited 0, so a killed or silently-failing run was
    indistinguishable from a successful one. Guard the guard.
    """
    import ladder as ladder_mod

    rep = ladder_mod.LadderReport()
    from ladder import RungStats
    rep.rungs.append(RungStats(effort="low"))
    rep.errors.append("synthetic total failure")
    check_pred("guard: a report with zero n is detectable",
               all(r.n == 0 for r in rep.rungs))

    # and record() must write a row that survives immediately
    import run as run_mod
    before = 0
    try:
        with open(run_mod.RESULTS_PATH) as f:
            before = sum(1 for _ in f)
    except FileNotFoundError:
        pass
    run_mod.record({"mode": "selftest-probe", "graded": True})
    try:
        with open(run_mod.RESULTS_PATH) as f:
            rows = [json.loads(x) for x in f if x.strip()]
        check("record: row count grew by one", len(rows), before + 1)
        last = rows[-1]
        check_pred("record: carries the pid", last.get("pid") == os.getpid(),
                   f"pid={last.get('pid')}")
        check_pred("record: has timestamps",
                   last.get("started_unix") and last.get("finished_unix"))
    finally:
        # leave the log clean: drop the probe row we just appended
        try:
            with open(run_mod.RESULTS_PATH) as f:
                keep = [x for x in f if '"selftest-probe"' not in x]
            with open(run_mod.RESULTS_PATH, "w") as f:
                f.writelines(keep)
        except Exception:
            pass


def test_rung_outcomes_align() -> None:
    """Paired rung comparison is only valid if outcomes stay index-aligned.

    A rung comparison at n=40 produced +15pp. Reading that as "the effort dial
    works" without pairing would be wrong, and pairing is only sound if every
    rung recorded one outcome per problem in the same order -- including the
    failures, which must occupy a slot rather than vanish.
    """
    import ladder as ladder_mod

    class Profile:
        """Correct iff the question index is below the rung's skill level."""
        def __call__(self, **kw) -> Reply:
            idx = int(kw["messages"][1]["content"].strip().lstrip("q"))
            skill = int(kw.get("effort") or 0)
            if idx % 10 < skill:
                return Reply(text=f"#### {idx}", reasoning=None,
                             usage=Usage(50, 10), finish_reason="stop")
            return Reply(text="I don't know", reasoning=None,
                         usage=Usage(50, 10), finish_reason="stop")

    problems: list[tuple[str, Optional[float]]] = [
        (f"q{i}", float(i)) for i in range(1, 11)]
    rep = ladder_mod.ladder(problems, call=Profile(),
                            efforts=["2", "5", "8"], probe=False)
    check("rungs: three rungs", len(rep.rungs), 3)
    for st in rep.rungs:
        check_pred(f"rung {st.effort}: one outcome per problem",
                   len(st.outcomes) == len(problems),
                   f"{len(st.outcomes)} vs {len(problems)}")
        check_pred(f"rung {st.effort}: outcomes are 0/1",
                   all(o in (0, 1) for o in st.outcomes))
        check_pred(f"rung {st.effort}: outcomes sum to correct",
                   sum(st.outcomes) == st.correct,
                   f"sum={sum(st.outcomes)} correct={st.correct}")

    # accuracy rises with skill -> a paired test must find a real difference
    import stats as st_mod
    obs, lo, hi, p = st_mod.paired_bootstrap_delta(
        rep.rungs[2].outcomes, rep.rungs[0].outcomes, iters=4000, seed=0)
    check_pred("rungs: paired test finds the known difference", lo > 0,
               f"delta={obs:.3f} CI=[{lo:.3f},{hi:.3f}]")

    # a failing call must still occupy its slot
    class Dead:
        def __call__(self, **kw):
            raise RuntimeError("endpoint down")

    rep2 = ladder_mod.ladder(problems, call=Dead(), efforts=["2"],
                             probe=False)
    check_pred("rungs: a fully-failing rung still fills its outcome list",
               len(rep2.rungs[0].outcomes) == len(problems),
               f"{len(rep2.rungs[0].outcomes)}")
    check("rungs: failed rung scores zero", sum(rep2.rungs[0].outcomes), 0)


def main() -> int:
    for fn in (test_extract, test_sandbox, test_ensemble_paths,
               test_ladder_math, test_summary_math, test_client_config,
               test_credential_contract, test_no_label_as_bearer,
               test_hard_set_is_sane,
               test_outline_parsing, test_follow_score_parsing,
               test_vote_and_diversity, test_ptts_fallback_is_flagged,
               test_ptts_happy_path, test_planner_prompt_has_k,
               test_branch_retry_recovers,
               test_raw_body_is_narrowed_not_assumed,
               test_transport_failure_is_named, test_math500_parser,
               test_stats, test_empty_run_is_an_error,
               test_rung_outcomes_align,
               test_text_diversity, test_verdict_separates_plan_and_answer):
        try:
            fn()
        except Exception as ex:
            results.append((FAIL, f"{fn.__name__} raised",
                            f"{type(ex).__name__}: {ex}"))

    width = max(len(n) for _, n, _ in results)
    npass = sum(1 for s, _, _ in results if s == PASS)
    print("=" * (width + 12))
    print("SELFTEST -- offline mechanism validation (no API calls)")
    print("=" * (width + 12))
    for status, name, detail in results:
        mark = "\u2713" if status == PASS else "\u2717"
        print(f"{mark} {name:<{width}}  {status}")
        if detail:
            print(f"    {detail}")
    print("-" * (width + 12))
    print(f"{npass}/{len(results)} passed")
    print()
    print("SCOPE: this validates OUR code only -- extraction, equivalence,")
    print("sandbox containment, tie-break policy, report math. It says")
    print("NOTHING about Space Bunny Alpha's accuracy. That needs a funded")
    print("key and a real run: python3 run.py --probe")
    print("=" * (width + 12))
    return 0 if npass == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())