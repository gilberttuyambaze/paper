"""Backend package initializer.

This file makes the `backend` directory importable as a Python package
so commands like `python -m uvicorn backend.main:app` work reliably when
the project root is not automatically on `sys.path` in some reloaders.
"""

__all__ = ["main"]
