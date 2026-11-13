"""P1.6 — `.svli` interface artifacts.

A `.svli` file records a module's public surface (function signatures, struct layouts,
const types).  The linker refuses an import whose source no longer matches it, so a
silently-changed library is a named link error instead of a recompiled surprise.
"""
import json

import pytest

from svl.cli import main as cli_main
from svl.compiler_wasm import compile_file_to_wasm
from svl.interface import (
    generate_interface, interface_path_for, load_interface, verify_against_interface,
    write_interface,
)

LIB = ('module lib { func add(a: int, b: int) type int { return a + b } '
       'struct P { x: int  y: int } const N: int = 6 }')


def test_interface_records_the_public_surface():
    iface = generate_interface(LIB)
    assert iface['functions']['add'] == {'params': ['int', 'int'], 'return': 'int'}
    assert iface['structs']['P'] == ['x', 'y']
    assert iface['consts']['N'] == 'int'
    assert len(iface['source_hash']) == 64


def test_interface_round_trips(tmp_path):
    path = tmp_path / "lib.svli"
    write_interface(str(path), generate_interface(LIB))
    assert load_interface(str(path)) == generate_interface(LIB)


def test_matching_source_has_no_problems():
    assert verify_against_interface(LIB, generate_interface(LIB)) == []


@pytest.mark.parametrize("mutation, expected", [
    ("return-type", "function 'add' changed"),
    ("arity", "function 'add' changed"),
])
def test_a_changed_surface_is_detected(mutation, expected):
    iface = generate_interface(LIB)
    if mutation == "return-type":
        iface['functions']['add']['return'] = 'string'
    elif mutation == "arity":
        iface['functions']['add']['params'] = ['int']
    problems = verify_against_interface(LIB, iface)
    assert any(expected in p for p in problems), problems


def test_a_function_missing_from_the_source_is_detected():
    """The interface lists `add`; a source that no longer has it is a mismatch."""
    iface = generate_interface(LIB)
    problems = verify_against_interface('module lib { }', iface)
    assert any("function 'add' is missing" in p for p in problems), problems


def test_compile_accepts_a_matching_interface(tmp_path):
    (tmp_path / "lib.svl").write_text(LIB)
    write_interface(str(interface_path_for(str(tmp_path / "lib.svl"))),
                    generate_interface(LIB))
    main = 'import "lib.svl"\nmodule m { func main() type int { return add(1,2) } }'
    compile_file_to_wasm(main, base_dir=str(tmp_path))


def test_compile_refuses_a_tampered_interface(tmp_path):
    (tmp_path / "lib.svl").write_text(LIB)
    iface = generate_interface(LIB)
    iface['functions']['add']['return'] = 'string'
    write_interface(str(interface_path_for(str(tmp_path / "lib.svl"))), iface)
    main = 'import "lib.svl"\nmodule m { func main() type int { return add(1,2) } }'
    with pytest.raises(SyntaxError, match="does not match"):
        compile_file_to_wasm(main, base_dir=str(tmp_path))


def test_cli_write_interface(tmp_path):
    src = tmp_path / "lib.svl"
    src.write_text(LIB)
    rc = cli_main(["build", str(src), "--interface"])
    assert rc == 0
    path = interface_path_for(str(src))
    assert load_interface(path)['functions']['add']['return'] == 'int'
