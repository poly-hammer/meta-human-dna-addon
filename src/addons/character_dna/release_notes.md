## Patch Changes

* Fixed Legacy data migration op
* Added validation to the Append/Link MetaHuman op to check for legacy data

> [!WARNING]
> You must use [poly-hammer-build-tool-workflow](https://github.com/poly-hammer/poly-hammer-build-tool-workflow) `1.0.0` or higher. If you have an older version, you will need to re-copy the template repo and [follow the setup tutorial again](https://www.youtube.com/watch?v=BAyCV8GwmCM). This is essential for your compiled dependencies to work correctly.

## Tests Passing On

* Metahuman Creator Version `6.0.0`
* Blender `4.5`, `5.1` (installed from blender.org)
* Unreal `5.6`, `5.7`

> [!NOTE]
> Due to all the changes in Unreal 5.6, MetaHumans v6, and the addon still being in Beta, there is no backward support for earlier versions. Please use an older addon release if needed.
