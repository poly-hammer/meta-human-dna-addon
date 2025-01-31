## Minor Changes
* Texture Logic Node Input Name now are 1-to-1 with Unreal Material Instance Parameter names.
    * `Color_MAIN`
    * `Color_CM1`
    * `Color_CM2`
    * `Color_CM3`
    * `Normal_MAIN`
    * `Normal_WM1`
    * `Normal_WM2`
    * `Normal_WM3`
    * `Cavity_MAIN`
    * `Roughness_MAIN`

## Patch Changes
* Fixed bone hierarchy and texture assignment bug [#37](https://github.com/poly-hammer/meta-human-dna-addon/issues/37)
* Fixed missing material slots bug [#46](https://github.com/poly-hammer/meta-human-dna-addon/issues/46)
* Fixed disorganization when having pre existing collections bug [#44](https://github.com/poly-hammer/meta-human-dna-addon/issues/44)
* Added pre DNA conversion mesh clean up logic that separates the mesh, finding the UVs by the unreal material name. [#39](https://github.com/poly-hammer/meta-human-dna-addon/issues/39)


## Tests Passing On
* Blender `4.2` (installed from blender.org)
* Unreal `5.4`
* Metahuman Preset `3.1.0`
* Metahuman Creator Version `1.3.0`
