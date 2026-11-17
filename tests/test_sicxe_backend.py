"""Contract tests for the optional SIC/XE backend bridge."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from svl.backends import SICXEBackend, SICXEBackendUnavailable


class SICXEBackendTests(unittest.TestCase):
    def test_adapter_imports_without_external_backend(self):
        # Import of svl.backends itself must not eagerly import SIC/XE.
        self.assertIsNotNone(SICXEBackend)

    def test_missing_backend_has_actionable_error(self):
        with patch("svl.backends.sicxe.import_module", side_effect=ModuleNotFoundError("No module named 'svl_to_sic'")):
            with self.assertRaisesRegex(SICXEBackendUnavailable, "PYTHONPATH"):
                SICXEBackend.load()

    def test_adapter_delegates_to_external_compiler(self):
        calls = []

        class FakeCodeGen:
            def compile(self, program):
                calls.append(("compile", program))
                return [("MAIN", "HALT", "", "")]

        class FakeAssembler:
            def __init__(self, source):
                calls.append(("assembler", source))
                self.errors = []

            def assemble(self):
                return True, {"H": "H^TEST  ^001000^000001", "T": [], "E": "E^001000"}

        compiler = SimpleNamespace(
            SICXECodeGen=FakeCodeGen,
            assembly_to_source=lambda lines: "MAIN HALT",
        )
        machine = SimpleNamespace(
            Assembler=FakeAssembler,
            Simulator=object,
            parse_source=lambda text: [text],
        )
        def fake_import(name):
            return {"svl_to_sic": compiler, "sic_xe_assembler_sim": machine}[name]

        with patch("svl.backends.sicxe.import_module", side_effect=fake_import):
            success, records, errors = SICXEBackend().assemble("ast")
        self.assertTrue(success)
        self.assertEqual(errors, [])
        self.assertEqual(records["E"], "E^001000")
        self.assertEqual(calls, [("compile", "ast"), ("assembler", ["MAIN HALT"])])


if __name__ == "__main__":
    unittest.main()
