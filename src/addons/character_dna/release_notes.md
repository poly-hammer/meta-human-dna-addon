## Major Changes

* Initial implementation of the Behavior Viewer

## Minor Changes

* Added Freeze option to Raw Editor and Shape Key Editor list filter
* Added Ghost indicator for shape keys that do not contain deltas. Also added toggle to filter them from the view.
* Added option to turn off dependency chain isolation in Shape Key Editor

## Patch Changes

* Fixed incomplete/opaque eye and saliva materials on Blender 4.x [#346](https://github.com/poly-hammer/character-dna-addon/issues/346)
* New Coordinate System policy is enforced on the DNA Reader to properly convert DNA's saved in other coordinate systems.

## Tests Passing On

* Blender `4.5`, `5.1`, `5.2` (installed from blender.org)
* Unreal `5.6`, `5.7`, `5.8`
