"""Project tooling: `svlc new`, the lockfile, and the agent JSON interface.

The project model predates these commands: there was a `svl.toml` and an installed-module
tree, but no way to create a project, nothing pinning WHICH BYTES a rebuild used, and no
machine-readable compile/run report for an agent to branch on.

Every gate here is executable: the scaffold is compiled and run when it is created, the
lockfile is checked against the bytes on disk, and a tampered dependency is refused.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from svl.cli import main as cli_main
from svl.compiler_wasm import compile_file_to_wasm
from svl.package_manager import PackageManager
from svl.project import (
    ManifestError,
    SOURCE_NAME,
    create_project,
    load_lockfile,
    save_lockfile,
    Lockfile,
    LockedDependency,
    find_project_root,
    verify_lockfile,
)
from svl.repl import run_wat

LIB = ('module lib {\n'
       '  func answer() type int { return 42 }\n'
       '}\n')


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _publish(sandbox, name="lib", version="1.0.0"):
    lib_dir = sandbox / "libsrc"
    lib_dir.mkdir(exist_ok=True)
    (lib_dir / f"{name}.svl").write_text(LIB)
    registry = sandbox / "registry"
    rc = cli_main(["publish", str(lib_dir / f"{name}.svl"), "--name", name,
                   "--version", version, "--registry", str(registry)])
    assert rc == 0, "publish failed"
    return registry


class TestNew:
    def test_scaffold_is_a_working_program(self, sandbox):
        project = create_project("demo", root=sandbox)
        assert project.manifest_path().is_file()
        source = project.root / SOURCE_NAME
        assert source.is_file()
        wat = compile_file_to_wasm(source.read_text(), strict=True)
        rv, _ = run_wat(wat)
        assert rv == 42

    def test_cli_new_then_run_by_directory(self, sandbox):
        assert cli_main(["new", "demo"]) == 0
        assert (sandbox / "demo" / SOURCE_NAME).is_file()
        # A bare project directory is enough: `svlc run demo` resolves source.svl.
        assert cli_main(["run", "demo"]) == 0

    def test_refuses_a_non_empty_target(self, sandbox):
        (sandbox / "demo").mkdir()
        (sandbox / "demo" / "occupied.txt").write_text("x")
        with pytest.raises(ManifestError):
            create_project("demo", root=sandbox)


class TestLockfile:
    def test_install_records_the_locked_bytes(self, sandbox):
        registry = _publish(sandbox)
        assert cli_main(["new", "proj"]) == 0
        assert cli_main(["add", "lib@1.0.0", "--into", str(sandbox / "proj"),
                         "--registry", str(registry)]) == 0
        lock = load_lockfile(sandbox / "proj")
        assert lock is not None
        assert lock.dependencies["lib"].version == "1.0.0"
        assert len(lock.dependencies["lib"].source_sha256) == 64
        assert len(lock.dependencies["lib"].wasm_sha256) == 64

    def test_a_clean_tree_verifies(self, sandbox):
        registry = _publish(sandbox)
        cli_main(["new", "proj"])
        cli_main(["add", "lib@1.0.0", "--into", str(sandbox / "proj"),
                  "--registry", str(registry)])
        assert verify_lockfile(sandbox / "proj") == []

    def test_a_tampered_source_is_reported(self, sandbox):
        registry = _publish(sandbox)
        cli_main(["new", "proj"])
        cli_main(["add", "lib@1.0.0", "--into", str(sandbox / "proj"),
                  "--registry", str(registry)])
        installed = sandbox / "proj" / "svl_modules" / "lib" / "1.0.0" / SOURCE_NAME
        installed.write_text(installed.read_text() + "\n// drift\n")
        problems = verify_lockfile(sandbox / "proj")
        assert problems, "a changed dependency must not pass the lockfile gate"
        assert any("source hash mismatch" in p for p in problems)

    def test_a_deleted_module_is_reported(self, sandbox):
        registry = _publish(sandbox)
        cli_main(["new", "proj"])
        cli_main(["add", "lib@1.0.0", "--into", str(sandbox / "proj"),
                  "--registry", str(registry)])
        installed = sandbox / "proj" / "svl_modules" / "lib" / "1.0.0" / SOURCE_NAME
        installed.unlink()
        problems = verify_lockfile(sandbox / "proj")
        assert any("locked source is missing" in p for p in problems)

    def test_build_refuses_on_lock_drift(self, sandbox, capsys):
        registry = _publish(sandbox)
        cli_main(["new", "proj"])
        cli_main(["add", "lib@1.0.0", "--into", str(sandbox / "proj"),
                  "--registry", str(registry)])
        installed = sandbox / "proj" / "svl_modules" / "lib" / "1.0.0" / SOURCE_NAME
        installed.write_text(LIB + "\n// drift\n")
        rc = cli_main(["build", str(sandbox / "proj" / SOURCE_NAME)])
        assert rc == 1
        assert "does not match svl.lock" in capsys.readouterr().err

    def test_no_lockfile_is_not_an_error(self, sandbox):
        cli_main(["new", "proj"])
        assert load_lockfile(sandbox / "proj") is None
        assert verify_lockfile(sandbox / "proj") == []
        assert cli_main(["build", str(sandbox / "proj" / SOURCE_NAME)]) == 0


class TestAgentInterface:
    def test_json_round_trip_on_a_good_project(self, sandbox, capsys):
        assert cli_main(["new", "demo"]) == 0
        capsys.readouterr()                       # drain the scaffolding report
        rc = cli_main(["agent", "demo"])
        out = capsys.readouterr().out
        report = json.loads(out)
        assert rc == 0
        assert report["ok"] is True
        assert report["compiled"] is True
        assert report["result"] == 42
        assert report["problems"] == []
        assert len(report["wat_sha256"]) == 64
        assert report["timings_ms"]["compile"] >= 0

    def test_json_reports_a_broken_program(self, sandbox, capsys):
        bad = sandbox / "bad.svl"
        bad.write_text("module bad { func main() type int { return nope(1) } }")
        rc = cli_main(["agent", str(bad)])
        report = json.loads(capsys.readouterr().out)
        assert rc == 1
        assert report["ok"] is False
        assert report["compiled"] is False
        assert report["problems"]

    def test_json_reports_lock_drift_without_compiling(self, sandbox, capsys):
        registry = _publish(sandbox)
        cli_main(["new", "proj"])
        cli_main(["add", "lib@1.0.0", "--into", str(sandbox / "proj"),
                  "--registry", str(registry)])
        capsys.readouterr()
        installed = sandbox / "proj" / "svl_modules" / "lib" / "1.0.0" / SOURCE_NAME
        installed.write_text(LIB + "\n// drift\n")
        rc = cli_main(["agent", str(sandbox / "proj")])
        report = json.loads(capsys.readouterr().out)
        assert rc == 1
        assert report["ok"] is False
        assert any("hash mismatch" in p for p in report["problems"])


class TestProjectResolution:
    def test_find_project_root_walks_up(self, sandbox):
        cli_main(["new", "proj"])
        nested = sandbox / "proj" / "sub" / "dir"
        nested.mkdir(parents=True)
        assert find_project_root(nested) == (sandbox / "proj").resolve()

    def test_project_dependency_resolves_through_search_dirs(self, sandbox):
        """An installed package imports like a local file once the project is found."""
        registry = _publish(sandbox)
        cli_main(["new", "proj"])
        cli_main(["add", "lib@1.0.0", "--into", str(sandbox / "proj"),
                  "--registry", str(registry)])
        source = ('import "lib/1.0.0/source.svl"\n'
                  'module app {\n'
                  '  func main() type int { return answer() }\n'
                  '}\n')
        app = sandbox / "proj" / "app.svl"
        app.write_text(source)
        wat = compile_file_to_wasm(
            source, base_dir=str(app.parent),
            extra_dirs=[str(sandbox / "proj" / "svl_modules")])
        rv, _ = run_wat(wat)
        assert rv == 42
