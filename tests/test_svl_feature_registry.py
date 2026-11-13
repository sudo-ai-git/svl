"""P1.2 — the feature registry, and the versioning serialization gap.

The parser accepts a wide type surface.  The registry makes the status of every kind
explicit and self-checked, so a new kind cannot be added without a decision; strict
mode refuses what nothing enforces, and `strict=False` remains the escape hatch.
"""
import pytest

from svl.compiler_wasm import compile_file_to_wasm
from svl.verify_gate import SVLVerificationError
from svl.feature_registry import (
    FEATURES, REPRESENTATIVE, non_enforced_kinds, enforced_kinds, verify_registry,
)


def test_registry_covers_every_kind_the_parser_produces():
    ok, unknown, failures = verify_registry()
    assert ok, f"unregistered TypeExpr kinds: {unknown}; unparseable representatives: {failures}"


def test_every_kind_has_an_explicit_status():
    for kind, feature in FEATURES.items():
        assert feature.status in ("enforced", "engine-only", "parse-only"), (
            f"{kind} has status {feature.status!r}")
        assert feature.note, f"{kind} has no explanatory note"


def test_enforced_and_non_enforced_partition_the_surface():
    assert set(enforced_kinds()) & set(non_enforced_kinds()) == set()
    assert set(enforced_kinds()) | set(non_enforced_kinds()) == set(FEATURES)


@pytest.mark.parametrize("kind", sorted(non_enforced_kinds()))
def test_non_enforced_kind_is_refused_strictly_and_accepted_leniently(kind):
    """The honest contract: strict refuses what nothing enforces; lenient accepts it."""
    src = REPRESENTATIVE[kind]
    with pytest.raises((SVLVerificationError, SyntaxError)):
        compile_file_to_wasm(src)
    compile_file_to_wasm(src, strict=False)


@pytest.mark.parametrize("kind", sorted(enforced_kinds()))
def test_enforced_kind_is_not_refused_for_being_unsupported(kind):
    """An enforced kind must not trip the 'unsupported annotation' refusal."""
    src = REPRESENTATIVE[kind]
    try:
        compile_file_to_wasm(src)
    except SVLVerificationError as exc:
        assert "unsupported type annotation kind" not in str(exc), (
            f"{kind} is marked enforced but was refused as unsupported: {exc}")


# ---------------------------------------------------------------------------
# The versioning gap: Version/VersionConstraint were never serialisable
# ---------------------------------------------------------------------------

def test_versioned_module_compiles_and_roundtrips():
    """A versioned module was refused by the checksum layer ('Unknown node type: Version')."""
    from svl.lexer import tokenize
    from svl.parser_rd import parse
    from svl.serialization import to_binary, from_binary

    src = "module foo@1.2.3 { func main() type int { return 0 } }"
    compile_file_to_wasm(src)                     # must not raise
    ast = parse(tokenize(src))
    assert to_binary(from_binary(to_binary(ast))) == to_binary(ast)


def test_version_constraint_roundtrips():
    from svl.lexer import tokenize
    from svl.parser_rd import parse
    from svl.serialization import to_binary, from_binary

    src = 'import "foo"@^1.0.0 module m { func main() type int { return 0 } }'
    ast = parse(tokenize(src))
    assert to_binary(from_binary(to_binary(ast))) == to_binary(ast)
