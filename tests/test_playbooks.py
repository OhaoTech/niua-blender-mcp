from niua_blender_mcp.playbooks import list_playbooks, load_playbook


def test_modeling_playbook_loads():
    assert "modeling" in list_playbooks()
    text = load_playbook("modeling")
    assert "topology" in text.lower()
