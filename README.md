<div align="center">
    <img src="https://www.polyhammer.com/images/products/character-dna-dark.png" alt="Example Custom MetaHuman" width="250px" style="margin-right: 10px;">
    <h1>Character DNA Addon</h1>
</div>

![GitHub Release](https://img.shields.io/github/v/release/poly-hammer/character-dna-addon)
[![Release](https://github.com/poly-hammer/character-dna-addon/actions/workflows/release.yaml/badge.svg)](https://github.com/poly-hammer/character-dna-addon/actions/workflows/release.yaml)
[![Dev](https://github.com/poly-hammer/character-dna-addon/actions/workflows/on-pr.yaml/badge.svg?branch=dev)](https://github.com/poly-hammer/character-dna-addon/actions/workflows/on-pr.yaml) [![Docs](https://github.com/poly-hammer/character-dna-addon/actions/workflows/docs.yaml/badge.svg)](https://github.com/poly-hammer/character-dna-addon/actions/workflows/docs.yaml)
[![codecov](https://codecov.io/gh/poly-hammer/character-dna-addon/graph/badge.svg?token=322E36CVR4)](https://codecov.io/gh/poly-hammer/character-dna-addon)

Imports MetaHuman head and body components into Blender from a their DNA files, lets you customize them, then send them back to MetaHuman Creator. [Get Now](https://polyhammer.com/character-dna-addon).

<div align="center">
    <img src="docs/images/quick-start/0.gif" alt="Example Custom MetaHuman" height="250px" style="margin-right: 10px;">
    <img src="docs/images/rig-logic/1.gif" alt="RigLogic Comparison" height="250px" style="margin-left: 10px;">
</div>

## Overview

Welcome to the project! We are working hard to make this the best solution for customizing MetaHumans for Unreal Engine. We are very proud to make this the first open source project related to MetaHuman DNA customization in Blender. [Code contributions](https://docs.polyhammer.com/character-dna-addon/contributing/development/), and suggestions are welcome and we are excited to work with the community to make this even better!

The base version of the addon is **FREE** and fully supports Blender import and export of `.dna` files. It also fully integrates Epic's OpenRigLogic evaluation system, providing a fast 1-to-1 integration of both the MetaHuman head and body components (just like Unreal Engine). This allows user's to use powerful tools like [MetaHuman Animator](https://dev.epicgames.com/documentation/metahuman/metahuman-animator) to drive facial animation directly on their rigs in Blender. This is totally free and you can install it from from our extension server when you create an [account here](https://dashboard.portal.polyhammer.com/).

However, please consider [financially supporting](https://polyhammer.com/character-dna-addon) the project by purchasing the pro version. The pro version contains advanced DNA editors which allow individuals and studios to replace their entire custom MetaHuman pipeline with just Blender. We heavily rely on your support to keep this project going! Thank you!

> [!NOTE]
> The addon is in the final stages of the open beta. The pro version is discounted while in the beta, however purchasing the pro version gets you access to lifetime updates.

## Support

The addon is compatible with MetaHuman `.dna` files that have been created with MetaHuman Creator in Unreal `5.6`, `5.7`, `5.8`. The current Blender support for the addon is listed below:

| Blender Version | Platform | Architecture |
| --------------- | -------- | ------------ |
| 4.5             | Windows  | x64          |
| 4.5             | Linux    | x64          |
| 4.5             | Mac OS   | arm64        |
| 5.1             | Windows  | x64          |
| 5.1             | Linux    | x64          |
| 5.1             | Mac OS   | arm64        |

## Get Notified on a New Release

Never miss a new addon release! Do this:

1. At the top right of this page select `Watch`
1. Select `Custom` from the dropdown.
1. Check `Releases`
1. Click `Apply`.

You will now get an email notification every time there is a new version of the addon released.

## Credits

* Demo asset in GIFs from [3D Scan Store](https://www.3dscanstore.com/).
* Facial ROMS in GIFs provided by [Bryan Steagall](https://www.linkedin.com/in/bryan-steagall-kks).

## License

The Character DNA add-on is licensed under the [GNU General Public License v3.0](LICENSE.md).

## Third-Party Software & Trademarks

This add-on bundles and redistributes the following third-party components.

* **OpenRigLogic** (DNA and RigLogic libraries) — © Epic Games, Inc., licensed under the [MIT License](https://github.com/EpicGames/OpenRigLogic/blob/main/LICENSE).
* **Sentry SDK for Python** — © Functional Software, Inc. dba Sentry, licensed under the MIT License.

Epic Games, Unreal Engine, Fab, MetaHuman, RigLogic, and OpenRigLogic and associated design logos
are trademarks or registered trademarks of Epic Games, Inc. All other trademarks are the property of
their respective owners. This add-on is not affiliated with, endorsed by, or sponsored by Epic Games,
Inc. References to MetaHuman, RigLogic, and OpenRigLogic are made under nominative use solely to
describe compatibility and the origin of the bundled libraries.
