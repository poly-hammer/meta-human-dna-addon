# Character DNA Addon

Bring MetaHuman characters into Blender and evaluate their face rigs in real time, exactly like Unreal Engine. The addon reads Epic Games' `.dna` files and drives them using the [OpenRigLogic](https://github.com/EpicGames/OpenRigLogic) runtime.

<video autoplay loop muted playsinline class="rounded-image" style="width:100%" poster="./images/getting-started/riglogic_merged_compare.png">
  <source src="./images/getting-started/riglogic_merged_compare.webm" type="video/webm">
</video>

The addon comes in two editions:

- **Free** — Import, animate, bake data, and export your scene data to your MetaHuman's DNA.
- **Pro** — Everything in Free, plus advanced editors for users who need full control over the data structures that define DNA behavior.

Because of this, the documentation has been organized by Free or Pro features.

## Install the Addon

Create an account on the [Poly Hammer Portal](https://dashboard.portal.polyhammer.com/signup), then link the extensions server by following these [instructions](https://docs.polyhammer.com/poly-hammer-portal/blender-extension-repo).

Once installed, a `Character DNA` tab appears on the right side of the 3D Viewport (toggle with the `N` key). Most panels start hidden and become visible once a [Rig Instance](./terminology.md#rig-instance) exists in the scene.

## Import Your DNA

The fastest way to start is to drag and drop a `head.dna` file into the Blender viewport. You can also do this via `File > Import > MetaHuman DNA (.dna)` from Blender's header menu.

<video autoplay loop muted playsinline class="rounded-image" style="width:100%" poster="./images/getting-started/metahuman_creator_support.png">
  <source src="./images/getting-started/metahuman_creator_support.webm" type="video/webm">
</video>

If a `Maps` folder sits alongside the `.dna` file, the importer automatically links matching textures.

!!! note
    `.dna` files are a proprietary format from Epic Games and are core to the MetaHuman identity — they encode the complete shape and rig of a MetaHuman. You can obtain them by exporting them from [MetaHuman Creator](https://dev.epicgames.com/documentation/metahuman/metahuman-creator-export-tool-in-unreal-engine#dccexport){: target="blank"} via its DCC export.

## Next Steps

You now have a MetaHuman evaluating in real time in Blender.

- New to MetaHuman terms? Read the [Terminology](terminology.md) overview.
- Ready to learn the addon's features? Explore the [Free Features](./free-features/rig-instances.md) and [Pro Features](./pro-features/converter.md).
- Hitting a snag? Check the [FAQ](faq.md).
