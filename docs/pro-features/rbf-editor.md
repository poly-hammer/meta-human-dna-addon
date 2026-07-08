# RBF Editor

!!! info "Pro Feature"
    The RBF Editor is part of the **Pro** edition and only appears when Pro is installed.

Modify, add, and delete corrective bone poses on your MetaHuman's **body**. These correctives interpolate between one another using **Radial Basis Functions (RBF)**. As a `driver` bone on the body moves, the corresponding `driven` corrective bones blend into position via a falloff function.

<video autoplay loop muted playsinline class="rounded-image" style="width:100%" poster="../../images/rbf-editor/rbf_editor.png">
  <source src="../../images/rbf-editor/rbf_editor.webm" type="video/webm">
</video>

## Solvers & Poses

- The **Solvers** list holds the RBF solvers on the body. (This also defines the joints in a joint group in DNA.)
- The **Poses** list holds the `driven` corrective bone poses for the active solver. You can have as many or as few poses as needed to make your solver interpolate to all the corrective positions.

Click **Edit** to modify a solver. While editing, you can **Add**, **Remove**, and **Mirror** solvers (mirroring maps the driving bones left ↔ right).

## Settings

Expand **Settings** while editing to choose the **Function Type**, the RBF kernel (e.g. Gaussian, Linear), with a live curve preview showing how the interpolation falls off.

## Committing

**Commit** writes your changes into the body DNA; **Revert** discards them.

!!! note
    While in RBF editing mode, you must click **Apply Pose Transform Edits** before switching to another pose. This is how you associate the changes with a pose. Please note these are still ephemeral until committed to the DNA.
