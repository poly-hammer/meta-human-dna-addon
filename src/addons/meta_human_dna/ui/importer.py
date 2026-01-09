# standard library imports
from pathlib import Path

# third party imports
import bpy

from bpy_extras.io_utils import ImportHelper  # type: ignore

# local imports
from ..constants import NUMBER_OF_HEAD_LODS
from ..dna_io import get_dna_reader
from ..typing import *  # noqa: F403


class META_HUMAN_DNA_FILE_DATA_PT_panel(bpy.types.Panel):
    bl_space_type = "FILE_BROWSER"
    bl_region_type = "TOOL_PROPS"
    bl_label = "File Data"
    bl_parent_id = "FILE_PT_operator"
    bl_options = {"HEADER_LAYOUT_EXPAND"}

    @classmethod
    def poll(cls, context: "Context") -> bool:
        return context.space_data.active_operator.bl_idname == "META_HUMAN_DNA_OT_import_dna"  # type: ignore[attr-defined]

    def draw(self, context: "Context"):
        if not self.layout:
            return

        operator = context.space_data.active_operator  # type: ignore
        stem = Path(operator.filepath).stem.lower()
        layout = self.layout
        row = layout.row()
        row.prop(operator, "import_mesh")
        row = layout.row()
        # TODO: Fix implementation normals import
        # row.prop(operator, "import_normals")  # noqa: ERA001
        row = layout.row()
        row.prop(operator, "import_bones")
        # row = layout.row()  # noqa: ERA001
        # TODO: See if we what to import shape keys during initial import
        # row.prop(operator, "import_shape_keys")  # noqa: ERA001
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
    bl_space_type = "FILE_BROWSER"
    bl_region_type = "TOOL_PROPS"
    bl_label = "Lods"
    bl_parent_id = "FILE_PT_operator"
    bl_options = {"HEADER_LAYOUT_EXPAND"}

    @classmethod
    def poll(cls, context: "Context") -> bool:
        return context.space_data.active_operator.bl_idname == "META_HUMAN_DNA_OT_import_dna"  # type: ignore[attr-defined]

    def draw(self, context: "Context"):
        if not self.layout:
            return

        operator = context.space_data.active_operator  # type: ignore[attr-defined]
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
    bl_space_type = "FILE_BROWSER"
    bl_region_type = "TOOL_PROPS"
    bl_label = "Extras"
    bl_parent_id = "FILE_PT_operator"
    bl_options = {"HEADER_LAYOUT_EXPAND"}

    @classmethod
    def poll(cls, context: "Context") -> bool:
        return context.space_data.active_operator.bl_idname == "META_HUMAN_DNA_OT_import_dna"  # type: ignore[attr-defined]

    def _get_path_error(self, folder_path: str) -> str:
        if not folder_path:
            return ""

        path = Path(folder_path)
        if not path.exists():
            return "Folder does not exist"
        if not path.is_dir():
            return "Path is not a folder"
        return ""

    def draw(self, context: "Context"):
        if not self.layout:
            return

        operator = context.space_data.active_operator  # type: ignore[attr-defined]
        stem = Path(operator.filepath).stem.lower()
        body_file = Path(operator.filepath).parent / "body.dna"
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
            row.label(text=path_error, icon="ERROR")


class META_HUMAN_DNA_FILE_INFO_PT_panel(bpy.types.Panel):
    bl_space_type = "FILE_BROWSER"
    bl_region_type = "TOOL_PROPS"
    bl_label = "DNA File Info"
    bl_parent_id = "FILE_PT_operator"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context: "Context") -> bool:
        operator = context.space_data.active_operator  # type: ignore[attr-defined]
        is_dna_importer = context.space_data.active_operator.bl_idname == "META_HUMAN_DNA_OT_import_dna"  # type: ignore[attr-defined]
        if not hasattr(operator, "filepath"):
            return False

        is_dna_file = operator.filepath.lower().endswith(".dna") and Path(operator.filepath).exists()
        return is_dna_importer and is_dna_file

    def draw(self, context: "Context"):
        if not self.layout:
            return

        operator = context.space_data.active_operator  # type: ignore[attr-defined]
        wm = context.window_manager.meta_human_dna.dna_info

        if operator.filepath.lower().endswith(".dna") and Path(operator.filepath).exists():
            if not wm["_dna_reader"] or operator.filepath != wm["_previous_file_path"]:
                wm["_previous_file_path"] = operator.filepath
                reader = get_dna_reader(
                    file_path=Path(operator.filepath), file_format="binary", data_layer="Descriptor"
                )
                if not reader:
                    return

                wm["_dna_reader"] = reader

            dna_reader = wm["_dna_reader"]
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
    This class subclasses the import helper to define a custom file browser
    """

    bl_options = {"UNDO", "PRESET"}

    def draw(self, context: "Context"):
        pass

    @property
    def settings_title(self) -> str:
        return ""


class ImportAnimation(ImportAsset):
    def draw(self, context: "Context"):
        layout = getattr(self, "layout", None)
        if not layout:
            return

        operator = context.space_data.active_operator  # type: ignore[attr-defined]
        if not operator:
            return

        row = layout.row()
        row.label(text=self.settings_title)
        row = layout.row()
        row.prop(operator, "round_sub_frames")
        row = layout.row()
        row.prop(operator, "match_frame_rate")
        row = layout.row()
        row.prop(operator, "prefix_instance_name")
        row = layout.row()
        row.prop(operator, "prefix_component_name")


class LinkAppendMetaHumanImportHelper(ImportHelper):
    """
    This class subclasses the import helper to define a custom file browser
    """

    bl_options = {"UNDO"}

    def refresh_meta_human_list(self, operator: bpy.types.Operator):
        self.meta_human_list.clear()  # type: ignore[attr-defined]
        scene_properties: "MetahumanSceneProperties" = bpy.context.scene.meta_human_dna  # type: ignore[attr-defined]  # noqa: UP037
        rig_instance_names = [i.name for i in scene_properties.rig_instance_list]

        with bpy.data.libraries.load(operator.filepath) as (data_from, _data_to):  # type: ignore[arg-type]
            object_names = list(data_from.objects)

            for name in data_from.collections:
                if (f"{name}_head_lod0_mesh" in object_names and f"{name}_head_rig" in object_names) or (
                    f"{name}_body_lod0_mesh" in object_names and f"{name}_body_rig" in object_names
                ):
                    item = operator.meta_human_list.add()  # type: ignore[attr-defined]
                    item.name = name
                    item.include = False
                    # disable items that would cause name conflicts with existing rig instances
                    if name in rig_instance_names:
                        item.enabled = False
                    else:
                        item.enabled = True

        # save the current filepath to detect changes
        operator.previous_file_path = operator.filepath  # type: ignore[attr-defined]

    def draw(self, context: "Context"):
        layout = self.layout  # type: ignore
        if not layout:
            return

        operator = context.space_data.active_operator  # type: ignore[attr-defined]

        row = layout.row()
        row.prop(operator, "operation_type", expand=True)
        file_path = Path(bpy.path.abspath(operator.filepath))

        if not operator.filepath or not file_path.is_file():
            row = layout.row()
            row.alert = True
            row.label(text="Select a .blend file to see MetaHuman(s)")
            return

        if Path(bpy.data.filepath) == file_path:
            row = layout.row()
            row.alert = True
            row.label(text="Select different .blend than current")
            return

        if not file_path.exists() or not file_path.is_file() or file_path.suffix.lower() != ".blend":
            return

        row = layout.row()
        row.label(text=f"Choose MetaHuman(s) to {operator.operation_type.lower()}:")

        # only refresh the list if the selected file path has changed
        if operator.previous_file_path != operator.filepath:
            self.refresh_meta_human_list(operator)

        for item in operator.meta_human_list:
            row = layout.row()
            icon = "NONE"
            text = item.name
            if not item.enabled:
                row.enabled = False
                row.alert = True
                icon = "ERROR"
                text = f"{item.name} (Exists in current scene)"

            row.prop(item, "include", text="")
            row.label(text=text, icon=icon)
