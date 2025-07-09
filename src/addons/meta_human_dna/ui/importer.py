import os
import bpy
from bpy_extras.io_utils import ImportHelper # type: ignore
from ..constants import NUMBER_OF_HEAD_LODS
from ..dna_io import get_dna_reader
from pathlib import Path

class META_HUMAN_DNA_FILE_DATA_PT_panel(bpy.types.Panel):
    bl_space_type = 'FILE_BROWSER'
    bl_region_type = 'TOOL_PROPS'
    bl_label = "File Data"
    bl_parent_id = "FILE_PT_operator"
    bl_options = {'HEADER_LAYOUT_EXPAND'}

    @classmethod
    def poll(cls, context):
        return context.space_data.active_operator.bl_idname == "META_HUMAN_DNA_OT_import_dna" # type: ignore

    def draw(self, context):
        if not self.layout:
            return
        
        operator = context.space_data.active_operator # type: ignore
        stem = Path(operator.filepath).stem.lower()
        layout = self.layout
        row = layout.row()
        row.prop(operator, "import_mesh")
        row = layout.row()
        # TODO: Fix implementation normals import
        # row.prop(operator, "import_normals")
        row = layout.row()
        row.prop(operator, "import_bones")
        # row = layout.row()
        # TODO: See if we what to import shape keys during initial import
        # row.prop(operator, "import_shape_keys")
        row = layout.row()
        row.prop(operator, "import_vertex_groups")
        if stem != "body":
            row = layout.row()
            row.prop(operator, "import_vertex_colors")
        row = layout.row()
        row.prop(operator, "import_materials")
        if stem != "body":
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
        if not self.layout:
            return
        
        operator = context.space_data.active_operator # type: ignore
        stem = Path(operator.filepath).stem.lower()
        layout = self.layout
        row = layout.row()
        for i in range(NUMBER_OF_HEAD_LODS):
            if i == 0:
                row.enabled = False
            # bodies only have one LOD, so we don't need to show the LODs for them
            if stem == "body" and i > 3:
                return
            row.prop(operator, f"import_lod{i}")
            row = layout.row()

class META_HUMAN_DNA_EXTRAS_PT_panel(bpy.types.Panel):
    bl_space_type = 'FILE_BROWSER'
    bl_region_type = 'TOOL_PROPS'
    bl_label = "Extras"
    bl_parent_id = "FILE_PT_operator"
    bl_options = {'HEADER_LAYOUT_EXPAND'}

    @classmethod
    def poll(cls, context):
        return context.space_data.active_operator.bl_idname == "META_HUMAN_DNA_OT_import_dna" # type: ignore
    
    def _get_path_error(self, folder_path: str) -> str:
        if not folder_path:
            return ''

        if not os.path.exists(folder_path):
            return "Folder does not exist"
        if not os.path.isdir(folder_path):
            return "Path is not a folder"
        return ''

    def draw(self, context):
        if not self.layout:
            return
        
        operator = context.space_data.active_operator # type: ignore
        stem = Path(operator.filepath).stem.lower()
        body_file = Path(operator.filepath).parent / 'body.dna'
        layout = self.layout
        if stem == "head":
            row = layout.row()
            row.enabled = body_file.exists()
            row.prop(operator, "include_body")
            row = layout.row()
            row.enabled = operator.import_face_board
            row.prop(operator, "reuse_face_board")
        row = layout.row()
        row.label(text="Alternate Maps Folder:")
        row = layout.row()
        path_error = self._get_path_error(operator.alternate_maps_folder)
        
        if path_error:
            row.alert = True
        
        row.prop(operator, "alternate_maps_folder", text="")
        
        if path_error:
            row = layout.row()
            row.alert = True
            row.label(text=path_error, icon='ERROR')


class META_HUMAN_DNA_FILE_INFO_PT_panel(bpy.types.Panel):
    bl_space_type = 'FILE_BROWSER'
    bl_region_type = 'TOOL_PROPS'
    bl_label = "DNA File Info"
    bl_parent_id = "FILE_PT_operator"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        operator = context.space_data.active_operator # type: ignore
        is_dna_importer = context.space_data.active_operator.bl_idname == "META_HUMAN_DNA_OT_import_dna" # type: ignore
        if not hasattr(operator, 'filepath'):
            return False

        is_dna_file = operator.filepath.lower().endswith(".dna") and os.path.exists(operator.filepath)
        return is_dna_importer and is_dna_file

    def draw(self, context):
        if not self.layout:
            return
        
        operator = context.space_data.active_operator # type: ignore
        wm = bpy.context.window_manager.meta_human_dna.dna_info # type: ignore

        if operator.filepath.lower().endswith(".dna") and os.path.exists(operator.filepath):
            if not wm['_dna_reader'] or operator.filepath != wm['_previous_file_path']:
                wm['_previous_file_path'] = operator.filepath
                reader = get_dna_reader(
                    file_path=Path(operator.filepath),
                    file_format='binary',
                    data_layer='Descriptor'
                )
                if not reader:
                    return
                
                wm['_dna_reader'] = reader
        
            dna_reader = wm['_dna_reader']
            row = self.layout.row()
            row.label(text="Name: ")
            row.label(text=str(dna_reader.getName()))
            row = self.layout.row()
            row.label(text="Archetype: ")
            row.label(text=str(dna_reader.getArchetype().name))
            row = self.layout.row()
            row.label(text="Gender: ")
            row.label(text=str(dna_reader.getGender().name))
            row = self.layout.row()
            row.label(text="Age: ")
            row.label(text=str(dna_reader.getAge()))
            row = self.layout.row()
            row.label(text="LOD Count: ")
            row.label(text=str(dna_reader.getLODCount()))
            row = self.layout.row()
            row.label(text="Max LOD: ")
            row.label(text=str(dna_reader.getDBMaxLOD()))
            row = self.layout.row()
            row.label(text="Complexity: ")
            row.label(text=str(dna_reader.getDBComplexity()))
            row = self.layout.row()
            row.label(text="Database Name: ")
            row.label(text=str(dna_reader.getDBName()))
            row = self.layout.row()
            row.label(text="Translation Units: ")
            row.label(text=str(dna_reader.getTranslationUnit().name))
            row = self.layout.row()
            row.label(text="Rotation Units: ")
            row.label(text=str(dna_reader.getRotationUnit().name))
            row = self.layout.row()
            row.label(text="X Axis: ")
            row.label(text=str(dna_reader.getCoordinateSystem().xAxis.name))
            row = self.layout.row()
            row.label(text="Y Axis: ")
            row.label(text=str(dna_reader.getCoordinateSystem().yAxis.name))
            row = self.layout.row()
            row.label(text="Z Axis: ")
            row.label(text=str(dna_reader.getCoordinateSystem().zAxis.name))


class ImportAsset(ImportHelper):
    """
    This class subclasses the export helper to define a custom file browser
    """
    bl_idname = "meta_human_dna.import_dna"
    bl_options = {'UNDO', 'PRESET'}

    def draw(self, context):
        pass
