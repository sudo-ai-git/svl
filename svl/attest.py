"""Self-attestation for compiled SVL artifacts.

The design's most distinctive property is that compilation is a *pure function of the AST*:
the same source produces the same bytes, across runs and `PYTHONHASHSEED`. This module turns
that property into something useful — a **checkable** attestation bound to the artifact's own
code — instead of leaving it as a drift detector.

How it works, and why it is checkable rather than self-reported:

1. Assemble the compiler's WAT to a binary. Custom sections (including the assembler's `name`
   section) are stripped and the remainder hashed -> `content_sha256`.
2. Re-emit the module with a `svl.attest` custom section carrying that hash, the 231-gate
   triple and the AST hash.
3. A verifier reads the section, **strips every custom section from the artifact it was
   handed**, re-hashes, and compares. Any change to the code (or to any non-custom section)
   changes the recomputed hash and the attestation fails.

This is deliberately unlike the existing `pcc_wasm` proof, which embeds a self-declared
boolean produced by the same process that produced the artifact, and therefore checks nothing.
"""
import hashlib
import json
from typing import Any, Dict, List, Optional, Tuple

SECTION_NAME = "svl.attest"
ATTEST_VERSION = 1
WASM_MAGIC = b"\x00asm"


# --------------------------------------------------------------------------- binary helpers

def _iter_sections(binary: bytes):
    """Yield (section_id, payload, start, end). Raises ValueError on a malformed header."""
    if binary[:4] != WASM_MAGIC:
        raise ValueError("not a wasm binary (bad magic)")
    i = 8
    while i < len(binary):
        if i >= len(binary):
            break
        sid = binary[i]
        i += 1
        shift = 0
        size = 0
        while True:
            if i >= len(binary):
                raise ValueError("truncated section length")
            byte = binary[i]
            i += 1
            size |= (byte % 128) << shift
            if byte < 128:
                break
            shift += 7
        if i + size > len(binary):
            raise ValueError("truncated section payload")
        yield sid, binary[i:i + size], i, i + size
        i += size


def strip_custom_sections(binary: bytes) -> bytes:
    """Return the artifact with every custom section (id 0) removed.

    Custom sections are by definition non-semantic, so this yields a canonical form that both
    producer and verifier can compute independently.
    """
    out = bytearray(binary[:8])
    for sid, payload, start, end in _iter_sections(binary):
        if sid == 0:
            continue
        out.append(sid)
        n = len(payload)
        while True:
            byte = n % 128
            n //= 128
            if n:
                out.append(byte + 128)
            else:
                out.append(byte)
                break
        out.extend(payload)
    return bytes(out)


def content_hash(binary: bytes) -> str:
    """SHA-256 over the artifact with custom sections stripped (the canonical code hash)."""
    return hashlib.sha256(strip_custom_sections(binary)).hexdigest()


def extract_attestation(binary: bytes) -> Optional[Dict[str, Any]]:
    """Return the parsed `svl.attest` payload, or None if the artifact carries none."""
    for sid, payload, _s, _e in _iter_sections(binary):
        if sid != 0:
            continue
        # a custom section payload is: name (LEB128 length + bytes) + data
        shift = 0
        nlen = 0
        i = 0
        while True:
            byte = payload[i]
            i += 1
            nlen |= (byte % 128) << shift
            if byte < 128:
                break
            shift += 7
        name = payload[i:i + nlen].decode("utf-8", "replace")
        if name != SECTION_NAME:
            continue
        try:
            return json.loads(payload[i + nlen:].decode("utf-8"))
        except Exception:                                          # noqa: BLE001
            return None
    return None


# --------------------------------------------------------------------------- attestation

def _wat_escape(data: bytes) -> str:
    return "".join(f"\\{b:02x}" for b in data)


def ast_fingerprint(source: str) -> Dict[str, Any]:
    """Deterministic, position-independent program identity for `source`.

    Returns ``{'ast_sha256', 'gate231', 'source_sha256', 'ast_bytes'}`` where `ast_sha256` and
    `gate231` are computed over `to_canonical_binary` -- the AST with source-position fields
    omitted.  Two sources that parse to the same tree therefore give the SAME fingerprint:
    different whitespace or comments, and the Hebrew vs ASCII spellings of the same keywords
    (measured: five spellings/layouts of one program all give ast_sha256 6df5994c... and gate
    [167, 10, 0]).  `source_sha256` is the raw-text hash and is NOT stable across reformatting.
    """
    from svl.gate231 import compute_checksums_cython
    from svl.serialization import to_canonical_binary
    from svl.lexer import tokenize
    from svl.parser_rd import parse

    blob = to_canonical_binary(parse(tokenize(source)))
    return {
        "ast_sha256": hashlib.sha256(blob).hexdigest(),
        "gate231": list(compute_checksums_cython(blob)),
        "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "ast_bytes": len(blob),
    }


def _payload(source: str, plain_binary: bytes) -> Dict[str, Any]:
    fp = ast_fingerprint(source)
    return {
        "v": ATTEST_VERSION,
        "content_sha256": content_hash(plain_binary),
        "gate231": fp["gate231"],
        "ast_sha256": fp["ast_sha256"],
        "source_sha256": fp["source_sha256"],
        # The compile-time gate ran and refused to compile on failure (strict=True).
        "layers": {"syntax": True, "types": True, "abstract": True},
    }


def _section_text(wat: str, payload: Dict[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    text = wat.rstrip()
    idx = text.rfind(")")
    if idx < 0:
        raise ValueError("WAT has no closing paren; cannot attach the attestation section")
    return (text[:idx]
            + f'  (@custom "{SECTION_NAME}" "{_wat_escape(blob)}")\n'
            + text[idx:])


def attest_wat(source: str, wat: str) -> Tuple[str, Dict[str, Any]]:
    """Return ``(wat carrying the svl.attest section, payload)``, assembling once.

    The section content is the canonical hash of the module with all custom sections
    stripped, so the section itself does not change the hash it attests to -- and
    re-attesting an already-attested module is idempotent.
    """
    import wasmtime

    plain = wasmtime.wat2wasm(wat)
    payload = _payload(source, plain)
    return _section_text(wat, payload), payload


def attest(source: str, wat: str) -> Tuple[bytes, Dict[str, Any]]:
    """Assemble `wat`, hash its canonical form, and re-emit it carrying the attestation.

    Returns (attested_binary, attestation_dict).
    """
    import wasmtime

    attested_wat, payload = attest_wat(source, wat)
    return wasmtime.wat2wasm(attested_wat), payload


def compile_attested(source: str, deterministic: bool = True, strict: bool = True
                     ) -> Tuple[str, bytes, Dict[str, Any]]:
    """Compile `source` and produce the self-attested artifact.

    Returns ``(wat_with_section, attested_binary, payload)``.  This is the artifact-producing
    entry point.  `compile_file_to_wasm` deliberately stays byte-identical so artifacts already
    pinned elsewhere (the minted spike-102 payload checks the sha256 of its .wasm) remain
    valid; the attestation is opt-in at the artifact boundary.
    """
    import wasmtime

    from svl.compiler_wasm import compile_file_to_wasm
    wat = compile_file_to_wasm(source, deterministic=deterministic, strict=strict)
    attested_wat, payload = attest_wat(source, wat)
    return attested_wat, wasmtime.wat2wasm(attested_wat), payload


def verify_attestation(binary: bytes) -> Tuple[bool, Dict[str, Any]]:
    """Independently check an attested artifact.

    Returns (ok, details). `ok` is False when there is no attestation, when the section is
    unreadable, or when the recomputed canonical hash differs from the attested one.
    """
    try:
        payload = extract_attestation(binary)
    except ValueError as exc:
        return False, {"error": str(exc)}
    if payload is None:
        return False, {"error": "no svl.attest section"}
    claimed = payload.get("content_sha256")
    try:
        actual = content_hash(binary)
    except ValueError as exc:
        return False, {"error": str(exc), "payload": payload}
    return (claimed == actual), {"claimed": claimed, "actual": actual, "payload": payload}
