"""The package workflow: publish -> install -> import, and the gates around it.

W3 of `INTEGRATION_PLAN_ECOSYSTEM.md`.  The end-to-end gate is:

    publish a library -> install into an empty project -> compile a program that
    imports it -> correct answer; tamper the installed source -> REFUSED;
    rebuild -> byte-identical.

`PackageManager` writes under `Path.home()`, so every test points HOME at a temp dir.
"""
import hashlib
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from svl.cli import main as cli_main
from svl.compiler_wasm import compile_file_to_wasm
from svl.package_manager import PackageManager
from svl.project import load_project, find_project_root

LIB = ('module mathx {\n'
       '  func add(a: int, b: int) type int { return a + b }\n'
       '  func twice(a: int) type int { return a * 2 }\n'
       '}\n')

APP = ('import "mathlib/1.0.0/source.svl"\n'
       'module app {\n'
       '  func main() type int {\n'
       '    return add(40, 2)\n'
       '  }\n'
       '}\n')


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """Isolate the package store and registry from the developer's real ~/.svl."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _publish(sandbox, name="mathlib", version="1.0.0", registry=None):
    lib = sandbox / "lib"
    lib.mkdir(exist_ok=True)
    (lib / f"{name}.svl").write_text(LIB)
    registry = registry or (sandbox / "registry")
    rc = cli_main(["publish", str(lib / f"{name}.svl"), "--name", name,
                   "--version", version, "--registry", str(registry)])
    assert rc == 0, "publish failed"
    return registry


def _add(sandbox, spec="mathlib@1.0.0", into=None, registry=None):
    into = into or (sandbox / "proj")
    into.mkdir(parents=True, exist_ok=True)
    rc = cli_main(["add", spec, "--into", str(into), "--registry", str(registry)])
    assert rc == 0, "add failed"
    return into


class TestPublish:
    def test_registry_tree_is_written(self, sandbox):
        registry = _publish(sandbox)
        assert (registry / "index.json").is_file()
        assert (registry / "mathlib" / "1.0.0" / "source.svl").is_file()
        assert (registry / "mathlib" / "1.0.0" / "module.wasm").is_file()
        assert (registry / "mathlib" / "1.0.0" / "metadata.json").is_file()

    def test_package_carries_its_interface_artifact(self, sandbox):
        """Without the .svli the consumer's import has nothing to be checked against."""
        _publish(sandbox)
        assert (sandbox / "home" / ".svl" / "packages" / "mathlib" / "1.0.0"
                / "source.svli").is_file()

    def test_registry_index_records_the_version(self, sandbox):
        registry = _publish(sandbox)
        with open(registry / "index.json") as fh:
            index = json.load(fh)
        assert "mathlib" in index["packages"]
        assert "1.0.0" in index["packages"]["mathlib"]

    def test_publish_round_trip_bytes_match_the_package(self, sandbox):
        """Publish reads back what it wrote; a mismatch is a failure, not a message."""
        registry = _publish(sandbox)
        with open(registry / "mathlib" / "1.0.0" / "metadata.json") as fh:
            meta = json.load(fh)
        source = (registry / "mathlib" / "1.0.0" / "source.svl").read_text()
        assert hashlib.sha256(source.encode()).hexdigest() == meta["source_sha256"]
        assert (registry / "mathlib" / "1.0.0" / "source.svli").is_file()

    def test_publishing_the_same_version_twice_is_refused(self, sandbox):
        _publish(sandbox)
        lib = sandbox / "lib" / "mathlib.svl"
        rc = cli_main(["publish", str(lib), "--name", "mathlib", "--version", "1.0.0",
                       "--registry", str(sandbox / "registry")])
        assert rc == 1

    def test_a_deleted_package_can_be_recreated(self, sandbox):
        """The artifact is the directory; a stale index entry must not block recovery."""
        _publish(sandbox)
        pkg_dir = sandbox / "home" / ".svl" / "packages" / "mathlib" / "1.0.0"
        import shutil
        shutil.rmtree(pkg_dir)
        lib = sandbox / "lib" / "mathlib.svl"
        rc = cli_main(["publish", str(lib), "--name", "mathlib", "--version", "1.0.0",
                       "--registry", str(sandbox / "registry2")])
        assert rc == 0, "a stale index entry blocked recreating a deleted package"


class TestInstall:
    def test_install_writes_source_artifact_and_manifest(self, sandbox):
        registry = _publish(sandbox)
        proj = _add(sandbox, registry=registry)
        assert (proj / "svl_modules" / "mathlib" / "1.0.0" / "source.svl").is_file()
        assert (proj / "svl_modules" / "mathlib" / "1.0.0" / "source.svli").is_file()
        project = load_project(proj)
        assert project.dependencies == {"mathlib": "1.0.0"}

    def test_manifest_lists_the_dependency(self, sandbox):
        registry = _publish(sandbox)
        proj = _add(sandbox, registry=registry)
        text = (proj / "svl.toml").read_text()
        assert "[dependencies]" in text and 'mathlib = "1.0.0"' in text

    def test_installing_the_same_version_twice_is_refused(self, sandbox):
        registry = _publish(sandbox)
        _add(sandbox, registry=registry)
        rc = cli_main(["add", "mathlib@1.0.0", "--into", str(sandbox / "proj"),
                       "--registry", str(registry)])
        assert rc == 1

    def test_installing_an_unknown_package_is_refused(self, sandbox):
        registry = _publish(sandbox)
        rc = cli_main(["add", "nosuch@1.0.0", "--into", str(sandbox / "proj2"),
                       "--registry", str(registry)])
        assert rc == 1

    def test_install_refuses_a_corrupt_registry_package(self, sandbox):
        """The registry's recorded hashes are checked BEFORE anything is written."""
        registry = _publish(sandbox)
        (registry / "mathlib" / "1.0.0" / "source.svl").write_text("tampered\n")
        rc = cli_main(["add", "mathlib@1.0.0", "--into", str(sandbox / "proj"),
                       "--registry", str(registry)])
        assert rc == 1
        assert not (sandbox / "proj" / "svl_modules").exists(), \
            "a corrupt registry package must not be installed"

    def test_install_without_a_registry_index_is_refused(self, sandbox):
        rc = cli_main(["add", "mathlib@1.0.0", "--into", str(sandbox / "proj"),
                       "--registry", str(sandbox / "empty-registry")])
        assert rc == 1

    def test_install_records_the_manifest_directly(self, sandbox):
        """`PackageManager.install` itself records the dependency, not just the CLI.

        The CLI (`cmd_add`) also records it, so a test that goes through the CLI cannot
        tell whether the library keeps its own contract.  This calls the library.
        """
        registry = _publish(sandbox)
        pm = PackageManager(registry_dir=str(registry))
        into = sandbox / "proj-direct"
        into.mkdir()
        pm.install("mathlib", "1.0.0", registry_dir=str(registry), into_dir=str(into))
        assert (into / "svl.toml").is_file()
        assert load_project(into).dependencies == {"mathlib": "1.0.0"}


class TestEndToEnd:
    def test_installed_package_compiles_and_runs(self, sandbox):
        registry = _publish(sandbox)
        proj = _add(sandbox, registry=registry)
        src = proj / "src"
        src.mkdir()
        (src / "main.svl").write_text(APP)

        rc = cli_main(["run", str(src / "main.svl")])
        assert rc == 0

    def test_rebuild_is_byte_identical(self, sandbox):
        registry = _publish(sandbox)
        proj = _add(sandbox, registry=registry)
        src = proj / "src"
        src.mkdir()
        (src / "main.svl").write_text(APP)

        first = compile_file_to_wasm(APP, base_dir=str(src),
                                     extra_dirs=[str(proj / "svl_modules")])
        second = compile_file_to_wasm(APP, base_dir=str(src),
                                      extra_dirs=[str(proj / "svl_modules")])
        assert first == second

    def test_a_tampered_body_is_refused(self, sandbox):
        """Same signature, different behaviour -> the source hash must catch it."""
        registry = _publish(sandbox)
        proj = _add(sandbox, registry=registry)
        src = proj / "src"
        src.mkdir()
        (src / "main.svl").write_text(APP)

        installed = proj / "svl_modules" / "mathlib" / "1.0.0" / "source.svl"
        installed.write_text(LIB.replace("a + b", "a - b"))

        with pytest.raises(SyntaxError) as ei:
            compile_file_to_wasm(APP, base_dir=str(src),
                                 extra_dirs=[str(proj / "svl_modules")])
        assert "does not match source.svli" in str(ei.value)

    def test_a_changed_signature_is_refused(self, sandbox):
        registry = _publish(sandbox)
        proj = _add(sandbox, registry=registry)
        src = proj / "src"
        src.mkdir()
        (src / "main.svl").write_text(APP)

        installed = proj / "svl_modules" / "mathlib" / "1.0.0" / "source.svl"
        installed.write_text('module mathx {\n'
                             '  func add(a: int) type int { return a }\n'
                             '}\n')

        with pytest.raises(SyntaxError) as ei:
            compile_file_to_wasm(APP, base_dir=str(src),
                                 extra_dirs=[str(proj / "svl_modules")])
        assert "does not match source.svli" in str(ei.value)

    def test_the_project_root_is_discovered_from_a_nested_source(self, sandbox):
        registry = _publish(sandbox)
        proj = _add(sandbox, registry=registry)
        nested = proj / "src" / "deep"
        nested.mkdir(parents=True)
        assert find_project_root(nested) == proj


class TestListPackages:
    def test_lists_published_packages(self, sandbox, capsys):
        registry = _publish(sandbox)
        rc = cli_main(["list-packages", "--registry", str(registry)])
        assert rc == 0
        assert "mathlib@1.0.0" in capsys.readouterr().out

    def test_empty_registry_reports_nothing(self, sandbox, capsys):
        empty = sandbox / "empty"
        empty.mkdir()
        rc = cli_main(["list-packages", "--registry", str(empty)])
        assert rc == 0
        assert "no packages" in capsys.readouterr().out
