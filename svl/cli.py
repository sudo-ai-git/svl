"""`svlc` — the SVL command line.

Subcommands:
  svlc version            print the version
  svlc build <file.svl>   compile to WAT (add --wasm for a binary)
  svlc run   <file.svl>   compile and execute, printing the result
  svlc check <file.svl>   run the verification gate and report
  svlc corpus             run the corpus regression check

The gate runs by default; pass --no-strict to compile past a verification failure.
"""
from __future__ import annotations

import argparse
import sys


def _compiler():
    from svl.compiler_wasm import compile_file_to_wasm
    return compile_file_to_wasm


def cmd_version(args) -> int:
    from svl import __version__
    print(__version__)
    return 0


def cmd_build(args) -> int:
    from svl.compiler_wasm import compile_file_to_wasm
    src = open(args.file, encoding="utf-8").read()
    try:
        wat = compile_file_to_wasm(src, strict=not args.no_strict)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if args.wasm:
        try:
            import wasmtime
        except ImportError:
            print("error: wasmtime is required for --wasm", file=sys.stderr)
            return 1
        sys.stdout.buffer.write(wasmtime.wat2wasm(wat))
    else:
        print(wat)
    return 0


def cmd_run(args) -> int:
    from svl.compiler_wasm import compile_file_to_wasm
    from svl.repl import run_wat
    src = open(args.file, encoding="utf-8").read()
    try:
        wat = compile_file_to_wasm(src, strict=not args.no_strict)
        rv, out = run_wat(wat)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if out:
        sys.stdout.write(out.decode("utf-8", "replace"))
    if rv is not None:
        print(f"[main() returned {rv}]")
    return 0


def cmd_check(args) -> int:
    from svl.verify_gate import verify_program
    src = open(args.file, encoding="utf-8").read()
    problems = verify_program(src)
    if not problems:
        print("verified: no problems found")
        return 0
    for p in problems:
        print(f"  - {p}")
    return 1


def cmd_corpus(args) -> int:
    from svl.corpus_check import main as corpus_main
    return corpus_main()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="svlc", description="SVL — Self-Verifying Language")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("version", help="print the version").set_defaults(func=cmd_version)

    b = sub.add_parser("build", help="compile to WAT")
    b.add_argument("file")
    b.add_argument("--wasm", action="store_true", help="emit a binary module")
    b.add_argument("--no-strict", action="store_true")
    b.set_defaults(func=cmd_build)

    r = sub.add_parser("run", help="compile and execute")
    r.add_argument("file")
    r.add_argument("--no-strict", action="store_true")
    r.set_defaults(func=cmd_run)

    c = sub.add_parser("check", help="run the verification gate")
    c.add_argument("file")
    c.set_defaults(func=cmd_check)

    sub.add_parser("corpus", help="run the corpus regression check").set_defaults(func=cmd_corpus)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
