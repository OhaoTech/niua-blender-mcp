from niua_mcp_bridge.core.overlay import face_type_groups


class _Poly:
    def __init__(self, index, sides):
        self.index = index
        self.vertices = list(range(sides))


def test_groups_faces_by_side_count():
    polys = [_Poly(0, 3), _Poly(1, 4), _Poly(2, 5), _Poly(3, 4)]
    groups = face_type_groups(polys)
    assert groups == {"tris": [0], "quads": [1, 3], "ngons": [2]}


def test_empty_mesh_groups_empty():
    assert face_type_groups([]) == {"tris": [], "quads": [], "ngons": []}
