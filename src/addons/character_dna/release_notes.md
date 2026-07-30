## Minor Changes

* Changed animation import operators to use ufbx bindings for cleaner and more optimized importing of large animations.
* Removed batched dependency graph evaluations

## Patch Changes

* Fixed rig instance index error
* Fixed the face board being left outside the character's collection when using Metahuman Append/Link > Link [#341](https://github.com/poly-hammer/character-dna-addon/issues/341)
* Fixed shape keys staying un-driven for the rest of the session when the head mesh was renamed or merged [#333](https://github.com/poly-hammer/character-dna-addon/issues/333)
* Fixed an error in the Migrate Legacy Data panel when an older Meta-Human DNA addon is still installed

## Tests Passing On

* Blender `4.5`, `5.1`, `5.2` (installed from blender.org)
* Unreal `5.6`, `5.7`, `5.8`
