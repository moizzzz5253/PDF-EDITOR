"""Operation registry.

To add a new feature, write a function in any module under app/ops/ and decorate it
with @operation(...). It shows up in the dashboard automatically (the UI builds its
form from the `params` list), with tracing and error reporting included.
"""
from .registry import OPERATIONS, operation, OpContext  # noqa: F401
from . import convert, pages  # noqa: F401  (import = register)
