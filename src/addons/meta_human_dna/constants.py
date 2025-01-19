import os
from enum import Enum
from pathlib import Path
from mathutils import Vector
from typing import Literal


class ToolInfo:
    NAME = "meta_human_dna"

Axis = Literal["X", "Y", "Z"]

FACE_BOARD_NAME = "face_gui"
HEAD_MATERIAL_NAME = "head_shader"
MASKS_TEXTURE = "combined_masks.tga"
TOPOLOGY_TEXTURE = "head_topology.png"
NUMBER_OF_FACE_LODS = 8
SENTRY_DSN = "https://38575ef4609265865b46dcc274249962@sentry.polyhammer.com/13"

INVALID_NAME_CHARACTERS_REGEX = r"[^-+\w]+"
LOD_REGEX = r"(?i)(_LOD\d).*"

HEAD_TOPOLOGY_MESH = "head_topology"
HEAD_TOPOLOGY_MESH_CAGE = "head_topology_cage"
HEAD_SHRINK_WRAP_MODIFIER_PREFIX = "shrink_wrap"
TOPO_GROUP_PREFIX = "TOPO_GROUP_"
SHAPE_KEY_GROUP_PREFIX = "SHAPE_KEY_"

# this is the difference in scale between unreal and blender
SCALE_FACTOR = 100.0
BONE_TAIL_OFFSET = 1 / (SCALE_FACTOR * SCALE_FACTOR * 10)
CUSTOM_BONE_SHAPE_SCALE = Vector([0.15] * 3)
CUSTOM_BONE_SHAPE_NAME = "sphere_control"
TEXTURE_LOGIC_NODE_NAME = "texture_logic"
TEXTURE_LOGIC_NODE_LABEL = "Texture Logic"
UV_MAP_NAME = "DiffuseUV"
VERTEX_COLOR_ATTRIBUTE_NAME = "Color"
MAX_BONE_HIERARCHY_DEPTH = 7
MESH_VERTEX_COLORS_FILE_NAME = "vertex_colors.json"
FLOATING_POINT_PRECISION = 0.0001

MESH_SHADER_MAPPING = {
    "head_lod": "head_shader",
    "teeth_lod": "teeth_shader",
    "saliva_lod": "saliva_shader",
    "eyeLeft_lod": "eyeLeft_shader",
    "eyeRight_lod": "eyeRight_shader",
    "eyeshell_lod": "eyeshell_shader",
    "eyelashes_lod": "eyelashes_shader",
    "eyelashesShadow_lod": "eyelashesShadow_shader",
    "eyeEdge_lod": "eyeEdge_shader",
    "cartilage_lod": "eyeEdge_shader",
}

MATERIAL_SLOT_TO_MATERIAL_INSTANCE_DEFAULTS = {
    "head_shader": "/Game/MetaHumans/Common/Face/Materials/Baked/MI_HeadSynthesized_Baked",
    "teeth_shader": "/Game/MetaHumans/Common/Materials/M_TeethCharacterCreator_Inst",
    "saliva_shader": "",
    "eyeLeft_shader": "/Game/MetaHumans/Common/Face/Materials/MI_EyeRefractive_Inst_L",
    "eyeRight_shader": "/Game/MetaHumans/Common/Face/Materials/MI_EyeRefractive_Inst_R",
    "eyeshell_shader": "",
    "eyelashes_shader": "/Game/MetaHumans/Common/Materials/M_EyeLash_HigherLODs_Inst",
    "eyelashesShadow_shader": "/Game/MetaHumans/Common/Face/Materials/MI_EyeOcclusion_Inst",
    "eyeEdge_shader": "/Game/MetaHumans/Common/Face/Materials/MI_lacrimal_fluid_Inst",
}

RESOURCES_FOLDER = Path(os.path.dirname(__file__), "resources")
BINDINGS_FOLDER = Path(os.path.dirname(__file__), "bindings")
PACKAGES_FOLDER = RESOURCES_FOLDER / "packages"
POSES_FOLDER = RESOURCES_FOLDER / "poses"
BLENDS_FOLDER = RESOURCES_FOLDER / "blends"
IMAGES_FOLDER = RESOURCES_FOLDER / "images"
MAPPINGS_FOLDER = RESOURCES_FOLDER / "mappings"
BASE_DNA_FOLDER = RESOURCES_FOLDER / "dna"

LEAF_BONE_TO_VERTEX_MAPPING_FILE_PATH = MAPPINGS_FOLDER / "leaf_bone_to_vert_index.json"
LEAF_BONE_IMMEDIATE_PARENT_OFFSETS_FILE_PATH = MAPPINGS_FOLDER / "leaf_bone_immediate_parent_offsets.json"
LIP_BONE_OFFSETS_FILE_PATH = MAPPINGS_FOLDER / "lip_bone_offsets.json"
EYE_BONE_OFFSETS_FILE_PATH = MAPPINGS_FOLDER / "eye_bone_offsets.json"
TOPOLOGY_VERTEX_GROUPS_FILE_PATH = MAPPINGS_FOLDER / "topology_vertex_groups.json"
MESH_VERTEX_COLORS_FILE_PATH = MAPPINGS_FOLDER / MESH_VERTEX_COLORS_FILE_NAME

MASKS_TEXTURE_FILE_PATH = IMAGES_FOLDER / MASKS_TEXTURE

TOPOLOGY_TEXTURE_FILE_PATH = IMAGES_FOLDER / TOPOLOGY_TEXTURE

MATERIALS_FILE_PATH = BLENDS_FOLDER / "materials.blend"

FACE_BOARD_FILE_PATH = BLENDS_FOLDER / "face_board.blend"

CAGE_MESH_FILE_PATH = BLENDS_FOLDER / "cage_mesh_and_basis.blend"

SEND2UE_FACE_SETTINGS = RESOURCES_FOLDER / 'send2ue' / "meta-human_dna.json"

SEND2UE_EXTENSION = RESOURCES_FOLDER / 'send2ue' / "meta_human_dna_extension.py"

HEAD_MAPS = {
    "cm_base": "head_color_map.tga",
    "cm1": "head_cm1_color_map.tga",
    "cm2": "head_cm2_color_map.tga",
    "cm3": "head_cm3_color_map.tga",
    "wm_base": "head_normal_map.tga",
    "wm1": "head_wm1_normal_map.tga",
    "wm2": "head_wm2_normal_map.tga",
    "wm3": "head_wm3_normal_map.tga"
}


PLATFORM_NAMES = {
    "linux": "Linux",
    "linux2": "Linux",
    "win32": "Windows",
    "darwin": "Mac OS X",
}

FACE_GUI_EMPTIES = [
    "GRP_C_eyesAim", 
    "GRP_faceGUI", 
    "LOC_C_eyeDriver",
    "head_grp",
    "headRig_grp",
    "headGui_grp",
    "headRigging_grp",
    "eyesSetup_grp"
]