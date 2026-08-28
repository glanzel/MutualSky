"""UI package – PyJSX templates.

This module MUST be imported before any ``.px`` module is imported: it
registers the JSX codec + import hook (this is required by the pyjsx library).
"""

import pyjsx.auto_setup  # noqa: F401