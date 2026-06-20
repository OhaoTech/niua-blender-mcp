# Scene Tree / Outliner Design

Status: approved direction for subsystem 2.

## Why This Subsystem Exists

The current MCP can read a flat object list with `scene.info`, create primitives, and
set transforms. That is enough to prove the bridge, but it is not enough for an agent to
work like a Blender artist. Artists organize scenes through the Outliner: collections,
object membership, parent/child hierarchy, view-layer restrictions, visibility, render
flags, selectability, linked datablocks, and orphan cleanup.

Subsystem 2 makes that logical Outliner state explicit and controllable through MCP. The
implementation must use Blender data APIs and RNA state, not GUI clicks. This keeps it
headless-safe and deterministic while still matching what the user sees in the Outliner.

## Boundary

This subsystem owns logical scene-tree and Outliner state:

- scenes, collections, objects, and parent/child hierarchy
- object membership in collections
- collection hierarchy
- object and collection visibility/restriction flags
- view-layer listing and layer-collection restrictions
- object/collection/datablock description and search
- orphan datablock listing and explicit purge

This subsystem does not own:

- active object, selected objects, edit/object/pose modes, or selection mechanics
  (subsystem 3)
- object primitive creation and transforms beyond parent assignment (subsystem 4)
- mesh/material/modifier domain behavior (later subsystems)
- physical mouse/keyboard interaction with the Outliner UI (subsystem 12)

## Namespace

Use `outliner.*`.

The name matches Blender's UI language, but every tool is data-backed. This is not a
promise that the MCP is clicking the Outliner; it is a promise that it can inspect and
mutate the same logical state that the Outliner displays.

## Current Evidence

Existing curated tools:

- `scene.info`
- `scene.create_object`
- `scene.set_transform`

Existing fallback:

- `rna.describe`, `rna.search`, `rna.get_property`, `rna.set_property`, and
  `rna.call_operator` can reach some state manually, but they require exact RNA paths or
  context hints and do not provide a stable Outliner model.

Live Blender 5.1.1 checks confirmed these data-backed operations work headlessly:

- `bpy.data.collections.new(name)`
- `scene.collection.children.link(collection)`
- `collection.objects.link(object)`
- `collection.objects.unlink(object)`
- `bpy.data.collections.remove(collection)`
- `scene.view_layers.new(name)`
- `scene.view_layers.remove(view_layer)`
- `object.parent = parent_object`
- `object.hide_viewport`, `object.hide_render`, `object.hide_select`
- `collection.hide_viewport`, `collection.hide_render`, `collection.hide_select`
- `LayerCollection.exclude`, `LayerCollection.hide_viewport`, `LayerCollection.holdout`,
  `LayerCollection.indirect_only`

The manifest also contains many `outliner.*` operators, but those are UI/context
operators. They are useful reference material, not the primary implementation path for
this subsystem.

## Tool Surface

### Read Tools

`outliner.tree()`

Returns a structured view of the current scene tree:

- active scene name
- scenes list
- view layers list
- root collection tree with nested collections
- objects under each collection
- parent/child object hierarchy
- object flags: type, parent, children, collections, hidden/selectable/renderable,
  visible in active view layer where Blender can answer that
- collection flags: hide viewport, hide render, hide select, color tag, users, library

`outliner.describe(target, kind="AUTO")`

Describes one object, collection, scene, or view layer by name. `AUTO` searches object,
collection, scene, then view layer in that order and returns the resolved kind.

`outliner.find(query, kind="ANY", limit=50)`

Searches objects, collections, scenes, and view layers by case-insensitive substring.
Returns compact matches with kind, name, path, and type when applicable.

`outliner.orphans()`

Lists orphaned datablocks from safe high-value categories where `users == 0`: meshes,
materials, images, curves, cameras, lights, actions, collections, and objects. This is
read-only.

### Mutation Tools

`outliner.collection_create(name, parent="")`

Creates a collection under a parent collection, or under the active scene root when
`parent` is empty. Names are captured from Blender after creation because Blender may
auto-rename on collision.

`outliner.collection_rename(collection, name)`

Renames a collection and returns its new description.

`outliner.collection_delete(collection, force=False)`

Deletes an empty collection. If it contains objects or child collections, `force=True`
is required. Forced delete unlinks the collection from all parents and removes the
collection datablock; object datablocks are not deleted by this tool.

`outliner.object_link(object, collection)`

Links an existing object into an existing collection without removing it from other
collections.

`outliner.object_unlink(object, collection, force=False)`

Unlinks an object from a collection. If this would leave the object in zero collections,
`force=True` is required. Forced unlink is allowed because Blender can keep an object
datablock without a collection user, but the response must clearly report the remaining
collections.

`outliner.object_move(object, collection)`

Links the object to the target collection and unlinks it from all other current
collections. This is the Outliner "move to collection" action. It must use the object's
actual `users_collection`, not assume the scene root.

`outliner.parent_set(object, parent, keep_transform=True)`

Sets an object's parent. With `keep_transform=True`, preserve the object's world matrix
by setting `matrix_parent_inverse = parent.matrix_world.inverted()` after assigning the
parent. Reject self-parenting.

`outliner.parent_clear(object, keep_transform=True)`

Clears an object's parent. With `keep_transform=True`, preserve world matrix.

`outliner.visibility_set(object, viewport=None, render=None, selectable=None)`

Sets object-level Outliner restrictions:

- `viewport` maps to `object.hide_viewport = not viewport`
- `render` maps to `object.hide_render = not render`
- `selectable` maps to `object.hide_select = not selectable`

At least one flag is required.

`outliner.collection_visibility_set(collection, viewport=None, render=None, selectable=None)`

Sets collection-level restrictions:

- `viewport` maps to `collection.hide_viewport = not viewport`
- `render` maps to `collection.hide_render = not render`
- `selectable` maps to `collection.hide_select = not selectable`

At least one flag is required.

`outliner.view_layers()`

Lists view layers and their layer-collection tree restrictions.

`outliner.view_layer_create(name)`

Creates a view layer and returns the view-layer list.

`outliner.view_layer_delete(name, force=False)`

Deletes a view layer. Deleting the last view layer is rejected. `force=True` is required
because this changes render organization.

`outliner.layer_collection_set(view_layer, collection, exclude=None, viewport=None,
holdout=None, indirect_only=None)`

Sets active view-layer collection restrictions for a collection in a named view layer.
At least one flag is required.

`outliner.orphans_purge(force=False)`

Purges orphan datablocks using Blender's orphan purge API/operator. `force=True` is
always required.

## Error Handling

- Missing object/collection/scene/view layer returns `not_found`.
- Empty required names return `invalid_params`.
- Operations that can discard organization require `force=True` and otherwise return
  `precondition_failed`.
- Self-parenting returns `precondition_failed`.
- Unlinking the final collection for an object requires `force=True`.
- Deleting the last view layer is always rejected with `precondition_failed`.
- GUI-only Outliner actions are not exposed here; they are deferred to subsystem 12.

## Testing

Fake-bpy tests must cover every tool:

- tree/describe/find shape
- collection create/rename/delete
- object link/unlink/move
- parent set/clear with keep-transform paths
- object and collection visibility flags
- view-layer and layer-collection restrictions
- orphan list/purge force guard
- command/spec parity

Real Blender smoke must verify the high-risk data-backed workflow:

1. create object
2. create collection
3. move object to collection
4. set parent and clear parent
5. toggle object/collection visibility
6. create/delete view layer
7. set layer-collection restrictions
8. read `outliner.tree` after each major mutation

## Completion Bar

Subsystem 2 is complete when an agent can reconstruct and mutate the logical Outliner
tree without using GUI clicks, and those operations are covered by fake-bpy tests plus
real Blender smoke. It is acceptable that actual Outliner mouse/keyboard parity remains
deferred to subsystem 12.
