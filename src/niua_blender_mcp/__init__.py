# SPDX-License-Identifier: Apache-2.0
#
# This package is a STANDALONE process: it never imports bpy and reaches Blender only
# over a localhost socket (see bridge.py). That boundary is what keeps it separable
# from the GPL add-on in blender_addon/. Keeping bpy out of this tree is a licensing
# invariant, enforced by tests/test_no_bpy_in_server.py. See LICENSING.md.
"""Agentic Blender MCP server package."""

__version__ = "0.1.0"
