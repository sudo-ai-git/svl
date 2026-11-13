"""`svlc` — the SVL command line.

Subcommands:
  svlc version            print the version
  svlc build <file.svl>   compile to WAT (add --wasm for a binary, --prove for SMT,
                         --interface to write the .svli contract)
  svlc run   <file.svl>   compile and execute, printing the result
                         (--link MODULE.wasm to satisfy `extern "c"` imports from a
                         compiled foreign module; repeatable)
  svlc check <file.svl>   run the verification gate and report
  svlc publish <lib.svl>  verify a library and publish it to a registry (--version)
  svlc install <name>[@<ver>] [--into DIR]   install a package from a registry
  svlc add <name>[@<ver>] [--into DIR]       install it and record it in svl.toml
  svlc list-packages      list packages in a registry
  svlc diff <a> <b>      prove or refute that two functions are equivalent
  svlc corpus             run the corpus regression check
  svlc repl               interactive shell (evaluates a block, remembers definitions)
  svlc lsp                language server over stdio

Imports resolve against the source file's own directory by default, then against the
enclosing project's `svl_modules/` when an `svl.toml` is present.

The gate runs by default; pass --no-strict to compile past a verification failure.
"""
from __future__ import annotations

import argparse
import os
import sys


def _project_context(file_path, base_dir=None):
    """Return (base_dir, extra_dirs) for compiling `file_path`.

    `base_dir` defaults to the source file's own directory, so `import "lib.svl"` next to
    the program resolves — previously the CLI passed no `base_dir` at all, so even a local
    sibling import failed.  If the file lives in a project (an `svl.toml` at or above it),
    the project's `svl_modules/` is appended to the search path so installed dependencies
    resolve exactly like local files.
    """
    src_dir = os.path.dirname(os.path.abspath(file_path))
    base = os.path.abspath(base_dir) if base_dir else src_dir

    extra: list = []
    try:
        from svl.project import find_project_root, load_project
        root = find_project_root(file_path)
        if root is not None:
            extra = load_project(root).search_dirs()
    except Exception:                                           # noqa: BLE001
        pass  # a malformed manifest must not break a plain compile
    return base, extra


def _resolve_source(path):
    """Accept a source file OR a project directory; return the `.svl` file to compile."""
    if os.path.isdir(path):
        from svl.project import project_source_path, SOURCE_NAME
        found = project_source_path(path)
        if found is None:
            raise SystemExit(f"error: {path} has no {SOURCE_NAME}")
        return str(found)
    return path


def _lock_problems(file_path):
    """Lockfile drift for the project enclosing `file_path` (empty when consistent)."""
    try:
        from svl.project import find_project_root, verify_lockfile
        root = find_project_root(file_path)
        return verify_lockfile(root) if root is not None else []
    except Exception as exc:                                    # noqa: BLE001
        return [f"could not read the project lockfile: {exc}"]


def cmd_version(args) -> int:
    from svl import __version__
    print(__version__)
    return 0


def cmd_build(args) -> int:
    path = _resolve_source(args.file)
    src = open(path, encoding="utf-8").read()
    if args.interface:
        from svl.interface import generate_interface, interface_path_for, write_interface
        out_path = interface_path_for(path)
        write_interface(out_path, generate_interface(src))
        print(f"interface written: {out_path}")
        return 0
    drift = _lock_problems(path)
    if drift:
        for problem in drift:
            print(f"error: {problem}", file=sys.stderr)
        print("error: the installed dependency tree does not match svl.lock",
              file=sys.stderr)
        return 1
    from svl.compiler_wasm import compile_file_to_wasm
    base, extra = _project_context(path, getattr(args, "base_dir", None))
    try:
        wat = compile_file_to_wasm(src, strict=not args.no_strict, prove=args.prove,
                                   base_dir=base, extra_dirs=extra)
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
    path = _resolve_source(args.file)
    src = open(path, encoding="utf-8").read()
    drift = _lock_problems(path)
    if drift:
        for problem in drift:
            print(f"error: {problem}", file=sys.stderr)
        return 1
    try:
        base, extra = _project_context(path, getattr(args, "base_dir", None))
        wat = compile_file_to_wasm(src, strict=not args.no_strict, prove=args.prove,
                                   base_dir=base, extra_dirs=extra)
        foreign = _load_links(args.link)
        rv, out = run_wat(wat, foreign=foreign)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if out:
        sys.stdout.write(out.decode("utf-8", "replace"))
    if rv is not None:
        print(f"[main() returned {rv}]")
    return 0


def _load_links(paths):
    """Read each `--link` target as compiled `.wasm` bytes.

    A missing file or a WAT-text file is an error, not a silent skip: the program
    declares the `extern`, so silently dropping it would trap at run time instead of
    failing where the mismatch is visible.
    """
    if not paths:
        return None
    out = []
    for p in paths:
        try:
            with open(p, "rb") as f:
                out.append(f.read())
        except OSError as exc:
            raise SystemExit(f"error: cannot read --link target {p!r}: {exc}")
    return out


def cmd_check(args) -> int:
    from svl.verify_gate import verify_program
    path = _resolve_source(args.file)
    src = open(path, encoding="utf-8").read()
    drift = _lock_problems(path)
    base, extra = _project_context(path, getattr(args, "base_dir", None))
    try:
        from svl.compiler_wasm import compile_file_to_wasm
        # Compiling runs the gate on the LINKED program (imports included), so the
        # check is on the same artifact the compiler would produce.
        compile_file_to_wasm(src, strict=True, base_dir=base, extra_dirs=extra)
        problems = verify_program(src)
    except Exception as exc:
        problems = [str(exc)]
    problems = list(drift) + list(problems)
    if args.json:
        import json
        print(json.dumps({"file": path, "ok": not problems,
                          "problems": problems}, indent=2))
    elif not problems:
        print("verified: no problems found")
    else:
        for p in problems:
            print(f"  - {p}")
    return 0 if not problems else 1


def cmd_publish(args) -> int:
    """Verify a source file, create a package, and publish it to a registry directory."""
    from svl.package_manager import PackageManager
    src = open(args.file, encoding="utf-8").read()
    name = args.name or os.path.splitext(os.path.basename(args.file))[0]
    try:
        pm = PackageManager(registry_dir=args.registry)
        meta = pm.create_package(name, args.version, src,
                                 description=args.description, author=args.author)
        pm.publish(name, args.version, registry_dir=args.registry)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"published {meta.name}@{meta.version} -> {pm.registry_dir / name / args.version}")
    print(f"  source sha256  {meta.source_sha256}")
    print(f"  wasm   sha256  {meta.wasm_sha256}")
    return 0


def cmd_install(args) -> int:
    """Install a package from a registry into a project's `svl_modules/`."""
    from svl.package_manager import PackageManager
    name, _, version = args.spec.partition("@")
    if not name:
        print(f"error: expected <name>[@<version>], got {args.spec!r}", file=sys.stderr)
        return 1
    try:
        pm = PackageManager(registry_dir=args.registry)
        path = pm.install(name, version or "latest",
                          registry_dir=args.registry, into_dir=args.into)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"installed {name} -> {path}")
    return 0


def cmd_add(args) -> int:
    """Install a dependency and record it in the project manifest."""
    from svl.package_manager import PackageManager
    from svl.project import load_project, record_dependency
    name, _, version = args.spec.partition("@")
    if not name:
        print(f"error: expected <name>[@<version>], got {args.spec!r}", file=sys.stderr)
        return 1
    try:
        pm = PackageManager(registry_dir=args.registry)
        path = pm.install(name, version or "latest",
                          registry_dir=args.registry, into_dir=args.into)
        manifest = record_dependency(load_project(args.into), name, version or "latest")
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"added {name} -> {path}")
    print(f"manifest: {manifest}")
    return 0


def cmd_list_packages(args) -> int:
    from svl.package_manager import PackageManager
    pm = PackageManager(registry_dir=args.registry)
    entries = []
    index = args.registry if args.registry else str(pm.registry_dir)
    import json
    from pathlib import Path
    index_file = Path(index) / "index.json"
    if index_file.is_file():
        with open(index_file) as fh:
            for name, versions in json.load(fh).get("packages", {}).items():
                for version in versions:
                    entries.append(f"{name}@{version}")
    if not entries:
        print(f"no packages published to {index}")
        return 0
    for e in sorted(entries):
        print(e)
    return 0


def cmd_diff(args) -> int:
    """Prove (or refute) that two function files are equivalent."""
    from svl.equivalence import svlc_diff
    f_src = open(args.file_a, encoding="utf-8").read()
    g_src = open(args.file_b, encoding="utf-8").read()
    print(svlc_diff(f_src, g_src))
    return 0


def cmd_corpus(args) -> int:
    from svl.corpus_check import main as corpus_main
    return corpus_main()


def cmd_repl(args) -> int:
    from svl.repl import run_repl
    run_repl()
    return 0


def cmd_lsp(args) -> int:
    from svl.lsp_server import main
    main()
    return 0


def cmd_explore(args) -> int:
    """Write a self-contained HTML page showing the AST and inferred types."""
    from svl.ast_explorer import build_explorer_html
    path = _resolve_source(args.file)
    src = open(path, encoding="utf-8").read()
    try:
        page = build_explorer_html(src, title=os.path.basename(path))
    except Exception as exc:                                    # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        return 1
    out = args.out or (os.path.splitext(path)[0] + ".html")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(page)
    print(f"explorer written: {out}")
    return 0


def cmd_new(args) -> int:
    """Scaffold a project and prove the starter program compiles and runs."""
    from svl.project import create_project, ManifestError, SOURCE_NAME
    try:
        project = create_project(args.name, args.version, root=args.dir)
    except ManifestError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    src = (project.root / SOURCE_NAME).read_text(encoding="utf-8")
    # The scaffold is verified, not assumed: compile it, then run it.
    try:
        from svl.compiler_wasm import compile_file_to_wasm
        from svl.repl import run_wat
        wat = compile_file_to_wasm(src, strict=True)
        rv, out = run_wat(wat)
    except Exception as exc:                                    # noqa: BLE001
        print(f"error: the generated starter did not verify: {exc}", file=sys.stderr)
        return 1

    print(f"created {project.root}")
    print(f"  {project.manifest_path()}")
    print(f"  {project.root / SOURCE_NAME}")
    print(f"starter verified: main() returned {rv}")
    if out:
        sys.stdout.write(out.decode("utf-8", "replace"))
    print("run it with: svlc run", project.root)
    return 0


def cmd_agent(args) -> int:
    """Machine-readable compile/run/verify report for one source file.

    This is the agent interface: a single JSON document on stdout with no prose, so an
    automated caller can branch on `ok` without parsing human output.  `--wat` adds the
    binary artifact as base64.
    """
    import base64
    import json
    import time

    path = _resolve_source(args.file)
    src = open(path, encoding="utf-8").read()
    drift = _lock_problems(path)
    base, extra = _project_context(path, getattr(args, "base_dir", None))

    report = {
        "file": path,
        "ok": False,
        "compiled": False,
        "wat_sha256": None,
        "wat_bytes": None,
        "result": None,
        "stdout": None,
        "problems": [],
        "timings_ms": {},
    }
    if args.wat:
        report["wasm_base64"] = None

    t0 = time.perf_counter()
    try:
        from svl.compiler_wasm import compile_file_to_wasm, wasm_sha256
        wat = compile_file_to_wasm(src, strict=not args.no_strict, prove=args.prove,
                                   base_dir=base, extra_dirs=extra)
        report["compiled"] = True
        report["wat_sha256"] = wasm_sha256(wat)
        report["wat_bytes"] = len(wat.encode("utf-8"))
    except Exception as exc:                                    # noqa: BLE001
        report["problems"].append(str(exc))
        report["timings_ms"]["compile"] = round((time.perf_counter() - t0) * 1000, 3)
        report["problems"].extend(drift)
        print(json.dumps(report, indent=2))
        return 1
    report["timings_ms"]["compile"] = round((time.perf_counter() - t0) * 1000, 3)

    t1 = time.perf_counter()
    try:
        from svl.repl import run_wat
        foreign = _load_links(args.link) if getattr(args, "link", None) else None
        rv, out = run_wat(wat, foreign=foreign)
        report["result"] = rv
        report["stdout"] = out.decode("utf-8", "replace") if out else ""
    except Exception as exc:                                    # noqa: BLE001
        report["problems"].append(f"run: {exc}")
    report["timings_ms"]["run"] = round((time.perf_counter() - t1) * 1000, 3)

    if args.wat:
        import wasmtime
        report["wasm_base64"] = base64.b64encode(wasmtime.wat2wasm(wat)).decode("ascii")

    report["problems"].extend(drift)
    report["ok"] = not report["problems"]
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="svlc",
        description="SVL — Self-Verifying Language (compile to WASM with a verification gate)",
        epilog="The verification gate runs by default; --no-strict bypasses it.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("version", help="print the version").set_defaults(func=cmd_version)

    b = sub.add_parser("build", help="compile to WAT")
    b.add_argument("file")
    b.add_argument("--wasm", action="store_true", help="emit a binary module")
    b.add_argument("--interface", action="store_true",
                   help="write the module's .svli interface artifact and exit")
    b.add_argument("--prove", action="store_true",
                   help="discharge every assert with the Z3 SMT prover")
    b.add_argument("--base-dir", default=None,
                   help="directory imports resolve against (default: the source file's own)")
    b.add_argument("--no-strict", action="store_true")
    b.set_defaults(func=cmd_build)

    r = sub.add_parser("run", help="compile and execute")
    r.add_argument("file")
    r.add_argument("--prove", action="store_true")
    r.add_argument("--no-strict", action="store_true")
    r.add_argument("--base-dir", default=None,
                   help="directory imports resolve against (default: the source file's own)")
    r.add_argument("--link", action="append", metavar="MODULE.wasm",
                   help="link a compiled foreign module to satisfy `extern \"c\"` "
                        "imports (repeatable)")
    r.set_defaults(func=cmd_run)

    c = sub.add_parser("check", help="run the verification gate")
    c.add_argument("file")
    c.add_argument("--json", action="store_true", help="emit the problems as JSON")
    c.add_argument("--base-dir", default=None)
    c.set_defaults(func=cmd_check)

    pub = sub.add_parser("publish", help="verify a library and publish it to a registry")
    pub.add_argument("file")
    pub.add_argument("--name", default=None,
                     help="package name (default: the source file's stem)")
    pub.add_argument("--version", required=True, help="package version (semver)")
    pub.add_argument("--description", default="")
    pub.add_argument("--author", default="")
    pub.add_argument("--registry", default=None,
                     help="registry directory (default: ~/.svl/registry)")
    pub.set_defaults(func=cmd_publish)

    inst = sub.add_parser("install", help="install a package into a project")
    inst.add_argument("spec", help="<name>[@<version>] (default version: latest)")
    inst.add_argument("--into", default=".", help="project directory (default: cwd)")
    inst.add_argument("--registry", default=None,
                      help="registry directory (default: ~/.svl/registry)")
    inst.set_defaults(func=cmd_install)

    add = sub.add_parser("add", help="install a dependency and record it in svl.toml")
    add.add_argument("spec", help="<name>[@<version>]")
    add.add_argument("--into", default=".", help="project directory (default: cwd)")
    add.add_argument("--registry", default=None,
                     help="registry directory (default: ~/.svl/registry)")
    add.set_defaults(func=cmd_add)

    lp = sub.add_parser("list-packages", help="list packages in a registry")
    lp.add_argument("--registry", default=None,
                    help="registry directory (default: ~/.svl/registry)")
    lp.set_defaults(func=cmd_list_packages)

    d = sub.add_parser("diff", help="prove or refute that two functions are equivalent")
    d.add_argument("file_a", help="file containing the first function")
    d.add_argument("file_b", help="file containing the second function")
    d.set_defaults(func=cmd_diff)

    sub.add_parser("corpus", help="run the corpus regression check").set_defaults(func=cmd_corpus)
    sub.add_parser("repl", help="interactive shell").set_defaults(func=cmd_repl)
    sub.add_parser("lsp", help="language server over stdio").set_defaults(func=cmd_lsp)

    n = sub.add_parser("new", help="scaffold a project (svl.toml + source.svl)")
    n.add_argument("name", help="project name (a directory of this name is created)")
    n.add_argument("--version", default="0.1.0", help="initial version (default 0.1.0)")
    n.add_argument("--dir", default=None,
                   help="parent directory (default: create ./<name>)")
    n.set_defaults(func=cmd_new)

    ex = sub.add_parser("explore", help="write an HTML AST/type explorer page")
    ex.add_argument("file", help="source file, or a project directory")
    ex.add_argument("--out", default=None, help="output path (default: <file>.html)")
    ex.set_defaults(func=cmd_explore)

    ag = sub.add_parser("agent", help="JSON compile/run/verify report for an agent")
    ag.add_argument("file", help="source file, or a project directory")
    ag.add_argument("--prove", action="store_true")
    ag.add_argument("--no-strict", action="store_true")
    ag.add_argument("--wat", action="store_true",
                    help="include the binary artifact as base64")
    ag.add_argument("--link", action="append", metavar="MODULE.wasm")
    ag.add_argument("--base-dir", default=None)
    ag.set_defaults(func=cmd_agent)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
