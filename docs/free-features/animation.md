# Animation

Import MetaHuman performances onto your character and bake them to plain Blender data for rendering or simulation. The panel has a **Face Board** section and a **Body Animation** section, each with **Import** and **Bake**.

## Face Board Animation

Import facial performance curves — for example from **MetaHuman Animator** — onto the face board.

<video autoplay loop muted playsinline class="rounded-image" style="width:100%" poster="../../images/animation/metahuman_animator_face_board_support.png">
  <source src="../../images/animation/metahuman_animator_face_board_support.webm" type="video/webm">
</video>

- **Export from Unreal** — check out [this video](https://youtu.be/j59ftPt7MUY?si=fyU8Z9BMiQ3MqU-X&t=269) on how to do this.
- **Import to Blender** — load a face board animation exported from an Unreal Engine Level Sequence.
- **(Optional) Bake** — write the active face board action down to keyframes on the pose bones, shape key values, and [Texture Logic](../terminology.md#texture-logic) node mask values.

## Body Animation

Import body performances — from MetaHuman Animator or any re-targeted animation — onto the body rig.

<video autoplay loop muted playsinline class="rounded-image" style="width:100%" poster="../../images/animation/metahuman_animator_body_support.png">
  <source src="../../images/animation/metahuman_animator_body_support.webm" type="video/webm">
</video>

- **Export from Unreal** — check out [this video](https://youtu.be/V4mWGrTJqFg?si=42fupxfBvWyVLK9D&t=265) on how to do this.
- **Import to Blender** — load a body animation onto the character's skeleton.
- **(Optional) Bake** — write the evaluated transforms of the RBF corrective bones down to keyframes.

## Why Bake?

<video autoplay loop muted playsinline class="rounded-image" style="width:100%" poster="../../images/animation/bake_animation.png">
  <source src="../../images/animation/bake_animation.webm" type="video/webm">
</video>

This can be useful for simulations or exporting to other software.
