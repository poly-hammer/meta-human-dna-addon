## Patch Changes

* Fixed Undo crash on body [#25](https://github.com/orgs/poly-hammer/discussions/25), [#321](https://github.com/poly-hammer/character-dna-addon/issues/321), [#317](https://github.com/poly-hammer/character-dna-addon/issues/317),
* Optimized body evaluations for driven/swig/twist bones
* Fixed false positive from Legacy Migration Panel [#314](https://github.com/poly-hammer/character-dna-addon/issues/314), [#21](https://github.com/orgs/poly-hammer/discussions/21)

> [!WARNING]
> You must use [poly-hammer-build-tool-workflow](https://github.com/poly-hammer/poly-hammer-build-tool-workflow) `1.0.0` or higher. If you have an older version, you will need to re-copy the template repo and [follow the setup tutorial again](https://www.youtube.com/watch?v=BAyCV8GwmCM). This is essential for your compiled dependencies to work correctly.

## Tests Passing On

* Metahuman Creator Version `6.0.0`
* Blender `4.5`, `5.1` (installed from blender.org)
* Unreal `5.6`, `5.7`

> [!NOTE]
> Due to all the changes in Unreal 5.6, MetaHumans v6, and the addon still being in Beta, there is no backward support for earlier versions. Please use an older addon release if needed.
