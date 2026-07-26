"""The UV overlap broad-phase must not degenerate on mixed-size faces.

Regression for the real_prop finisher timeout (docs/reports/acceptance-2026-07-25.md):
`_uv_overlap_detected` bucketed every face into every grid cell its bbox touched, so ONE
UV-space-spanning face registered in cells*cells buckets. `mesh.tris_to_quads` produces
exactly those faces -- it merges triangle pairs that sat on different UV islands -- and on
the 978k-triangle fixture uv.report went from 12.7s to over 142s, breaching the finisher's
120s budget and invalidating an entire benchmark run.

These tests pin both halves of the fix: it must stay CORRECT (no missed or invented
overlaps, including for the oversized faces) and it must stay FAST.
"""

from __future__ import annotations

import time

from niua_mcp_bridge.core.uv_metrics import _uv_overlap_detected


def _square(x: float, y: float, size: float = 0.4) -> list[tuple[float, float]]:
    return [(x, y), (x + size, y), (x + size, y + size), (x, y + size)]


def _grid_of_disjoint_squares(count: int) -> list[list[tuple[float, float]]]:
    """`count` non-overlapping unit-ish squares laid out on a lattice."""
    side = int(count ** 0.5) + 1
    step = 1.0
    return [_square((i % side) * step, (i // side) * step, size=0.4) for i in range(count)]


def test_still_detects_a_real_overlap() -> None:
    assert _uv_overlap_detected([_square(0, 0), _square(0.2, 0.2)]) is True


def test_still_reports_no_overlap_when_faces_are_disjoint() -> None:
    assert _uv_overlap_detected(_grid_of_disjoint_squares(200)) is False


def test_detects_overlap_involving_an_oversized_face() -> None:
    """An oversized face is pulled out of the grid -- it must still be compared."""
    polys = _grid_of_disjoint_squares(400)
    spanning = [(0.0, 0.0), (400.0, 0.0), (400.0, 400.0), (0.0, 400.0)]  # covers everything
    polys.append(spanning)
    assert _uv_overlap_detected(polys) is True


def test_oversized_face_that_misses_everything_reports_no_overlap() -> None:
    """Correctness the other way: a huge face far away must not invent an overlap."""
    polys = _grid_of_disjoint_squares(150)
    far = [(1e5, 1e5), (1e5 + 50, 1e5), (1e5 + 50, 1e5 + 50), (1e5, 1e5 + 50)]
    polys.append(far)
    assert _uv_overlap_detected(polys) is False


def test_spanning_faces_do_not_blow_up_the_broad_phase() -> None:
    """The actual regression: faces whose bbox covers the whole UV range.

    Grid resolution is ``cells = sqrt(n)``, so a face spanning both axes touches
    ``cells * cells == n`` buckets. Here that is ~30,000 dict insertions per spanning face
    and ~4.5M in total *before* the pre-fix code even begins comparing — which is what took
    uv.report from 12.7s to 142s on the real fixture.

    The fix pulls those faces out of the grid and compares them first, so the overlap that
    obviously exists here is found immediately. The gap between the two behaviours is ~100x,
    so a generous bound still separates them on a slow CI runner.
    """
    polys = _grid_of_disjoint_squares(10_000)
    for k in range(4000):                     # each covers the entire lattice, both axes
        e = 300.0 - k * 0.01                  # slight jitter so the faces are distinct
        polys.append([(0.0, 0.0), (e, 0.0), (e, e), (0.0, e)])

    started = time.perf_counter()
    result = _uv_overlap_detected(polys)
    elapsed = time.perf_counter() - started

    assert result is True, "the spanning faces cover the lattice, so they overlap it"
    # Measured on this machine: 0.02s with the cap, 6.72s without it (336x). The bound sits
    # two orders of magnitude above the fixed cost, so a slow CI runner still passes.
    assert elapsed < 2.0, f"broad-phase degenerated: {elapsed:.1f}s for {len(polys)} faces"
