# FAQ

Answers to the questions we hear most. If your issue isn't covered here, search the [GitHub issues](https://github.com/poly-hammer/character-dna-addon/issues) — chances are someone has hit it before. If not, open a new one with your Blender version, addon version, and any console output.

## Installation & Setup

### Import fails with a `riglogic` / `dna` / `OpenMode_Binary` error

These come from a mismatched or partially-installed build. Reinstall the latest addon release for your exact Blender version, then fully restart Blender. If you built the Pro edition yourself, rebuild from a clean checkout of the latest release. Include the full console traceback when reporting.

## Face Board & Evaluation

### My Face Board isn't evaluating

Check these in order:

1. The face board is an armature — select it and enter **Pose Mode** to grab the yellow controls.
2. A control is actually selected (bright yellow) before you move it.
3. Evaluation isn't disabled — check the toggles on the instance in the [Rig Instances](./free-features/rig-instances.md) list.
4. As a last resort, click **Force Evaluate** to reset and re-cache. If that fixes it, please report what led to the bad state.

### Face Board controls stop being selectable after importing animation or shape keys

Selecting the board selects the whole armature instead of individual controls. Make sure you're in **Pose Mode** on the face board object, and that the face board is visible/selectable in [View Options](./free-features/view-options.md). See [Animation](./free-features/animation.md).

## Animation & Rendering

### The face is static or laggy during render

Live RigLogic evaluation doesn't run before each frame when rendering. **Bake** the face board animation to keyframes first so the pose bones, shape keys, and mask values are stored on the timeline. See [Animation](./free-features/animation.md).

## Still stuck?

Browse or search existing reports and open a new issue here:

[github.com/poly-hammer/character-dna-addon/issues](https://github.com/poly-hammer/character-dna-addon/issues)
