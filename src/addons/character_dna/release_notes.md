## Minor Changes

* Switched Bone Matching Operator to use PyTorch solver (Now works on MacOS)
* Relative mesh fitting option for extra meshes added to Convertor
* `Overwrite` output method supports copying DNA blend shape wiring to meshes of the same name. (Experimental)

## Patch Changes

* Fixed Raw Editor leaf bone rotation commit values
* Fixed Raw Editor Mesh operators vertex selection mask
* Fixed Raw Editor bone selection mask and added locking for bones outside the DNA joint group

## Tests Passing On

* Blender `4.5`, `5.1` (installed from blender.org)
* Unreal `5.6`, `5.7`, `5.8`
