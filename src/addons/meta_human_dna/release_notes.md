## Minor Changes
* Add an option to solo shape key value when switching to sculpt/edit it's shape [#105](https://github.com/poly-hammer/meta-human-dna-addon/issues/105)

## Patch Changes
* Fixed bug with duplicate actor when re-importing actor into level and level sequence
* Fixed bug Send to Unreal Validation for Shape Key Import [#95](https://github.com/poly-hammer/meta-human-dna-addon/issues/95)
* Added extra Send to Unreal validations for asset paths [#96](https://github.com/poly-hammer/meta-human-dna-addon/issues/96)
* Fixed DNA calibration bone rotations bug [#100](https://github.com/poly-hammer/meta-human-dna-addon/issues/100)


> [!WARNING]  
> You must use [poly-hammer-build-tool-workflow](https://github.com/poly-hammer/poly-hammer-build-tool-workflow) `0.5.2` or higher. If you have an older version, you will need to re-copy the template repo and [follow the setup tutorial again](https://www.youtube.com/watch?v=BAyCV8GwmCM). This is essential for your compiled dependencies to work correctly.

## Tests Passing On
* Metahuman Creator Version `4.0.2`
* Blender `4.2`, `4.3` (installed from blender.org)
* Unreal `5.4`, `5.5`
> [!NOTE]  
> For the Send to Unreal Feature to work on Unreal 5.5 and higher, the default FBX Importer should be set to use the Legacy FBX Importer. This can be done by changing the project's DefaultEngine.ini file to contain.
```ini
[ConsoleVariables]
Interchange.FeatureFlags.Import.FBX=False
```