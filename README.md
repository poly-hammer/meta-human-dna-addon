# Meta-Human DNA Addon

[![Tests](https://github.com/poly-hammer/metahuman-addon/actions/workflows/tests.yaml/badge.svg)](https://github.com/poly-hammer/metahuman-addon/actions/workflows/tests.yaml)

Imports a metahuman from its `.dna` file.

## Get Notified on a New Release
Never miss a new addon release! Do this:
1. At the top right of this page select `Watch`
1. Select `Custom` from the dropdown.
1. Check `Releases`
1. Click `Apply`.

You will now get an email notification every time there is a new version of an addon released.

## Development Dependencies

* [VS Code](https://code.visualstudio.com/download) 

    Alternatively, you can use another Python IDE, but development will be more streamlined in VS Code due to pre-configured profiles and launch settings. Additionally, `debugpy` is integrated into the environments when launching Blender from VS Code, facilitating debugging.

* [Python 3.11](https://www.python.org/downloads/release/python-3117/)
    
    Grab the installer from the provided link.

* [Git](https://git-scm.com/download/win) 

    Ensure that Git LFS is installed. The most recent Git installer typically includes Git LFS by default. When running the installer, opt for the default settings.

* [Blender 4.2](https://www.blender.org/download/)

### Reloading the addon code
```python
from poly_hammer_utils.helpers import reload_addon_source_code
reload_addon_source_code(['meta_human_dna'])
```