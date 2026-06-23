from niua_mcp_bridge.core.uv_metrics import polygon_area_2d, polygons_overlap_2d, uv_bounds_from_points


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
