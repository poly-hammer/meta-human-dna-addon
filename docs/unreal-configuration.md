# Unreal Configuration

## Project Setup
Todo...

## Asset Configuration

### Curves
The MetaHuman head skeleton needs both Material and Morph Target curves defined for RigLogic to work correcting in Unreal with the texture masks and shape keys. After your initial import of a new head SkeletalMesh, you will need to copy over the curve names from `/Game/MetaHumans/Common/Face/Face_Archetype_Skeleton` to your newly imported skeleton.

![](../images/unreal-configuration/3.gif){: class="rounded-image center-image"}

!!! note
    If you added/renamed [expressions](https://dev.epicgames.com/documentation/en-us/metahuman/control-curves-driven-by-metahuman-animator) in your .dna file for new morph targets or texture masks,
    you would need to ensure you add or rename these.
