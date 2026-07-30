"""FBX animation reading and fast Action writing.

:mod:`.reader` and :mod:`.maths` are free of Blender imports so they can be
tested standalone; :mod:`.writer` is the Blender-facing half.
"""

from .reader import FbxAnimationClip, load_fbx_animation, load_fbx_animation_buffer


__all__ = [
    "FbxAnimationClip",
    "load_fbx_animation",
    "load_fbx_animation_buffer",
]
