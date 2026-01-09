# standard library imports
import json
import logging
import math
import re
import sys

from abc import ABCMeta, abstractmethod
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# third party imports
import bpy

from mathutils import Matrix

# local imports
from .. import utilities
from ..constants import (
    ALTERNATE_HEAD_TEXTURE_FILE_NAMES,
    ALTERNATE_TEXTURE_FILE_EXTENSIONS,
    BODY_MATERIAL_NAME,
    BODY_MESH_SHADER_MAPPING,
    BODY_TEXTURE_LOGIC_NODE_NAME,
    BODY_TOPOLOGY_TEXTURE,
    BODY_TOPOLOGY_TEXTURE_FILE_PATH,
    DEFAULT_UV_TOLERANCE,
    FACE_BOARD_NAME,
    HEAD_MATERIAL_NAME,
    HEAD_MESH_SHADER_MAPPING,
    HEAD_TEXTURE_LOGIC_NODE_NAME,
    HEAD_TOPOLOGY_TEXTURE,
    HEAD_TOPOLOGY_TEXTURE_FILE_PATH,
    INVALID_NAME_CHARACTERS_REGEX,
    LEGACY_ALTERNATE_HEAD_TEXTURE_FILE_NAMES,
    MASKS_TEXTURE,
    MASKS_TEXTURE_FILE_PATH,
    MATERIALS_FILE_PATH,
    NUMBER_OF_HEAD_LODS,
    SCALE_FACTOR,
    UNREAL_EXPORTED_HEAD_MATERIAL_NAMES,
    UV_MAP_NAME,
    ComponentType,
    ToolInfo,
)
from ..dna_io import DNAImporter, get_dna_reader
from ..typing import *  # noqa: F403
from ..utilities import preserve_context


logger = logging.getLogger(__name__)


class MetaHumanComponentBase(metaclass=ABCMeta):
    def __init__(
        self,
        name: str | None = None,
        rig_instance: "RigInstance | None" = None,
        dna_file_path: Path | None = None,
        dna_import_properties: "MetahumanImportProperties | None" = None,
        component_type: ComponentType = "head",
    ):
        # make sure dna file path is a Path object
        dna_file_path = Path(bpy.path.abspath(str(dna_file_path))) if dna_file_path else None

        assert rig_instance or dna_file_path, (
            f"Either rig_instance or dna_file_path must be provided to {self.__class__.__name__}!"
        )

        self._linear_modifier = None
        self._angle_modifier = None
        self._component_type = component_type

        # determine the asset root folder based on the dna file path
        self.asset_root_folder = None
        if dna_file_path:
            self.asset_root_folder = dna_file_path.parent
        elif rig_instance:
            if rig_instance.head_dna_file_path:
                self.asset_root_folder = Path(bpy.path.abspath(str(rig_instance.head_dna_file_path))).parent
            elif rig_instance.body_dna_file_path:
                self.asset_root_folder = Path(bpy.path.abspath(str(rig_instance.body_dna_file_path))).parent

        self.rig_instance: "RigInstance" = rig_instance  # type: ignore[assignment]  # noqa: UP037
        self.addon_properties: "MetahumanAddonProperties" = bpy.context.preferences.addons[ToolInfo.NAME].preferences  # pyright: ignore[reportAttributeAccessIssue, reportOptionalMemberAccess]  # noqa: UP037
        self.window_manager_properties: "MetahumanWindowMangerProperties" = bpy.context.window_manager.meta_human_dna  # pyright: ignore[reportOptionalMemberAccess, reportAttributeAccessIssue]  # noqa: UP037
        self.scene_properties: "MetahumanSceneProperties" = bpy.context.scene.meta_human_dna  # pyright: ignore[reportOptionalMemberAccess, reportAttributeAccessIssue] # noqa: UP037
        self.dna_import_properties: "MetahumanImportProperties" = dna_import_properties  # noqa: UP037

        # if no rig_instance is provided, create a new one and supply the dna_file_path to it
        if not self.rig_instance and dna_file_path:
            name = self._get_name(name=name, dna_file_path=dna_file_path)
            # find a rig instance with the same name and use it if it exists
            for instance in self.scene_properties.rig_instance_list:
                if instance.name == name:
                    self.rig_instance = instance
                    break
            # otherwise create a new one
            else:
                self.rig_instance = self.scene_properties.rig_instance_list.add()
                self.rig_instance.name = name
                # set the active rig instance
                self.scene_properties.rig_instance_list_active_index = len(self.scene_properties.rig_instance_list) - 1

            if component_type == "head":
                self.rig_instance.head_dna_file_path = str(dna_file_path)
            elif component_type == "body":
                self.rig_instance.body_dna_file_path = str(dna_file_path)

        if (not self.dna_import_properties or not self.dna_import_properties.alternate_maps_folder) and dna_file_path:
            self.maps_folder = dna_file_path.parent / "Maps"
            if not self.maps_folder.exists():
                self.maps_folder = dna_file_path.parent / "maps"
        elif self.dna_import_properties and self.dna_import_properties.alternate_maps_folder:
            self.maps_folder = Path(self.dna_import_properties.alternate_maps_folder)

        file_format = "binary" if (dna_file_path or self.dna_file_path).suffix.lower() == ".dna" else "json"
        self.dna_reader = get_dna_reader(file_path=dna_file_path or self.dna_file_path, file_format=file_format)
        self.dna_importer = DNAImporter(
            instance=self.rig_instance,
            import_properties=self.dna_import_properties,
            linear_modifier=self.linear_modifier,
            reader=self.dna_reader,
            component_type=self.component_type,
            dna_file_path=dna_file_path,
        )

    @property
    def component_type(self) -> ComponentType:
        return self._component_type  # type: ignore[return-value]

    @property
    def linear_modifier(self) -> float:
        unit = self.dna_reader.getTranslationUnit()
        # is centimeter
        if unit.name.lower() == "cm":
            return 1 / SCALE_FACTOR
        # is meter
        if unit.name.lower() == "m":
            return 1
        return 1

    @property
    def angle_modifier(self) -> float:
        unit = self.dna_reader.getRotationUnit()
        # is degree
        if unit.name.lower() == "degrees":
            return 180 / math.pi
        # is radians
        if unit.name.lower() == "radians":
            return math.pi / 180
        return 1

    @property
    def name(self) -> str:
        return self.rig_instance.name

    @property
    def dna_file_path(self) -> Path:
        if self._component_type == "head":
            return Path(bpy.path.abspath(self.rig_instance.head_dna_file_path))
        if self._component_type == "body":
            return Path(bpy.path.abspath(self.rig_instance.body_dna_file_path))
        return None  # type: ignore[return-value]

    @property
    def face_board_object(self) -> bpy.types.Object | None:
        return self.rig_instance.face_board or bpy.data.objects.get(f"{self.name}_{FACE_BOARD_NAME}")

    @property
    def head_mesh_object(self) -> bpy.types.Object | None:
        return self.rig_instance.head_mesh or bpy.data.objects.get(f"{self.name}_head_lod0_mesh")

    @property
    def head_rig_object(self) -> bpy.types.Object | None:
        return self.rig_instance.head_rig or bpy.data.objects.get(f"{self.name}_head_rig")

    @property
    def body_mesh_object(self) -> bpy.types.Object | None:
        return self.rig_instance.body_mesh or bpy.data.objects.get(f"{self.name}_body_lod0_mesh")

    @property
    def body_rig_object(self) -> bpy.types.Object | None:
        return self.rig_instance.body_rig or bpy.data.objects.get(f"{self.name}_body_rig")

    @property
    def metadata(self) -> dict:
        if not self.asset_root_folder:
            return {}

        export_manifest = self.asset_root_folder / "ExportManifest.json"
        if export_manifest.exists():
            with export_manifest.open() as file:
                try:
                    return json.load(file)
                except json.JSONDecodeError:
                    logger.warning(f"Failed to load metadata from '{export_manifest}'")
                    return {}
        logger.warning("Could not load metahuman metadata file! Must not be in a metahuman directory.")
        return {}

    @property
    def thumbnail(self) -> Path | None:
        if not self.asset_root_folder:
            return None

        name = self.metadata.get("metaHumanName")
        if name:
            thumbnail_path = self.asset_root_folder / f"{name}.png"
            if thumbnail_path.exists():
                return thumbnail_path
        return None

    def _get_name(self, name: str | None = None, dna_file_path: Path | None = None) -> str:
        if name:
            return re.sub(INVALID_NAME_CHARACTERS_REGEX, "_", name)
        if dna_file_path:
            name = re.sub(INVALID_NAME_CHARACTERS_REGEX, "_", name or dna_file_path.stem.strip())
        return self.metadata.get("metaHumanName", name)

    def _get_lods_settings(self) -> list[tuple[int, bool]]:
        return [(i, getattr(self.dna_import_properties, f"import_lod{i}")) for i in range(NUMBER_OF_HEAD_LODS)]

    def _organize_viewport(self):
        if self.head_rig_object:
            for mesh_object in self.head_rig_object.children:
                if mesh_object.type == "MESH" and "lod0" not in mesh_object.name.lower():
                    mesh_object.hide_set(True)

            utilities.hide_empties()
            self.head_rig_object.hide_set(True)
            utilities.move_to_collection(
                scene_objects=[self.head_rig_object], collection_name=self.name, exclusively=True
            )

        if self.body_rig_object:
            for mesh_object in self.body_rig_object.children:
                if mesh_object.type == "MESH" and "lod0" not in mesh_object.name.lower():
                    mesh_object.hide_set(True)

            self.body_rig_object.hide_set(True)
            utilities.move_to_collection(
                scene_objects=[self.body_rig_object], collection_name=self.name, exclusively=True
            )

        # move the lod collections under the main asset collection
        asset_collection = bpy.data.collections.get(self.name)
        if asset_collection and bpy.context.scene:
            for lod_index in range(NUMBER_OF_HEAD_LODS):
                lod_collection = bpy.data.collections.get(f"{self.name}_lod{lod_index}")
                # move the lod collection to the asset collection
                if lod_collection and lod_collection not in asset_collection.children.values():
                    asset_collection.children.link(lod_collection)
                # unlink the lod collection from the scene collection
                if lod_collection in bpy.context.scene.collection.children.values():
                    bpy.context.scene.collection.children.unlink(lod_collection)

    def _get_alternate_image_path(self, image_file: Path, mapping: dict) -> Path:
        # Check for alternate image file names
        if not image_file.exists():
            # check for alternate file names with different extensions
            for extension in ALTERNATE_TEXTURE_FILE_EXTENSIONS:
                alternate_file_name = mapping.get(image_file.name, None)
                if alternate_file_name:
                    # check for lowercase extension
                    alternate_image_path = self.maps_folder / f"{alternate_file_name}{extension.lower()}"
                    if alternate_image_path.exists():
                        return alternate_image_path

                    # check for uppercase extension
                    alternate_image_path = self.maps_folder / f"{alternate_file_name}{extension.upper()}"
                    if alternate_image_path.exists():
                        return alternate_image_path
        return image_file

    def _set_image_textures(self, materials: list[bpy.types.Material]):  # noqa: PLR0912
        # set the combined mask image and topology image
        if self.component_type == "head":
            bpy.data.images[MASKS_TEXTURE].filepath = str(MASKS_TEXTURE_FILE_PATH)
            bpy.data.images[HEAD_TOPOLOGY_TEXTURE].filepath = str(HEAD_TOPOLOGY_TEXTURE_FILE_PATH)
        elif self.component_type == "body":
            bpy.data.images[BODY_TOPOLOGY_TEXTURE].filepath = str(BODY_TOPOLOGY_TEXTURE_FILE_PATH)

        for material in materials:
            if not material.node_tree:
                continue

            for node in material.node_tree.nodes:
                if node.type == "TEX_IMAGE" and node.image:  # type: ignore[attr-defined]
                    # get the image file name without the postfixes for duplicates i.e. .001
                    image_file = node.image.name  # type: ignore[attr-defined]
                    if image_file.count(".") > 1:
                        image_file = image_file.rsplit(".", 1)[0]

                    # update the texture paths to images in the maps folder
                    new_image_path = self.maps_folder / image_file

                    # Check for alternate image file names
                    new_image_path = self._get_alternate_image_path(
                        new_image_path, mapping=ALTERNATE_HEAD_TEXTURE_FILE_NAMES
                    )
                    if not new_image_path.exists():
                        new_image_path = self._get_alternate_image_path(
                            new_image_path, mapping=LEGACY_ALTERNATE_HEAD_TEXTURE_FILE_NAMES
                        )

                    if new_image_path.exists():
                        node.image = bpy.data.images.load(str(new_image_path))  # type: ignore[attr-defined]

                    # Set the color space for color and normal textures, taking into account alternate
                    # color management workflows like ACES
                    stem = new_image_path.stem.lower()
                    try:
                        if stem.endswith(("color_map", "color")) or "color_animated_" in stem:
                            try:
                                node.image.colorspace_settings.name = "sRGB"  # type: ignore[attr-defined]
                            except TypeError:
                                node.image.colorspace_settings.name = "sRGB - Display"  # type: ignore[attr-defined]

                        if stem.endswith(("normal_map", "normal")) or "normal_animated_" in stem:
                            try:
                                node.image.colorspace_settings.name = "Non-Color"  # type: ignore[attr-defined]
                            except TypeError:
                                node.image.colorspace_settings.name = "Raw"  # type: ignore[attr-defined]

                    except Exception as error:
                        logger.error(f"Failed to set colorspace for {node.image.name}: {error}")  # type: ignore[attr-defined]

        # remove any extra masks and topology images
        for image in bpy.data.images:
            if self.component_type == "head":
                image_names = [MASKS_TEXTURE, HEAD_TOPOLOGY_TEXTURE]
            if self.component_type == "body":
                image_names = [BODY_TOPOLOGY_TEXTURE]

            if image.name in image_names:
                continue
            if any(i in image.name for i in image_names if i != image.name):
                bpy.data.images.remove(image)

        # set the masks and topology textures for all node groups
        for node_group in bpy.data.node_groups:
            for node in node_group.nodes:
                if node.type == "TEX_IMAGE":
                    # set the masks and topology textures
                    if self.component_type == "head":
                        if node.label == MASKS_TEXTURE:
                            node.image = bpy.data.images[MASKS_TEXTURE]  # type: ignore[attr-defined]
                        if node.label == HEAD_TOPOLOGY_TEXTURE:
                            node.image = bpy.data.images[HEAD_TOPOLOGY_TEXTURE]  # type: ignore[attr-defined]
                    elif self.component_type == "body":
                        if node.label == BODY_TOPOLOGY_TEXTURE:
                            node.image = bpy.data.images[BODY_TOPOLOGY_TEXTURE]  # type: ignore[attr-defined]

    def _purge_existing_materials(self):
        shader_mapping = HEAD_MESH_SHADER_MAPPING if self.component_type == "head" else BODY_MESH_SHADER_MAPPING
        for material_name in shader_mapping.values():
            material = bpy.data.materials.get(f"{self.name}_{material_name}")
            if material:
                bpy.data.materials.remove(material)

        if self.component_type == "head":
            masks_image = bpy.data.images.get(MASKS_TEXTURE)
            if masks_image:
                bpy.data.images.remove(masks_image)

            head_topology_image = bpy.data.images.get(HEAD_TOPOLOGY_TEXTURE)
            if head_topology_image:
                bpy.data.images.remove(head_topology_image)

        elif self.component_type == "body":
            body_topology_image = bpy.data.images.get(BODY_TOPOLOGY_TEXTURE)
            if body_topology_image:
                bpy.data.images.remove(body_topology_image)

    def _mirror_bone_to(self, from_bone: bpy.types.PoseBone, to_bone_name: str) -> bpy.types.PoseBone | None:
        if self.head_rig_object and self.head_rig_object.pose:
            to_bone = self.head_rig_object.pose.bones.get(to_bone_name)
            location = from_bone.matrix.to_translation()
            location.x *= -1
            if to_bone:
                to_bone.matrix = Matrix.Translation(location)
                return to_bone

        logger.error(f"Could not find bone {to_bone_name}")
        return None

    def _delete_rig_instance(self):
        if (
            not self.rig_instance.head_mesh
            and not self.rig_instance.head_rig
            and not self.rig_instance.body_mesh
            and not self.rig_instance.body_rig
        ):
            my_list = self.scene_properties.rig_instance_list
            active_index = self.scene_properties.rig_instance_list_active_index
            my_list.remove(active_index)
            to_index = min(active_index, len(my_list) - 1)
            self.scene_properties.rig_instance_list_active_index = to_index

    def import_materials(self) -> list[bpy.types.Material] | None:  # noqa: PLR0912
        if self.dna_import_properties and not self.dna_import_properties.import_materials:
            return None

        from ..ui import callbacks

        sep = "\\"
        if sys.platform != "win32":
            sep = "/"

        logger.info(f"Importing materials for {self.name}")
        materials = []
        directory_path = f"{MATERIALS_FILE_PATH}{sep}Material{sep}"

        # Set the active collection to the scene collection. This ensures that the materials are appended
        # to the scene collection.
        bpy.context.view_layer.active_layer_collection = bpy.context.view_layer.layer_collection  # pyright: ignore[reportOptionalMemberAccess]

        # remove existing matching materials for this face to avoid duplicates being imported
        self._purge_existing_materials()

        shader_mapping = HEAD_MESH_SHADER_MAPPING if self.component_type == "head" else BODY_MESH_SHADER_MAPPING
        for key, material_name in shader_mapping.items():
            material = bpy.data.materials.get(material_name)
            if not material:
                # import the materials
                file_path = f"{MATERIALS_FILE_PATH}{sep}Material{sep}{material_name}"
                bpy.ops.wm.append(filepath=file_path, filename=material_name, directory=directory_path)

                # get the imported material
                material = bpy.data.materials.get(material_name)
                if not material:
                    material = bpy.data.materials.get(f"{self.name}_{material_name}")
                    # create the transparent materials if they don't exist
                    # These are for eyes and saliva
                    if not material:
                        material = utilities.create_new_material(
                            name=f"{self.name}_{material_name}", color=(1.0, 1.0, 1.0, 0.0), alpha=0.0
                        )

                # set the material on the head texture logic instance
                if material.name == HEAD_MATERIAL_NAME:
                    self.rig_instance.head_material = material
                    node = callbacks.get_head_texture_logic_node(material)
                    if node:
                        node.name = f"{self.name}_{HEAD_TEXTURE_LOGIC_NODE_NAME}"
                        node.label = f"{self.name}_{HEAD_TEXTURE_LOGIC_NODE_NAME}"
                        if node.node_tree:
                            node.node_tree.name = f"{self.name}_{HEAD_TEXTURE_LOGIC_NODE_NAME}"

                # set the material on the body texture logic instance
                if material.name == BODY_MATERIAL_NAME:
                    self.rig_instance.body_material = material
                    node = callbacks.get_body_texture_logic_node(material)
                    if node:
                        node.name = f"{self.name}_{BODY_TEXTURE_LOGIC_NODE_NAME}"
                        node.label = f"{self.name}_{BODY_TEXTURE_LOGIC_NODE_NAME}"
                        if node.node_tree:
                            node.node_tree.name = f"{self.name}_{BODY_TEXTURE_LOGIC_NODE_NAME}"

                # rename to match metahuman
                material.name = f"{self.name}_{material_name}"

                # set the uv maps on the material nodes
                if material.node_tree:
                    for node in material.node_tree.nodes:
                        if node.type == "UVMAP":
                            node.uv_map = UV_MAP_NAME  # type: ignore[attr-defined]
                for node_group in bpy.data.node_groups:
                    if node_group.name.startswith("Mask"):
                        for node in node_group.nodes:
                            if node.type == "UVMAP":
                                node.uv_map = UV_MAP_NAME  # type: ignore[attr-defined]
                    if node_group.name.lower().rsplit(".", 1)[0].endswith("_texture_logic"):
                        for node in node_group.nodes:
                            if node.type == "NORMAL_MAP":
                                node.uv_map = UV_MAP_NAME  # type: ignore[attr-defined]
                for mesh_object in bpy.data.objects:
                    if mesh_object.name.startswith(f"{self.name}_{key}"):
                        if mesh_object.data.materials:  # type: ignore[attr-defined]
                            mesh_object.data.materials[0] = material  # type: ignore[attr-defined]
                        else:
                            mesh_object.data.materials.append(material)  # type: ignore[attr-defined]

            if material:
                materials.append(material)

        # switch to material view
        utilities.set_viewport_shading("MATERIAL")

        # set the image textures to match
        self._set_image_textures(materials)
        # prefix the material image names with the metahuman name
        for material in materials:
            utilities.prefix_material_image_names(material=material, prefix=self.name)

        return materials

    def validate_conversion(
        self, mesh_object: bpy.types.Object, tolerance: float = DEFAULT_UV_TOLERANCE
    ) -> tuple[bool, str]:
        if not mesh_object.data or not isinstance(mesh_object.data, bpy.types.Mesh):
            return False, f'The mesh "{mesh_object.name}" has no data! Please provide a valid mesh object.'

        uv_layers = mesh_object.data.uv_layers
        if len(uv_layers) != 1:
            return (
                False,
                (
                    f'The mesh "{mesh_object.name}" must have exactly one UV layer! '
                    "Please ensure the mesh has a single UV map."
                ),
            )

        uv_layer = uv_layers.active
        if uv_layer is None:
            return (
                False,
                f'The mesh "{mesh_object.name}" has no active UV layer! Please ensure the mesh has an active UV map.',
            )

        # the first mesh index is always the head mesh or body mesh
        dna_u_values = utilities.reduce_close_floats(
            float_list=[float(i) for i in self.dna_reader.getVertexTextureCoordinateUs(0)], tolerance=tolerance
        )
        dna_v_values = utilities.reduce_close_floats(
            float_list=[float(i) for i in self.dna_reader.getVertexTextureCoordinateVs(0)], tolerance=tolerance
        )

        u_values, v_values = utilities.get_uv_values(mesh_object=mesh_object)
        u_values = utilities.reduce_close_floats(float_list=u_values, tolerance=tolerance)
        v_values = utilities.reduce_close_floats(float_list=v_values, tolerance=tolerance)

        if len(u_values) != len(dna_u_values) or len(v_values) != len(dna_v_values):
            uv_differences = abs(len(u_values) - len(dna_u_values)) + abs(len(v_values) - len(dna_v_values))
            return False, (
                f'UV validation failed! The mesh "{mesh_object.name}" has {uv_differences} UV values '
                "that do not match the layout in the template DNA file. Did you select the correct component? "
                'Right-click the "Convert Selected to DNA" button to see the online manual that shows '
                "the correct UV layout. Otherwise, disable the UV validation or adjust "
                "the tolerance value."
            )

        return True, "Validation successful!"

    def mirror_selected_bones(self) -> tuple[bool, str]:
        if self.head_rig_object:
            ignored_bone_names = utilities.get_ignored_bones_names(self.head_rig_object)
            selected_pose_bones = [
                pose_bone for pose_bone in bpy.context.selected_pose_bones if pose_bone.name not in ignored_bone_names
            ]

            # Validate that the selected bones are all on the same side
            left_side_count = 0
            right_side_count = 0
            for pose_bone in selected_pose_bones:
                if pose_bone.name.endswith("_l") or pose_bone.name.startswith("FACIAL_L"):
                    left_side_count += 1
                elif pose_bone.name.endswith("_r") or pose_bone.name.startswith("FACIAL_R"):
                    right_side_count += 1

            if left_side_count and right_side_count:
                return False, (
                    "Selected bones must all be on the same side! Your selection "
                    f"has {left_side_count} on the left and {right_side_count} on the right."
                )

            # Now mirror the bones
            for pose_bone in selected_pose_bones:
                mirrored_bone = None
                if pose_bone.name.endswith("_l"):
                    parts = pose_bone.name.rsplit("_l", 1)
                    bone_name = "_r".join(parts)
                    mirrored_bone = self._mirror_bone_to(from_bone=pose_bone, to_bone_name=bone_name)
                elif pose_bone.name.startswith("FACIAL_L"):
                    bone_name = pose_bone.name.replace("FACIAL_L", "FACIAL_R", 1)
                    mirrored_bone = self._mirror_bone_to(from_bone=pose_bone, to_bone_name=bone_name)
                elif pose_bone.name.endswith("_r"):
                    parts = pose_bone.name.rsplit("_r", 1)
                    bone_name = "_l".join(parts)
                    mirrored_bone = self._mirror_bone_to(from_bone=pose_bone, to_bone_name=bone_name)
                elif pose_bone.name.startswith("FACIAL_R"):
                    bone_name = pose_bone.name.replace("FACIAL_R", "FACIAL_L", 1)
                    mirrored_bone = self._mirror_bone_to(from_bone=pose_bone, to_bone_name=bone_name)

                if mirrored_bone:
                    mirrored_bone.bone.select = True

            # apply the pose changes
            utilities.apply_pose(self.head_rig_object, selected=True)

        return True, "Bones mirrored successfully!"

    @preserve_context
    def pre_convert_mesh_cleanup(self, mesh_object: bpy.types.Object) -> bpy.types.Object | None:
        if not mesh_object.data or not isinstance(mesh_object.data, bpy.types.Mesh):
            return None

        mesh_object_name = mesh_object.name
        mesh_name = mesh_object.data.name
        head_material_name = None
        for material in mesh_object.data.materials:
            if material and material.name in UNREAL_EXPORTED_HEAD_MATERIAL_NAMES:
                head_material_name = material.name

        # separate the head mesh by material if it has the a unreal head material
        if head_material_name:
            new_mesh_object = None
            utilities.switch_to_edit_mode(mesh_object)
            bpy.ops.mesh.select_all(action="SELECT")
            bpy.ops.mesh.separate(type="MATERIAL")
            for separated_mesh in bpy.context.selectable_objects:
                if head_material_name in [i.name for i in separated_mesh.data.materials]:  # type: ignore[attr-defined]
                    new_mesh_object = separated_mesh
                    new_mesh_object.name = mesh_object_name
                    new_mesh_object.data.name = mesh_name  # type: ignore[attr-defined]
                else:
                    bpy.data.objects.remove(separated_mesh, do_unlink=True)
            return new_mesh_object

        return mesh_object

    def write_export_manifest(self):
        """
        Writes the export manifest to a JSON file like MetaHuman Creator does for a DCC export.
        """
        from .. import bl_info

        file_path = Path(bpy.path.abspath(str(self.rig_instance.output_folder_path))) / "ExportManifest.json"
        with file_path.open("w") as file:
            json.dump(
                {
                    "metaHumanName": self.name,
                    "exportBlenderAddonVersion": ".".join([str(i) for i in bl_info.get("version", [])]),
                    "exportPluginVersion": self.metadata.get("exportPluginVersion", "1.0.0"),
                    "exportEngineVersion": self.metadata.get("exportEngineVersion", "5.6.0-0+UE5"),
                    "exportedAt": datetime.now(tz=UTC).strftime("%Y.%m.%d-%H.%M.%S"),
                },
                file,
                indent=4,
            )

    @preserve_context
    def constrain_head_to_body(self):
        if not self.rig_instance.head_rig or not self.rig_instance.body_rig:
            logger.warning("Head rig or body rig not found. Cannot constrain head rig to body rig.")
            return

        body_bone_names = [pose_bone.name for pose_bone in self.rig_instance.body_rig.pose.bones]

        # add copy transforms constraint to the head rig
        for pose_bone in self.rig_instance.head_rig.pose.bones:
            if pose_bone.name in body_bone_names:
                name = utilities.get_body_constraint_name(pose_bone.name)
                constraint = pose_bone.constraints.get(name)
                if not constraint:
                    constraint = pose_bone.constraints.new(type="COPY_TRANSFORMS")
                    constraint.name = name

                constraint.target = self.rig_instance.body_rig
                constraint.subtarget = pose_bone.name
                constraint.target_space = "WORLD"
                constraint.owner_space = "WORLD"

        self.rig_instance.head_to_body_constraint_influence = 1.0

    def set_head_to_body_constraint_influence(self, influence: float):
        if not self.rig_instance.head_rig:
            return

        for pose_bone in self.rig_instance.head_rig.pose.bones:
            constraint = pose_bone.constraints.get(utilities.get_body_constraint_name(pose_bone.name))
            if constraint:
                constraint.influence = influence

    @preserve_context
    def snap_head_bones_to_body_bones(self):
        if not self.rig_instance.head_rig or not self.rig_instance.body_rig:
            return

        self.rig_instance.head_rig.hide_set(False)
        self.rig_instance.body_rig.hide_set(False)
        # Switch to edit mode to access edit bones data
        utilities.switch_to_bone_edit_mode(self.rig_instance.head_rig, self.rig_instance.body_rig)

        # snap the head rig to the body rig in rest pose
        for head_edit_bone in self.rig_instance.head_rig.data.edit_bones:
            # get the corresponding body edit bone
            body_edit_bone = self.rig_instance.body_rig.data.edit_bones.get(head_edit_bone.name)
            if body_edit_bone:
                # Get world space matrices
                body_world_matrix = self.rig_instance.body_rig.matrix_world
                head_world_matrix = self.rig_instance.head_rig.matrix_world

                # Convert body bone positions to world space
                body_head_world = body_world_matrix @ body_edit_bone.head
                body_tail_world = body_world_matrix @ body_edit_bone.tail

                # Convert world positions to head rig local space
                head_edit_bone.head = head_world_matrix.inverted() @ body_head_world
                head_edit_bone.tail = head_world_matrix.inverted() @ body_tail_world
                head_edit_bone.roll = body_edit_bone.roll

    @abstractmethod
    def ingest(self, align: bool = True, constrain: bool = True) -> tuple[bool, str]:
        pass

    @abstractmethod
    def export(self):
        pass

    @abstractmethod
    def delete(self):
        pass

    @abstractmethod
    def create_topology_vertex_groups(self):
        pass

    @abstractmethod
    def select_vertex_group(self):
        pass

    @abstractmethod
    def select_bone_group(self):
        pass

    @abstractmethod
    def shrink_wrap_vertex_group(self):
        pass

    @abstractmethod
    def revert_bone_transforms_to_dna(self):
        pass

    @abstractmethod
    def import_action(self, file_path: Path, **kwargs: Any) -> bpy.types.Action | None:
        pass
