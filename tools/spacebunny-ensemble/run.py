#!/usr/bin/env python3
"""spacebunny-ensemble -- papers #2 and #4 against stealth/space-bunny-alpha.

  #4  2604.17433  CoT-PoT ensembling: 2 samples instead of k, third call
                 only on disagreement.
  #2  2607.02436  reasoning_effort as a measured ladder, reporting
                 first-try rate and tokens-per-correct.

Everything is inference-time only: no weights, no gradients, no logprobs
(the endpoint does not offer logprobs, which is why nothing here depends on
them).

  python3 run.py --probe                     # is the endpoint usable?
  python3 run.py --ladder -n 20              # measure the effort dial
  python3 run.py --ensemble -n 20            # measure CoT-PoT
  python3 run.py --both -n 20                # both, sequentially
  python3 run.py -q "What is 17*23?::391"    # one problem, inline

Results append to results.jsonl so runs are comparable over time. Every row
records the model id and whether the run was graded -- an ungraded run must
never be mistaken for a measured one.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import datasets as ds          # noqa: E402
import extract                  # noqa: E402
import ladder as ladder_mod     # noqa: E402
import nous_client              # noqa: E402
import selftest as st          # noqa: E402

RESULTS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "results.jsonl")


_T0 = time.time()          # process start, so elapsed spans are real


def record(payload: dict) -> None:
    payload["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    payload["model"] = nous_client.MODEL
    payload.setdefault("pid", os.getpid())
    # started_unix may be supplied by the caller so a long run's duration is
    # measurable. Defaulting it HERE made every span zero, because the default
    # was taken at record time -- long runs looked instantaneous in the log.
    payload.setdefault("started_unix", time.time())
    payload["finished_unix"] = time.time()
    payload["elapsed_sec"] = round(
        payload["finished_unix"] - payload["started_unix"], 1)
    with open(RESULTS_PATH, "a") as f:
        f.write(json.dumps(payload) + "\n")
        f.flush()
        os.fsync(f.fileno())      # a kill at minute 25 must not lose the row


def make_call(effort_default: str | None):
    """Bind the verified-lite client into the signature the modules expect."""
    def call(*, messages, effort=None, temperature=None, top_p=None,
             max_tokens=2048, **_):
        return nous_client.chat(
            messages, effort=effort if effort is not None else effort_default,
            temperature=temperature, top_p=top_p, max_tokens=max_tokens)
    return call


def get_problems(args) -> list:
    if args.question:
        return ds.load_inline(args.question)
    if args.jsonl:
        return ds.load_jsonl(args.jsonl, limit=args.n)
    if args.math500:
        import math500 as m5
        items = (m5.load_math500_hard(args.n, seed=args.seed) if args.hard
                 else m5.load_math500(args.n, seed=args.seed))
        print(f"dataset: MATH-500 ({'levels 4-5' if args.hard else 'all levels'})"
              f"  {m5.describe(items)}")
        return items
    if args.hard:
        return ds.load_hard(args.n)
    return ds.load_gsm8k(args.n, split=args.split, seed=args.seed,
                         shuffle=args.shuffle)


def banner(text: str) -> None:
    print()
    print("=" * 96)
    print(text)
    print("=" * 96)


def do_probe() -> int:
    banner(f"ENDPOINT PROBE -- {nous_client.MODEL}")
    p = nous_client.probe_endpoint()
    for k, v in p.items():
        print(f"  {k:20} {v}")
    if p.get("usable"):
        print()
        print("  Endpoint is live. Run --ladder or --ensemble for real numbers.")
        record({"mode": "probe", "usable": True})
        return 0

    print()
    print(f"  NOT USABLE -- {p.get('diagnosis', 'unknown')}")
    if p.get("remedy"):
        print(f"  remedy: {p['remedy']}")
    print()
    print("  Facts, so this is not re-diagnosed from scratch next time:")
    print("    * /v1/models is PUBLIC (200 with no auth) and lists this model")
    print("    * /v1/chat/completions requires auth; unauthenticated it answers")
    print("      400 'Unknown model' for EVERY listed model -- that message is")
    print("      the no-auth path, not a bad model id (a truly absent model")
    print("      returns 404 'not found in our configuration')")
    print("    * pricing is 0/0, so the blocker is auth, not credits-at-odds")
    print()
    print("  No accuracy number for this model exists in this repo. Nothing")
    print("  below will run until --probe reports usable=True.")
    record({"mode": "probe", "usable": False,
            "diagnosis": p.get("diagnosis"), "chat_status": p.get("chat_status")})
    return 2


def do_selftest() -> int:
    return st.main()


def do_ladder(args) -> int:
    problems = get_problems(args)
    if not problems:
        print("no problems loaded")
        return 1
    call = make_call(args.effort)
    banner(f"REASONING-EFFORT LADDER -- {len(problems)} problems "
           f"(paper 2607.02436)\nefforts: {' -> '.join(args.rungs)}")
    print("CoT only, temperature 0. Effort is the only variable.")
    rep = ladder_mod.ladder(problems, call=call, efforts=args.rungs,
                            probe=not args.no_probe,
                            max_tokens=args.max_tokens, verbose=args.verbose)
    print(rep.render())
    payload = {"mode": "ladder", "graded": True, "n": len(problems),
               "started_unix": _T0,
               "efforts": args.rungs, "errors": rep.errors[:5],
               "rungs": [{"effort": r.effort, "n": r.n, "correct": r.correct,
                          "acc": r.acc, "first_try": r.first_try_rate,
                          "tokens": r.tokens, "cost_per_correct":
                              (None if r.cost_per_correct == float("inf")
                               else r.cost_per_correct)}
                         for r in rep.rungs],
                # per-item correctness per rung. Needed to run a PAIRED test
                # between rungs: they see the same problems, so pairing is
                # both valid and much tighter than comparing two independent
                # accuracies. Without it a +15pp swing is uninterpretable.
                "rung_outcomes": {str(r.effort): r.outcomes
                                  for r in rep.rungs}}
    if rep.rungs and all(r.n == 0 for r in rep.rungs):
        # Every rung failed. Returning 0 here would report success for a run
        # that measured nothing -- the exact failure this harness exists to
        # prevent. A run that produced no data is an error, loudly.
        print("\nERROR: every rung failed; no data was collected.", file=sys.stderr)
        for e in rep.errors[:10]:
            print(f"  {e}", file=sys.stderr)
        print(f"  ({len(rep.errors)} errors total)", file=sys.stderr)
        return 1

    record(payload)
    print(f"\nappended to {RESULTS_PATH}")
    return 0


def do_ensemble(args) -> int:
    problems = get_problems(args)
    if not problems:
        print("no problems loaded")
        return 1
    call = make_call(args.effort)
    banner(f"CoT-PoT ENSEMBLE -- {len(problems)} problems (paper 2604.17433)\n"
           f"effort={args.effort or 'unset'}  "
           f"escalation={'on' if not args.no_escalate else 'off'}")
    results, s = ladder_mod.ensemble_sweep(
        problems, call=call, effort=args.effort,
        max_tokens=args.max_tokens,
        allow_escalation=not args.no_escalate,
        verbose=args.verbose)
    banner("ENSEMBLE SUMMARY")
    graded = sum(1 for r in results if r.correct is not None)
    print(f"  n                     {s['n']}")
    print(f"  graded                {graded}")
    if graded:
        print(f"  accuracy              {s['accuracy']:.1%}")
    print(f"  CoT/PoT agreed        {s['agreed_no_escalation']}/{s['n']} "
          f"({s['agreement_rate']:.1%})")
    print(f"  escalated             {s['escalated']}/{s['n']} "
          f"({s['escalation_rate']:.1%})")
    print(f"  calls/problem         {s['calls_per_problem']:.2f}"
          f"   <- the k-reduction claim")
    print(f"  tokens/problem        {s['tokens_per_problem']:.0f}")
    print(f"  tokens/correct        {s['tokens_per_correct']:.0f}")
    print(f"  wall clock            {s['wall_sec']:.1f}s")

    # PoT-vs-CoT head to head: is the executable path actually carrying weight?
    cot_only = [r.attempts[0] for r in results]
    pot_only = [r.attempts[1] for r in results]
    def acc(ats):
        g = [(a, r.gold) for a, r in zip(ats, results) if r.gold is not None]
        if not g:
            return None
        return sum(1 for a, gold in g
                   if extract.answers_agree(a.answer, gold) is True) / len(g)
    ac, ap = acc(cot_only), acc(pot_only)
    print()
    print("  --- mode head-to-head (independent accuracy, not the ensemble) ---")
    print(f"  CoT alone             {ac:.1%}" if ac is not None else "  CoT alone      n/a")
    print(f"  PoT alone             {ap:.1%}" if ap is not None else "  PoT alone      n/a")
    pot_exec = sum(1 for a in pot_only if a.ok)
    print(f"  PoT programs executed {pot_exec}/{len(pot_only)}")
    if ac is not None and ap is not None:
        better = "PoT" if ap > ac else ("CoT" if ac > ap else "tie")
        print(f"  stronger single mode  {better}")
        print("  (this is the premise of 2604.17433: if one mode dominates,")
        print("   ensembling cannot help much -- check this before trusting it)")

    record({"mode": "ensemble", "graded": bool(graded),
            "started_unix": _T0, **s})
    print(f"\nappended to {RESULTS_PATH}")
    return 0


def do_planned(args) -> int:
    import compare
    problems = get_problems(args)
    if not problems:
        print("no problems loaded")
        return 1
    k = args.branches
    call = make_call(args.effort)

    banner(f"PLANNED vs REPEATED -- k={k} branches (paper 2609.27374)")
    print(f"{len(problems)} problems from {'hard set' if args.hard else args.split}")
    print(f"effort={args.effort or 'unset'}  "
          f"planner_temp={args.planner_temp}  "
          f"executor_temp={args.exec_temp}")
    print()
    print("--- baseline: k independent samples (repeated sampling) ---")
    base = compare.run_repeated(problems, k, call, effort=args.effort,
                                temperature=args.exec_temp,
                                max_tokens=args.max_tokens)
    print(f"  acc={base.acc:.1%}  pass@k={base.pass_at_k:.1%}  "
          f"diversity={base.mean_diversity:.2f}  calls={base.calls}")
    print()
    print("--- PTTS-ZS: 1 planner pass + k coordinated branches ---")
    pt = compare.run_ptts(problems, k, call, effort=args.effort,
                          planner_temperature=args.planner_temp,
                          executor_temperature=args.exec_temp,
                          max_tokens=args.max_tokens, verbose=args.verbose)
    print()
    print(compare.render("repeated", base, "PTTS-ZS", pt, k))

    payload = {"mode": "planned_vs_repeated", "graded": base.graded > 0,
               "started_unix": _T0,
               "k": k, "n": len(problems), "effort": args.effort,
               "planner_temp": args.planner_temp,
               "exec_temp": args.exec_temp,
               "arms": {"repeated": _arm(base), "ptts": _arm(pt)}}
    if pt.n == 0:
        print("\nERROR: PTTS arm collected no data; nothing to compare.",
              file=sys.stderr)
        for e in getattr(pt, "errors", [])[:10]:
            print(f"  {e}", file=sys.stderr)
        return 1
    if base.n == 0:
        print("\nERROR: baseline arm collected no data; refusing to report a "
              "comparison against nothing.", file=sys.stderr)
        return 1

    record(payload)
    print(f"appended to {RESULTS_PATH}")
    return 0


def _arm(st) -> dict:
    d = {"n": st.n, "graded": st.graded, "acc": st.acc,
         "pass_at_k": st.pass_at_k, "calls": st.calls, "tokens": st.tokens,
         "mean_diversity": st.mean_diversity,
         "mean_plan_diversity": st.mean_plan_diversity,
         "mean_spread": st.mean_spread,
         "fallbacks": st.fallbacks, "sec": st.sec}
    d["mean_adherence"] = st.mean_adherence
    return d


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--probe", action="store_true",
                   help="check endpoint liveness + auth, then exit")
    p.add_argument("--selftest", action="store_true",
                   help="offline mechanism tests, no API calls")
    p.add_argument("--ladder", action="store_true",
                   help="run the reasoning_effort ladder")
    p.add_argument("--planned", action="store_true",
                   help="PTTS-ZS vs repeated sampling at matched budget")
    p.add_argument("--ensemble", action="store_true",
                   help="run the CoT-PoT ensemble")
    p.add_argument("--both", action="store_true",
                   help="ladder then ensemble")

    p.add_argument("-n", type=int, default=10, help="how many problems")
    p.add_argument("--split", default="test", choices=["train", "test"])
    p.add_argument("--math500", action="store_true",
                   help="use MATH-500 instead of GSM8K -- a real published "
                        "suite with headroom, so a null result means something")
    p.add_argument("--hard", action="store_true",
                   help="use the built-in harder multi-step set instead of "
                        "GSM8K (GSM8K is saturated for this model)")
    p.add_argument("--jsonl", help="load problems from a JSONL file")
    p.add_argument("-q", "--question", action="append",
                   help='inline problem; "text ::42" for a gold answer')
    p.add_argument("--shuffle", action="store_true",
                   help="shuffle the sample (fixed seed)")
    p.add_argument("--seed", type=int, default=0)

    p.add_argument("--branches", type=int, default=4,
                   help="branches per problem for --planned (default: 4)")
    p.add_argument("--planner-temp", type=float, default=0.9,
                   help="planner temperature; must be >0 or the planner "
                        "returns k copies of one plan (default: 0.9)")
    p.add_argument("--exec-temp", type=float, default=0.7,
                   help="executor/baseline temperature (default: 0.7)")
    p.add_argument("--effort", default="medium",
                   help="effort for --ensemble (default: medium)")
    p.add_argument("--rungs", nargs="+",
                   default=["low", "medium", "high"],
                   help="effort ladder, ascending (low -> high)")
    p.add_argument("--max-tokens", type=int, default=2048)
    p.add_argument("--no-probe", action="store_true",
                   help="skip the effort-value probe on the ladder")
    p.add_argument("--no-escalate", action="store_true",
                   help="disable the third tie-break call")
    p.add_argument("-v", "--verbose", action="store_true")

    args = p.parse_args(argv)
    if args.selftest:
        return do_selftest()
    if args.probe:
        return do_probe()
    want_ladder = args.ladder or args.both
    want_ens = args.ensemble or args.both
    want_planned = args.planned
    if not (want_ladder or want_ens or want_planned):
        p.print_help()
        print("\nnothing to do -- pass --probe, --selftest, --ladder, "
              "--ensemble, --planned, or --both")
        return 1

    rc = 0
    if want_ladder:
        rc |= do_ladder(args)
    if want_ens:
        rc |= do_ensemble(args)
    if want_planned:
        rc |= do_planned(args)
    return rc


if __name__ == "__main__":
    sys.exit(main())