from niua_blender_mcp.evals.benchmark import list_items, load_item


def test_list_items_includes_real_asset():
    assert "real_character" in list_items()
    assert list_items() == sorted(list_items())


def test_load_item_resolves_rubric_and_asset_path():
    item = load_item("real_character")
    assert item["asset_class"] == "organic_prop"
    assert item["senior_threshold"] == 7.0
    assert item["stages"][0] == "repair"
    # asset-input item: references a generic fixture and the loader resolves it to an absolute path
    assert item["input"]["asset"] == "assets/real_character.glb"
    assert item["input"]["asset_path"].endswith("assets/real_character.glb")
    assert "0-10" in item["rubric_text"]  # the rubric markdown was loaded and inlined


def test_load_item_unknown_raises():
    import pytest

    with pytest.raises(KeyError):
        load_item("does_not_exist")


def test_benchmark_covers_real_categories():
    items = [load_item(i) for i in list_items()]
    categories = {i.get("category") for i in items}
    # the real benchmark spans humanoids, a creature, a multi-part asset, and a prop
    assert categories >= {"humanoid_character", "creature", "multipart_character", "prop_vessel"}
    assert len(items) >= 5
    for i in items:
        assert i["input"].get("asset"), f"{i['id']} is not an asset-input item"
        assert i["input"].get("asset_path"), f"{i['id']} asset_path not resolved"
        assert "0-10" in i["rubric_text"]
