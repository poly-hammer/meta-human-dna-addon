# Mesh Wrapping

To convert a custom head into a MetaHuman DNA with the [Converter](../pro-features/converter.md), your mesh must share the MetaHuman topology and UV layout. **Wrapping** is how you get there: you deform a copy of the base MetaHuman head and body meshes so they conform to your scan, sculpt, or alternative topology — keeping the MetaHuman topology while taking on your character's shape.

## Why Wrap?

The [DNA auto-fitting](../pro-features/converter.md) algorithm is **UV based**. It only produces a correct fit when your mesh uses the base MetaHuman UV layout with **no overlapping or extra islands, or distorted points**.

<div style="display:flex; gap:0; justify-content:center; align-items:flex-start;">
  <img src="../../images/mesh-wrapping/head.png" alt="MetaHuman body UV layout" class="rounded-image" style="height:360px; width:auto;">
  <img src="../../images/mesh-wrapping/body.png" alt="MetaHuman body UV layout" class="rounded-image" style="height:360px; width:auto;">
</div>

<div style="display:flex; gap:0; justify-content:center; align-items:flex-start;">
  <img src="../../images/mesh-wrapping/head_uv_layout.png" alt="MetaHuman body UV layout wireframe" class="rounded-image" style="height:360px; width:auto;">
  <img src="../../images/mesh-wrapping/body_uv_layout.png" alt="MetaHuman body UV layout wireframe" class="rounded-image" style="height:360px; width:auto;">
</div>

Wrapping preserves that layout because you start from the base MetaHuman head and body meshes and only move their vertices — you never change their topology or UVs.

## Methods

There are several ways to produce a wrapped, topology-matched head and body. Pick whichever fits your pipeline.

### 1. Face Form Wrap

A dedicated wrapping tool that is a fast and accurate way to conform the base MetaHuman head and body meshes onto your target scan or sculpt while preserving topology and UVs.

<div style="max-width:100%; margin:0 auto;">
  <iframe width="100%" style="aspect-ratio:16/9; border:0;" src="https://www.youtube.com/embed/813BCbIwGiE" title="Face Form Wrap tutorial" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" allowfullscreen></iframe>
</div>

### 2. Mesh to MetaHuman (Unreal Engine 5.8)

Epic's built-in **Mesh to MetaHuman** tool fits a MetaHuman topology onto your custom mesh directly in Unreal, then hands it back through MetaHuman Creator. Export the resulting DNA and bring it into Blender.

- [MetaHuman Creator from custom mesh tool in Unreal Engine](https://dev.epicgames.com/documentation/metahuman/metahuman-creator-from-custom-mesh-tool-in-unreal-engine)

### 3. Blender (Proportional Editing, Sculpt, Shrinkwrap)

Wrap entirely in Blender by reshaping a copy of the base MetaHuman head and body:

1. Use **Proportional Editing** to block in the overall shape toward your target.
2. Refine with **Sculpt** brushes for finer detail.
3. Systematically add **[Shrinkwrap modifiers](https://docs.blender.org/manual/en/latest/modeling/modifiers/deform/shrinkwrap.html)** targeting your reference mesh, scoping each to a **vertex group** so you can conform specific regions (cheeks, brow, jaw) without disturbing the rest. Apply as you go.

You can even combine these methods to achieve your desired result, using free or paid tools as needed.

## Convert

Once you have a wrapped head and body mesh, run **Convert to DNA**.

!!! tip
    Wrapping the character in a neutral position with the mouth slightly open and eyes slightly closed can be ideal for transferring textures or vertex group data. You can then edit the `default` item in the [Raw Editor](../pro-features/raw-editor.md) to close the mouth and fully open the eyes, defining the character's rest pose.
