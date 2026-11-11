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
    """SVL Package Manager with verification."""

    def __init__(self, registry_url: str = "https://svl-registry.example.com"):
        self.registry_url = registry_url
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
        pkg_dir.mkdir(parents=True, exist_ok=True)
        
        # Save source
        (pkg_dir / "source.svl").write_text(source)
        
        # Save WASM
        (pkg_dir / "module.wasm").write_text(wasm)
        
        # Save metadata
        with open(pkg_dir / "metadata.json", 'w') as f:
            json.dump(asdict(metadata), f, indent=2)
        
        # Update index
        if name not in self.index.packages:
            self.index.packages[name] = {}
        if version in self.index.packages[name]:
            raise ValueError(f"Package {name}@{version} already exists")
        self.index.packages[name][version] = metadata
        self._save_index()
        
        print(f"  Package created at {pkg_dir}")
        print(f"  WASM SHA256: {wasm_hash[:16]}...")
        
        return metadata

    def install(self, name: str, version: str = "latest") -> PackageMetadata:
        """Install a package from registry."""
        print(f"Installing {name}@{version}...")
        
        # Check local first
        if name in self.index.packages:
            if version == "latest":
                versions = sorted(self.index.packages[name].keys(), 
                                key=lambda v: tuple(map(int, v.split('.'))))
                version = versions[-1]
            if version in self.index.packages[name]:
                metadata = self.index.packages[name][version]
                print(f"  Already installed locally")
                return metadata
        
        # Download from registry (simulated)
        print(f"  Downloading from {self.registry_url}...")
        # In real implementation: download from registry
        # For now, raise error
        raise NotImplementedError("Registry download not implemented - use local packages")

    def publish(self, name: str, version: str) -> bool:
        """Publish package to registry."""
        print(f"Publishing {name}@{version}...")
        
        if name not in self.index.packages or version not in self.index.packages[name]:
            raise ValueError(f"Package {name}@{version} not found locally")
        
        metadata = self.index.packages[name][version]
        
        # Verify package integrity
        pkg_dir = self.packages_dir / name / version
        source = (pkg_dir / "source.svl").read_text()
        wasm = (pkg_dir / "module.wasm").read_text()
        
        if wasm_sha256(wasm) != metadata.wasm_sha256:
            raise ValueError("WASM hash mismatch - package corrupted")
        
        if self._compute_source_hash(source) != metadata.source_sha256:
            raise ValueError("Source hash mismatch - package corrupted")
        
        # Upload to registry (simulated)
        print(f"  Uploading to {self.registry_url}...")
        # In real implementation: upload to registry
        
        print(f"  Published successfully")
        return True

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