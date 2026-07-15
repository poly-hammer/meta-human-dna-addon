# FAQ

If your issue isn't covered here, search the [GitHub issues](https://github.com/poly-hammer/character-dna-addon/issues). Most likely, someone has hit it before. If not, open a new one with your Blender version, addon version, and any console output.

## Face Board & Evaluation

### My Face Board isn't evaluating

Check these in order:

1. The face board is an armature — select it and enter **Pose Mode** to grab the yellow controls.
2. A control is actually selected (bright yellow) before you move it.
3. Evaluation isn't disabled — check the toggles on the instance in the [Rig Instances](./free-features/rig-instances.md) list.
4. As a last resort, click **Force Evaluate** to reset and re-cache.

## Animation & Rendering

### The face is static or jittery during render

Live RigLogic evaluation doesn't run before each frame when rendering. **Bake** the face board animation to keyframes first so the pose bones, shape keys, and mask values are stored on the timeline. See [Animation](./free-features/animation.md).

!!! note
    It is now possible to disable `Batched Evaluations` in the addon preferences. This is currently experimental. Please report any issues with evaluation in the scene or while rendering with this option on.

## Still stuck?

Browse or search existing reports and open a new issue here:

[github.com/poly-hammer/character-dna-addon/issues](https://github.com/poly-hammer/character-dna-addon/issues)
