#!/usr/bin/env python3
"""Spike 012: register LSP handlers as unbound functions so the server boots (F11)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, "/home/sudosudo/.openclaw/workspace")

from harness import verdict                                    # noqa: E402

from lsprotocol.types import (                                    # noqa: E402
    INITIALIZE, TEXT_DOCUMENT_DID_OPEN, TEXT_DOCUMENT_DID_CHANGE,
    TEXT_DOCUMENT_DID_CLOSE, TEXT_DOCUMENT_DID_SAVE, TEXT_DOCUMENT_COMPLETION,
    TEXT_DOCUMENT_HOVER, TEXT_DOCUMENT_DEFINITION, TEXT_DOCUMENT_SEMANTIC_TOKENS_FULL,
)
from svl.lsp_server import SVLLanguageServer                   # noqa: E402


def main():
    try:
        server = SVLLanguageServer("svl-lsp", "0.1.0")
        # the fix: pass the UNBOUND function, not server.<method>
        server.feature(INITIALIZE)(SVLLanguageServer.initialize)
        server.feature(TEXT_DOCUMENT_DID_OPEN)(SVLLanguageServer.did_open)
        server.feature(TEXT_DOCUMENT_DID_CHANGE)(SVLLanguageServer.did_change)
        server.feature(TEXT_DOCUMENT_DID_CLOSE)(SVLLanguageServer.did_close)
        server.feature(TEXT_DOCUMENT_DID_SAVE)(SVLLanguageServer.did_save)
        server.feature(TEXT_DOCUMENT_COMPLETION)(SVLLanguageServer.completion)
        server.feature(TEXT_DOCUMENT_HOVER)(SVLLanguageServer.hover)
        server.feature(TEXT_DOCUMENT_DEFINITION)(SVLLanguageServer.definition)
        server.feature(TEXT_DOCUMENT_SEMANTIC_TOKENS_FULL)(SVLLanguageServer.semantic_tokens_full)
        return verdict("012-lsp-boot-fix", True,
                       "all nine features registered with no AttributeError")
    except Exception as exc:
        return verdict("012-lsp-boot-fix", False, f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    sys.exit(main())
