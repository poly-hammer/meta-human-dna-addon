## Minor Changes

* It is now possible to optionally disable `Batched Evaluations` in the addon preferences. This is currently experimental. This removes the need to bake before rendering. Please report any issues with evaluation in the scene or while rendering with this option on.

## Patch Changes

* Added experimental option to turn off batched evaluations
* Fixed center eye control baking bug [#308](https://github.com/poly-hammer/character-dna-addon/issues/308)
* Fixed bug with eye aim control when eyes follow head is false [#309](https://github.com/poly-hammer/character-dna-addon/issues/309)

## Tests Passing On

* Blender `4.5`, `5.1` (installed from blender.org)
* Unreal `5.6`, `5.7`, `5.8`
