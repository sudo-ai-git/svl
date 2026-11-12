#!/usr/bin/env python3
"""Spike 014: pyproject.toml + `svlc` console script (L3)."""
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, "/home/sudosudo/.openclaw/workspace")

from harness import verdict                                    # noqa: E402

PYPROJECT = """[build-system]
requires = ["setuptools>=61"]
build-backend = "setuptools.build_meta"

[project]
name = "svl"
version = "0.1.0"
description = "Self-Verifying Language"

[project.scripts]
svlc = "svl.cli:main"
"""

CLI = '''"""Thin `svlc` entry point."""
import sys


def main():
    from svl.compiler_wasm import compile_file_to_wasm
    if len(sys.argv) < 2:
        print("usage: svlc <file.svl>")
        return 2
    with open(sys.argv[1]) as fh:
        wat = compile_file_to_wasm(fh.read())
    print(wat)
    return 0
'''


def main():
    tmp = tempfile.mkdtemp(prefix="svlc_spike_")
    try:
        pkg = os.path.join(tmp, "pkg")
        shutil.copytree("/home/sudosudo/.openclaw/workspace/svl", os.path.join(pkg, "svl"))
        with open(os.path.join(pkg, "svl", "__init__.py"), "w") as fh:
            fh.write('"""SVL — Self-Verifying Language."""\n__version__ = "0.1.0"\n')
        with open(os.path.join(pkg, "svl", "cli.py"), "w") as fh:
            fh.write(CLI)
        with open(os.path.join(pkg, "pyproject.toml"), "w") as fh:
            fh.write(PYPROJECT)

        site = os.path.join(tmp, "site")
        p = subprocess.run([sys.executable, "-m", "pip", "install", "--no-deps",
                            "--target", site, pkg],
                           capture_output=True, text=True, timeout=180)
        if p.returncode != 0:
            return verdict("014-svlc-cli-pyproject", False,
                           f"pip install failed: {p.stderr.strip()[-200:]}")
        script = os.path.join(site, "bin", "svlc")
        if not os.path.exists(script):
            return verdict("014-svlc-cli-pyproject", False, "console script not created")
        env = dict(os.environ, PYTHONPATH=site)
        prog = os.path.join(tmp, "hello.svl")
        with open(prog, "w") as fh:
            fh.write("module m { func main() type int { return 7 } }")
        r = subprocess.run([script, prog], capture_output=True, text=True, env=env, timeout=60)
        ok = (r.returncode == 0 and "(module" in r.stdout)
        return verdict("014-svlc-cli-pyproject", ok,
                       f"svlc ran a program: exit={r.returncode}, WAT emitted={'yes' if '(module' in r.stdout else 'no'}")
    except Exception as exc:
        return verdict("014-svlc-cli-pyproject", False, f"{type(exc).__name__}: {exc}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
