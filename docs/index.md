# Meta-Human DNA Addon

## Build a Release
This addon needs parts of Unreal Engine's source code compiled into a standalone library, as well as our own core module. Because of that, we can't re-distribute all the dependencies. However, you can agree to the Epic EULA and compile a release for yourself. The [Hammer Build Tool](https://docs.polyhammer.com/hammer-build-tool/setup) makes it super easy. Once you have followed those instructions and obtained your addon release from the `.zip` file, continue to the next step.

![](./images/quick-start/1.gif){: class="rounded-image"}

## Install the Addon in Blender
To install into Blender, simply drag and drop the `.zip` file that you downloaded into an open window of Blender.

![](./images/quick-start/2.gif){: class="rounded-image"}

You will now see a tab on the right-side of the 3D Viewport bar called `Meta-Human DNA` (Hide/Show with `N` key.). You will notice that the panels are grayed out and have warning messages. These panels become active when there is an active [RigLogic Instance](./terminology.md/#rig-logic-instance).

## Option 1: Import a DNA File
The easiest way to get started, is to just drag and drop a `.dna` file into the blender scene.

![](./images/quick-start/3.gif){: class="rounded-image"}

If a `maps` folder exists alongside the `.dna` file, the importer will link any textures that follow the same naming conventions as the Metahuman source assets from bridge.

!!! note
    If you didn't already know, `.dna` files are a proprietary file format created by Epic Games. DNA is an integral part of the MetaHuman identity. DNA files encode all the details of the shape and rig for MetaHuman heads. You can obtain a `.dna` file for your Metahuman by exporting the source assets from [Bridge](https://dev.epicgames.com/documentation/en-us/metahuman/downloading-and-exporting-metahumans-to-unreal-engine-5-and-maya){: target="blank"}.

!!! tip
    If you are eager to get started, and don't want to setup Bridge. You can grab [these example](https://github.com/EpicGames/MetaHuman-DNA-Calibration/tree/main/data/dna_files){: target="blank"} `.dna` files directly from one of Epic's repos.

## Option 2: Convert Mesh to DNA
The addon also has a UV based "Auto fitting" algorithm. So as long as your selected mesh has the same UVs as a Metahuman mesh, then under the `Utilities` panel you can click `Convert Selected to DNA`.

![](./images/quick-start/4.gif){: class="rounded-image"}

This will also snap the eyes and mouth and face bones into place relative to where it thinks they should be. This can be a great start to a custom metahuman pipeline.

A very common workflow is to wrap your Metahuman topology head mesh to your raw scans or sculpted base meshes in a software like [Face Form Wrap](https://faceform.com/download-wrap/){: target="blank"}. This will allow for an easy UV based conversion with the `Convert Selected to DNA` operator. (This workflow is discussed [further in another section](./workflows/face-form-wrap.md))


## Congratulations! 🎉 
If you have made it this far, you have installed the addon and already have your first Metahuman head in Blender the real-time RigLogic should be evaluating just like in Unreal Engine! Your ready to start diving deeper into facial customization!

!!! tip
    Check out our [terminology overview](terminology.md) since we use some pretty Metahuman specific lingo in our docs.