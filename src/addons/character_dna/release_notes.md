## Patch Changes

* Fixed Blender freezing or crashing part way through rendering an animation with rig logic evaluation turned on
* Fixed the character's face lagging a frame behind the face board when rendering an animation
* Fixed DNA files never being released and from memory
* Fixed Face Board origin on second MetaHuman import
* Fixed the eyes not aiming at the eyes aim control when the head bone is rotated and only the head DNA has been imported [#309](https://github.com/poly-hammer/character-dna-addon/issues/309)
* Fixed the head RBFs not evaluating in real time when the head bone is rotated and only the head DNA has been imported [#359](https://github.com/poly-hammer/character-dna-addon/issues/359)

## Tests Passing On

* Blender `4.5`, `5.1`, `5.2` (installed from blender.org)
* Unreal `5.6`, `5.7`, `5.8`
