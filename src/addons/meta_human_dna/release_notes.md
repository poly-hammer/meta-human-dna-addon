## Minor Changes
* Added custom color space support [#173](https://github.com/poly-hammer/meta-human-dna-addon/issues/173)
* Added eye aim control [#189](https://github.com/poly-hammer/meta-human-dna-addon/issues/189)

## Patch Changes
* Fixed disappearing component sub-panels under RigLogic panel [#167](https://github.com/poly-hammer/meta-human-dna-addon/issues/167)
* Fixed fps scale when importing face board animation [#186](https://github.com/poly-hammer/meta-human-dna-addon/issues/186)
* Fixed face board pose order [#177](https://github.com/poly-hammer/meta-human-dna-addon/issues/177)
* Added custom operator `File > Import > MetaHuman Link/Append` that allows users to link and append metahuman rigs from other .blend files [#169](https://github.com/poly-hammer/meta-human-dna-addon/issues/169)
* Fixed face board switches [#165](https://github.com/poly-hammer/meta-human-dna-addon/issues/165)
* Fixed multiplied textures [#145](https://github.com/poly-hammer/meta-human-dna-addon/issues/145)
* Fixed incorrect wrinkle map poses [#42](https://github.com/poly-hammer/meta-human-dna-addon/issues/42)
* Fixed namespace bug with multiple rig instances


> [!WARNING]  
> You must use [poly-hammer-build-tool-workflow](https://github.com/poly-hammer/poly-hammer-build-tool-workflow) `0.6.1` or higher. If you have an older version, you will need to re-copy the template repo and [follow the setup tutorial again](https://www.youtube.com/watch?v=BAyCV8GwmCM). This is essential for your compiled dependencies to work correctly.

## Tests Passing On
* Metahuman Creator Version `6.0.0`
* Blender `4.5` (installed from blender.org)
* Unreal `5.6`
> [!NOTE]  
> Due to all the changes in Unreal 5.6, MetaHumans v6, and the addon still being in Beta, there is no backward support for earlier versions. Please use an older addon release if needed.