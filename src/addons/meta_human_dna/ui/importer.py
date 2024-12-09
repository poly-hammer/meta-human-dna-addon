import bpy # type: ignore
from bpy_extras.io_utils import ImportHelper # type: ignore
from ..constants import NUMBER_OF_FACE_LODS


class META_HUMAN_DNA_MESH_DATA_PT_panel(bpy.types.Panel):
    bl_space_type = 'FILE_BROWSER'
    bl_region_type = 'TOOL_PROPS'
    bl_label = "Mesh Data"
    bl_parent_id = "FILE_PT_operator"
    bl_options = {'HEADER_LAYOUT_EXPAND'}

    @classmethod
    def poll(cls, context):
        return context.space_data.active_operator.bl_idname == "META_HUMAN_DNA_OT_import_dna" # type: ignore

    def draw(self, context):
        operator = context.space_data.active_operator # type: ignore
        layout = self.layout
        row = layout.row()
        row.prop(operator, "import_mesh")
        row = layout.row()
        # TODO: Fix implementation normals import
        # row.prop(operator, "import_normals")
        row = layout.row()
        row.prop(operator, "import_bones")
        row = layout.row()
        # TODO: See if we what to import shape keys during initial import
        # row.prop(operator, "import_shape_keys")
        # row = layout.row()
        row.prop(operator, "import_vertex_groups")
        row = layout.row()
        row.prop(operator, "import_vertex_colors")
        row = layout.row()
        row.prop(operator, "import_materials")
        row = layout.row()
        row.prop(operator, "import_face_board")


class META_HUMAN_DNA_LODS_PT_panel(bpy.types.Panel):
    bl_space_type = 'FILE_BROWSER'
    bl_region_type = 'TOOL_PROPS'
    bl_label = "Lods"
    bl_parent_id = "FILE_PT_operator"
    bl_options = {'HEADER_LAYOUT_EXPAND'}

    @classmethod
    def poll(cls, context):
        return context.space_data.active_operator.bl_idname == "META_HUMAN_DNA_OT_import_dna" # type: ignore

    def draw(self, context):
        operator = context.space_data.active_operator # type: ignore
        layout = self.layout
        row = layout.row()
        for i in range(NUMBER_OF_FACE_LODS):
            if i == 0:
                row.enabled = False
            row.prop(operator, f"import_lod{i}")
            row = layout.row()


class ImportAsset(ImportHelper):
    """
    This class subclasses the export helper to define a custom file browser
    """
    bl_idname = "meta_human_dna.import_dna"
    bl_options = {'UNDO', 'PRESET'}

    def draw(self, context):
        pass
