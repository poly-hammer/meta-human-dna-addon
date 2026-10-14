## Patch Changes

* Fixed rig logic driver re-initialization issue [#370](https://github.com/poly-hammer/character-dna-addon/issues/370)
* Fixed eye control visibility when opening, appending, or linking Blender 4.5 rigs in Blender 5.x.
* Fixed false migration warnings after editor previews and preserved preview playback behavior when recovering drivers.
* Fixed legacy collection migration when loading a file without an active collection or with another collection selected.
* Improved undo/redo speed by reusing unchanged DNA models and indexing driver validation, while rebuilding Blender references and evaluation sessions safely.

## Tests Passing On

* Blender `4.5`, `5.2` (installed from blender.org)
* Unreal `5.6`, `5.7`, `5.8`
