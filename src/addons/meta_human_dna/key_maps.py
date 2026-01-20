# standard library imports
import logging

# third-party imports
import bpy


logger = logging.getLogger(__name__)

# Store addon keymaps for proper cleanup
addon_keymaps: list[tuple[bpy.types.KeyMap, bpy.types.KeyMapItem]] = []


def register():
    """
    Register addon keymaps.

    These keymaps provide default shortcuts that users can customize
    in Edit > Preferences > Keymap.
    """
    wm = bpy.context.window_manager
    if wm is None:
        logger.warning("Window manager not available, skipping keymap registration")
        return

    kc = wm.keyconfigs.addon
    if kc is None:
        logger.warning("Addon keyconfig not available, skipping keymap registration")
        return

    # Create a keymap for Pose mode (where RBF editing happens)
    km = kc.keymaps.new(name="Pose", space_type="EMPTY")

    # Apply RBF Pose Edits - default: Ctrl+Shift+A
    key_map_item = km.keymap_items.new(
        idname="meta_human_dna.apply_rbf_pose_edits",
        type="A",
        value="PRESS",
        ctrl=True,
        shift=True,
    )
    addon_keymaps.append((km, key_map_item))

    logger.debug("Registered MetaHuman DNA addon keymaps")


def unregister():
    """
    Unregister addon keymaps.
    """
    for key_map, key_map_item in addon_keymaps:
        key_map.keymap_items.remove(key_map_item)
    addon_keymaps.clear()

    logger.debug("Unregistered MetaHuman DNA addon keymaps")
