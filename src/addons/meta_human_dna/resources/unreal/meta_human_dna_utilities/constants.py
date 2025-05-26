class RecomputeTangentsVertexMaskChannel:
    RED = 0
    GREEN = 1
    BLUE = 2
    ALL = 3


SKELETAL_MESH_LOD_INFO_PROPERTIES = [
    "allow_cpu_access",
    "allow_mesh_deformer",
    "bake_pose",
    "bake_pose_override",
    "bones_to_prioritize",
    "bones_to_remove",
    "build_half_edge_buffers",
    "build_settings",
    "lod_hysteresis",
    "morph_target_position_error_tolerance",
    "reduction_settings",
    "screen_size",
    "sections_to_prioritize",
    "skin_cache_usage",
    "support_uniformly_distributed_sampling",
    "vertex_attributes",
    "weight_of_prioritization",
]

MATERIAL_INSTANCE_PARAMETERS = {
    "MI_HeadSynthesized_Baked": {
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
}

FACE_GROOM_NAMES = [
    "Eyelashes",
    "Fuzz",
    "Eyebrows",
    "Hair",
    "Mustache",
    "Beard"
]
