"""SIC/XE backend adapter for the external sic-xe-assembler repository.

The SIC/XE implementation is kept in its own repository:
https://github.com/chadcoulter/sic-xe-assembler

Install or place that repository on PYTHONPATH before compiling. Importing
this adapter does not require the optional backend to be available.
"""

from importlib import import_module
from importlib.util import find_spec
from typing import Any, NamedTuple


class SICXEBackendUnavailable(ImportError):
    """The optional SIC/XE compiler/assembler modules are not importable."""


class SICXEComponents(NamedTuple):
    codegen: type
    assembler: type
    simulator: type
    parse_source: Any
    assembly_to_source: Any


class SICXEBackend:
    """Lazy bridge from an SVL AST to the existing SIC/XE implementation.

    This adapter is deliberately limited to integration. Instruction encoding,
    runtime correctness, and verification behavior remain responsibilities of
    the existing SIC/XE implementation.
    """

    @staticmethod
    def available() -> bool:
        """Whether both backend modules can be resolved on sys.path."""
        return (
            find_spec("sic_xe_assembler_sim") is not None
            and find_spec("svl_to_sic") is not None
        )

    @staticmethod
    def load() -> SICXEComponents:
        """Import the external compiler and simulator only when needed."""
        try:
            compiler = import_module("svl_to_sic")
            machine = import_module("sic_xe_assembler_sim")
        except ModuleNotFoundError as exc:
            raise SICXEBackendUnavailable(
                "SIC/XE backend dependency is missing: "
                + str(exc)
                + ". Clone https://github.com/chadcoulter/sic-xe-assembler "
                + "and add its directory to PYTHONPATH alongside the SVL repository."
            ) from exc

        return SICXEComponents(
            codegen=compiler.SICXECodeGen,
            assembler=machine.Assembler,
            simulator=machine.Simulator,
            parse_source=machine.parse_source,
            assembly_to_source=compiler.assembly_to_source,
        )

    def generate_assembly(self, program: Any) -> str:
        """Generate textual SIC/XE assembly from an already-parsed SVL AST."""
        backend = self.load()
        return backend.assembly_to_source(backend.codegen().compile(program))

    def assemble(self, program: Any) -> tuple:
        """Return (success, records, errors) using the external assembler."""
        backend = self.load()
        source = backend.parse_source(self.generate_assembly(program))
        assembler = backend.assembler(source)
        success, records = assembler.assemble()
        return success, records, assembler.errors
