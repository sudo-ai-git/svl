# svl/project.py
# The SVL project model: a `svl.toml` manifest and the `svl_modules/` dependency tree.
#
# A project is a directory.  Dependencies live in `svl_modules/<name>/<version>/`
# with their `.svli` interface artifact beside them, so `_link_imports` refuses an
# import whose source no longer matches the published interface.  The manifest
# records which versions were installed, which is what makes a rebuild reproducible.
#
# The manifest is deliberately a narrow TOML subset — `[package]` and
# `[dependencies]` with string values — because that is all a dependency manifest
# needs.  `tomllib` (3.11+) is used when present, with `tomli` as the 3.10 fallback.

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import hashlib

try:
    import tomllib
except ImportError:                                       # Python 3.10
    try:
        import tomli as tomllib                         # type: ignore[no-redef]
    except ImportError:                                 # pragma: no cover
        tomllib = None                                  # type: ignore[assignment]

MANIFEST = "svl.toml"
LOCKFILE = "svl.lock"
MODULES_DIR = "svl_modules"
SOURCE_NAME = "source.svl"

# The scaffold written by `svlc new`.  It is a REAL program: it compiles, runs and
# returns 42, so a freshly created project is verified rather than assumed working.
STARTER_SOURCE = """module {name} {{
  func main() type int {{
    return 42
  }}
}}
"""

STARTER_MANIFEST = """[package]
name = "{name}"
version = "{version}"

[dependencies]
"""


class ManifestError(Exception):
    """The manifest is missing, unreadable, or not the expected shape."""


@dataclass
class Project:
    """A project directory: a manifest plus an installed-module tree."""
    root: Path
    name: str = ""
    version: str = "0.1.0"
    dependencies: Dict[str, str] = field(default_factory=dict)

    @property
    def modules_dir(self) -> Path:
        return self.root / MODULES_DIR

    def module_path(self, name: str, version: str) -> Path:
        """Where an installed dependency's source lives."""
        return self.modules_dir / name / version / SOURCE_NAME

    def resolve(self, name: str, version: Optional[str] = None) -> Optional[Path]:
        """Locate an installed dependency's source, or None if it is not installed."""
        if version is not None:
            path = self.module_path(name, version)
            return path if path.is_file() else None
        if not self.modules_dir.is_dir():
            return None
        candidates = [d for d in sorted(self.modules_dir.glob(f"{name}/*"))
                      if (d / SOURCE_NAME).is_file()]
        if not candidates:
            return None
        latest = max(candidates, key=lambda d: _version_key(d.name))
        return latest / SOURCE_NAME

    def search_dirs(self) -> List[str]:
        """Directories an `import` path may be resolved against, in priority order.

        The project's own module tree is searched BEFORE the source's directory, so an
        installed package wins over a same-named local file — otherwise adding a
        dependency could silently change what an existing relative import means.
        """
        dirs = []
        if self.modules_dir.is_dir():
            dirs.append(str(self.modules_dir))
        return dirs

    def manifest_path(self) -> Path:
        return self.root / MANIFEST


def _version_key(version: str):
    parts = []
    for piece in version.split("."):
        try:
            parts.append(int(piece))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def load_project(root) -> Project:
    """Read `<root>/svl.toml`.  A missing manifest is an empty project, not an error."""
    root = Path(root)
    path = root / MANIFEST
    if not path.is_file():
        return Project(root=root)

    if tomllib is None:                                     # pragma: no cover
        raise ManifestError(
            "reading svl.toml needs tomllib (Python 3.11+) or the 'tomli' package")

    try:
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
    except Exception as exc:                                # noqa: BLE001
        raise ManifestError(f"cannot parse {path}: {exc}") from exc

    pkg = data.get("package", {})
    if not isinstance(pkg, dict):
        raise ManifestError(f"{path}: [package] must be a table")
    deps = data.get("dependencies", {})
    if not isinstance(deps, dict):
        raise ManifestError(f"{path}: [dependencies] must be a table")
    for name, version in deps.items():
        if not isinstance(version, str):
            raise ManifestError(
                f"{path}: dependency '{name}' must be a version string, "
                f"got {type(version).__name__}")

    return Project(
        root=root,
        name=str(pkg.get("name", "")),
        version=str(pkg.get("version", "0.1.0")),
        dependencies={str(k): str(v) for k, v in deps.items()},
    )


def _render(project: Project) -> str:
    lines = ["[package]"]
    lines.append(f'name = "{project.name}"')
    lines.append(f'version = "{project.version}"')
    lines.append("")
    lines.append("[dependencies]")
    for name in sorted(project.dependencies):
        lines.append(f'{name} = "{project.dependencies[name]}"')
    return "\n".join(lines) + "\n"


def save_project(project: Project) -> Path:
    """Write the manifest, creating the project directory if needed."""
    project.root.mkdir(parents=True, exist_ok=True)
    path = project.manifest_path()
    path.write_text(_render(project), encoding="utf-8")
    return path


def find_project_root(start) -> Optional[Path]:
    """Walk up from `start` looking for an `svl.toml`."""
    cur = Path(start).resolve()
    if cur.is_file():
        cur = cur.parent
    for cand in [cur, *cur.parents]:
        if (cand / MANIFEST).is_file():
            return cand
    return None


def record_dependency(project: Project, name: str, version: str) -> Path:
    """Add `name@version` to the manifest and write it."""
    project.dependencies[name] = version
    return save_project(project)


# -- lockfile ------------------------------------------------------------
#
# `svl.toml` records which versions were installed; `svl.lock` records WHICH BYTES
# those versions were.  A rebuild is reproducible only if both agree, so `build`/`run`
# verify the installed tree against the lock when one is present and refuse on drift.

LOCK_VERSION = 1


@dataclass
class LockedDependency:
    version: str
    source_sha256: str = ""
    wasm_sha256: str = ""


@dataclass
class Lockfile:
    version: int = LOCK_VERSION
    dependencies: Dict[str, LockedDependency] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps({
            "version": self.version,
            "dependencies": {
                name: asdict(dep) for name, dep in sorted(self.dependencies.items())
            },
        }, indent=2) + "\n"

    @classmethod
    def from_json(cls, text: str) -> "Lockfile":
        data = json.loads(text)
        deps = {name: LockedDependency(**dep)
                for name, dep in data.get("dependencies", {}).items()}
        return cls(version=int(data.get("version", LOCK_VERSION)), dependencies=deps)


def lockfile_path(root) -> Path:
    return Path(root) / LOCKFILE


def load_lockfile(root) -> Optional[Lockfile]:
    """Read `<root>/svl.lock`; None when there is no lockfile (a fresh project)."""
    path = lockfile_path(root)
    if not path.is_file():
        return None
    try:
        return Lockfile.from_json(path.read_text(encoding="utf-8"))
    except Exception as exc:                                # noqa: BLE001
        raise ManifestError(f"cannot parse {path}: {exc}") from exc


def save_lockfile(root, lock: Lockfile) -> Path:
    path = lockfile_path(root)
    path.write_text(lock.to_json(), encoding="utf-8")
    return path


def locked_dependency(project: Project, name: str, version: str,
                      source_bytes: bytes, wasm_text: str) -> LockedDependency:
    """Build a lock entry from the bytes that were actually installed."""
    from svl.compiler_wasm import wasm_sha256
    return LockedDependency(
        version=version,
        source_sha256=hashlib.sha256(source_bytes).hexdigest(),
        wasm_sha256=wasm_sha256(wasm_text),
    )


def verify_lockfile(root) -> List[str]:
    """Check every locked dependency's installed bytes against the lock.

    Returns a list of problems (empty = the tree matches).  A missing module is a
    problem: the manifest says it is installed, the lock says which bytes, and neither
    is true any more.
    """
    root = Path(root)
    lock = load_lockfile(root)
    if lock is None:
        return []
    project = load_project(root)
    problems: List[str] = []
    for name, dep in sorted(lock.dependencies.items()):
        path = project.modules_dir / name / dep.version
        source_file = path / SOURCE_NAME
        wasm_file = path / "module.wasm"
        if not source_file.is_file():
            problems.append(f"{name}@{dep.version}: locked source is missing at {source_file}")
            continue
        got_source = hashlib.sha256(source_file.read_bytes()).hexdigest()
        if dep.source_sha256 and got_source != dep.source_sha256:
            problems.append(
                f"{name}@{dep.version}: source hash mismatch "
                f"(lock {dep.source_sha256[:12]}…, found {got_source[:12]}…)")
        if dep.wasm_sha256:
            if not wasm_file.is_file():
                problems.append(f"{name}@{dep.version}: locked artifact is missing at {wasm_file}")
                continue
            from svl.compiler_wasm import wasm_sha256
            got_wasm = wasm_sha256(wasm_file.read_text(encoding="utf-8"))
            if got_wasm != dep.wasm_sha256:
                problems.append(
                    f"{name}@{dep.version}: artifact hash mismatch "
                    f"(lock {dep.wasm_sha256[:12]}…, found {got_wasm[:12]}…)")
    return problems


def create_project(name: str, version: str = "0.1.0", root=None) -> Project:
    """Scaffold `<root|./>/<name>/` with an `svl.toml` and a runnable `source.svl`.

    `root` is the PARENT directory; the project directory is `<root>/<name>`.  An
    existing non-empty target is refused rather than overwritten.
    """
    parent = Path(root) if root else Path.cwd()
    target = parent / name
    if target.exists() and any(target.iterdir()):
        raise ManifestError(f"{target} already exists and is not empty")
    target.mkdir(parents=True, exist_ok=True)
    project = Project(root=target, name=name, version=version)
    save_project(project)
    (target / SOURCE_NAME).write_text(
        STARTER_SOURCE.format(name=name), encoding="utf-8")
    return project


def project_source_path(root) -> Optional[Path]:
    """The default source file for a project (`<root>/source.svl`), if present."""
    candidate = Path(root) / SOURCE_NAME
    return candidate if candidate.is_file() else None
