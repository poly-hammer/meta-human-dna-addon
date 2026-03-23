## Patch Changes

* Fixed Invalid Pose bone keyframe on Face Board Import [261](https://github.com/poly-hammer/meta-human-dna-addon/issues/261)
* Fixed Body Rig Resets After Adjusting and Undoing head board rig [281](https://github.com/poly-hammer/meta-human-dna-addon/issues/281)
* Fixed Pushing Down face board Action in NLA editor breaks rig/bones connection [280](https://github.com/poly-hammer/meta-human-dna-addon/issues/280)
* Fixed Render crash issues [279](https://github.com/poly-hammer/meta-human-dna-addon/issues/279)
* Fixed Migrate Legacy Data Error [272](https://github.com/poly-hammer/meta-human-dna-addon/issues/272)
* Fixed Error exporting manifest when running the Convert to DNA operator.

> [!WARNING]
> You must use [poly-hammer-build-tool-workflow](https://github.com/poly-hammer/poly-hammer-build-tool-workflow) `0.8.1` or higher. If you have an older version, you will need to re-copy the template repo and [follow the setup tutorial again](https://www.youtube.com/watch?v=BAyCV8GwmCM). This is essential for your compiled dependencies to work correctly.

## Tests Passing On

* Metahuman Creator Version `6.0.0`
* Blender `4.5`, `5.0` (installed from blender.org)
* Unreal `5.6`, `5.7`

> [!NOTE]
> Due to all the changes in Unreal 5.6, MetaHumans v6, and the addon still being in Beta, there is no backward support for earlier versions. Please use an older addon release if needed.
