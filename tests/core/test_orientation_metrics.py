from niua_mcp_bridge.core.orientation_metrics import normal_consistency


def test_normal_consistency_all_aligned():
    assert normal_consistency([(0, 0, 1), (0, 0, 1)]) == 1.0


def test_normal_consistency_half_opposed():
    assert normal_consistency([(0, 0, 1), (0, 0, -1)]) == 0.0


def test_normal_consistency_empty_is_none():
    assert normal_consistency([]) is None
