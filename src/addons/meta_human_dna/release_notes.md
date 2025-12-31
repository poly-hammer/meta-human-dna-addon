## Minor Changes
* Added confirm option when deleting rig instances with option to delete linked data [#202](https://github.com/poly-hammer/meta-human-dna-addon/issues/202)

## Patch Changes
* Fixed Blender 5.0 shape key imports [#229](https://github.com/poly-hammer/meta-human-dna-addon/issues/229)
* Fixed Blender 5.0 action baking [#229](https://github.com/poly-hammer/meta-human-dna-addon/issues/229)
* Fixed animation import bugs with root motion [#233](https://github.com/poly-hammer/meta-human-dna-addon/issues/233)
* Fixed Crashes with Shader Edits and Undo/Redo [#237](https://github.com/poly-hammer/meta-human-dna-addon/issues/237)
* Added validation for when user tries to append/link rig instance with the same name [#203](https://github.com/poly-hammer/meta-human-dna-addon/issues/203)


> [!WARNING]  
> You must use [poly-hammer-build-tool-workflow](https://github.com/poly-hammer/poly-hammer-build-tool-workflow) `0.7.1` or higher. If you have an older version, you will need to re-copy the template repo and [follow the setup tutorial again](https://www.youtube.com/watch?v=BAyCV8GwmCM). This is essential for your compiled dependencies to work correctly.

## Tests Passing On
* Metahuman Creator Version `6.0.0`
* Blender `4.5`, `5.0` (installed from blender.org)
* Unreal `5.6`, `5.7`
> [!NOTE]  
> Due to all the changes in Unreal 5.6, MetaHumans v6, and the addon still being in Beta, there is no backward support for earlier versions. Please use an older addon release if needed.