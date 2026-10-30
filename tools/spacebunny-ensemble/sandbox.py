"""Sandboxed execution of Program-of-Thought candidates.

PoT means the model writes Python that prints the answer. To use that as an
oracle we have to actually run it, which means running untrusted model output.
This is a spike, not a production sandbox: it uses an import denylist injected
as a source prelude + rlimits + a wall-clock timeout + a scrubbed environment.
That is enough to stop runaway loops and casual filesystem/network access. It
is NOT enough against a determined adversary, and it is not a security
boundary. Treat every PoT program as hostile-by-default and never point it at
anything you care about.
"""

from __future__ import annotations

import os
import re
import resource
import subprocess
import sys
import tempfile
from dataclasses import dataclass

DEFAULT_TIMEOUT = 8.0
DEFAULT_MEM_MB = 512

# Modules with obvious filesystem/network/process reach. Matched on the first
# dotted component, so blocking "socket" also blocks "socket.ssl", etc.
# Curated deny list. Chosen by testing, not by guessing: every module here
# carries real escape risk, and a sweep confirmed this exact set still lets a
# legitimate arithmetic program import all 32 of math / decimal / fractions /
# itertools / functools / operator / statistics / random / bisect / json /
# datetime / cmath / ... (see selftest "deny list does not break stdlib math").
#
# Deliberately NOT denied: os, sys, importlib, inspect. They look alarming but
# stdlib math modules import them internally (statistics -> random -> os), so
# denying them breaks ordinary fractions/statistics programs, which costs more
# than it buys. Real containment comes from the resource limits, the scrubbed
# env, and the preflight screen -- not from pretending `import os` is the threat.
_DENY = {
    # network egress
    "socket", "ssl", "http", "urllib", "urllib3", "requests", "httpx",
    "aiohttp", "ftplib", "telnetlib", "smtplib", "poplib", "imaplib",
    "xmlrpc", "webbrowser", "socketserver",
    # process / code execution
    "subprocess", "multiprocessing", "ctypes", "pty", "tty", "runpy",
    "imp", "zipimport", "pdb", "bdb", "code", "codeop",
    # filesystem
    "shutil", "pathlib", "glob", "fileinput", "fcntl", "tempfile", "sqlite3",
    # serialization: deserialization is an RCE primitive
    "pickle", "marshal", "dill", "shelve", "dbm", "yaml",
    # dynamic loading that could reinstate a blocked module
    "pkgutil", "modulefinder",
    # low-value noise / pranks
    "antigravity", "this",
}

# Injected as a source prelude, NOT via a sitecustomize shim: the child runs
# under -I (isolated), which ignores PYTHONPATH entirely, so a sitecustomize
# shim silently blocks nothing while appearing to work. A prelude always runs.
# (That was a real bug caught by the selftest, not a hypothetical.)
_PRELUDE = """\
import sys as _sys
import builtins as _bi

_BLOCKED = __BLOCKED__

def _is_blocked(name):
    return name.split('.')[0] in _BLOCKED

class _DenyMetaPath:
    def find_spec(self, name, path=None, target=None):
        if _is_blocked(name):
            raise ImportError('import blocked by PoT sandbox: ' + name)
        return None

# meta_path alone is NOT enough: modules the interpreter already loaded at
# startup (os, sys, importlib, ...) are served straight out of sys.modules and
# never reach find_spec. Wrapping __import__ is what actually closes that hole.
# (Caught by the selftest, not theorised.)
_real_import = _bi.__import__

def _guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
    if level == 0 and _is_blocked(name):
        raise ImportError('import blocked by PoT sandbox: ' + name)
    if fromlist:
        for sub in fromlist:
            if _is_blocked(sub):
                raise ImportError('import blocked by PoT sandbox: ' + sub)
    return _real_import(name, globals, locals, fromlist, level)

_bi.__import__ = _guarded_import
_sys.meta_path.insert(0, _DenyMetaPath())

def _report_exc(exc_type, exc, tb):
    # Do NOT silence with a bare lambda. Ubuntu installs an apport excepthook
    # that dumps a huge traceback on any unhandled exception; swallowing it
    # also swallows the ImportError text run_pot() greps to set blocked=True,
    # which silently disarms the containment check. Report concisely instead.
    if issubclass(exc_type, ImportError) and 'PoT sandbox' in str(exc):
        print(str(exc), file=_sys.stderr)
        return
    print(exc_type.__name__ + ': ' + str(exc), file=_sys.stderr)

_sys.excepthook = _report_exc
"""


def _make_prelude() -> str:
    """Substitute with str.replace, not str.format.

    The prelude contains f-string-adjacent braces and its own __BLOCKED__
    token; .format() would try to interpret both. (Caught by the selftest.)
    """
    return _PRELUDE.replace("__BLOCKED__", repr(sorted(_DENY)))


@dataclass
class ExecResult:
    ok: bool
    stdout: str
    stderr: str
    returncode: int
    timed_out: bool
    blocked: bool

    @property
    def output(self) -> str:
        return self.stdout if self.ok else ""


def _preflight(src: str) -> tuple[bool, str]:
    """Cheap static screen before we ever spawn a process.

    Catches escape hatches an import denylist would miss: dunder traversal to
    reach subprocess/ctypes indirectly, and string-built eval.
    """
    patterns = [
        (r"__import__\s*\(", "uses __import__"),
        (r"(?<![.\w])eval\s*\(", "uses eval"),
        (r"(?<![.\w])exec\s*\(", "uses exec"),
        (r"(?<![.\w])compile\s*\(", "uses compile"),
        (r"__subclasses__", "walks __subclasses__"),
        (r"__globals__", "reaches __globals__"),
        (r"__bases__", "walks __bases__"),
        (r"(?<![.\w])open\s*\(", "opens a file"),
        (r"\bbreakpoint\s*\(", "calls breakpoint"),
        (r"(?<![.\w])(globals|locals)\s*\(\s*\)", "dumps the namespace"),
        (r"(?<![.\w])vars\s*\(\s*\)", "dumps the namespace"),
        # `os` itself is NOT import-denied (stdlib math needs it), so the
        # dangerous attribute calls have to be screened here instead.
        (r"\bos\s*\.\s*(system|popen|spawn\w*|exec\w*|fork|remove|unlink|"
         r"rmdir|removedirs|rename|chmod|chown|symlink|link|putenv|"
         r"unsetenv|startfile|kill)\b", "calls a dangerous os function"),
        (r"\bos\s*\.\s*(environ|getenv|putenv)\b", "reads process environment"),
        (r"\bos\s*\.\s*(getcwd|listdir|walk|scandir|stat)\s*\(", "enumerates the filesystem"),
    ]
    for pat, why in patterns:
        if re.search(pat, src):
            return False, why
    return True, ""


def run_pot(src: str, timeout: float = DEFAULT_TIMEOUT,
            mem_mb: int = DEFAULT_MEM_MB) -> ExecResult:
    """Execute a PoT program under limits. Never raises."""
    if not src or not src.strip():
        return ExecResult(False, "", "empty program", -1, False, False)

    ok, why = _preflight(src)
    if not ok:
        return ExecResult(False, "", f"blocked by preflight: {why}", -1, False, True)

    with tempfile.TemporaryDirectory(prefix="pot_") as td:
        prog = os.path.join(td, "prog.py")
        with open(prog, "w") as f:
            f.write(_make_prelude())
            f.write("\n")
            f.write(src)

        env = {
            "PATH": "/usr/bin:/bin",
            "PYTHONHASHSEED": "0",
            "HOME": td,
            "TMPDIR": td,
            "no_proxy": "*",
            "http_proxy": "",
            "https_proxy": "",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
        }

        def _limit():
            nbytes = mem_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (nbytes, nbytes))
            cpu = max(1, int(timeout) + 1)
            resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
            resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
            resource.setrlimit(resource.RLIMIT_FSIZE, (1 << 20, 1 << 20))
            os.setsid()  # own process group: a timeout kills the whole tree

        try:
            p = subprocess.run(
                [sys.executable, "-I", prog],
                capture_output=True, text=True, timeout=timeout,
                cwd=td, env=env, preexec_fn=_limit, errors="replace",
            )
        except subprocess.TimeoutExpired as e:
            out = e.stdout or ""
            if isinstance(out, bytes):
                out = out.decode("utf-8", "replace")
            return ExecResult(False, out[:2000], "timeout", -1, True, False)
        except Exception as e:  # pragma: no cover - defensive
            return ExecResult(False, "", f"spawn failed: {e}", -1, False, False)

        stderr = (p.stderr or "")[:2000]
        blocked = "blocked by PoT sandbox" in stderr
        return ExecResult(
            ok=(p.returncode == 0),
            stdout=(p.stdout or "")[:4000],
            stderr=stderr,
            returncode=p.returncode,
            timed_out=False,
            blocked=blocked,
        )


# First fenced block anywhere in the text; also tolerates a missing close fence
# because truncated generations are common at max_tokens.
_FENCE_BLOCK = re.compile(
    r"```[ \t]*(?:python|py|python3)?[ \t]*\r?\n(.*?)(?:```|\Z)", re.S | re.I)


def strip_markdown_fence(src: str) -> str:
    """Models wrap PoT in ```python ... ``` despite being told not to, and
    often prefix chatter. Take the first fenced block found anywhere; if there
    is no fence at all, treat the whole thing as the program."""
    if not src:
        return ""
    m = _FENCE_BLOCK.search(src)
    if m:
        body = m.group(1).strip()
        if body:
            return body
    return src.strip()