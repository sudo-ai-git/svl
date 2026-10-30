"""Module/function discovery via introspection and reflection.

Discovers all callable functions and classes in the pcomp and grAIl
packages, extracting signatures, docstrings, and source metadata needed
for automated test generation.
"""
from __future__ import annotations
import inspect
import importlib
import sys
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple


@dataclass
class DiscoveredFunction:
    """A function or method discovered via introspection."""
    name: str
    qualified_name: str
    module: str
    func: Any
    signature: Optional[str] = None
    docstring: str = ""
    param_count: int = 0
    is_async: bool = False
    source_file: str = ""
    source_line: int = 0
    return_annotation: str = ""

    def __repr__(self) -> str:
        return f"<DiscoveredFunction {self.qualified_name} from {self.module}>"


@dataclass
class DiscoveredClass:
    """A class discovered via introspection."""
    name: str
    qualified_name: str
    module: str
    cls: Any
    docstring: str = ""
    methods: List[DiscoveredFunction] = field(default_factory=list)
    source_file: str = ""
    source_line: int = 0

    def __repr__(self) -> str:
        return f"<DiscoveredClass {self.qualified_name} from {self.module}>"


class FunctionDiscovery:
    """Discover all functions in a module or package."""

    def __init__(self, package_path: str = None):
        self.package_path: str = package_path or "/home/sudosudo/.local/lib/python3.12/site-packages/pcomp"
        self._discovered: List[DiscoveredFunction] = []
        self._classes: List[DiscoveredClass] = []

    def discover_module(self, module_name: str) -> Tuple[List[DiscoveredFunction], List[DiscoveredClass]]:
        """Import a module and enumerate all functions and classes."""
        try:
            mod = importlib.import_module(module_name)
        except Exception as e:
            # Try adding the package path
            if self.package_path and self.package_path not in sys.path:
                sys.path.insert(0, self.package_path)
                try:
                    mod = importlib.import_module(module_name)
                except Exception:
                    return ([], [])
            else:
                return ([], [])

        funcs = []
        classes = []

        for name in dir(mod):
            if name.startswith("_"):
                continue
            try:
                obj = getattr(mod, name)
            except Exception:
                continue

            if inspect.isfunction(obj) or inspect.ismethod(obj):
                if obj.__module__ == module_name or obj.__module__.startswith(module_name + "."):
                    func = self._extract_function(obj, module_name)
                    if func:
                        funcs.append(func)
            elif inspect.isclass(obj):
                if obj.__module__ == module_name or obj.__module__.startswith(module_name + "."):
                    cls = self._extract_class(obj, module_name)
                    if cls:
                        classes.append(cls)

        self._discovered.extend(funcs)
        self._classes.extend(classes)
        return funcs, classes

    def discover_package(self, package_name: str) -> Tuple[List[DiscoveredFunction], List[DiscoveredClass]]:
        """Discover all submodules in a package."""
        all_funcs: List[DiscoveredFunction] = []
        all_classes: List[DiscoveredClass] = []

        try:
            pkg = importlib.import_module(package_name)
            if hasattr(pkg, "__path__"):
                for submodule_name in dir(pkg):
                    if submodule_name.startswith("_"):
                        continue
                    full_name = f"{package_name}.{submodule_name}"
                    funcs, classes = self.discover_module(full_name)
                    all_funcs.extend(funcs)
                    all_classes.extend(classes)
        except Exception:
            # Fall back to direct module discovery
            pass

        # Also discover top-level
        funcs, classes = self.discover_module(package_name)
        all_funcs.extend(funcs)
        all_classes.extend(classes)

        self._discovered = all_funcs
        self._classes = all_classes
        return all_funcs, all_classes

    def _extract_function(self, obj, module_name: str) -> Optional[DiscoveredFunction]:
        """Extract metadata from a function object."""
        try:
            sig = str(inspect.signature(obj))
        except (ValueError, TypeError):
            sig = "(*args, **kwargs)"

        try:
            source_file = inspect.getsourcefile(obj) or ""
            source_line = inspect.getsourcelines(obj)[1] if inspect.getsourcelines(obj) else 0
        except (OSError, TypeError):
            source_file = ""
            source_line = 0

        doc = inspect.getdoc(obj) or ""
        param_count = len(inspect.signature(obj).parameters) if hasattr(obj, '__signature__') else 0

        # Get return annotation
        return_ann = ""
        try:
            sig_obj = inspect.signature(obj)
            if sig_obj.return_annotation is not sig_obj.empty:
                return_ann = str(sig_obj.return_annotation)
        except (ValueError, TypeError):
            pass

        return DiscoveredFunction(
            name=obj.__name__,
            qualified_name=f"{module_name}.{obj.__name__}",
            module=module_name,
            func=obj,
            signature=sig,
            docstring=doc,
            param_count=param_count,
            is_async=inspect.iscoroutinefunction(obj),
            source_file=source_file,
            source_line=source_line,
            return_annotation=return_ann,
        )

    def _extract_class(self, obj, module_name: str) -> Optional[DiscoveredClass]:
        """Extract metadata from a class object."""
        try:
            source_file = inspect.getsourcefile(obj) or ""
            source_line = inspect.getsourcelines(obj)[1] if inspect.getsourcelines(obj) else 0
        except (OSError, TypeError):
            source_file = ""
            source_line = 0

        doc = inspect.getdoc(obj) or ""
        methods: List[DiscoveredFunction] = []

        for mname in dir(obj):
            if mname.startswith("_"):
                continue
            try:
                meth = getattr(obj, mname)
                if inspect.isfunction(meth) or inspect.ismethod(meth):
                    func = self._extract_function(meth, f"{module_name}.{obj.__name__}")
                    if func:
                        methods.append(func)
            except Exception:
                continue

        return DiscoveredClass(
            name=obj.__name__,
            qualified_name=f"{module_name}.{obj.__name__}",
            module=module_name,
            cls=obj,
            docstring=doc,
            methods=methods,
            source_file=source_file,
            source_line=source_line,
        )

    @property
    def discovered_functions(self) -> List[DiscoveredFunction]:
        return self._discovered

    @property
    def discovered_classes(self) -> List[DiscoveredClass]:
        return self._classes

    def summary(self) -> Dict[str, Any]:
        """Return a summary of discovered items."""
        return {
            "total_functions": len(self._discovered),
            "total_classes": len(self._classes),
            "total_methods": sum(len(c.methods) for c in self._classes),
            "functions_by_module": {},
            "classes_by_module": {},
        }


class ModuleInspector:
    """Inspect module structure and dependencies."""

    @staticmethod
    def get_module_dependencies(module_name: str) -> List[str]:
        """Get import dependencies of a module."""
        try:
            mod = importlib.import_module(module_name)
            imports = []
            for name in dir(mod):
                if name.startswith("_"):
                    continue
                val = getattr(mod, name)
                if inspect.ismodule(val):
                    imports.append(f"{module_name}.{name}")
            return imports
        except Exception:
            return []

    @staticmethod
    def get_function_complexity(func: Any) -> str:
        """Estimate function complexity from source."""
        try:
            source = inspect.getsource(func)
            lines = source.strip().split("\n")
            if len(lines) > 50:
                return "high"
            elif len(lines) > 20:
                return "medium"
            return "low"
        except (OSError, TypeError):
            return "unknown"


class ClassDiscovery:
    """Discover all classes in a module or package."""

    def __init__(self, package_path: str = None):
        self.function_discovery = FunctionDiscovery(package_path)
        self._discovered: List[DiscoveredClass] = []

    def discover_module(self, module_name: str) -> List[DiscoveredClass]:
        """Discover all classes in a module."""
        _, classes = self.function_discovery.discover_module(module_name)
        self._discovered.extend(classes)
        return classes

    def discover_package(self, package_name: str) -> List[DiscoveredClass]:
        """Discover all classes in a package."""
        _, classes = self.function_discovery.discover_package(package_name)
        self._discovered.extend(classes)
        return classes

    @property
    def discovered_classes(self) -> List[DiscoveredClass]:
        return self._discovered

    def summary(self) -> Dict[str, Any]:
        """Return a summary of discovered classes."""
        return {
            "total_classes": len(self._discovered),
            "total_methods": sum(len(c.methods) for c in self._discovered),
        }
