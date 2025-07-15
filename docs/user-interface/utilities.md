# Utilities

These are one-off operations that can be used during the customization process.

!!! warning
    These are changing more rapidly than other parts of the tool, and some of these may be removed.


## Mesh
![](../images/user-interface/utilities/1.png){: class="rounded-image"}

## Armature
![](../images/user-interface/utilities/2.png){: class="rounded-image"}

### Mirror Selected Bones
Mirrors the selected bone positions to the other side of the head mesh.

### Auto Fit
Auto-fits the selected bones to the head mesh

### Revert
Revert the selected bone's transforms to their values in the DNA file.

## Convert Selected to DNA
Converts the selected mesh object to a valid mesh that matches the provided base DNA file.

!!! Warning
    The auto fitting algorithm is UV based, so it will only work correctly if your UV layout matches the one below. You can't have overlapping/or extra islands.

![](../images/user-interface/utilities/3.png){: class="rounded-image" style="height:400px"}
![](../images/user-interface/utilities/4.png){: class="rounded-image" style="height:400px"}
<br>
![](../images/user-interface/utilities/5.png){: class="rounded-image" style="height:365px"}
![](../images/user-interface/utilities/6.png){: class="rounded-image" style="height:365px"}
