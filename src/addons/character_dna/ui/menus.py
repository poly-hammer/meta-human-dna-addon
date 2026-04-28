# third party imports
import bpy

# local imports
from ..constants import ToolInfo
from ..typing import *  # noqa: F403


def dna_import_operator_menu_item(self: bpy.types.Menu, _: "Context"):
    if not self.layout:
        return
    self.layout.operator(f"{ToolInfo.NAME}.import_dna", text="MetaHuman DNA (.dna)")
    self.layout.operator(f"{ToolInfo.NAME}.append_or_link_metahuman", text="MetaHuman Append/Link (.blend)")


def add_dna_import_menu():
    try:
        bpy.types.TOPBAR_MT_file_import.remove(dna_import_operator_menu_item)
    finally:
        bpy.types.TOPBAR_MT_file_import.append(dna_import_operator_menu_item)


def remove_dna_import_menu():
    bpy.types.TOPBAR_MT_file_import.remove(dna_import_operator_menu_item)


def rig_logic_texture_node_menu_item(self: bpy.types.Menu, _: "Context"):
    if not self.layout:
        return
    self.layout.operator(f"{ToolInfo.NAME}.add_rig_logic_texture_node", text="Add Rig Logic Texture Node")


def add_rig_logic_texture_node_menu():
    try:
        bpy.types.NODE_MT_node.remove(rig_logic_texture_node_menu_item)
    finally:
        bpy.types.NODE_MT_node.append(rig_logic_texture_node_menu_item)


def remove_rig_logic_texture_node_menu():
    bpy.types.NODE_MT_node.remove(rig_logic_texture_node_menu_item)
