## Minor Changes
* Display the .dna file info [#69](https://github.com/poly-hammer/meta-human-dna-addon/issues/69)
* Add alternate folder location option for wrinkle maps [#81](https://github.com/poly-hammer/meta-human-dna-addon/issues/81)

> [!WARNING]  
> You must use [poly-hammer-build-tool-workflow](https://github.com/poly-hammer/poly-hammer-build-tool-workflow) `0.5.2` or higher. If you have an older version, you will need to re-copy the template repo and [follow the setup tutorial again](https://www.youtube.com/watch?v=BAyCV8GwmCM). This is essential for your compiled dependencies to work correctly.

## Tests Passing On
* Metahuman Creator Version `4.0.2`
* Blender `4.2`, `4.3` (installed from blender.org)
* Unreal `5.4`, `5.5`
> [!NOTE]  
> For Send to Unreal Feature to work on Unreal 5.5 and higher, the default FBX Importer should be set to use the Legacy FBX Importer. This can be done by changing the project's DefaultEngine.ini file to contain.
```ini
[ConsoleVariables]
Interchange.FeatureFlags.Import.FBX=False
```

@poly-hammer/meta_human_dna_addon_early_access