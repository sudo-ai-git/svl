"""Optional compilation targets for SVL.

Backends are imported explicitly so SVL's core lexer, parser, and verifier
remain usable when an optional target is not installed.
"""

from .sicxe import SICXEBackend, SICXEBackendUnavailable

__all__ = ["SICXEBackend", "SICXEBackendUnavailable"]
