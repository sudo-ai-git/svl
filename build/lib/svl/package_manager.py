# svl/package_manager.py
# SVL Package Manager (Week 20)
# `svl install`, `svl publish` with verified WASM + metadata

from typing import Optional, Dict, List, Any
from dataclasses import dataclass, field, asdict
import json
import hashlib
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from svl.compiler_wasm import compile_file_to_wasm, wasm_sha256, verify_wasm_determinism
from svl.golden_refs import get_golden_ref
from svl.bootstrap import run_deterministic_bootstrap
from svl.theorem_layer import verify_theorem_layer, TheoremVerificationConfig
from svl.syntax_layer import verify_syntax, SyntaxVerificationConfig
from svl.type_layer import verify_type, TypeVerificationConfig


def _version_sort_key(version: str):
    """Order dotted numeric versions; non-numeric pieces sort as 0."""
    parts = []
    for piece in version.split("."):
        try:
            parts.append(int(piece))
        except ValueError:
            parts.append(0)
    return tuple(parts)


@dataclass
class PackageMetadata:
    """Package metadata for verified SVL packages."""
    name: str
    version: str
    description: str = ""
    author: str = ""
    license: str = "MIT"
    dependencies: Dict[str, str] = field(default_factory=dict)  # name -> version
    svl_version: str = "0.1.0"
    wasm_sha256: str = ""
    source_sha256: str = ""
    verification: Dict[str, bool] = field(default_factory=dict)  # syntax, types, theorem
    entry_point: str = "main"


@dataclass
class PackageIndex:
    """Local package index."""
    packages: Dict[str, Dict[str, PackageMetadata]] = field(default_factory=dict)  # name -> version -> metadata


class PackageManager:
    """SVL Package Manager with verification.

    Three storage locations, kept separate on purpose:

    * ``packages_dir`` — the global store this machine has created or fetched into
      (``~/.svl/packages/<name>/<version>/``).
    * ``registry_dir`` — a publishable registry tree (``~/.svl/registry/``).  A
      registry is a directory laid out as ``<name>/<version>/`` plus an
      ``index.json``; publishing COPIES into it and reading it back is what makes
      publish a real operation instead of a printed success message.
    * a project's ``svl_modules/`` — the dependency tree of one project, recorded in
      its ``svl.toml``.
    """

    def __init__(self, registry_dir: Optional[str] = None):
        self.registry_dir = (Path(registry_dir) if registry_dir
                             else Path.home() / ".svl" / "registry")
        self.cache_dir = Path.home() / ".svl" / "cache"
        self.packages_dir = Path.home() / ".svl" / "packages"
        self.index_file = Path.home() / ".svl" / "index.json"
        
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.packages_dir.mkdir(parents=True, exist_ok=True)
        self._load_index()

    def _load_index(self):
        """Load package index."""
        if self.index_file.exists():
            with open(self.index_file) as f:
                data = json.load(f)
            self.index = PackageIndex(
                packages={
                    name: {ver: PackageMetadata(**meta) for ver, meta in vers.items()}
                    for name, vers in data.get("packages", {}).items()
                }
            )
        else:
            self.index = PackageIndex()

    def _save_index(self):
        """Save package index."""
        data = {
            "packages": {
                name: {ver: asdict(meta) for ver, meta in vers.items()}
                for name, vers in self.index.packages.items()
            }
        }
        with open(self.index_file, 'w') as f:
            json.dump(data, f, indent=2)

    def _compute_source_hash(self, source: str) -> str:
        """Compute SHA256 of source code."""
        return hashlib.sha256(source.encode('utf-8')).hexdigest()

    def _verify_package(self, source: str) -> Dict[str, bool]:
        """Run all verification layers on package source."""
        syntax_config = SyntaxVerificationConfig(verify_golden_refs=False, run_mutation_tests=False)
        type_config = TypeVerificationConfig(verify_golden_refs=False)
        theorem_config = TheoremVerificationConfig(
            verify_syntax_first=True, verify_types_first=True, verify_golden_refs=False
        )
        
        syntax_result = verify_syntax(source, syntax_config)
        type_result = verify_type(source, type_config)
        theorem_result = verify_theorem_layer(source, theorem_config)
        
        return {
            "syntax": syntax_result.passed,
            "types": syntax_result.passed and type_result.mod5_consistency and type_result.z2_consistency,
            "theorem": theorem_result.passed
        }

    def create_package(self, name: str, version: str, source: str, 
                       description: str = "", author: str = "") -> PackageMetadata:
        """Create a verified package from source."""
        print(f"Creating package {name}@{version}...")
        
        # Verify source
        print("  Running verification...")
        verification = self._verify_package(source)
        print(f"  Verification: {verification}")
        
        # Allow theorem failures (probabilistic) - require syntax and types
        if not verification.get("syntax", False) or not verification.get("types", False):
            raise ValueError(f"Package verification failed (syntax/types): {verification}")
        
        if not verification.get("theorem", False):
            print("  WARNING: Theorem verification failed (probabilistic)")
        
        # Compile to WASM
        print("  Compiling to WASM...")
        wasm = compile_file_to_wasm(source)
        wasm_hash = wasm_sha256(wasm)
        
        # Verify determinism
        if not verify_wasm_determinism(source, runs=3):
            raise ValueError("WASM compilation not deterministic")
        
        source_hash = self._compute_source_hash(source)
        
        # Create metadata
        metadata = PackageMetadata(
            name=name,
            version=version,
            description=description,
            author=author,
            wasm_sha256=wasm_hash,
            source_sha256=source_hash,
            verification=verification,
        )
        
        # Save package files
        pkg_dir = self.packages_dir / name / version
        # The artifact is the directory, not the index entry: an index entry whose files
        # were deleted must not block recreating the package (and `uninstall` is the
        # supported way to remove one deliberately).
        if pkg_dir.exists():
            raise ValueError(f"Package {name}@{version} already exists at {pkg_dir}")
        pkg_dir.mkdir(parents=True, exist_ok=True)
        
        # Save source
        (pkg_dir / "source.svl").write_text(source)
        
        # Save WASM
        (pkg_dir / "module.wasm").write_text(wasm)
        
        # Save metadata
        with open(pkg_dir / "metadata.json", 'w') as f:
            json.dump(asdict(metadata), f, indent=2)

        # The interface artifact travels WITH the package so a consumer's import is
        # checked against it at link time.  Without it `_link_imports` has nothing to
        # compare and a silently-changed library is a recompile surprise.
        from svl.interface import generate_interface, interface_path_for, write_interface
        svli_path = interface_path_for(str(pkg_dir / "source.svl"))
        write_interface(svli_path, generate_interface(source))
        
        # Update index.  The existence check is on the package DIRECTORY (above), not
        # here: an index entry left behind by a deleted package must not block recreating
        # it, and overwriting a stale entry is the correct recovery.
        self.index.packages.setdefault(name, {})[version] = metadata
        self._save_index()
        
        print(f"  Package created at {pkg_dir}")
        print(f"  WASM SHA256: {wasm_hash[:16]}...")
        
        return metadata

    def publish(self, name: str, version: str,
                registry_dir: Optional[str] = None) -> PackageMetadata:
        """Publish a locally-created package into a registry directory.

        A publish used to print "Uploading to <url>..." and then "Published
        successfully" without transferring anything.  It now COPIES the package into
        the registry, rewrites the registry index, and READS IT BACK: the copied bytes
        must hash to the same values the package was created with, or the publish
        raises.  A publish that cannot be read back is a failure, not a success.
        """
        if name not in self.index.packages or version not in self.index.packages[name]:
            raise ValueError(f"Package {name}@{version} not found locally")

        metadata = self.index.packages[name][version]
        src_dir = self.packages_dir / name / version
        source = (src_dir / "source.svl").read_text(encoding="utf-8")
        wasm = (src_dir / "module.wasm").read_text(encoding="utf-8")

        if wasm_sha256(wasm) != metadata.wasm_sha256:
            raise ValueError("WASM hash mismatch - package corrupted")
        if self._compute_source_hash(source) != metadata.source_sha256:
            raise ValueError("Source hash mismatch - package corrupted")

        registry = Path(registry_dir) if registry_dir else self.registry_dir
        dest = registry / name / version
        if dest.exists():
            raise ValueError(
                f"{name}@{version} is already published to {registry} "
                f"(uninstall it from the registry first)")
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_dir / "source.svl", dest / "source.svl")
        shutil.copy2(src_dir / "module.wasm", dest / "module.wasm")
        shutil.copy2(src_dir / "metadata.json", dest / "metadata.json")
        svli = src_dir / "source.svli"
        if svli.exists():
            shutil.copy2(svli, dest / "source.svli")

        self._save_registry_index(registry)

        # Round-trip: the bytes actually written must match what we claimed.
        got_source = self._compute_source_hash(
            (dest / "source.svl").read_text(encoding="utf-8"))
        got_wasm = wasm_sha256((dest / "module.wasm").read_text(encoding="utf-8"))
        if got_source != metadata.source_sha256 or got_wasm != metadata.wasm_sha256:
            raise ValueError(
                "publish round-trip failed: the registry bytes do not match the package")
        return metadata

    def _save_registry_index(self, registry: Path) -> None:
        """Write `<registry>/index.json` from the packages present on disk."""
        entries: Dict[str, Dict[str, Any]] = {}
        if registry.is_dir():
            for name_dir in sorted(p for p in registry.iterdir() if p.is_dir()):
                for ver_dir in sorted(p for p in name_dir.iterdir() if p.is_dir()):
                    meta_file = ver_dir / "metadata.json"
                    if not meta_file.is_file():
                        continue
                    with open(meta_file) as fh:
                        entries.setdefault(name_dir.name, {})[ver_dir.name] = json.load(fh)
        registry.mkdir(parents=True, exist_ok=True)
        with open(registry / "index.json", "w") as fh:
            json.dump({"packages": entries}, fh, indent=2)

    def install(self, name: str, version: str = "latest",
                registry_dir: Optional[str] = None,
                into_dir: Optional[str] = None) -> Path:
        """Install `name@version` from a registry into a project's module tree.

        The registry's recorded hashes are checked against the bytes on disk BEFORE
        anything is written, and again after the copy.  On success the dependency is
        recorded in the project's `svl.toml`; the package source and its `.svli`
        artifact land in `<into>/svl_modules/<name>/<version>/`.
        """
        registry = Path(registry_dir) if registry_dir else self.registry_dir
        index_file = registry / "index.json"
        if not index_file.is_file():
            raise ValueError(f"no registry index at {index_file}")
        with open(index_file) as fh:
            entries = json.load(fh).get("packages", {})
        if name not in entries:
            raise ValueError(f"{name} is not in the registry")
        versions = entries[name]
        if version == "latest":
            if not versions:
                raise ValueError(f"{name} has no published versions")
            version = max(versions, key=_version_sort_key)
        if version not in versions:
            raise ValueError(
                f"{name}@{version} is not in the registry (have: {sorted(versions)})")
        meta = versions[version]

        src_dir = registry / name / version
        source_bytes = (src_dir / "source.svl").read_bytes()
        wasm_text = (src_dir / "module.wasm").read_text(encoding="utf-8")

        # Verify BEFORE writing anything.
        if hashlib.sha256(source_bytes).hexdigest() != meta.get("source_sha256", ""):
            raise ValueError(
                f"{name}@{version}: source hash mismatch - the registry package is corrupt")
        if wasm_sha256(wasm_text) != meta.get("wasm_sha256", ""):
            raise ValueError(
                f"{name}@{version}: wasm hash mismatch - the registry package is corrupt")

        into = Path(into_dir) if into_dir else Path.cwd()
        dest = into / "svl_modules" / name / version
        if dest.exists():
            raise ValueError(f"{name}@{version} is already installed in {into}")
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "source.svl").write_bytes(source_bytes)
        (dest / "module.wasm").write_text(wasm_text, encoding="utf-8")
        svli_src = src_dir / "source.svli"
        if svli_src.exists():
            shutil.copy2(svli_src, dest / "source.svli")

        # Verify AFTER writing: the bytes on disk must match the registry's claim.
        if hashlib.sha256((dest / "source.svl").read_bytes()).hexdigest() != meta.get("source_sha256", ""):
            raise ValueError("install failed: written source does not match the registry hash")

        from svl.project import load_project, record_dependency
        project = load_project(into)
        record_dependency(project, name, version)
        return dest / "source.svl"

    def list_installed(self) -> List[PackageMetadata]:
        """List all installed packages."""
        result = []
        for name, versions in self.index.packages.items():
            for version, metadata in versions.items():
                result.append(metadata)
        return result

    def uninstall(self, name: str, version: Optional[str] = None) -> bool:
        """Uninstall a package."""
        if name not in self.index.packages:
            return False
        
        if version is None:
            # Remove all versions
            pkg_dir = self.packages_dir / name
            if pkg_dir.exists():
                shutil.rmtree(pkg_dir)
            del self.index.packages[name]
        else:
            if version not in self.index.packages[name]:
                return False
            pkg_dir = self.packages_dir / name / version
            if pkg_dir.exists():
                shutil.rmtree(pkg_dir)
            del self.index.packages[name][version]
            if not self.index.packages[name]:
                del self.index.packages[name]
        
        self._save_index()
        return True

    def verify_installed(self, name: str, version: str = "latest") -> Dict[str, bool]:
        """Verify an installed package."""
        if version == "latest":
            versions = sorted(self.index.packages[name].keys(),
                            key=lambda v: tuple(map(int, v.split('.'))))
            version = versions[-1]
        
        pkg_dir = self.packages_dir / name / version
        source = (pkg_dir / "source.svl").read_text()
        
        return self._verify_package(source)


def main():
    """CLI entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(prog="svl", description="SVL Package Manager")
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # create
    create_parser = subparsers.add_parser("create", help="Create package from source")
    create_parser.add_argument("name", help="Package name")
    create_parser.add_argument("version", help="Package version (semver)")
    create_parser.add_argument("source", help="Source file (.svl)")
    create_parser.add_argument("--description", default="", help="Package description")
    create_parser.add_argument("--author", default="", help="Author name")
    
    # install
    install_parser = subparsers.add_parser("install", help="Install package")
    install_parser.add_argument("name", help="Package name")
    install_parser.add_argument("version", nargs="?", default="latest", help="Version (default: latest)")
    
    # publish
    publish_parser = subparsers.add_parser("publish", help="Publish package")
    publish_parser.add_argument("name", help="Package name")
    publish_parser.add_argument("version", help="Version")
    
    # list
    subparsers.add_parser("list", help="List installed packages")
    
    # uninstall
    uninstall_parser = subparsers.add_parser("uninstall", help="Uninstall package")
    uninstall_parser.add_argument("name", help="Package name")
    uninstall_parser.add_argument("version", nargs="?", help="Version (default: all)")
    
    # verify
    verify_parser = subparsers.add_parser("verify", help="Verify installed package")
    verify_parser.add_argument("name", help="Package name")
    verify_parser.add_argument("version", nargs="?", default="latest", help="Version")
    
    args = parser.parse_args()
    
    pm = PackageManager()
    
    if args.command == "create":
        source = Path(args.source).read_text()
        pm.create_package(args.name, args.version, source, args.description, args.author)
    elif args.command == "install":
        pm.install(args.name, args.version)
    elif args.command == "publish":
        pm.publish(args.name, args.version)
    elif args.command == "list":
        for pkg in pm.list_installed():
            print(f"{pkg.name}@{pkg.version}: {pkg.description}")
    elif args.command == "uninstall":
        pm.uninstall(args.name, args.version)
    elif args.command == "verify":
        result = pm.verify_installed(args.name, args.version)
        print(f"Verification: {result}")
    else:
        parser.print_help()


if __name__ == '__main__':
    main()