import os
import math
from pathlib import Path
from mathutils import Vector, Euler
from typing import Literal

class ToolInfo:
    NAME = "meta_human_dna"
    BUILD_TOOL_DOCUMENTATION = "https://docs.polyhammer.com/hammer-build-tool/setup/"
    METRICS_COLLECTION_AGREEMENT = "https://www.polyhammer.com/dpa"

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
MESH_VERTEX_COLORS_FILE_NAME = "vertex_colors.json"
FLOATING_POINT_PRECISION = 0.0001
DEFAULT_UV_TOLERANCE = 0.001

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
    "cartilage_lod": "cartilage_shader",
}

MATERIAL_SLOT_TO_MATERIAL_INSTANCE_DEFAULTS = {
    "head_shader": "/Game/MetaHumans/Common/Face/Materials/Baked/MI_HeadSynthesized_Baked",
    "teeth_shader": "/Game/MetaHumans/Common/Materials/M_TeethCharacterCreator_Inst",
    "saliva_shader": "/Game/MetaHumans/Common/Face/Materials/MI_lacrimal_fluid_Inst",
    "eyeLeft_shader": "/Game/MetaHumans/Common/Face/Materials/MI_EyeRefractive_Inst_L",
    "eyeRight_shader": "/Game/MetaHumans/Common/Face/Materials/MI_EyeRefractive_Inst_R",
    "eyeshell_shader": "/Game/MetaHumans/Common/Face/Materials/MI_EyeOcclusion_Inst",
    "eyelashes_shader": "/Game/MetaHumans/Common/Materials/M_EyelashLowerLODs_Inst",
    "eyelashesShadow_shader": "/Game/MetaHumans/Common/Face/Materials/MI_EyeOcclusion_Inst",
    "eyeEdge_shader": "/Game/MetaHumans/Common/Face/Materials/MI_lacrimal_fluid_Inst",
    "cartilage_shader": "/Game/MetaHumans/Common/Face/Materials/M_Cartilage",
}


RESOURCES_FOLDER = Path(os.path.dirname(__file__), "resources")
BINDINGS_FOLDER = Path(os.path.dirname(__file__), "bindings")
PACKAGES_FOLDER = RESOURCES_FOLDER / "packages"
POSES_FOLDER = RESOURCES_FOLDER / "poses"
BLENDS_FOLDER = RESOURCES_FOLDER / "blends"
IMAGES_FOLDER = RESOURCES_FOLDER / "images"
MAPPINGS_FOLDER = RESOURCES_FOLDER / "mappings"
BASE_DNA_FOLDER = RESOURCES_FOLDER / "dna"

TOPOLOGY_VERTEX_GROUPS_FILE_PATH = MAPPINGS_FOLDER / "topology_vertex_groups.json"
MESH_VERTEX_COLORS_FILE_PATH = MAPPINGS_FOLDER / MESH_VERTEX_COLORS_FILE_NAME

MASKS_TEXTURE_FILE_PATH = IMAGES_FOLDER / MASKS_TEXTURE

TOPOLOGY_TEXTURE_FILE_PATH = IMAGES_FOLDER / TOPOLOGY_TEXTURE

MATERIALS_FILE_PATH = BLENDS_FOLDER / "materials.blend"

FACE_BOARD_FILE_PATH = BLENDS_FOLDER / "face_board.blend"

CAGE_MESH_FILE_PATH = BLENDS_FOLDER / "cage_mesh_and_basis.blend"

SEND2UE_FACE_SETTINGS = RESOURCES_FOLDER / 'send2ue' / "meta-human_dna.json"

SEND2UE_EXTENSION = RESOURCES_FOLDER / 'send2ue' / "meta_human_dna_extension.py"

ALTERNATE_TEXTURE_FILE_EXTENSIONS = [
    ".tga",
    ".png"   
]

ALTERNATE_HEAD_TEXTURE_FILE_NAMES = {
    "head_color_map.tga": "Head_Basecolor",
    "head_cm1_color_map.tga": "Head_Basecolor_Animated_CM1",
    "head_cm2_color_map.tga": "Head_Basecolor_Animated_CM2",
    "head_cm3_color_map.tga": "Head_Basecolor_Animated_CM3",
    "head_normal_map.tga": "Head_Normal",
    "head_wm1_normal_map.tga": "Head_Normal_Animated_WM1",
    "head_wm2_normal_map.tga": "Head_Normal_Animated_WM2",
    "head_wm3_normal_map.tga": "Head_Normal_Animated_WM3",
    "eyes_color_map.tga": "Eyes_Color",
    "eyes_normal_map.tga": "Eyes_Normal",
    "teeth_color_map.tga": "Teeth_Color",
    "teeth_normal_map.tga": "Teeth_Normal",
    "eyelashes_color_map.tga": "Eyelashes_Color"
}

LEGACY_ALTERNATE_HEAD_TEXTURE_FILE_NAMES = {
    "head_color_map.tga": "FaceColor_MAIN",
    "head_cm1_color_map.tga": "FaceColor_CM1",
    "head_cm2_color_map.tga": "FaceColor_CM2",
    "head_cm3_color_map.tga": "FaceColor_CM3",
    "head_normal_map.tga": "FaceNormal_MAIN",
    "head_wm1_normal_map.tga": "FaceNormal_WM1",
    "head_wm2_normal_map.tga": "FaceNormal_WM2",
    "head_wm3_normal_map.tga": "FaceNormal_WM3",
    "head_cavity_map.tga": "FaceCavity_MAIN",
    "head_roughness_map.tga": "FaceRoughness_MAIN"
}

HEAD_MAPS = {
    "Color_MAIN": "head_color_map.tga",
    "Color_CM1": "head_cm1_color_map.tga",
    "Color_CM2": "head_cm2_color_map.tga",
    "Color_CM3": "head_cm3_color_map.tga",
    "Normal_MAIN": "head_normal_map.tga",
    "Normal_WM1": "head_wm1_normal_map.tga",
    "Normal_WM2": "head_wm2_normal_map.tga",
    "Normal_WM3": "head_wm3_normal_map.tga",
    "Cavity_MAIN": "head_cavity_map.tga",
    "Roughness_MAIN": "head_roughness_map.tga"
}

UNREAL_EXPORTED_HEAD_MATERIAL_NAMES = [
    'MI_HeadSynthesized_Baked'
]

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

# Set to Ada's height, but locations will be scaled proportionally to match spine_04 location from DNA file.
# Also in Y-up coordinate system like the metahuman creator DNA files
FIRST_BONE_Y_LOCATION = 107.86403

EXTRA_BONES = [
    ('root', {
        'parent': None,
        'location': Vector((0, 0, 0)),
        'rotation': Euler((0, 0, 0), 'XYZ')
    }),
    ('pelvis', {
        'parent': 'root',
        'location': Vector((0.0, 0.8707, 0.0209)),
        'rotation': Euler((math.radians(-90.0), math.radians(-2.053), math.radians(90.0)), 'XYZ')
    }),
    ('spine_01', {
        'parent': 'pelvis',
        'location': Vector((0.0, 0.8910, 0.0206)),
        'rotation': Euler((math.radians(-90.0), math.radians(-13.003), math.radians(90.0)), 'XYZ')
    }),
    ('spine_02', {
        'parent': 'spine_01',
        'location': Vector((0.0, 0.9326, 0.0302)),
        'rotation': Euler((math.radians(-90.0), math.radians(-5.68216), math.radians(90.0)), 'XYZ')
    }),
    ('spine_03', {
        'parent': 'spine_02',
        'location': Vector((0.0, 0.9998, 0.0369)),
        'rotation': Euler((math.radians(-90.0), math.radians(3.82404), math.radians(90.0)), 'XYZ')
    })
]