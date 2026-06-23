from niua_mcp_bridge.core.uv_metrics import polygon_area_2d, uv_bounds_from_points


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
