## Major Changes

* New integration of Epic's official SDK for MetaHumans. (OpenRigLogic) The build workflow is now deprecated.
* New Raw Control Editor that allows users to edit bone poses per activated expressions.
* New NLS Worker that integrates Epic's ML model for joint matching. (Note, you must download the .zip for [MetaHuman for Maya](https://www.fab.com/listings/9e3bf55e-d4c3-44fc-a3d4-ec4cb772ec29) and link it in your addon preferences)
* Re-Written implementation of the Shape Key Editor, allowing for controlled isolation of expression dependency chains
* Re-Written auto-fitting algorithm now under the `Converter` panel.
* Automatic LOD mesh shape synchronization based on LOD0

## Minor Changes

* RigLogic evaluation optimizations increase FPS by 50-80% depending on hardware.
* Face Board panel now has scan reference poses, as well as PSD Correct Target expressions.
* Bone collections match bone groups in rig definition

## Deprecated

* Build Workflow for compiling Unreal Dependencies
* Utilities Panel

## Tests Passing On

* Blender `4.5`, `5.1` (installed from blender.org)
* Unreal `5.6`, `5.7`, `5.8`
