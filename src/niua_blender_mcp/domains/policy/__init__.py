"""Policy domains (server side): the ToolSpec mirrors of the opinionated tools.

The add-on half of this package is where the behaviour lives; this half is the typed
surface the agent sees. Both are excluded from their shipped artifact -- the wheel via
``[tool.setuptools.packages.find] exclude``, the add-on by simply not copying the
directory -- because ``domains/__init__.py`` discovers domains by module presence.

Keeping the two halves symmetric matters: ``tests/test_parity.py`` asserts the server's
``SPECS`` and the add-on's ``COMMANDS`` name exactly the same tools, so a server that
advertised ``feedback.readiness`` while the installed add-on had no such command would be
caught here rather than by a user hitting an unknown-command error mid-run.

See ``..policy`` on the add-on side for what each module holds, and ARCHITECTURE.md,
"What is and isn't the MCP".
"""

from __future__ import annotations
