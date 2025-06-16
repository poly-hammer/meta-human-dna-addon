import re
import sys
import bpy
import json
import math
import queue
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Literal
from mathutils import Vector, Matrix
from .dna_io import (
    get_dna_reader, 
    create_shape_key,
    DNAImporter,
    DNAExporter
)
from . import utilities
from .utilities import preserve_context
from .constants import (
    ToolInfo,
    HEAD_MATERIAL_NAME,
    MESH_SHADER_MAPPING,
    MASKS_TEXTURE_FILE_PATH,
    TOPOLOGY_TEXTURE_FILE_PATH,
    MATERIALS_FILE_PATH,
    FACE_BOARD_FILE_PATH,
    FACE_BOARD_NAME,
    MASKS_TEXTURE,
    TOPOLOGY_TEXTURE,
    NUMBER_OF_FACE_LODS,
    FACE_GUI_EMPTIES, 
    TOPOLOGY_VERTEX_GROUPS_FILE_PATH,
    SCALE_FACTOR,
    INVALID_NAME_CHARACTERS_REGEX,
    TEXTURE_LOGIC_NODE_NAME,
    UV_MAP_NAME,
    TOPO_GROUP_PREFIX,
    EXTRA_BONES,
    ALTERNATE_HEAD_TEXTURE_FILE_NAMES,
    LEGACY_ALTERNATE_HEAD_TEXTURE_FILE_NAMES,
    ALTERNATE_TEXTURE_FILE_EXTENSIONS,
    UNREAL_EXPORTED_HEAD_MATERIAL_NAMES,
    DEFAULT_UV_TOLERANCE
)

if TYPE_CHECKING:
    from .rig_logic import RigLogicInstance
    from .properties import (
        MetahumanDnaImportProperties,
        MetahumanSceneProperties, 
        MetahumanWindowMangerProperties
    )


logger = logging.getLogger(__name__)


class MetahumanFace:
    def __init__(
            self, 
            name: str | None = None,
            rig_logic_instance: 'RigLogicInstance | None' = None,
            dna_file_path: Path | None = None,
            dna_import_properties: 'MetahumanDnaImportProperties | None' = None
        ):
        # make sure dna file path is a Path object
        dna_file_path = Path(dna_file_path) if dna_file_path else None

        assert rig_logic_instance or dna_file_path, \
            f"Either rig_logic_instance or dna_file_path must be provided to {self.__class__.__name__}!"

        self._linear_modifier = None
        self._angle_modifier = None

        self.asset_root_folder = None
        if dna_file_path:    
            self.asset_root_folder = dna_file_path.parent
        self.rig_logic_instance: 'RigLogicInstance' = rig_logic_instance # type: ignore
        self.addon_properties = bpy.context.preferences.addons[ToolInfo.NAME].preferences # type: ignore
        self.window_manager_properties: MetahumanWindowMangerProperties = bpy.context.window_manager.meta_human_dna # type: ignore
        self.scene_properties: MetahumanSceneProperties = bpy.context.scene.meta_human_dna # type: ignore
        self.dna_import_properties: MetahumanDnaImportProperties = dna_import_properties # type: ignore

        # if no rig_logic_instance is provided, create a new one and supply the dna_file_path to it
        if not self.rig_logic_instance and dna_file_path:
            name = self._get_name(name=name, dna_file_path=dna_file_path)
            # find a rig logic instance with the same name and use it if it exists
            for instance in self.scene_properties.rig_logic_instance_list:
                if instance.name == name:
                    self.rig_logic_instance = instance
                    break
            # otherwise create a new one
            else:
                self.rig_logic_instance = self.scene_properties.rig_logic_instance_list.add()
                self.rig_logic_instance.name = name
                # set the active rig logic instance
                self.scene_properties.rig_logic_instance_list_active_index = len(self.scene_properties.rig_logic_instance_list) - 1

            self.rig_logic_instance.dna_file_path = str(dna_file_path)

        if not self.dna_import_properties or not self.dna_import_properties.alternate_maps_folder:
            self.maps_folder = self.dna_file_path.parent / 'Maps'
            if not self.maps_folder.exists():
                self.maps_folder = self.dna_file_path.parent / 'maps'
        else:
            self.maps_folder = Path(self.dna_import_properties.alternate_maps_folder)

        file_format = 'binary' if self.dna_file_path.suffix.lower() == ".dna" else 'json'
        self.dna_reader = get_dna_reader(
            file_path=self.dna_file_path,
            file_format=file_format
        )
        self.dna_importer = DNAImporter(
            instance=self.rig_logic_instance, 
            import_properties=self.dna_import_properties,
            linear_modifier=self.linear_modifier,
            reader=self.dna_reader
        )
    
    @property
    def linear_modifier(self) -> float:
        unit = self.dna_reader.getTranslationUnit()
        # is centimeter
        if unit.name.lower() == 'cm':
            return 1/SCALE_FACTOR
        # is meter
        elif unit.name.lower() == 'm':
            return 1
        return 1
    
    @property
    def angle_modifier(self) -> float:
        unit = self.dna_reader.getRotationUnit()
        # is degree
        if unit.name.lower() == 'degrees':
            return 180 / math.pi
        # is radians
        elif unit.name.lower() == 'radians':
            return math.pi / 180
        return 1
    
    @property
    def name(self) -> str:
        return self.rig_logic_instance.name

    @property
    def dna_file_path(self) -> Path:
        return Path(self.rig_logic_instance.dna_file_path)

    @property
    def face_board_object(self) -> bpy.types.Object | None:
        return self.rig_logic_instance.face_board or bpy.data.objects.get(f'{self.name}_{FACE_BOARD_NAME}')
    
    @property
    def head_mesh_object(self) -> bpy.types.Object | None:
        return self.rig_logic_instance.head_mesh or bpy.data.objects.get(f'{self.name}_head_lod0_mesh')
    
    @property
    def head_rig_object(self) -> bpy.types.Object | None:
        return self.rig_logic_instance.head_rig or bpy.data.objects.get(f'{self.name}_rig')

    @property
    def metadata(self) -> dict:
        if not self.asset_root_folder:
            return {}
        
        export_manifest = self.asset_root_folder / 'ExportManifest.json'
        if export_manifest.exists():
            with open(export_manifest, 'r') as file:
                return json.load(file)            
        logger.warning('Could not load metahuman metadata file! Must not be in a metahuman directory.')
        return {}

    @property
    def thumbnail(self) -> Path | None:
        if not self.asset_root_folder:
            return None
        
        name = self.metadata.get('metaHumanName')
        if name:
            thumbnail_path = self.asset_root_folder / f'{name}.png'
            if thumbnail_path.exists():
                return thumbnail_path
            
    def _get_name(
            self, name: str | None = None, 
            dna_file_path: Path | None = None
        ) -> str:
        if name:
            return re.sub(INVALID_NAME_CHARACTERS_REGEX, "_",  name)
        elif dna_file_path:
            name = re.sub(INVALID_NAME_CHARACTERS_REGEX, "_",  name or dna_file_path.stem.strip())
        return self.metadata.get('metaHumanName', name)

    def _get_lods_settings(self):
        return [(i, getattr(self.dna_import_properties, f'import_lod{i}')) for i in range(NUMBER_OF_FACE_LODS)]

    def _organize_viewport(self):
        if self.head_mesh_object and self.head_rig_object:
            for mesh_object in self.head_rig_object.children:
                if mesh_object.type == 'MESH' and 'lod0' not in mesh_object.name:
                    mesh_object.hide_set(True)

            utilities.hide_empties()        
            self.head_rig_object.hide_set(True)

    def _get_alternate_image_path(
            self, 
            image_file: Path, 
            mapping: dict
        ) -> Path:
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

    def _set_image_textures(self, materials: list[bpy.types.Material]):
        # set the combined mask image and topology image
        bpy.data.images[MASKS_TEXTURE].filepath = str(MASKS_TEXTURE_FILE_PATH)
        bpy.data.images[TOPOLOGY_TEXTURE].filepath = str(TOPOLOGY_TEXTURE_FILE_PATH)

        for material in materials:
            if not material.node_tree:
                continue

            for node in material.node_tree.nodes: # type: ignore
                if node.type == 'TEX_IMAGE' and node.image: # type: ignore
                    # get the image file name without the postfixes for duplicates i.e. .001
                    image_file = node.image.name # type: ignore
                    if image_file.count('.') > 1:
                        image_file = image_file.rsplit('.', 1)[0]

                    # update the texture paths to images in the maps folder
                    new_image_path = self.maps_folder / image_file

                    # Check for alternate image file names
                    new_image_path = self._get_alternate_image_path(
                        new_image_path,
                        mapping=ALTERNATE_HEAD_TEXTURE_FILE_NAMES
                    )
                    if not new_image_path.exists():
                        new_image_path = self._get_alternate_image_path(
                            new_image_path,
                            mapping=LEGACY_ALTERNATE_HEAD_TEXTURE_FILE_NAMES
                        )

                    if new_image_path.exists():
                        node.image = bpy.data.images.load(str(new_image_path)) # type: ignore

                        # reloading images defaults the color space, so reset normal map to Non-Color
                        stem = new_image_path.stem.lower()
                        if stem.endswith('normal_map') or stem.endswith('normal') or '_normal_animated_' in stem:
                            node.image.colorspace_settings.name = 'Non-Color' # type: ignore

        # remove any extra masks and topology images
        for image in bpy.data.images:
            if image.name in [MASKS_TEXTURE, TOPOLOGY_TEXTURE]:
                continue
            if any(i in image.name for i in [MASKS_TEXTURE, TOPOLOGY_TEXTURE]):
                bpy.data.images.remove(image)

        # set the masks and topology textures for all node groups
        for node_group in bpy.data.node_groups:
            for node in node_group.nodes:
                if node.type == 'TEX_IMAGE' and node.image: # type: ignore
                    # set the masks and topology textures
                    if node.image.name == MASKS_TEXTURE: # type: ignore
                        node.image = bpy.data.images[MASKS_TEXTURE] # type: ignore
                    if node.image.name == TOPOLOGY_TEXTURE: # type: ignore
                        node.image = bpy.data.images[TOPOLOGY_TEXTURE] # type: ignore

    def _purge_existing_materials(self):
        for material_name in MESH_SHADER_MAPPING.values():
            material = bpy.data.materials.get(f'{self.name}_{material_name}')
            if material:
                bpy.data.materials.remove(material)

        masks_image = bpy.data.images.get(MASKS_TEXTURE)
        if masks_image:
            bpy.data.images.remove(masks_image)
        
        topology_image = bpy.data.images.get(TOPOLOGY_TEXTURE)
        if topology_image:
            bpy.data.images.remove(topology_image)


    def import_materials(self):
        if self.dna_import_properties and not self.dna_import_properties.import_materials:
            return

        from .ui import callbacks
        sep = '\\'
        if sys.platform != 'win32':
            sep = '/'
        
        logger.info(f'Importing materials for {self.name}')
        materials = []
        directory_path = f'{MATERIALS_FILE_PATH}{sep}Material{sep}'

        # Set the active collection to the scene collection. This ensures that the materials are appended to the scene collection
        bpy.context.view_layer.active_layer_collection = bpy.context.view_layer.layer_collection # type: ignore

        # remove existing matching materials for this face to avoid duplicates being imported
        self._purge_existing_materials()

        for key, material_name in MESH_SHADER_MAPPING.items():
            material = bpy.data.materials.get(material_name)
            if not material:
                # import the materials
                file_path = f'{MATERIALS_FILE_PATH}{sep}Material{sep}{material_name}'
                bpy.ops.wm.append(
                    filepath=file_path,
                    filename=material_name,
                    directory=directory_path
                )

                # get the imported material
                material = bpy.data.materials.get(material_name)
                if not material:
                    material = bpy.data.materials.get(f'{self.name}_{material_name}')
                    # create the transparent materials if they don't exist
                    # These are for eyes and saliva
                    if not material:
                        material = utilities.create_new_material(
                            name=f'{self.name}_{material_name}', 
                            color=(1.0, 1.0, 1.0, 0.0),
                            alpha=0.0
                        )

                # set the material on the rig logic instance
                if material.name == HEAD_MATERIAL_NAME:
                    self.rig_logic_instance.material = material
                    node = callbacks.get_texture_logic_node(material)
                    if node:
                        node.name = f'{self.name}_{TEXTURE_LOGIC_NODE_NAME}'
                        node.label = f'{self.name}_{TEXTURE_LOGIC_NODE_NAME}'
                        if node.node_tree:
                            node.node_tree.name = f'{self.name}_{TEXTURE_LOGIC_NODE_NAME}'

                # rename to match metahuman
                material.name = f'{self.name}_{material_name}' # type: ignore

                # set the uv maps on the material nodes
                for node in material.node_tree.nodes: # type: ignore
                    if node.type == 'UVMAP':
                        node.uv_map = UV_MAP_NAME # type: ignore
                    elif node.type == 'NORMAL_MAP':
                        node.uv_map = UV_MAP_NAME # type: ignore
                for node_group in bpy.data.node_groups:
                    if node_group.name.startswith('Mask'):
                        for node in node_group.nodes:
                            if node.type == 'UVMAP':
                                node.uv_map = UV_MAP_NAME # type: ignore

                for mesh_object in bpy.data.objects:
                    if mesh_object.name.startswith(f'{self.name}_{key}'):
                        if mesh_object.data.materials: # type: ignore
                            mesh_object.data.materials[0] = material # type: ignore
                        else:
                            mesh_object.data.materials.append(material) # type: ignore

            if material:
                materials.append(material)

        # switch to material view
        utilities.set_viewport_shading('MATERIAL')

        # set the image textures to match
        self._set_image_textures(materials)
        # prefix the material image names with the metahuman name
        for material in materials:
            utilities.prefix_material_image_names(
                material=material, 
                prefix=self.name
            )

        return materials
    
    @staticmethod
    def _hide_face_board_widgets():
        # unlink from scene and make fake users so they are not deleted by garbage collection
        for empty_name in FACE_GUI_EMPTIES:
            empty = bpy.data.objects.get(empty_name)
            if empty:
                for collection in [
                    bpy.data.collections.get('Collection'),
                    bpy.context.scene.collection # type: ignore
                ]:
                    if not collection:
                        continue

                    for child in empty.children_recursive:
                        if child in collection.objects.values(): # type: ignore
                            collection.objects.unlink(child) # type: ignore
                        child.use_fake_user = True
                    
                    if empty in collection.objects.values(): # type: ignore
                        collection.objects.unlink(empty) # type: ignore
                    empty.use_fake_user = True
                
    def _purge_face_board_components(self):
        with bpy.data.libraries.load(str(FACE_BOARD_FILE_PATH)) as (data_from, data_to):
            if data_from.objects:
                for name in data_from.objects:
                    scene_object = bpy.data.objects.get(name)
                    if scene_object:
                        bpy.data.objects.remove(scene_object, do_unlink=True)

    def _import_face_board(self) -> bpy.types.Object | None:
        if not self.dna_import_properties.import_face_board:
            return

        sep = '\\'
        if sys.platform != 'win32':
            sep = '/'

        # delete all face board objects in the scene that already exist
        self._purge_face_board_components()

        bpy.ops.wm.append(
            filepath=f'{FACE_BOARD_FILE_PATH}{sep}Object{sep}{FACE_BOARD_NAME}',
            filename=FACE_BOARD_NAME,
            directory=f'{FACE_BOARD_FILE_PATH}{sep}Object{sep}'
        )
        face_board_object = bpy.data.objects[FACE_BOARD_NAME]
        # rename to be prefixed with a unique name
        face_board_object.name = f'{self.name}_{FACE_BOARD_NAME}' # type: ignore

        if self.head_mesh_object:
            head_mesh_center = utilities.get_bounding_box_center(self.head_mesh_object)
            face_gui_center = utilities.get_bounding_box_center(face_board_object)
            head_mesh_right_x = utilities.get_bounding_box_right_x(self.head_mesh_object)
            face_gui_left_x = utilities.get_bounding_box_left_x(face_board_object)

            # align the face gui object to the head mesh vertically
            translation_vector = head_mesh_center - face_gui_center
            face_board_object.location.z += translation_vector.z

            # offset the face gui object to the left of the head mesh
            x_value = head_mesh_right_x - face_gui_left_x
            face_board_object.location.x = x_value

            # apply the translation to the face gui object
            utilities.apply_transforms(face_board_object, location=True) # type: ignore

        # parent rig to face gui
        if self.head_rig_object:
            self.head_rig_object.parent = face_board_object

        # hide all face board elements
        self._hide_face_board_widgets()

        face_board_object.data.relation_line_position = 'HEAD' # type: ignore
        return face_board_object

    def import_action(self, file_path: Path):
        file_path = Path(file_path)
        if not self.face_board_object:
            return
        
        if file_path.suffix.lower() == '.json':
            utilities.import_action_from_json(file_path, self.face_board_object)    
        elif file_path.suffix.lower() == '.fbx':
            utilities.import_action_from_fbx(file_path, self.face_board_object)

    def ingest(self) -> tuple[bool, str]:        
        valid, message = self.dna_importer.run()
        self.rig_logic_instance.head_rig = self.dna_importer.rig_object

        self._organize_viewport()
        self.import_materials()
        # import the face board if one does not already exist in the scene
        if not any(i.face_board for i in self.scene_properties.rig_logic_instance_list):
            face_board_object = self._import_face_board()
        else:
            face_board_object = next(i.face_board for i in self.scene_properties.rig_logic_instance_list if i.face_board)

        # Note that the topology vertex groups are only valid for the default metahuman head mesh with 24408 vertices
        if len(self.dna_reader.getVertexLayoutPositionIndices(0)) == 24408:
            self._create_topology_vertex_groups()

        # set the references on the rig logic instance
        self.rig_logic_instance.head_mesh = self.head_mesh_object
        self.rig_logic_instance.head_rig = self.head_rig_object
        self.rig_logic_instance.face_board = face_board_object

        if self.head_rig_object and self.head_mesh_object:
            utilities.set_bone_collections(
                mesh_object=self.head_mesh_object,
                rig_object=self.head_rig_object,
            )

            # if this isn't the first rig, move it to the right of the last head mesh
            if len(self.scene_properties.rig_logic_instance_list) > 1:
                last_instance = self.scene_properties.rig_logic_instance_list[-2] # type: ignore
                if last_instance.head_mesh:
                    self.head_rig_object.location.x = utilities.get_bounding_box_right_x(self.head_rig_object) - 0.5

            # then parent the rig to the face board
            self.head_rig_object.parent = face_board_object

        # focus the view on head object
        if self.rig_logic_instance.head_mesh:
            utilities.select_only(self.rig_logic_instance.head_mesh)
            utilities.focus_on_selected()

        # collapse the outliner
        utilities.toggle_expand_in_outliner()

        # switch to pose mode on the face gui object
        if face_board_object:
            bpy.context.view_layer.objects.active = face_board_object # type: ignore
            utilities.switch_to_pose_mode(face_board_object) # type: ignore
        
        return valid, message

    @preserve_context
    def convert(self, mesh_object: bpy.types.Object):
        from .bindings import meta_human_dna_core
        if self.head_mesh_object and self.face_board_object and self.head_rig_object:
            target_center = utilities.get_bounding_box_center(mesh_object)
            head_center = utilities.get_bounding_box_center(self.head_mesh_object)
            delta = target_center - head_center

            # translate the head rig and the face board
            self.face_board_object.location += delta

            # must be unhidden to switch to edit bone mode
            self.head_rig_object.hide_set(False) # type: ignore
            utilities.switch_to_bone_edit_mode(self.head_rig_object)
            # adjust the root bone so the root bone is still at zero
            root_bone = self.head_rig_object.data.edit_bones.get('root') # type: ignore
            if root_bone:
                root_bone.head.z -= delta.z
                root_bone.tail.z -= delta.z

            # adjust the head rig origin to zero
            utilities.switch_to_object_mode() # type: ignore
            # select all the objects and set their origins to the 3d cursor
            utilities.deselect_all()
            for item in self.rig_logic_instance.output_item_list:
                if item.scene_object:
                    item.scene_object.hide_set(False)
                    item.scene_object.select_set(True)
                    bpy.context.view_layer.objects.active = item.scene_object # type: ignore
            self.face_board_object.select_set(True)

            bpy.context.scene.cursor.location = Vector((target_center.x, 0, 0)) # type: ignore
            bpy.ops.object.origin_set(type='ORIGIN_CURSOR')

            from_bmesh_object = DNAExporter.get_bmesh(mesh_object=mesh_object, rotation=0)
            from_data = {
                'name': mesh_object.name,
                'uv_data': DNAExporter.get_mesh_vertex_uvs(from_bmesh_object),
                'vertex_data': DNAExporter.get_mesh_vertex_positions(from_bmesh_object)
            }
            to_bmesh_object = DNAExporter.get_bmesh(mesh_object=mesh_object, rotation=0)
            to_data = {
                'name': self.head_mesh_object.name,
                'uv_data': DNAExporter.get_mesh_vertex_uvs(to_bmesh_object),
                'vertex_data': DNAExporter.get_mesh_vertex_positions(to_bmesh_object),
                'dna_reader': self.dna_reader
            }

            from_bmesh_object.free()
            to_bmesh_object.free()

            vertex_positions = meta_human_dna_core.calculate_dna_mesh_vertex_positions(from_data, to_data)
            self.head_mesh_object.data.vertices.foreach_set("co", vertex_positions.ravel()) # type: ignore
            self.head_mesh_object.data.update() # type: ignore

            utilities.auto_fit_bones(
                armature_object=self.head_rig_object,
                mesh_object=self.head_mesh_object,
                dna_reader=self.dna_reader,
                only_selected=False
            )

    @preserve_context
    def pre_convert_mesh_cleanup(self, mesh_object: bpy.types.Object) -> bpy.types.Object | None:
        mesh_object_name = mesh_object.name
        mesh_name = mesh_object.data.name # type: ignore
        head_material_name = None
        for material in mesh_object.data.materials: # type: ignore
            if material.name in UNREAL_EXPORTED_HEAD_MATERIAL_NAMES: # type: ignore
                head_material_name = material.name # type: ignore

        # separate the head mesh by material if it has the a unreal head material
        if head_material_name:
            new_mesh_object = None
            utilities.switch_to_edit_mode(mesh_object)
            bpy.ops.mesh.select_all(action='SELECT')
            bpy.ops.mesh.separate(type='MATERIAL')
            for separated_mesh in bpy.context.selectable_objects: # type: ignore
                if head_material_name in [i.name for i in separated_mesh.data.materials]: # type: ignore
                    new_mesh_object = separated_mesh
                    new_mesh_object.name = mesh_object_name
                    new_mesh_object.data.name = mesh_name # type: ignore
                else:
                    bpy.data.objects.remove(separated_mesh, do_unlink=True)
            return new_mesh_object
        
        return mesh_object        

    def validate_conversion(
            self, 
            mesh_object: bpy.types.Object, 
            tolerance: float = DEFAULT_UV_TOLERANCE
        ) -> tuple[bool, str]:
        if not mesh_object.data:
            return False, f'The mesh "{mesh_object.name}" has no data! Please provide a valid mesh object.'
        
        uv_layers = mesh_object.data.uv_layers # type: ignore
        if not len(uv_layers) == 1: # type: ignore
            return False, f'The mesh "{mesh_object.name}" must have exactly one UV layer! Please ensure the mesh has a single UV map.'
        
        uv_layer = uv_layers.active
        if uv_layer is None:
            return False, f'The mesh "{mesh_object.name}" has no active UV layer! Please ensure the mesh has an active UV map.'

        # the first mesh index is always the head mesh or body mesh
        dna_u_values = utilities.reduce_close_floats(float_list=[float(i) for i in self.dna_reader.getVertexTextureCoordinateUs(0)], tolerance=tolerance)
        dna_v_values = utilities.reduce_close_floats(float_list=[float(i) for i in self.dna_reader.getVertexTextureCoordinateVs(0)], tolerance=tolerance)

        u_values, v_values = utilities.get_uv_values(mesh_object=mesh_object)
        u_values = utilities.reduce_close_floats(float_list=u_values, tolerance=tolerance)
        v_values = utilities.reduce_close_floats(float_list=v_values, tolerance=tolerance)

        if len(u_values) != len(dna_u_values) or len(v_values) != len(dna_v_values):
            uv_differences = abs(len(u_values)-len(dna_u_values)) + abs(len(v_values)-len(dna_v_values))
            return False, (
                f'UV validation failed! The mesh "{mesh_object.name}" has {uv_differences} UV values '
                'that do not match the layout in the template DNA file. Right-click the '
                '"Convert Selected to DNA" button to see the online manual that shows '
                'the correct UV layout. Otherwise, disable the UV validation or adjust '
                'the tolerance value.'
            )
        
        return True, 'Validation successful!'
        
    def export(self):
        pass

    def delete(self):
        for item in self.rig_logic_instance.output_item_list:
            if item.scene_object:
                bpy.data.objects.remove(item.scene_object, do_unlink=True)
            if item.image_object:
                bpy.data.images.remove(item.image_object, do_unlink=True)

        my_list = self.scene_properties.rig_logic_instance_list
        active_index = self.scene_properties.rig_logic_instance_list_active_index
        my_list.remove(active_index)
        to_index = min(active_index, len(my_list) - 1)
        self.scene_properties.rig_logic_instance_list_active_index = to_index # type: ignore

    def push_selected_bones_along_mesh_normals(
            self, 
            direction: Literal['forward', 'backward']
        ):
        if self.head_rig_object and self.head_mesh_object:
            amount = self.scene_properties.push_along_normal_distance
            for pose_bone in bpy.context.selected_pose_bones: # type: ignore
                normal = utilities.get_ray_cast_normal(
                    self.head_mesh_object, 
                    pose_bone,
                    max_distance=0.01
                )
                if normal:
                    bone_world_position = self.head_rig_object.matrix_world @ pose_bone.matrix.to_translation()
                    if direction == 'forward':
                        bone_world_position += normal.normalized()*amount
                    elif direction == 'backward':
                        bone_world_position -= normal.normalized()*amount

                    pose_bone.matrix = self.head_rig_object.matrix_world.inverted() @ Matrix.Translation(bone_world_position)

            utilities.apply_pose(self.head_rig_object, selected=True)
        
    def _mirror_bone_to(
            self, 
            from_bone: bpy.types.PoseBone, 
            to_bone_name: str
        ) -> bpy.types.PoseBone | None:
        if self.head_rig_object:
            to_bone = self.head_rig_object.pose.bones.get(to_bone_name) # type: ignore
            location = from_bone.matrix.to_translation()
            location.x *= -1
            if to_bone:
                to_bone.matrix = Matrix.Translation(location)
                return to_bone
                        
        logger.error(f'Could not find bone {to_bone_name}')

    def mirror_selected_bones(self) -> tuple[bool, str]:
        if self.head_rig_object:
            ignored_bone_names = utilities.get_ignored_bones_names(self.head_rig_object)
            selected_pose_bones = [
                pose_bone for pose_bone in bpy.context.selected_pose_bones # type: ignore
                if pose_bone.name not in ignored_bone_names
            ] # type: ignore
            
            # Validate that the selected bones are all on the same side
            left_side_count = 0
            right_side_count = 0
            for pose_bone in selected_pose_bones:
                if pose_bone.name.endswith('_l'):
                    left_side_count += 1
                elif pose_bone.name.startswith('FACIAL_L'):
                    left_side_count += 1
                elif pose_bone.name.endswith('_r'):
                    right_side_count += 1
                elif pose_bone.name.startswith('FACIAL_R'):
                    right_side_count += 1

            if left_side_count and right_side_count:
                return False, (
                    'Selected bones must all be on the same side! Your selection '
                    f'has {left_side_count} on the left and {right_side_count} on the right.'
                )

            # Now mirror the bones
            for pose_bone in selected_pose_bones:
                mirrored_bone = None
                if pose_bone.name.endswith('_l'):
                    parts = pose_bone.name.rsplit('_l', 1)
                    bone_name = '_r'.join(parts)
                    mirrored_bone = self._mirror_bone_to(from_bone=pose_bone, to_bone_name=bone_name)
                elif pose_bone.name.startswith('FACIAL_L'):
                    bone_name = pose_bone.name.replace('FACIAL_L', 'FACIAL_R', 1)
                    mirrored_bone = self._mirror_bone_to(from_bone=pose_bone, to_bone_name=bone_name)
                elif pose_bone.name.endswith('_r'):
                    parts = pose_bone.name.rsplit('_r', 1)
                    bone_name = '_l'.join(parts)
                    mirrored_bone = self._mirror_bone_to(from_bone=pose_bone, to_bone_name=bone_name)
                elif pose_bone.name.startswith('FACIAL_R'):
                    bone_name = pose_bone.name.replace('FACIAL_R', 'FACIAL_L', 1)
                    mirrored_bone = self._mirror_bone_to(from_bone=pose_bone, to_bone_name=bone_name)

                if mirrored_bone:
                    mirrored_bone.bone.select = True
            
            # apply the pose changes
            utilities.apply_pose(self.head_rig_object, selected=True)

        return True, 'Bones mirrored successfully!'

    def _create_topology_vertex_groups(self):
        if not self.dna_import_properties.import_mesh:
            return

        if self.head_mesh_object:
            with open(TOPOLOGY_VERTEX_GROUPS_FILE_PATH, 'r') as file:
                data = json.load(file)
                logger.info("Creating topology vertex groups...")
                for vertex_group_name, vertex_indexes in data.items():
                    # get the existing vertex_group or create a new one
                    vertex_group = self.head_mesh_object.vertex_groups.get(vertex_group_name)
                    if not vertex_group:
                        vertex_group = self.head_mesh_object.vertex_groups.new(name=vertex_group_name)

                    vertex_group.add(
                        index=vertex_indexes,
                        weight=1.0,
                        type='REPLACE'
                    )

    def select_vertex_group(self):
        if self.rig_logic_instance and self.rig_logic_instance.head_mesh:
            utilities.select_vertex_group(
                mesh_object=self.rig_logic_instance.head_mesh,
                vertex_group_name=self.rig_logic_instance.head_mesh_topology_groups,
                add=self.rig_logic_instance.head_mesh_topology_selection_mode == 'add'
            )

    def select_bone_group(self):
        if self.rig_logic_instance and self.rig_logic_instance.head_rig:
            if self.rig_logic_instance.head_rig_bone_group_selection_mode != 'add':
                # deselect all bones first
                for bone in self.rig_logic_instance.head_rig.data.bones: # type: ignore
                    bone.select = False
            
            from .bindings import meta_human_dna_core
            for bone_name in meta_human_dna_core.BONE_SELECTION_GROUPS.get(self.rig_logic_instance.head_rig_bone_groups, []): # type: ignore
                bone = self.rig_logic_instance.head_rig.data.bones.get(bone_name) # type: ignore
                if bone:
                    bone.select = True

            if self.rig_logic_instance.head_rig_bone_groups.startswith(TOPO_GROUP_PREFIX):
                for bone in utilities.get_topology_group_surface_bones(
                    mesh_object=self.rig_logic_instance.head_mesh,
                    armature_object=self.rig_logic_instance.head_rig,
                    vertex_group_name=self.rig_logic_instance.head_rig_bone_groups,
                    dna_reader=self.dna_reader
                ):
                    bone.select = True

            self.rig_logic_instance.head_rig.hide_set(False)
            utilities.switch_to_pose_mode(self.rig_logic_instance.head_rig) # type: ignore

    def set_face_pose(self):        
        for instance in self.scene_properties.rig_logic_instance_list:
            thumbnail_file = Path(bpy.context.window_manager.meta_human_dna.face_pose_previews) # type: ignore
            json_file_path = thumbnail_file.parent / 'pose.json'
            if json_file_path.exists():
                logger.info(f'Applying face pose from {json_file_path}')
                # dont evaluate while updating the face board transforms
                self.window_manager_properties.evaluate_dependency_graph = False
                with open(json_file_path, 'r') as file:
                    data = json.load(file)
                                        
                    # clear the pose location for all the control bones
                    for pose_bone in instance.face_board.pose.bones:
                        if not pose_bone.bone.children and pose_bone.name.startswith('CTRL_'):
                            pose_bone.location = Vector((0.0, 0.0, 0.0))

                    for bone_name, transform_data in data.items():
                        pose_bone = instance.face_board.pose.bones.get(bone_name) # type: ignore
                        if pose_bone:
                            pose_bone.location = Vector(transform_data['location'])

                self.window_manager_properties.evaluate_dependency_graph = True
                # now evaluate the face board
                instance.evaluate()
                

    def shrink_wrap_vertex_group(self):
        if self.rig_logic_instance and self.rig_logic_instance.head_mesh:
            modifier = self.rig_logic_instance.head_mesh.modifiers.get(self.rig_logic_instance.head_mesh_topology_groups)
            if not modifier:
                modifier = self.rig_logic_instance.head_mesh.modifiers.new(name=self.rig_logic_instance.head_mesh_topology_groups, type='SHRINKWRAP')
                modifier.show_viewport = False
                modifier.wrap_method = 'PROJECT'
                modifier.use_negative_direction = True

            modifier.target = self.rig_logic_instance.shrink_wrap_target
            modifier.vertex_group = self.rig_logic_instance.head_mesh_topology_groups
            # toggle the visibility of the modifier
            modifier.show_viewport = not modifier.show_viewport

            utilities.set_vertex_selection(
                mesh_object=self.rig_logic_instance.head_mesh, 
                vertex_indexes=[],
                add=False
            )
            utilities.select_vertex_group(
                mesh_object=self.rig_logic_instance.head_mesh,
                vertex_group_name=self.rig_logic_instance.head_mesh_topology_groups
            )

    @preserve_context
    def revert_bone_transforms_to_dna(self):
        if self.head_rig_object:
            extra_bone_lookup = dict(EXTRA_BONES)
            # make sure the dna importer has the rig object set
            self.dna_importer.rig_object = self.head_rig_object
            
            bone_names = [pose_bone.name for pose_bone in bpy.context.selected_pose_bones] # type: ignore
            utilities.switch_to_bone_edit_mode(self.rig_logic_instance.head_rig)
            
            for bone_name in bone_names:
                edit_bone = self.head_rig_object.data.edit_bones[bone_name] # type: ignore
                extra_bone = extra_bone_lookup.get(bone_name)
                if bone_name == 'root':
                    edit_bone.matrix = self.head_rig_object.matrix_world
                # reverts the default bone transforms back to their default values
                elif extra_bone:
                    location = extra_bone['location']
                    rotation = extra_bone['rotation']
                    # Scale the location of the bones based on the height scale factor
                    location.y = location.y * self.dna_importer.get_height_scale_factor()
                    global_matrix = Matrix.Translation(location) @ rotation.to_matrix().to_4x4()
                    # default values are stored in Y-up, so convert to Z-up
                    edit_bone.matrix = Matrix.Rotation(math.radians(90), 4, 'X').to_4x4() @ global_matrix
                else:
                    bone_matrix = self.dna_importer.get_bone_matrix(bone_name=bone_name)
                    if bone_matrix:
                        edit_bone.matrix = bone_matrix

    @utilities.exclude_rig_logic_evaluation
    def import_shape_keys(self, commands_queue: queue.Queue) -> list:
        if not self.head_mesh_object:
            raise ValueError('Head mesh object not found!')
        
        commands = []

        def get_initialize_kwargs(index: int, mesh_index: int):
            mesh_dna_name = self.dna_reader.getMeshName(mesh_index)
            mesh_object = bpy.data.objects.get(f'{self.name}_{mesh_dna_name}')
            return {
                'mesh_object': mesh_object,
            }

        def get_create_kwargs(index: int, mesh_index: int):
            channel_index = self.dna_reader.getBlendShapeChannelIndex(mesh_index, index)
            shape_key_name = self.dna_reader.getBlendShapeChannelName(channel_index)
            mesh_dna_name = self.dna_reader.getMeshName(mesh_index)
            mesh_object = bpy.data.objects.get(f'{self.name}_{mesh_dna_name}')
            return {
                'index': index,
                'mesh_index': mesh_index,
                'mesh_object': mesh_object,
                'reader': self.dna_reader,
                'name': shape_key_name,
                'is_neutral': self.rig_logic_instance.generate_neutral_shapes,
                'linear_modifier': self.linear_modifier,
                'prefix': f'{mesh_dna_name}__'
            }

        for mesh_index in range(self.dna_reader.getMeshCount()):
            count = self.dna_reader.getBlendShapeTargetCount(mesh_index)
            if count > 0:
                commands_queue.put((
                    0, 
                    mesh_index,
                    'Initializing basis shape...',
                    get_initialize_kwargs,
                    lambda **kwargs: utilities.initialize_basis_shape_key(**kwargs)
                ))
                
            for index in range(count):
                commands_queue.put((
                    index, 
                    mesh_index,
                    f'{index}/{count}' + ' {name} ...',
                    get_create_kwargs,
                    lambda **kwargs: create_shape_key(**kwargs)
                ))
        
        return commands