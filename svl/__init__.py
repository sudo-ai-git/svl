"""SVL — Self-Verifying Language.

Kept deliberately light: importing the package must not pull in the compiler, the
verifier or any third-party dependency, so `import svl` works everywhere and the CLI
can report a version before anything heavy loads.
"""

__version__ = "0.4.0"
