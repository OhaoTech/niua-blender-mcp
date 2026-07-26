"""NOT THE PRODUCT — this is the benchmark harness that measures the product.

It lives inside the server package for import convenience and nothing else. Two rules
keep that from becoming a lie, both pinned by ``tests/test_evals_is_not_the_product.py``:

* **Leaf only.** Nothing in the MCP server or the add-on may import from here. The
  dependency runs one way: the harness measures the product, never the reverse. If the
  server ever needs something in this package, that thing belongs in the product.
* **Never shipped.** ``pyproject.toml`` excludes ``niua_blender_mcp.evals`` from the
  wheel. The benchmark's fixtures are ~72 MB of real generator output under
  ``benchmark/assets/`` that are deliberately untracked, so a shipped harness could only
  ever fail to load an item -- ``list_items()`` returns ``[]`` and ``load_item()`` raises
  ``KeyError``. Developers still import it fine: pytest puts ``src`` on the path.

What is here: the benchmark items and rubrics (``benchmark/``), the deterministic
gate-driven reference finisher used to score them (``finisher.py``), the objective
scorer (``objective_bench.py``, ``scorecard.py``, ``stage_gates.py``), and the Godot
glTF import check (``godot_roundtrip.py``).

See ARCHITECTURE.md, "What is and isn't the MCP".
"""
