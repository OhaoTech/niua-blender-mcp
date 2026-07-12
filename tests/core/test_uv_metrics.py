from niua_mcp_bridge.core.uv_metrics import (
    _uv_overlap_detected,
    polygon_area_2d,
    polygons_overlap_2d,
    uv_bounds_from_points,
)


def _all_pairs_overlap(polys):
    """Reference O(n^2) all-pairs overlap -- the semantics the fast path must match exactly."""
    return any(
        polygons_overlap_2d(a, b)
        for i, a in enumerate(polys)
        for b in polys[i + 1 :]
    )


def _square(x, y, s=1.0):
    return [(x, y), (x + s, y), (x + s, y + s), (x, y + s)]


def test_uv_overlap_true_when_two_faces_overlap():
    assert _uv_overlap_detected([_square(0, 0), _square(0.5, 0.5)]) is True


def test_uv_overlap_false_when_faces_are_separate():
    assert _uv_overlap_detected([_square(0, 0), _square(2, 2), _square(4, 0)]) is False


def test_uv_overlap_false_for_edge_touching_faces():
    # adjacent faces sharing an edge (a packed atlas) must NOT count as overlapping
    assert _uv_overlap_detected([_square(0, 0), _square(1.0, 0)]) is False


def test_uv_overlap_handles_empty_and_single():
    assert _uv_overlap_detected([]) is False
    assert _uv_overlap_detected([_square(0, 0)]) is False


def test_uv_overlap_matches_all_pairs_reference_on_random_layouts():
    import random

    rng = random.Random(1234)
    for _ in range(60):
        n = rng.randint(2, 40)
        polys = []
        for _ in range(n):
            x = rng.uniform(0, 6)
            y = rng.uniform(0, 6)
            s = rng.uniform(0.2, 1.2)
            polys.append(_square(x, y, s))
        assert _uv_overlap_detected(polys) == _all_pairs_overlap(polys), polys


def test_polygon_area_2d_unit_square():
    assert polygon_area_2d([(0, 0), (1, 0), (1, 1), (0, 1)]) == 1.0


def test_polygon_area_2d_triangle():
    assert polygon_area_2d([(0, 0), (1, 0), (0, 1)]) == 0.5


def test_uv_bounds_from_points_counts_out_of_bounds():
    out = uv_bounds_from_points([(0.0, 0.0), (1.0, 1.0), (1.2, -0.1)])
    assert out == {
        "min_u": 0.0,
        "min_v": -0.1,
        "max_u": 1.2,
        "max_v": 1.0,
        "out_of_bounds_loops": 1,
    }


def test_polygons_overlap_2d_false_when_separated():
    a = [(0, 0), (1, 0), (1, 1), (0, 1)]
    b = [(2, 0), (3, 0), (3, 1), (2, 1)]
    assert polygons_overlap_2d(a, b) is False


def test_polygons_overlap_2d_false_when_only_touching_edge():
    a = [(0, 0), (1, 0), (1, 1), (0, 1)]
    b = [(1, 0), (2, 0), (2, 1), (1, 1)]
    assert polygons_overlap_2d(a, b) is False


def test_polygons_overlap_2d_true_when_area_overlaps():
    a = [(0, 0), (1, 0), (1, 1), (0, 1)]
    b = [(0.5, 0.5), (1.5, 0.5), (1.5, 1.5), (0.5, 1.5)]
    assert polygons_overlap_2d(a, b) is True
