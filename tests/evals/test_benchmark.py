from niua_blender_mcp.evals.benchmark import list_items, load_item


def test_list_items_includes_seed():
    assert "hard_surface_crate" in list_items()
    assert list_items() == sorted(list_items())


def test_load_item_resolves_rubric_text():
    item = load_item("hard_surface_crate")
    assert item["asset_class"] == "hard_surface_prop"
    assert item["senior_threshold"] == 7.0
    assert item["stages"][0] == "repair"
    assert isinstance(item["input"]["recipe"], list)
    assert "0-10" in item["rubric_text"]  # the rubric markdown was loaded and inlined


def test_load_item_unknown_raises():
    import pytest
    with pytest.raises(KeyError):
        load_item("does_not_exist")


def test_benchmark_is_diverse():
    items = [load_item(i) for i in list_items()]
    classes = {i["asset_class"] for i in items}
    assert classes >= {"hard_surface_prop", "organic_prop", "generated_cleanup", "from_scratch_prop"}
    assert len(items) >= 7
    for i in items:
        assert i["input"]["recipe"], f"{i['id']} has empty recipe"
        assert "0-10" in i["rubric_text"]
