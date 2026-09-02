## Patch Changes

* Fixed face board import to properly exclude bones not effecting DNA GUI controls
* Fixed a crash importing a character whose collection was excluded from the view layer or left outside the scene
* Fixed a crash toggling the face board, switching LODs, or entering pose mode on a character not in the view layer
* Fixed a character's collections being moved out of the view layer when its asset collection was deleted
* Fixed the face rig silently stopping evaluation after a re-initialize that Blender would not let complete
* Fixed exporting a selected component when its DNA file had been moved or deleted
* Fixed baking the face board when its action held channels other than pose bone transforms
* Fixed an error when a panel drew while the addon was being disabled or reloaded

## Tests Passing On

* Blender `4.5`, `5.2` (installed from blender.org)
* Unreal `5.6`, `5.7`, `5.8`
