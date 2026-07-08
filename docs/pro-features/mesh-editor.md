# Mesh Editor

!!! info "Pro Feature"
    The Mesh Editor is part of the **Pro** edition and only appears when Pro is installed.

Symmetry and data-transfer tools for working with MetaHuman meshes.

<video autoplay loop muted playsinline class="rounded-image" style="width:100%" poster="../../images/mesh-editor/blender_sequence.png">
  <source src="../../images/mesh-editor/blender_sequence.webm" type="video/webm">
</video>

## Mesh Operations

Set the **Mirror Direction** (Left↔Right or Right↔Left), then use:

| Operation | Effect |
| --------- | ------ |
| Mirror | Mirror the mesh across the symmetry axis |
| Flip | Flip the mesh across the axis |
| Transfer | Transfer shape from a selected source mesh onto the target |

## Data Transfer

Expand **Data Transfer** to copy rig data between meshes — useful when moving weights and shapes onto a custom mesh.

- **Mode** — work from meshes in the current **Scene**, or from a cached topology **Shim**.
- **Shim Folder** — where topology shim (`.npz`) caches are stored.

**Scene mode** pairs a source DNA mesh with your custom target mesh, with options for deleting existing data and the space-transfer method.

| Button | Effect |
| ------ | ------ |
| Transfer Weights | Copy bone/vertex weights onto the target mesh |
| Transfer Shape Keys | Copy shape keys onto the target mesh |
| Save Topology Shim | Cache the topology mapping for reuse |

!!! tip
    Save a topology shim once, then reuse it to transfer data quickly onto meshes that share the same topology.
