## Major Changes
* Removed Send to Unreal functionality and refactored for Send to MetaHuman Creator. This can now be done entirely through DNA files now. (This will be more streamlined with RPC functionality in future releases)
* MetaHuman Creator - body support [#120](https://github.com/poly-hammer/meta-human-dna-addon/issues/120)

## Minor Changes
* Shape keys now calibrate to DNA instead of old Send to Unreal SkeletalMesh workflow
* Basis Shape key operator for quickly modifying the basis shape
* DNA exporter, now use the "component" (i.e. 'head.dna', 'body.dna') name for the file instead of the instance name

## Patch Changes
* Fixed Normal UV Map name on import [#126](https://github.com/poly-hammer/meta-human-dna-addon/issues/126)
* Fixed LOD import bug [#131](https://github.com/poly-hammer/meta-human-dna-addon/issues/131)
* Head frequently gets messed up on undo [#122](https://github.com/poly-hammer/meta-human-dna-addon/issues/122)


> [!WARNING]  
> You must use [poly-hammer-build-tool-workflow](https://github.com/poly-hammer/poly-hammer-build-tool-workflow) `0.5.2` or higher. If you have an older version, you will need to re-copy the template repo and [follow the setup tutorial again](https://www.youtube.com/watch?v=BAyCV8GwmCM). This is essential for your compiled dependencies to work correctly.

## Tests Passing On
* Metahuman Creator Version `6.0.0`
* Blender `4.2`, `4.3` (installed from blender.org)
* Unreal `5.6`
> [!NOTE]  
> Due to all the changes in Unreal 5.6, MetaHumans v6, and the addon still being in Beta, there is no backward support for earlier versions. Please use an older addon release if needed.