#!/usr/bin/env python3
"""Spike 015: CI triggers on the repo's real branch (L5)."""
import os
import subprocess
import sys
import tempfile

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, "/home/sudosudo/.openclaw/workspace")

from harness import verdict                                    # noqa: E402

REPO = "/home/sudosudo/svl-release"     # the public mirror: branch main, CI triggers master
CI = os.path.join(REPO, ".github", "workflows", "ci.yml")


def main():
    try:
        cur = yaml.safe_load(open(CI))
        cur_branch = (cur.get("on") or cur.get(True)).get("push", {}).get("branches")
        actual = subprocess.run(["git", "-C", REPO, "rev-parse", "--abbrev-ref", "HEAD"],
                                capture_output=True, text=True).stdout.strip()

        patched = open(CI).read().replace("branches: [master]", "branches: [master, main]")
        with tempfile.NamedTemporaryFile("w", suffix=".yml", delete=False) as fh:
            fh.write(patched)
            path = fh.name
        new = yaml.safe_load(open(path))
        new_branch = (new.get("on") or new.get(True)).get("push", {}).get("branches")
        os.unlink(path)

        ok = (actual in new_branch) and (actual not in (cur_branch or []))
        return verdict("015-ci-branch-fix", ok,
                       f"repo branch={actual}; current trigger={cur_branch}; "
                       f"patched trigger={new_branch}; YAML parses")
    except Exception as exc:
        return verdict("015-ci-branch-fix", False, f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    sys.exit(main())
