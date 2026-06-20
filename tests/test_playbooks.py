from niua_blender_mcp.playbooks import list_playbooks, load_playbook


def test_modeling_playbook_loads():
    assert "modeling" in list_playbooks()
    text = load_playbook("modeling")
    assert "topology" in text.lower()


def test_modeling_playbook_names_crate_craft_verbs():
    text = load_playbook("modeling")
    assert "model.recess_panels" in text
    assert "model.bevel_edges" in text
    assert "model.retopo_quads" in text
