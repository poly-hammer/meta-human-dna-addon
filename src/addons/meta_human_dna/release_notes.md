## Minor Changes
* Created new bindings for Unreal 5.6. (You must update your build tool to `0.6.0` or greater now or the built addon won't work)
* Added validate option to output panel. By default the validations are run before export, but this option allows the user to turn them off.

## Patch Changes
* Fixed Edit bone rotations on the body are not calibrating[#139](https://github.com/poly-hammer/meta-human-dna-addon/issues/139)
* Fixed Mesh origin validation [#140](https://github.com/poly-hammer/meta-human-dna-addon/issues/140)
* Fixed Multi-Language support [#141](https://github.com/poly-hammer/meta-human-dna-addon/issues/141)
* Fixed Seam from Misaligned bones roll on convert [#155](https://github.com/poly-hammer/meta-human-dna-addon/issues/155)
* Fixed Head LOD to Body LOD mapping. There are twice as many head LODs as body LODs.


> [!WARNING]  
> You must use [poly-hammer-build-tool-workflow](https://github.com/poly-hammer/poly-hammer-build-tool-workflow) `0.6.1` or higher. If you have an older version, you will need to re-copy the template repo and [follow the setup tutorial again](https://www.youtube.com/watch?v=BAyCV8GwmCM). This is essential for your compiled dependencies to work correctly.

## Tests Passing On
* Metahuman Creator Version `6.0.0`
* Blender `4.5` (installed from blender.org)
* Unreal `5.6`
> [!NOTE]  
> Due to all the changes in Unreal 5.6, MetaHumans v6, and the addon still being in Beta, there is no backward support for earlier versions. Please use an older addon release if needed.