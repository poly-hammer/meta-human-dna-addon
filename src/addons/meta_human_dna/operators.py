# standard library imports
import contextlib
import logging
import math
import queue
import shutil
import webbrowser

from datetime import UTC, datetime, timedelta
from pathlib import Path

# third party imports
import bpy

from mathutils import Matrix, Vector

# local imports
from . import constants, utilities
from .components import MetaHumanComponentBody, MetaHumanComponentHead, get_meta_human_component
from .constants import (
    DEFAULT_UV_TOLERANCE,
    FACE_BOARD_NAME,
    HEAD_TEXTURE_LOGIC_NODE_LABEL,
    HEAD_TEXTURE_LOGIC_NODE_NAME,
    NUMBER_OF_HEAD_LODS,
    SHAPE_KEY_BASIS_NAME,
    ToolInfo,
)
from .dna_io import DNACalibrator, DNAExporter, get_dna_reader
from .properties import BlendFileMetaHumanCollection, MetahumanImportProperties
from .typing import *  # noqa: F403
from .ui import callbacks, importer


logger = logging.getLogger(__name__)


class GenericUIListOperator:
    """Mix-in class containing functionality shared by operators
    that deal with managing Blender list entries."""

    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    active_index: bpy.props.IntProperty()  # pyright: ignore[reportInvalidTypeForm]


class GenericProgressQueueOperator(bpy.types.Operator):
    """
    Mix-in class containing functionality shared by operators that have a progress queue.
    """

    _timer: bpy.types.Timer | None = None
    _commands_queue = queue.Queue()
    _commands_queue_size = 0

    def modal(self, context: "Context", event: bpy.types.Event) -> set[str]:
        if event.type == "ESC":
            return self.finish(context)

        if event.type == "TIMER" and context.screen:
            [a.tag_redraw() for a in context.screen.areas]
            if self._commands_queue.empty():
                return self.finish(context)

            index, mesh_index, description, kwargs_callback, callback = self._commands_queue.get()
            new_size = self._commands_queue.qsize()

            # calculate the kwargs
            kwargs = kwargs_callback(index, mesh_index)
            # inject the kwargs into the description
            description = description.format(**kwargs)
            context.window_manager.meta_human_dna.progress = (
                self._commands_queue_size - new_size
            ) / self._commands_queue_size
            context.window_manager.meta_human_dna.progress_description = description
            callback(**kwargs)

        return {"PASS_THROUGH"}

    def execute(self, context: "Context") -> set[str]:
        if not self.validate(context):
            return {"CANCELLED"}

        self._timer = context.window_manager.event_timer_add(0.01, window=context.window)
        context.window_manager.modal_handler_add(self)
        head = utilities.get_active_head()
        if head:
            context.window_manager.meta_human_dna.progress = 0
            context.window_manager.meta_human_dna.progress_description = ""
            self._commands_queue = queue.Queue()
            self.set_commands_queue(context, head, self._commands_queue)
            self._commands_queue_size = self._commands_queue.qsize()
            return {"RUNNING_MODAL"}
        return {"CANCELLED"}

    def finish(self, context: "Context") -> set[str]:
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
        context.window_manager.meta_human_dna.progress = 1
        # re-initialize the rig instance so the shape key blocks collection is updated for the UI
        instance = callbacks.get_active_rig_instance()
        if instance:
            instance.data.clear()
            instance.initialize()
        return {"FINISHED"}

    def validate(self, context: "Context") -> bool:
        return True

    def set_commands_queue(
        self,
        context: "Context",
        component: MetaHumanComponentHead | MetaHumanComponentBody,
        commands_queue: queue.Queue,
    ):
        pass


class AppendOrLinkMetaHuman(bpy.types.Operator, importer.LinkAppendMetaHumanImportHelper):
    """Append or link a MetaHuman from a .blend file. The .blend file must contain a collection with all data related to the MetaHuman asset."""  # noqa: E501

    bl_idname = "meta_human_dna.append_or_link_metahuman"
    bl_label = "Import"
    filename_ext = ".blend"

    filter_glob: bpy.props.StringProperty(
        default="*.blend",
        options={"HIDDEN"},
        subtype="FILE_PATH",
    )  # pyright: ignore[reportInvalidTypeForm]

    relative_path: bpy.props.BoolProperty(default=True)  # pyright: ignore[reportInvalidTypeForm]
    previous_file_path: bpy.props.StringProperty(default="")  # pyright: ignore[reportInvalidTypeForm]
    operation_type: bpy.props.EnumProperty(
        items=[
            ("APPEND", "Append", "Append the selected MetaHuman"),
            ("LINK", "Link", "Link the selected MetaHuman"),
        ],
        default="APPEND",
    )  # pyright: ignore[reportInvalidTypeForm]
    meta_human_list: bpy.props.CollectionProperty(type=BlendFileMetaHumanCollection)  # pyright: ignore[reportInvalidTypeForm]
    meta_human_names: bpy.props.StringProperty(default="")  # pyright: ignore[reportInvalidTypeForm]

    def execute(self, context: "Context") -> set[str]:  # noqa: PLR0912
        file_path = self.filepath  # type: ignore[attr-defined]
        if not file_path:
            self.report({"ERROR"}, "You must select a .blend file")
            return {"CANCELLED"}

        if not Path(bpy.path.abspath(file_path)).exists():
            self.report({"ERROR"}, f"File not found: {file_path}")
            return {"CANCELLED"}

        if bpy.data.filepath == file_path:
            self.report({"ERROR"}, "You cannot import a MetaHuman from the current .blend file")
            return {"CANCELLED"}

        # this is for headless imports and automated tests
        if self.meta_human_names:
            self.meta_human_list.clear()
            for name in self.meta_human_names.split(","):
                item = self.meta_human_list.add()
                item.name = name
                item.include = True

        # track the current control objects
        current_control_objects = []
        for instance in context.scene.meta_human_dna.rig_instance_list:
            if instance.face_board:
                current_control_objects.extend(pose_bone.custom_shape for pose_bone in instance.face_board.pose.bones)

        collection_names = []
        with bpy.data.libraries.load(
            filepath=file_path,
            link=self.operation_type == "LINK",
            relative=self.relative_path,
        ) as (data_from, data_to):  # type: ignore[arg-type]
            # we only append/link the collections that the user has selected
            for item in self.meta_human_list:
                if item.include:
                    for collection_name in data_from.collections:
                        if collection_name == item.name:
                            data_to.collections.append(collection_name)
                            collection_names.append(collection_name)

        # extract the rig instance data from the blend file
        data, error = utilities.extract_rig_instance_data_from_blend_file(Path(bpy.path.abspath(file_path)))
        if error:
            logger.error(error)
            self.report({"ERROR"}, f"Failed to extract rig instance data from blend file: {error}")
            return {"CANCELLED"}

        # link the collections to the scene
        for collection_name in collection_names:
            collection = bpy.data.collections.get(collection_name)
            if collection and context.scene:
                context.scene.collection.children.link(collection)

            # delete the face board and its control object shapes if they exist
            face_board = bpy.data.objects.get(f"{collection_name}_{FACE_BOARD_NAME}")
            if face_board and face_board.pose:
                for pose_bone in face_board.pose.bones:
                    if pose_bone.custom_shape and pose_bone.custom_shape not in current_control_objects:
                        control_object = pose_bone.custom_shape
                        pose_bone.custom_shape = None
                        bpy.data.objects.remove(control_object, do_unlink=True)
                # remove the face board object
                bpy.data.objects.remove(face_board, do_unlink=True)

            # Extract the rig instance data from the .blend file and set them on the new rig instance
            instance = utilities.add_rig_instance(name=collection_name)
            instance.head_dna_file_path = data[collection_name]["head_dna_file_path"]
            instance.head_mesh = bpy.data.objects.get(data[collection_name]["head_mesh"] or "")
            instance.head_rig = bpy.data.objects.get(data[collection_name]["head_rig"] or "")
            instance.head_material = bpy.data.materials.get(data[collection_name]["head_material"] or "")
            instance.body_mesh = bpy.data.objects.get(data[collection_name]["body_mesh"] or "")
            instance.body_rig = bpy.data.objects.get(data[collection_name]["body_rig"] or "")
            instance.body_material = bpy.data.materials.get(data[collection_name]["body_material"] or "")
            instance.body_dna_file_path = data[collection_name]["body_dna_file_path"]
            instance.output_folder_path = data[collection_name]["output_folder_path"]

            # duplicate the face board if there is one already in the scene
            if any(i.face_board for i in context.scene.meta_human_dna.rig_instance_list):
                instance.face_board = utilities.duplicate_face_board(name=collection_name)
            # otherwise import it
            else:
                instance.face_board = utilities.import_face_board(name=collection_name)

            # position the face board next to the head mesh
            if instance.face_board:
                utilities.position_face_board(
                    head_mesh_object=instance.head_mesh,
                    head_rig_object=instance.head_rig,
                    face_board_object=instance.face_board,
                )
                if self.operation_type != "LINK":
                    utilities.move_to_collection(
                        scene_objects=[instance.face_board], collection_name=collection_name, exclusively=True
                    )

                utilities.constrain_face_board_to_head(
                    face_board_object=instance.face_board,
                    head_rig_object=instance.head_rig,
                    body_rig_object=instance.body_rig,
                    bone_name="CTRL_faceGUI",
                )
                utilities.constrain_face_board_to_head(
                    face_board_object=instance.face_board,
                    head_rig_object=instance.head_rig,
                    body_rig_object=instance.body_rig,
                    bone_name="CTRL_C_eyesAim",
                )

        return {"FINISHED"}


class ImportAnimationBase(bpy.types.Operator):
    filename_ext = ".fbx"

    filter_glob: bpy.props.StringProperty(
        default="*.fbx",
        options={"HIDDEN"},
        subtype="FILE_PATH",
    )  # pyright: ignore[reportInvalidTypeForm]

    round_sub_frames: bpy.props.BoolProperty(
        name="Round Sub Frames",
        default=True,
        description=(
            "Whether to round sub frames when importing the animation. This "
            "ensure all keyframes are on whole frames with integer values"
        ),
    )  # pyright: ignore[reportInvalidTypeForm]

    match_frame_rate: bpy.props.BoolProperty(
        name="Match Frame Rate",
        default=True,
        description=(
            "Whether to match the frame rate when importing the animation. This "
            "will scale the animation curves to match the current scene frame rate"
        ),
    )  # pyright: ignore[reportInvalidTypeForm]

    prefix_instance_name: bpy.props.BoolProperty(
        name="Prefix Instance Name",
        default=True,
        description=(
            "Prefixes the baked action name with the rig instance name. This helps avoid name "
            "collisions with other action names when multiple are in the same scene."
        ),
    )  # pyright: ignore[reportInvalidTypeForm]

    prefix_component_name: bpy.props.BoolProperty(
        name="Prefix Component Name",
        default=True,
        description=(
            "Prefixes the baked action name with the component name. This helps avoid name collisions "
            "with other components that might have the same action names."
        ),
    )  # pyright: ignore[reportInvalidTypeForm]

    @property
    def settings_title(self) -> str:
        return "Animation Import Settings:"


class ImportFaceBoardAnimation(ImportAnimationBase, importer.ImportAnimation):
    """Import an animation for the metahuman face board exported from an Unreal Engine Level Sequence"""

    bl_idname = "meta_human_dna.import_face_board_animation"
    bl_label = "Import"

    @property
    def settings_title(self) -> str:
        return "Face Board Animation Import Settings:"

    def execute(self, context: "Context") -> set[str]:
        file_path = self.filepath  # type: ignore[attr-defined]
        logger.info(f"Importing animation {file_path}")
        head = utilities.get_active_head()
        if head:
            head.import_action(
                Path(file_path),
                is_face_board=True,
                round_sub_frames=self.round_sub_frames,
                match_frame_rate=self.match_frame_rate,
                prefix_instance_name=self.prefix_instance_name,
                prefix_component_name=self.prefix_component_name,
            )
        return {"FINISHED"}


class ImportComponentAnimation(ImportAnimationBase, importer.ImportAnimation):
    """Import an animation for the selected metahuman component that has been exported from an Unreal Engine"""

    bl_idname = "meta_human_dna.import_component_animation"
    bl_label = "Import"

    component_type: bpy.props.StringProperty(default="body")  # pyright: ignore[reportInvalidTypeForm]

    @property
    def settings_title(self) -> str:
        return f"{self.component_type.capitalize()} Animation Import Settings:"

    def execute(self, context: "Context") -> set[str]:
        file_path = Path(bpy.path.abspath(self.filepath))  # type: ignore[attr-defined]
        logger.info(f"Importing animation {file_path}")
        if self.component_type == "head":
            head = utilities.get_active_head()
            if head:
                head.import_action(
                    file_path,
                    is_face_board=False,
                    round_sub_frames=self.round_sub_frames,
                    match_frame_rate=self.match_frame_rate,
                    prefix_instance_name=self.prefix_instance_name,
                    prefix_component_name=self.prefix_component_name,
                )

        elif self.component_type == "body":
            body = utilities.get_active_body()
            if body:
                body.import_action(
                    file_path,
                    round_sub_frames=self.round_sub_frames,
                    match_frame_rate=self.match_frame_rate,
                    prefix_instance_name=self.prefix_instance_name,
                    prefix_component_name=self.prefix_component_name,
                )

        self.report({"INFO"}, f"Imported {self.component_type} animation from {file_path}")

        return {"FINISHED"}


class BakeAnimationBase(bpy.types.Operator):
    action_name: bpy.props.StringProperty(
        name="Action Name",
        default="baked_action",
        description="The name of the action that will be created to store the baked animation data",
    )  # pyright: ignore[reportInvalidTypeForm]

    prefix_instance_name: bpy.props.BoolProperty(
        name="Prefix Instance Name",
        default=True,
        description=(
            "Prefixes the baked action name with the rig instance name. This helps avoid name collisions "
            "with other action names when multiple are in the same scene."
        ),
    )  # pyright: ignore[reportInvalidTypeForm]
    prefix_component_name: bpy.props.BoolProperty(
        name="Prefix Component Name",
        default=True,
        description=(
            "Prefixes the baked action name with the component name. This helps avoid name collisions "
            "with other components that might have the same action names."
        ),
    )  # pyright: ignore[reportInvalidTypeForm]

    replace_action: bpy.props.BoolProperty(
        name="Replace Action", default=False, description="Replaces the existing action with the baked action"
    )  # pyright: ignore[reportInvalidTypeForm]

    start_frame: bpy.props.IntProperty(
        name="Start Frame",
        default=1,
        min=1,
        get=callbacks.get_bake_start_frame,
        set=callbacks.set_bake_start_frame,
        description="The frame to start baking the animation on",
    )  # pyright: ignore[reportInvalidTypeForm]

    end_frame: bpy.props.IntProperty(
        name="End Frame",
        default=250,
        min=1,
        get=callbacks.get_bake_end_frame,
        set=callbacks.set_bake_end_frame,
        description="The frame to end baking the animation on",
    )  # pyright: ignore[reportInvalidTypeForm]

    step: bpy.props.IntProperty(
        name="Step",
        default=1,
        min=1,
        description="The frame step to bake the animation on. Essentially add a keyframe every nth frame",
    )  # pyright: ignore[reportInvalidTypeForm]

    masks: bpy.props.BoolProperty(
        name="Masks", default=True, description="Bakes the values of the wrinkle map masks over time"
    )  # pyright: ignore[reportInvalidTypeForm]

    shape_keys: bpy.props.BoolProperty(
        name="Shape Keys", default=True, description="Bakes the values of the shape keys over time"
    )  # pyright: ignore[reportInvalidTypeForm]

    clean_curves: bpy.props.BoolProperty(
        name="Clean Curves", default=False, description="Clean Curves, After baking curves, remove redundant keys"
    )  # pyright: ignore[reportInvalidTypeForm]

    bone_location: bpy.props.BoolProperty(
        name="Bone Location", default=True, description="Bakes the location of the bones"
    )  # pyright: ignore[reportInvalidTypeForm]
    bone_rotation: bpy.props.BoolProperty(
        name="Bone Rotation", default=True, description="Bakes the rotation of the bones"
    )  # pyright: ignore[reportInvalidTypeForm]
    bone_scale: bpy.props.BoolProperty(name="Bone Scale", default=True, description="Bakes the scale of the bones")  # pyright: ignore[reportInvalidTypeForm]

    def invoke(self, context: "Context", event: bpy.types.Event) -> set[str]:
        return context.window_manager.invoke_props_dialog(  # type: ignore[return-value]
            self, title=self.dialog_title, width=250
        )

    @property
    def dialog_title(self) -> str:
        return self.bl_label

    def draw_extra_settings(self, layout: bpy.types.UILayout, context: "Context") -> None:
        pass

    def draw(self, context: "Context") -> None:
        if not self.layout:
            return

        row = self.layout.row()
        row.label(text="Naming:")
        row = self.layout.row()
        row.prop(self, "action_name", text="")
        row = self.layout.row()
        row.prop(self, "prefix_instance_name")
        row = self.layout.row()
        row.prop(self, "prefix_component_name")
        row = self.layout.row()
        row.label(text="Settings:")
        row = self.layout.row()
        row.prop(self, "start_frame")
        row.prop(self, "end_frame")
        row = self.layout.row()
        row.prop(self, "step")
        row = self.layout.row()
        row.prop(self, "replace_action")
        row = self.layout.row()
        row.prop(self, "shape_keys")
        row = self.layout.row()
        row.prop(self, "masks")
        row = self.layout.row()
        self.draw_extra_settings(self.layout, context)
        row = self.layout.row()
        row.label(text="Bone Transforms:")
        row = self.layout.row()
        row.prop(self, "bone_location", text="Location")
        row = self.layout.row()
        row.prop(self, "bone_rotation", text="Rotation")
        row = self.layout.row()
        row.prop(self, "bone_scale", text="Scale")


class BakeFaceBoardAnimation(BakeAnimationBase):
    """Bakes the active face board action to the pose bones, shape key values, and texture logic mask values. Useful for rendering, simulations, etc. where rig logic evaluation is not available"""  # noqa: E501

    bl_idname = "meta_human_dna.bake_face_board_animation"
    bl_label = "Bake Face Board Animation"

    def execute(self, context: "Context") -> set[str]:
        if self.start_frame > self.end_frame:
            self.report({"ERROR"}, "The start frame must be less than the end frame")
            return {"CANCELLED"}

        instance = callbacks.get_active_rig_instance()
        if instance and instance.head_rig:
            channel_types = set()
            if self.bone_location:
                channel_types.add("LOCATION")
            if self.bone_rotation:
                channel_types.add("ROTATION")
            if self.bone_scale:
                channel_types.add("SCALE")

            action_name = utilities.get_action_name(
                instance=instance,
                action_name=self.action_name,
                component="head",
                prefix_component_name=self.prefix_component_name,
                prefix_instance_name=self.prefix_instance_name,
            )

            utilities.bake_face_board_to_action(
                instance=instance,
                armature_object=instance.head_rig,
                action_name=action_name,
                replace_action=self.replace_action,
                start_frame=self.start_frame,
                end_frame=self.end_frame,
                step=self.step,
                channel_types=channel_types,
                clean_curves=self.clean_curves,
                masks=self.masks,
                shape_keys=self.shape_keys,
            )
        return {"FINISHED"}

    @classmethod
    def poll(cls, _: "Context") -> bool:
        instance = callbacks.get_active_rig_instance()
        if not instance:
            return False
        if not instance.head_rig:
            return False
        if not instance.face_board:
            return False
        if not instance.face_board.animation_data:
            return False
        return instance.face_board.animation_data.action


class BakeComponentAnimation(BakeAnimationBase):
    """Bakes the active component action. This takes into account how the driver pose bones effect the rbf driven bones, shape key values, and texture logic mask values. Useful for rendering, simulations, etc. where rig logic evaluation is not available"""  # noqa: E501

    bl_idname = "meta_human_dna.bake_component_animation"
    bl_label = "Bake Component Animation"

    component_type: bpy.props.StringProperty(
        default="body",
        options={"HIDDEN"},
        subtype="FILE_PATH",
    )  # pyright: ignore[reportInvalidTypeForm]

    driver_bones: bpy.props.BoolProperty(
        name="Driver Bones", default=True, description="Bakes the values of the driver bones over time"
    )  # pyright: ignore[reportInvalidTypeForm]
    driven_bones: bpy.props.BoolProperty(
        name="Driven Bones", default=True, description="Bakes the values of the RBF driven bones over time"
    )  # pyright: ignore[reportInvalidTypeForm]
    twist_bones: bpy.props.BoolProperty(
        name="Twist Bones", default=True, description="Bakes the values of the twist bones over time"
    )  # pyright: ignore[reportInvalidTypeForm]
    swing_bones: bpy.props.BoolProperty(
        name="Swing Bones", default=True, description="Bakes the values of the swing bones over time"
    )  # pyright: ignore[reportInvalidTypeForm]
    other_bones: bpy.props.BoolProperty(
        name="Other Bones",
        default=True,
        description=(
            "Bakes the values of other bones on the rig that are not explicitly categorized as "
            "driver, driven, twist, or swing bones"
        ),
    )  # pyright: ignore[reportInvalidTypeForm]

    def execute(self, context: "Context") -> set[str]:
        if self.start_frame > self.end_frame:
            self.report({"ERROR"}, "The start frame must be less than the end frame")
            return {"CANCELLED"}

        instance = callbacks.get_active_rig_instance()
        if instance and instance.body_rig and self.component_type == "body":
            channel_types = set()
            if self.bone_location:
                channel_types.add("LOCATION")
            if self.bone_rotation:
                channel_types.add("ROTATION")
            if self.bone_scale:
                channel_types.add("SCALE")

            action_name = utilities.get_action_name(
                instance=instance,
                action_name=self.action_name,
                component=self.component_type,
                prefix_component_name=self.prefix_component_name,
                prefix_instance_name=self.prefix_instance_name,
            )

            utilities.bake_body_to_action(
                instance=instance,
                armature_object=instance.body_rig,
                action_name=action_name,
                replace_action=self.replace_action,
                start_frame=self.start_frame,
                end_frame=self.end_frame,
                step=self.step,
                channel_types=channel_types,
                clean_curves=self.clean_curves,
                masks=self.masks,
                shape_keys=self.shape_keys,
                driver_bones=self.driver_bones,
                driven_bones=self.driven_bones,
                twist_bones=self.twist_bones,
                swing_bones=self.swing_bones,
                other_bones=self.other_bones,
            )
        return {"FINISHED"}

    @property
    def dialog_title(self) -> str:
        return f"Bake {self.component_type.capitalize()} Animation"

    def draw_extra_settings(self, layout: bpy.types.UILayout, context: "Context") -> None:
        if self.component_type == "body":
            row = layout.row()
            row.label(text="Bone Types:")
            row = layout.row()
            row.prop(self, "driver_bones")
            row = layout.row()
            row.prop(self, "driven_bones")
            row = layout.row()
            row.prop(self, "twist_bones")
            row = layout.row()
            row.prop(self, "swing_bones")
            row = layout.row()
            row.prop(self, "other_bones")

    @classmethod
    def poll(cls, context: "Context") -> bool:
        instance = callbacks.get_active_rig_instance()

        if not instance:
            return False

        if context.window_manager.meta_human_dna.current_component_type == "body":
            if not instance.body_rig:
                return False
            if not instance.body_rig.animation_data:
                return False
            return instance.body_rig.animation_data.action

        return False


class ImportMetaHumanDna(bpy.types.Operator, importer.ImportAsset, MetahumanImportProperties):
    """Import a metahuman head from a DNA file"""

    bl_idname = "meta_human_dna.import_dna"
    bl_label = "Import DNA"
    filename_ext = ".dna"

    filter_glob: bpy.props.StringProperty(
        default="*.dna",
        options={"HIDDEN"},
        subtype="FILE_PATH",
    )  # pyright: ignore[reportInvalidTypeForm]

    def execute(self, context: "Context") -> set[str]:
        window_manager_properties = context.window_manager.meta_human_dna
        # we define the properties initially on the operator so has preset
        # transfer the settings from the operator onto the window properties, so they are globally accessible
        for key in self.__annotations__:
            if hasattr(MetahumanImportProperties, key):
                value = getattr(self.properties, key)
                setattr(window_manager_properties.meta_human_dna, key, value)

        file_path = Path(bpy.path.abspath(self.filepath))
        if not file_path.exists():
            self.report({"ERROR"}, f"File not found: {file_path}")
            return {"CANCELLED"}
        if not file_path.is_file():
            self.report({"ERROR"}, f'"{file_path}" is a folder. Please select a DNA file.')
            return {"CANCELLED"}
        if file_path.suffix not in [".dna"]:
            self.report({"ERROR"}, f'The file "{file_path}" is not a DNA file')
            return {"CANCELLED"}
        if round(context.scene.unit_settings.scale_length, 2) != 1.0:
            self.report({"ERROR"}, "The scene unit scale must be set to 1.0")
            return {"CANCELLED"}

        # we don't want to evaluate the dependency graph while importing the DNA
        window_manager_properties.evaluate_dependency_graph = False
        component = get_meta_human_component(
            file_path=file_path,
            properties=self.properties,  # type: ignore[arg-type]
        )
        # if the component is a head, we import the body first if the user has selected the option
        body_file = file_path.parent / "body.dna"
        if self.properties.include_body and component.component_type == "head" and body_file.exists():
            body_component = get_meta_human_component(
                file_path=body_file,
                properties=self.properties,  # type: ignore[arg-type]
                rig_instance=component.rig_instance,
            )
            valid, message = body_component.ingest()
            logger.info(f'Finished importing "{body_file}"')
            if not valid:
                self.report({"ERROR"}, message)
                return {"CANCELLED"}
            self.report({"INFO"}, message)

        # now we can import the chosen .dna file
        valid, message = component.ingest()
        logger.info(f'Finished importing "{self.filepath}"')
        if not valid:
            self.report({"ERROR"}, message)
            return {"CANCELLED"}
        self.report({"INFO"}, message)

        # populate the output items based on what was imported
        callbacks.update_head_output_items(None, bpy.context)  # type: ignore[arg-type]
        # now we can evaluate the dependency graph again
        window_manager_properties.evaluate_dependency_graph = True
        bpy.ops.meta_human_dna.force_evaluate()  # type: ignore[attr-defined]

        bpy.ops.meta_human_dna.metrics_collection_consent("INVOKE_DEFAULT")  # type: ignore[attr-defined]

        return {"FINISHED"}

    @classmethod
    def poll(cls, _: "Context") -> bool:
        return utilities.dependencies_are_valid()


class DNA_FH_import_dna(bpy.types.FileHandler):
    bl_idname = "DNA_FH_import_dna"
    bl_label = "File handler for .dna files"
    bl_import_operator = "meta_human_dna.import_dna"
    bl_file_extensions = ".dna"

    @classmethod
    def poll_drop(cls, context: "Context") -> bool:
        if not utilities.dependencies_are_valid():
            return False

        return (
            context.region is not None
            and context.region.type == "WINDOW"
            and context.area is not None
            and context.area.ui_type == "VIEW_3D"
        )


class ConvertSelectedToDna(bpy.types.Operator, MetahumanImportProperties):
    """Converts the selected mesh object to a valid mesh that matches the provided base DNA file"""

    bl_idname = "meta_human_dna.convert_selected_to_dna"
    bl_label = "Convert Selected to DNA"

    new_name: bpy.props.StringProperty(
        name="Name", default="", get=callbacks.get_copied_rig_instance_name, set=callbacks.set_copied_rig_instance_name
    )  # pyright: ignore[reportInvalidTypeForm]
    constrain_head_to_body: bpy.props.BoolProperty(
        name="Constrain Head to Body",
        default=True,
        description=(
            "If enabled, the head will be constrained to the body (if available) during the conversion process."
        ),
    )  # pyright: ignore[reportInvalidTypeForm]
    validate_uvs: bpy.props.BoolProperty(
        name="Validate UVs",
        default=True,
        description=(
            "Validates the selected mesh's UVs before trying to perform the conversion. "
            "This helps prevent issues with the conversion process, but can be disabled if "
            "you are sure the mesh is valid and want to skip this step."
        ),
    )  # pyright: ignore[reportInvalidTypeForm]
    uv_tolerance: bpy.props.FloatProperty(
        name="UV Tolerance",
        default=DEFAULT_UV_TOLERANCE,
        description=(
            "The tolerance distance used when considering if 2 UV points are in the "
            "same position. This is used when validating if the selected mesh has the "
            "same UV layout as the template DNA mesh."
        ),
        precision=5,
    )  # pyright: ignore[reportInvalidTypeForm]
    run_calibration: bpy.props.BoolProperty(
        name="Run Calibration",
        default=True,
        description=(
            "Runs the calibration process after converting the selected mesh. This export the DNA to "
            "disk and re-loads it into the rig instance."
        ),
    )  # pyright: ignore[reportInvalidTypeForm]

    # this can be used when invoking the operator programmatically to set the rig instance name
    new_instance_name: bpy.props.StringProperty(default="")  # pyright: ignore[reportInvalidTypeForm]
    new_folder: bpy.props.StringProperty(
        name="Output Folder", default="", subtype="DIR_PATH", options={"PATH_SUPPORTS_BLEND_RELATIVE"}
    )  # pyright: ignore[reportInvalidTypeForm]
    maps_folder: bpy.props.StringProperty(
        default="",
        name="Maps Folder",
        description=(
            "Optionally, this can be set to a folder location for the face wrinkle maps. Textures "
            "following the same naming convention as the metahuman source files will be found and set "
            "on the materials automatically."
        ),
        subtype="DIR_PATH",
        options={"PATH_SUPPORTS_BLEND_RELATIVE"},
    )  # pyright: ignore[reportInvalidTypeForm]

    def execute(self, context: "Context") -> set[str]:  # noqa: PLR0911, PLR0912, PLR0915
        window_manager_properties = context.window_manager.meta_human_dna

        # If values passed to the operator, we update them.
        # This allows clean programmatic access to the operator properties.
        if self.new_folder:
            window_manager_properties.new_folder = self.new_folder
        if self.maps_folder:
            window_manager_properties.maps_folder = self.maps_folder

        selected_object = context.active_object
        new_folder = Path(bpy.path.abspath(window_manager_properties.new_folder))
        new_name = self.new_name or self.new_instance_name
        if not selected_object or selected_object.type != "MESH":
            self.report({"ERROR"}, "You must select a mesh to convert.")
            return {"CANCELLED"}
        if not new_name:
            self.report({"ERROR"}, "You must set a new name.")
            return {"CANCELLED"}
        if not window_manager_properties.new_folder:
            self.report({"ERROR"}, "You must set an output folder.")
            return {"CANCELLED"}
        if not new_folder.exists():
            self.report({"ERROR"}, f"Folder not found: {new_folder}")
            return {"CANCELLED"}
        if round(context.scene.unit_settings.scale_length, 2) != 1.0:
            self.report({"ERROR"}, "The scene unit scale must be set to 1.0")
            return {"CANCELLED"}

        kwargs = {
            "import_face_board": True,
            "import_materials": True,
            "import_vertex_groups": True,
            "import_bones": True,
            "import_mesh": True,
            "import_normals": False,
            "import_shape_keys": False,
            "alternate_maps_folder": window_manager_properties.maps_folder,
        }

        for lod_index in range(NUMBER_OF_HEAD_LODS):
            kwargs[f"import_lod{lod_index}"] = lod_index == 0

        # set the properties
        for key, value in kwargs.items():
            setattr(self.properties, key, value)

        # we don't want to evaluate the dependency graph while importing the DNA
        window_manager_properties.evaluate_dependency_graph = False
        component = None

        base_dna_file = (
            Path(window_manager_properties.base_dna) / f"{window_manager_properties.current_component_type}.dna"
        )
        if not base_dna_file.exists():
            self.report({"ERROR"}, f"Base DNA file not found: {base_dna_file}")
            return {"CANCELLED"}

        if window_manager_properties.current_component_type == "head":
            component = MetaHumanComponentHead(
                name=new_name,
                dna_file_path=base_dna_file,
                component_type="head",
                dna_import_properties=self.properties,  # type: ignore[arg-type]
            )
        elif window_manager_properties.current_component_type == "body":
            component = MetaHumanComponentBody(
                name=new_name,
                dna_file_path=base_dna_file,
                component_type="body",
                dna_import_properties=self.properties,  # type: ignore[arg-type]
            )

        if not component:
            self.report({"ERROR"}, f"Failed to convert component {window_manager_properties.current_component_type}.")
            return {"CANCELLED"}

        # try to separate the selected object by its unreal material first if it has one
        selected_object = component.pre_convert_mesh_cleanup(mesh_object=selected_object)
        if not selected_object:
            window_manager_properties.evaluate_dependency_graph = True
            self.report({"ERROR"}, "The selected object failed to be separated by its material.")
            return {"CANCELLED"}

        # check if the selected object has the same UVs as the base DNA
        if self.validate_uvs:
            success, message = component.validate_conversion(mesh_object=selected_object, tolerance=self.uv_tolerance)
            if not success:
                component.delete()
                window_manager_properties.evaluate_dependency_graph = True
                self.report({"ERROR"}, message)
                return {"CANCELLED"}

        component.ingest(align=False, constrain=False)

        if window_manager_properties.current_component_type == "head":
            callbacks.update_head_output_items(None, bpy.context)  # type: ignore[arg-type]
        elif window_manager_properties.current_component_type == "body":
            callbacks.update_body_output_items(None, bpy.context)  # type: ignore[arg-type]

        component.convert(mesh_object=selected_object, constrain=self.constrain_head_to_body)
        # TODO: Might need to refactor usages of preserve_context decorator. This re-enables the dependency
        # graph evaluation, which we don't want until the end of this operator. So we disable it again here.
        window_manager_properties.evaluate_dependency_graph = False
        selected_object.hide_set(True)
        # populate the output items based on what was imported
        logger.info(f'Finished converting "{window_manager_properties.base_dna}"')

        # set the output folder path
        component.rig_instance.output_folder_path = window_manager_properties.new_folder

        if self.run_calibration:
            # now we can export the new DNA file
            calibrator = DNACalibrator(
                instance=component.rig_instance,
                linear_modifier=component.linear_modifier,
                component_type=window_manager_properties.current_component_type,
                file_name=f"{window_manager_properties.current_component_type}.dna",
            )
            calibrator.run()

            new_dna_file_path = str(new_folder / f"{window_manager_properties.current_component_type}.dna")
            # make the path relative to the blend file if it is saved
            if bpy.data.filepath:
                with contextlib.suppress(ValueError):
                    new_dna_file_path = bpy.path.relpath(new_dna_file_path, start=str(Path(bpy.data.filepath).parent))

            # now we can set the new DNA file path on the component
            if window_manager_properties.current_component_type == "head":
                component.rig_instance.head_dna_file_path = new_dna_file_path
            elif window_manager_properties.current_component_type == "body":
                component.rig_instance.body_dna_file_path = new_dna_file_path

        # now hide the component rig and switch it back to object mode and change the
        # active object to the face board
        utilities.switch_to_object_mode()

        if window_manager_properties.current_component_type == "head" and component.head_rig_object:
            if bpy.context.view_layer:
                bpy.context.view_layer.objects.active = component.face_board_object
            if component.face_board_object:
                utilities.switch_to_pose_mode(component.face_board_object)
            component.head_rig_object.hide_set(True)
        elif window_manager_properties.current_component_type == "body" and component.body_rig_object:
            if bpy.context.view_layer:
                bpy.context.view_layer.objects.active = component.body_mesh_object
            component.body_rig_object.hide_set(True)

        # now we can evaluate the dependency graph again
        window_manager_properties.evaluate_dependency_graph = True
        bpy.ops.meta_human_dna.force_evaluate()  # type: ignore[attr-defined]

        # Ask the user for consent to collect metrics
        bpy.ops.meta_human_dna.metrics_collection_consent("INVOKE_DEFAULT")  # type: ignore[attr-defined]

        return {"FINISHED"}

    def invoke(self, context: "Context", event: bpy.types.Event) -> set[str]:
        return context.window_manager.invoke_props_dialog(self, width=450)  # type: ignore[return-value]

    @classmethod
    def poll(cls, context: "Context") -> bool:
        if not utilities.dependencies_are_valid():
            return False

        selected_object = context.active_object
        properties = context.scene.meta_human_dna
        if selected_object and selected_object.type == "MESH" and selected_object.select_get():
            for instance in properties.rig_instance_list:
                for item in instance.output_head_item_list:
                    if item.scene_object == selected_object:
                        return False
                for item in instance.output_body_item_list:
                    if item.scene_object == selected_object:
                        return False
            return True
        return False

    def _get_path_error(self, folder_path: str) -> str:
        if not folder_path:
            return ""

        if not Path(folder_path).exists():
            return "Folder does not exist"
        if not Path(folder_path).is_dir():
            return "Path is not a folder"
        return ""

    def draw(self, context: "Context"):
        if not self.layout:
            return
        window_manager_properties = context.window_manager.meta_human_dna

        row = self.layout.row()

        column = row.column()
        row_inner = column.row()
        row_inner.label(text="Component Type:")
        row_inner = column.row()
        row_inner.prop(window_manager_properties, "current_component_type", text="")
        column = row.column()
        row_inner = column.row()
        row_inner.label(text="Base DNA:")
        row_inner = column.row()
        row_inner.prop(window_manager_properties, "base_dna", text="")

        row = self.layout.row()
        row.prop(self, "new_name")
        row = self.layout.row()
        row.prop(window_manager_properties, "new_folder")
        row = self.layout.row()
        path_error = self._get_path_error(window_manager_properties.maps_folder)
        if path_error:
            row.alert = True
        row.prop(window_manager_properties, "maps_folder")

        if path_error:
            row = self.layout.row()
            row.alert = True
            row.label(text=path_error, icon="ERROR")

        row = self.layout.row()
        column = row.column()
        column.prop(self, "validate_uvs")
        column = row.column()
        column.enabled = self.validate_uvs
        column.prop(self, "uv_tolerance")
        row = self.layout.row()
        row.prop(self, "constrain_head_to_body")
        row = self.layout.row()
        row.prop(self, "run_calibration")


class GenerateMaterial(bpy.types.Operator):
    """Generates a material for the head mesh object that you can then customize"""

    bl_idname = "meta_human_dna.generate_material"
    bl_label = "Generate Material"

    def execute(self, context: "Context") -> set[str]:
        head = utilities.get_active_head()
        if head and head.head_mesh_object:
            head.import_materials()
        return {"FINISHED"}

    @classmethod
    def poll(cls, _: "Context") -> bool:
        instance = callbacks.get_active_rig_instance()
        return (
            instance is not None
            and instance.head_mesh is not None
            and instance.head_material is None
            and bpy.context.mode == "OBJECT"
        )


class ImportShapeKeys(GenericProgressQueueOperator):
    """Imports the shape keys from the DNA file and their deltas"""

    bl_idname = "meta_human_dna.import_shape_keys"
    bl_label = "Import Shape Keys"

    def validate(self, context: "Context") -> bool:
        return True

    def set_commands_queue(self, context: "Context", component: MetaHumanComponentHead, commands_queue: queue.Queue):
        component.import_shape_keys(commands_queue)
        bpy.ops.meta_human_dna.force_evaluate()  # type: ignore[attr-defined]


class ForceEvaluate(bpy.types.Operator):
    """Force the rig logic to evaluate on the active rig instance"""

    bl_idname = "meta_human_dna.force_evaluate"
    bl_label = "Force Evaluate"

    def execute(self, context: "Context") -> set[str]:
        utilities.teardown_scene()
        utilities.setup_scene()
        instance = callbacks.get_active_rig_instance()
        if instance:
            instance.evaluate()
            # NOTE: Some dependency graph weirdness here. This is necessary to ensure that the rig logic
            # evaluates the pose bones, otherwise bone transform updates won't be applied when the face
            # board updates.
            current_context = utilities.get_current_context()
            if instance.head_rig:
                instance.head_rig.hide_set(False)
                instance.head_rig.hide_viewport = False
                utilities.switch_to_pose_mode(instance.head_rig)

            utilities.set_context(current_context)

        context.window_manager.meta_human_dna.evaluate_dependency_graph = True
        return {"FINISHED"}


class TestSentry(bpy.types.Operator):
    """Test the Sentry error reporting system"""

    bl_idname = "meta_human_dna.test_sentry"
    bl_label = "Test Sentry"

    def execute(self, context: "Context") -> set[str]:
        division_by_zero = 1 / 0  # pyright: ignore[reportUnusedVariable] # noqa: F841
        return {"FINISHED"}


class MigrateLegacyData(bpy.types.Operator):
    """Migrate legacy data to the latest format"""

    bl_idname = "meta_human_dna.migrate_legacy_data"
    bl_label = "Migrate Legacy Data"

    def execute(self, context: "Context") -> set[str]:
        utilities.migrate_legacy_data(context)
        bpy.ops.meta_human_dna.force_evaluate()  # type: ignore[attr-defined]
        return {"FINISHED"}


class OpenBuildToolDocumentation(bpy.types.Operator):
    """Opens the Build Tool documentation in the default web browser"""

    bl_idname = "meta_human_dna.open_build_tool_documentation"
    bl_label = "Open Build Tool Documentation"

    def execute(self, context: "Context") -> set[str]:
        webbrowser.open(ToolInfo.BUILD_TOOL_DOCUMENTATION)
        return {"FINISHED"}


class OpenMetricsCollectionAgreement(bpy.types.Operator):
    """Opens the metrics collection agreement in the default web browser"""

    bl_idname = "meta_human_dna.open_metrics_collection_agreement"
    bl_label = "Open Metrics Collection Agreement"

    def execute(self, context: "Context") -> set[str]:
        webbrowser.open(ToolInfo.METRICS_COLLECTION_AGREEMENT)
        return {"FINISHED"}


class SendToMetaHumanCreator(bpy.types.Operator):
    """Exports the MetaHuman DNA head and body components, as well as, textures in a format supported by MetaHuman Creator."""  # noqa: E501

    bl_idname = "meta_human_dna.send_to_meta_human_creator"
    bl_label = "Send to MetaHuman Creator"

    def execute(self, context: "Context") -> set[str]:
        instance = callbacks.get_active_rig_instance()
        if instance:
            # store the current auto evaluate settings
            auto_evaluate_head = instance.auto_evaluate_head
            auto_evaluate_body = instance.auto_evaluate_body

            # disable auto evaluate while we are exporting
            instance.auto_evaluate_head = False
            instance.auto_evaluate_body = False

            current_context = utilities.get_current_context()

            for attribute_name in ["head_mesh", "head_rig", "body_mesh", "body_rig"]:
                if not getattr(instance, attribute_name):
                    self.report(
                        {"ERROR"},
                        (
                            f"No {attribute_name} set on the active instance. Please ensure you have a "
                            "head and body mesh and rig set before sending to MetaHuman Creator."
                        ),
                    )
                    return {"CANCELLED"}

            if not bpy.path.abspath(instance.output_folder_path) and not bpy.data.filepath:
                self.report({"ERROR"}, "File must be saved to use a relative path")
                return {"CANCELLED"}

            head = utilities.get_active_head()
            body = utilities.get_active_body()
            if not head or not body:
                self.report(
                    {"ERROR"},
                    "No active instance found. Please select an instance from the list under the RigLogic panel.",
                )
                return {"CANCELLED"}

            last_component = None
            for component in [head, body]:
                dna_io_instance: DNAExporter = None  # type: ignore[assignment]
                if instance.output_method == "calibrate":
                    dna_io_instance = DNACalibrator(
                        instance=instance,
                        linear_modifier=component.linear_modifier,
                        file_name=f"{component.component_type}.dna",
                        component_type=component.component_type,
                    )
                elif instance.output_method == "overwrite":
                    dna_io_instance = DNAExporter(
                        instance=instance,
                        linear_modifier=component.linear_modifier,
                        file_name=f"{component.component_type}.dna",
                        component_type=component.component_type,
                    )

                valid, title, message, fix = dna_io_instance.run()
                if not valid:
                    utilities.report_error_panel(title=title, message=message, fix=fix, width=500)
                    return {"CANCELLED"}
                self.report({"INFO"}, message)

                last_component = component

            # write a manifest file to the output folder similar to the MetaHuman Creator DCC export
            if last_component:
                last_component.write_export_manifest()
                bpy.ops.meta_human_dna.force_evaluate()  # type: ignore[attr-defined]

            utilities.set_context(current_context)

            # restore the auto evaluate settings
            instance.auto_evaluate_head = auto_evaluate_head
            instance.auto_evaluate_body = auto_evaluate_body

        return {"FINISHED"}


class ExportSelectedComponent(bpy.types.Operator):
    """Export only the selected component to a single DNA file. No textures or supporting files will be exported."""

    bl_idname = "meta_human_dna.export_selected_component"
    bl_label = "Export Selected Component"

    def execute(self, context: "Context") -> set[str]:
        instance = callbacks.get_active_rig_instance()
        if not instance:
            self.report(
                {"ERROR"},
                "No active rig instance found. Please select an instance from the list under the Rig Instance panel.",
            )
            return {"CANCELLED"}

        current_context = utilities.get_current_context()
        component = None
        if instance.output_component == "head":
            component = utilities.get_active_head()
        elif instance.output_component == "body":
            component = utilities.get_active_body()

        if component:
            if not bpy.path.abspath(instance.output_folder_path) and not bpy.data.filepath:
                self.report({"ERROR"}, "File must be saved to use a relative path")
                return {"CANCELLED"}

            dna_io_instance: DNAExporter = None  # type: ignore[assignment]
            if instance.output_method == "calibrate":
                dna_io_instance = DNACalibrator(
                    instance=instance,
                    linear_modifier=component.linear_modifier,
                    file_name=f"{component.component_type}.dna",
                    component_type=component.component_type,
                    textures=False,
                )
            elif instance.output_method == "overwrite":
                dna_io_instance = DNAExporter(
                    instance=instance,
                    linear_modifier=component.linear_modifier,
                    file_name=f"{component.component_type}.dna",
                    component_type=component.component_type,
                    textures=False,
                )

            valid, title, message, fix = dna_io_instance.run()
            bpy.ops.meta_human_dna.force_evaluate()  # type: ignore[attr-defined]

            if not valid:
                utilities.report_error_panel(title=title, message=message, fix=fix, width=300)
                return {"CANCELLED"}
            self.report({"INFO"}, message)

        utilities.set_context(current_context)

        return {"FINISHED"}


class MirrorSelectedBones(bpy.types.Operator):
    """Mirrors the selected bone positions to the other side of the head mesh"""

    bl_idname = "meta_human_dna.mirror_selected_bones"
    bl_label = "Mirror Selected Bones"

    def execute(self, context: "Context") -> set[str]:
        head = utilities.get_active_head()
        if head:
            success, message = head.mirror_selected_bones()
            if not success:
                self.report({"ERROR"}, message)
                return {"CANCELLED"}
        return {"FINISHED"}

    @classmethod
    def poll(cls, context: "Context") -> bool:
        return callbacks.poll_head_rig_bone_selection(cls, context)  # type: ignore[arg-type]


class ShrinkWrapVertexGroup(bpy.types.Operator):
    """Shrink wraps the active vertex group on the head mesh using the shrink wrap modifier"""

    bl_idname = "meta_human_dna.shrink_wrap_vertex_group"
    bl_label = "Shrink Wrap Active Group"

    def execute(self, context: "Context") -> set[str]:
        current_component_type = context.window_manager.meta_human_dna.current_component_type
        head = utilities.get_active_head()
        body = utilities.get_active_body()
        if head and current_component_type == "head":
            head.shrink_wrap_vertex_group()
        elif body and current_component_type == "body":
            body.shrink_wrap_vertex_group()
        return {"FINISHED"}


class AutoFitSelectedBones(bpy.types.Operator):
    """Auto-fits the selected bones to the head mesh"""

    bl_idname = "meta_human_dna.auto_fit_selected_bones"
    bl_label = "Auto Fit Selected Bones"

    def execute(self, context: "Context") -> set[str]:
        head = utilities.get_active_head()
        if head and head.head_mesh_object and head.head_rig_object:
            if bpy.context.mode != "POSE":
                self.report({"ERROR"}, "You must be in pose mode")
                return {"CANCELLED"}

            if not bpy.context.selected_pose_bones:
                self.report({"ERROR"}, "You must at least have one pose bone selected")
                return {"CANCELLED"}

            for pose_bone in bpy.context.selected_pose_bones:
                if pose_bone.id_data != head.head_rig_object and pose_bone.id_data:
                    self.report(
                        {"ERROR"},
                        (
                            f'The selected bone "{pose_bone.id_data.name}:{pose_bone.name}" is not associated '
                            'with the rig instance "{head.rig_instance.name}"'
                        ),
                    )
                    return {"CANCELLED"}

            utilities.auto_fit_bones(
                mesh_object=head.head_mesh_object,
                armature_object=head.head_rig_object,
                dna_reader=head.dna_reader,
                only_selected=True,
            )

        return {"FINISHED"}

    @classmethod
    def poll(cls, context: "Context") -> bool:
        return callbacks.poll_head_rig_bone_selection(cls, context)  # type: ignore[arg-type]


class RevertBoneTransformsToDna(bpy.types.Operator):
    """Revert the selected bone's transforms to their values in the DNA file"""

    bl_idname = "meta_human_dna.revert_bone_transforms_to_dna"
    bl_label = "Revert Bone Transforms to DNA"

    def execute(self, context: "Context") -> set[str]:
        head = utilities.get_active_head()
        if head:
            if bpy.context.mode != "POSE":
                self.report({"ERROR"}, "Must be in pose mode")
                return {"CANCELLED"}

            if not head.rig_instance.head_rig:
                self.report({"ERROR"}, f'"{head.rig_instance.name}" does not have a head rig assigned')
                return {"CANCELLED"}

            head.revert_bone_transforms_to_dna()
        return {"FINISHED"}

    @classmethod
    def poll(cls, context: "Context") -> bool:
        return callbacks.poll_head_rig_bone_selection(cls, context)  # type: ignore[arg-type]


class ShapeKeyOperatorBase(bpy.types.Operator):
    shape_key_name: bpy.props.StringProperty(name="Shape Key Name")  # pyright: ignore[reportInvalidTypeForm]

    def get_select_shape_key(self, instance: "RigInstance") -> tuple[int | None, bpy.types.ShapeKey | None, int | None]:
        # find the related mesh objects for the head rig
        channel_index = instance.head_channel_name_to_index_lookup[self.shape_key_name]
        for shape_key_block in instance.head_shape_key_blocks.get(channel_index, []):
            if not shape_key_block.id_data:
                continue
            for index, key_block in enumerate(shape_key_block.id_data.key_blocks):  # type: ignore[attr-defined]
                if key_block.name == self.shape_key_name:
                    # set this as the active shape key so we can edit it
                    return index, key_block, channel_index
        return None, None, None

    def lock_all_other_shape_keys(self, mesh_object: bpy.types.Object, key_block: bpy.types.ShapeKey):
        mesh_object.hide_set(False)
        if bpy.context.view_layer:
            bpy.context.view_layer.objects.active = mesh_object

        # make sure the armature modifier is visible on mesh in edit mode
        for modifier in mesh_object.modifiers:
            if modifier.type == "ARMATURE":
                modifier.show_in_editmode = True
                modifier.show_on_cage = True

        if mesh_object.data and mesh_object.type == "MESH":
            shape_keys = mesh_object.data.shape_keys  # pyright: ignore[reportAttributeAccessIssue]
            if not shape_keys:
                return

            # lock all shape keys except the one we are editing
            for _key_block in shape_keys.key_blocks:
                _key_block.lock_shape = _key_block.name != self.shape_key_name

            # Unlock and set the active shape key block to the one we are editing
            key_block.lock_shape = False
            mesh_object.active_shape_key_index = shape_keys.key_blocks.find(self.shape_key_name)
            mesh_object.use_shape_key_edit_mode = True

    def validate(self, context: "Context", instance: "RigInstance") -> bool | tuple:
        mesh_object = bpy.data.objects.get(instance.active_shape_key_mesh_name)
        if not mesh_object:
            self.report({"ERROR"}, "The mesh object associated with the active shape key is not found")
            return False

        if self.shape_key_name == SHAPE_KEY_BASIS_NAME and mesh_object.data and mesh_object.type == "MESH":
            shape_keys = mesh_object.data.shape_keys  # pyright: ignore[reportAttributeAccessIssue]
            if not shape_keys:
                self.report({"ERROR"}, "The mesh object does not have shape keys")
                return False

            key_block = shape_keys.key_blocks.get(SHAPE_KEY_BASIS_NAME)
            return None, key_block, None, mesh_object

        if not instance.head_channel_name_to_index_lookup:
            instance.initialize()
            if not instance.head_channel_name_to_index_lookup:
                self.report({"ERROR"}, "The shape key blocks are not initialized")
                return False

        shape_key_index, key_block, channel_index = self.get_select_shape_key(instance)
        if shape_key_index is not None:
            mesh_object.active_shape_key_index = shape_key_index
        else:
            self.report({"ERROR"}, f'The shape key "{self.shape_key_name}" is not found')
            return False

        # Set the active shape key in the shape key list to the one we are editing
        for i, _shape_key in enumerate(instance.shape_key_list):
            if _shape_key.name == self.shape_key_name:
                instance.shape_key_list_active_index = i
                break

        return shape_key_index, key_block, channel_index, mesh_object


class ReportError(bpy.types.Operator):
    bl_idname = "meta_human_dna.report_error"
    bl_label = "Error"

    message: bpy.props.StringProperty(default="")  # pyright: ignore[reportInvalidTypeForm]

    def execute(self, context: "Context") -> set[str]:
        self.report({"ERROR"}, self.message)
        return {"CANCELLED"}


class ReportErrorWithFix(ShapeKeyOperatorBase):
    """Reports and error message to the user with a optional fix"""

    bl_idname = "meta_human_dna.report_error_with_fix"
    bl_label = "Error"

    title: bpy.props.StringProperty(default="")  # pyright: ignore[reportInvalidTypeForm]
    message: bpy.props.StringProperty(default="")  # pyright: ignore[reportInvalidTypeForm]
    width: bpy.props.IntProperty(default=300)  # pyright: ignore[reportInvalidTypeForm]

    def execute(self, context: "Context") -> set[str]:
        wm = context.window_manager
        fix = wm.meta_human_dna.errors.get(self.title, {}).get("fix", None)
        if fix:
            fix()
        return {"FINISHED"}

    def invoke(self, context: "Context", event: bpy.types.Event) -> set[str] | None:
        wm = context.window_manager
        if not wm:
            return None

        fix = wm.meta_human_dna.errors.get(self.title, {}).get("fix", None)
        return wm.invoke_props_dialog(self, confirm_text="Fix" if fix else "OK", cancel_default=False, width=self.width)  # type: ignore[return-value]

    def draw(self, context: "Context"):
        if not self.layout:
            return

        for line in self.title.split("\n"):
            row = self.layout.row()
            row.scale_y = 1.5
            row.label(text=line)
        for line in self.message.split("\n"):
            row = self.layout.row()
            row.alert = True
            row.label(text=line)


class MetricsCollectionConsent(bpy.types.Operator):
    """Tell the user that we collect metrics and ask for their consent"""

    bl_idname = "meta_human_dna.metrics_collection_consent"
    bl_label = "MetaHuman DNA Addon Metrics"

    def execute(self, context: "Context") -> set[str]:
        addon_preferences = utilities.get_addon_preferences()
        if not addon_preferences:
            return {"CANCELLED"}
        addon_preferences.metrics_collection = True
        utilities.init_sentry()
        bpy.ops.meta_human_dna.force_evaluate()  # type: ignore[attr-defined]
        return {"FINISHED"}

    def invoke(self, context: "Context", event: bpy.types.Event) -> set[str] | None:
        wm = context.window_manager
        if not wm:
            return None

        addon_preferences = utilities.get_addon_preferences()
        if not addon_preferences:
            return {"CANCELLED"}

        current_timestamp = datetime.now(UTC).timestamp()

        if addon_preferences.metrics_collection:
            utilities.init_sentry()
            return {"FINISHED"}

        if bpy.app.online_access and addon_preferences.next_metrics_consent_timestamp < current_timestamp:
            return wm.invoke_props_dialog(self, confirm_text="Allow", cancel_default=False, width=500)  # type: ignore[return-value]
        if bpy.app.online_access and addon_preferences.metrics_collection:
            utilities.init_sentry()

        return {"FINISHED"}

    def cancel(self, context: "Context") -> None:
        addon_preferences = utilities.get_addon_preferences()
        if not addon_preferences:
            return
        # wait 30 days before asking again
        addon_preferences.next_metrics_consent_timestamp = (datetime.now(UTC) + timedelta(days=30)).timestamp()
        addon_preferences.metrics_collection = False
        bpy.ops.meta_human_dna.force_evaluate()  # type: ignore[attr-defined]

    def draw(self, context: "Context"):
        if not self.layout:
            return

        row = self.layout.row()
        row.label(text="We collect anonymous metrics and bug reports to help improve the MetaHuman DNA addon.")
        row = self.layout.row()
        row.label(text="No personal data is collected.")
        row = self.layout.row()
        row.label(text="Will you allow us to collect bug reports?")
        row.operator("meta_human_dna.open_metrics_collection_agreement", text="", icon="URL")


class SculptThisShapeKey(ShapeKeyOperatorBase):
    """Sculpt this shape key"""

    bl_idname = "meta_human_dna.sculpt_this_shape_key"
    bl_label = "Edit this Shape Key"

    def execute(self, context: "Context") -> set[str]:
        instance = callbacks.get_active_rig_instance()
        if instance and instance.head_rig:
            result = self.validate(context, instance)
            if not result:
                return {"CANCELLED"}

            _, key_block, _, mesh_object = result  # type: ignore[return-value]

            # solo the shape key before sculpting if the solo option is enabled
            if instance.solo_shape_key:
                instance.solo_head_shape_key_value(shape_key=key_block)

            self.lock_all_other_shape_keys(mesh_object, key_block)
            utilities.switch_to_sculpt_mode(mesh_object)
            mesh_object.show_only_shape_key = False

        return {"FINISHED"}


class EditThisShapeKey(ShapeKeyOperatorBase):
    """Edit this shape key"""

    bl_idname = "meta_human_dna.edit_this_shape_key"
    bl_label = "Edit this Shape Key"

    def execute(self, context: "Context") -> set[str]:
        instance = callbacks.get_active_rig_instance()
        if instance and instance.head_rig:
            result = self.validate(context, instance)
            if not result:
                return {"CANCELLED"}

            _, key_block, _, mesh_object = result  # type: ignore[return-value]

            # solo the shape key before editing if the solo option is enabled
            if instance.solo_shape_key:
                instance.solo_head_shape_key_value(shape_key=key_block)

            self.lock_all_other_shape_keys(mesh_object, key_block)
            utilities.switch_to_edit_mode(mesh_object)
            mesh_object.show_only_shape_key = False

        return {"FINISHED"}


class ReImportThisShapeKey(ShapeKeyOperatorBase):
    """Re-Import this shape key from the DNA file"""

    bl_idname = "meta_human_dna.reimport_this_shape_key"
    bl_label = "Re-Import this Shape Key"

    shape_key_name: bpy.props.StringProperty(name="Shape Key Name")  # pyright: ignore[reportInvalidTypeForm]

    def execute(self, context: "Context") -> set[str]:
        head = utilities.get_active_head()
        if head and head.rig_instance:
            instance = head.rig_instance
            result = self.validate(context, instance)  # type: ignore[arg-type]
            if not result:
                return {"CANCELLED"}

            _, shape_key_block, _, mesh_object = result  # type: ignore[return-value]
            mesh_index = {v.name: k for k, v in instance.head_mesh_index_lookup.items()}.get(mesh_object.name)
            if mesh_index is None:
                self.report({"ERROR"}, f'The mesh index for "{mesh_object.name}" is not found')
                return {"CANCELLED"}

            current_context = utilities.get_current_context()
            utilities.switch_to_object_mode()
            short_name = self.shape_key_name.split("__", 1)[-1]

            if not instance.generate_neutral_shapes:
                reader = get_dna_reader(file_path=instance.head_dna_file_path)

                # determine the shape key index in the DNA file
                shape_key_index = None
                for index in range(reader.getBlendShapeTargetCount(mesh_index)):
                    channel_index = reader.getBlendShapeChannelIndex(mesh_index, index)
                    channel_name = reader.getBlendShapeChannelName(channel_index)
                    if channel_name == short_name:
                        shape_key_index = index
                        break

                if shape_key_index is None:
                    self.report({"ERROR"}, f'The shape key "{short_name}" is not found in the DNA file')
                    return {"CANCELLED"}

                # DNA is Y-up, Blender is Z-up, so we need to rotate the deltas
                rotation_matrix = Matrix.Rotation(math.radians(90), 4, "X")  # type: ignore[arg-type]

                delta_x_values = reader.getBlendShapeTargetDeltaXs(mesh_index, shape_key_index)
                delta_y_values = reader.getBlendShapeTargetDeltaYs(mesh_index, shape_key_index)
                delta_z_values = reader.getBlendShapeTargetDeltaZs(mesh_index, shape_key_index)
                vertex_indices = reader.getBlendShapeTargetVertexIndices(mesh_index, shape_key_index)

                # the new vertex layout is the original vertex layout with the deltas from the dna applied
                for vertex_index, delta_x, delta_y, delta_z in zip(
                    vertex_indices, delta_x_values, delta_y_values, delta_z_values, strict=False
                ):
                    try:
                        delta = Vector((delta_x, delta_y, delta_z)) * head.linear_modifier
                        rotated_delta = rotation_matrix @ delta

                        # set the positions of the shape key vertices
                        shape_key_block.data[vertex_index].co = (
                            mesh_object.data.vertices[vertex_index].co.copy() + rotated_delta
                        )
                    except IndexError:
                        logger.warning(
                            f'Vertex index {vertex_index} is missing for shape key "{short_name}". '
                            f'Was this deleted on the base mesh "{mesh_object.name}"?'
                        )
            else:
                # reset the shape key to the basis shape key
                shape_key_block.data.foreach_set("co", [v.co for v in mesh_object.data.vertices])

            utilities.set_context(current_context)
        return {"FINISHED"}


class DuplicateRigInstance(bpy.types.Operator):
    """Duplicate the active Rig Instance. This copies all it's associated data and offsets it to the right"""

    bl_idname = "meta_human_dna.duplicate_rig_instance"
    bl_label = "Duplicate Rig Instance"

    new_name: bpy.props.StringProperty(
        name="New Name",
        default="",
        get=callbacks.get_copied_rig_instance_name,
        set=callbacks.set_copied_rig_instance_name,
    )  # pyright: ignore[reportInvalidTypeForm]
    new_folder: bpy.props.StringProperty(
        name="New Output Folder", default="", subtype="DIR_PATH", options={"PATH_SUPPORTS_BLEND_RELATIVE"}
    )  # pyright: ignore[reportInvalidTypeForm]

    def execute(self, context: "Context") -> set[str]:  # noqa: PLR0912, PLR0915
        new_folder = Path(bpy.path.abspath(self.new_folder))
        if not bpy.path.abspath(self.new_folder) and not bpy.data.filepath:
            self.report({"ERROR"}, "File must be saved to use a relative path")
            return {"CANCELLED"}
        if not self.new_name:
            self.report({"ERROR"}, "You must set a new name.")
            return {"CANCELLED"}
        if not self.new_folder:
            self.report({"ERROR"}, "You must set an output folder.")
            return {"CANCELLED"}
        if not new_folder.exists():
            self.report({"ERROR"}, f"Folder not found: {new_folder}")
            return {"CANCELLED"}

        instance = callbacks.get_active_rig_instance()
        if instance:
            for component_type, mesh_object, rig_object in [
                ("body", instance.body_mesh, instance.body_rig),
                ("head", instance.head_mesh, instance.head_rig),
            ]:
                if mesh_object and rig_object:
                    new_mesh_object = utilities.copy_mesh(
                        mesh_object=mesh_object,
                        new_mesh_name=mesh_object.name.replace(instance.name, self.new_name),
                        modifiers=False,
                        materials=True,
                    )
                    new_rig_object = utilities.copy_armature(
                        armature_object=rig_object,
                        new_armature_name=rig_object.name.replace(instance.name, self.new_name),
                    )
                    # move the new rig to the right collection
                    utilities.move_to_collection(
                        scene_objects=[new_mesh_object], collection_name=f"{self.new_name}_lod0", exclusively=True
                    )
                    # move the new rig to the right collection
                    utilities.move_to_collection(
                        scene_objects=[new_rig_object], collection_name=self.new_name, exclusively=True
                    )
                    # move the face board also to the this collection
                    utilities.move_to_collection(
                        scene_objects=[instance.face_board], collection_name=self.new_name, exclusively=False
                    )

                    # duplicate the mesh materials
                    new_mesh_material = utilities.copy_materials(
                        mesh_object=new_mesh_object,
                        old_prefix=instance.name,
                        new_prefix=self.new_name,
                        new_folder=new_folder / self.new_name,
                    )
                    # duplicate the texture logic node
                    if new_mesh_material:
                        texture_logic_node = getattr(callbacks, f"get_{component_type}_texture_logic_node")(
                            new_mesh_material
                        )
                        if texture_logic_node and texture_logic_node.node_tree:
                            node_name_constant = getattr(constants, f"{component_type.upper()}_TEXTURE_LOGIC_NODE_NAME")
                            new_name = f"{self.new_name}_{node_name_constant}"
                            texture_logic_node.label = new_name
                            texture_logic_node_tree_copy = texture_logic_node.node_tree.copy()
                            texture_logic_node_tree_copy.name = new_name
                            texture_logic_node.node_tree = texture_logic_node_tree_copy

                    # match the hide state of the original
                    new_mesh_object.hide_set(mesh_object.hide_get())
                    new_rig_object.hide_set(rig_object.hide_get())

                    # assign the rig to the duplicated mesh
                    modifier = new_mesh_object.modifiers.new(name="Armature", type="ARMATURE")
                    modifier.object = new_rig_object
                    new_mesh_object.parent = new_rig_object

                    # now we need to duplicate the output items
                    for item in getattr(instance, f"output_{component_type}_item_list"):
                        if item.scene_object and item.scene_object.type == "MESH":
                            if item.scene_object == mesh_object:
                                continue

                            new_extra_mesh_object = utilities.copy_mesh(
                                mesh_object=item.scene_object,
                                new_mesh_name=item.scene_object.name.replace(instance.name, self.new_name),
                                modifiers=False,
                                materials=True,
                            )

                            lod_index = utilities.get_lod_index(new_extra_mesh_object.name)
                            if lod_index == -1:
                                lod_index = 0

                            # move the new mesh to the right collection
                            utilities.move_to_collection(
                                scene_objects=[new_extra_mesh_object],
                                collection_name=f"{self.new_name}_lod{lod_index}",
                                exclusively=True,
                            )
                            main_collection = bpy.data.collections.get(self.new_name)
                            lod_collection = bpy.data.collections.get(f"{self.new_name}_lod{lod_index}")
                            if main_collection and lod_collection and bpy.context.scene:
                                # unlink the lod collection from the scene collection if it exists
                                if lod_collection in bpy.context.scene.collection.children.values():
                                    bpy.context.scene.collection.children.unlink(lod_collection)
                                # link the lod collection to the main collection if it is not already linked
                                if lod_collection not in main_collection.children.values():
                                    main_collection.children.link(lod_collection)

                            # assign the rig to the duplicated extra mesh
                            modifier = new_extra_mesh_object.modifiers.new(name="Armature", type="ARMATURE")
                            modifier.object = new_rig_object
                            new_extra_mesh_object.parent = new_rig_object

                            # match the hide state of the original
                            new_extra_mesh_object.hide_set(item.scene_object.hide_get())
                            new_extra_mesh_object.hide_viewport = item.scene_object.hide_viewport

                            # duplicate the extra mesh's materials
                            utilities.copy_materials(
                                mesh_object=new_extra_mesh_object,
                                old_prefix=instance.name,
                                new_prefix=self.new_name,
                                new_folder=new_folder / self.new_name,
                            )

                    # move the duplicated rig to the right of the last mesh
                    last_instance = context.scene.meta_human_dna.rig_instance_list[-1]

                    if component_type == "body":
                        new_rig_object.location.x = utilities.get_bounding_box_left_x(last_instance.body_mesh) - (
                            utilities.get_bounding_box_width(last_instance.body_mesh) / 2
                        )

                    if component_type == "head" and last_instance.body_rig:
                        # Align the head rig with the body rig if it exists
                        body_object_head_bone = last_instance.body_rig.pose.bones.get("head")
                        head_object_head_bone = new_rig_object.pose.bones.get("head")
                        if body_object_head_bone and head_object_head_bone:
                            # get the location of the body head bone and the head head bone in world space
                            body_head_location = (
                                body_object_head_bone.id_data.matrix_world @ body_object_head_bone.matrix
                            ).to_translation()
                            head_head_location = (
                                head_object_head_bone.id_data.matrix_world @ head_object_head_bone.matrix
                            ).to_translation()
                            delta = body_head_location - head_head_location
                            # move the head rig object to align with the body rig head bone
                            new_rig_object.location += delta
                    # otherwise move it to the right of the last instance's head mesh
                    elif component_type == "head":
                        new_rig_object.location.x = utilities.get_bounding_box_left_x(last_instance.head_mesh) - (
                            utilities.get_bounding_box_width(last_instance.head_mesh) / 2
                        )

                    new_dna_file_path = new_folder / self.new_name / f"{component_type}.dna"
                    new_dna_file_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy(instance.head_dna_file_path, new_dna_file_path)

                    # add the duplicated instance to the list if it doesn't already exist
                    for _rig_instance in context.scene.meta_human_dna.rig_instance_list:
                        if _rig_instance.name == self.new_name:
                            new_instance = _rig_instance
                            break
                    else:
                        new_instance = context.scene.meta_human_dna.rig_instance_list.add()

                    # now set the values on the instance
                    new_instance.name = self.new_name
                    setattr(new_instance, f"{component_type}_dna_file_path", str(new_dna_file_path))
                    new_instance.active_lod = instance.active_lod
                    new_instance.active_material_preview = instance.active_material_preview
                    new_instance.face_board = instance.face_board
                    setattr(new_instance, f"{component_type}_mesh", new_mesh_object)
                    setattr(new_instance, f"{component_type}_rig", new_rig_object)
                    setattr(new_instance, f"{component_type}_material", new_mesh_material)
                    new_instance.output_folder_path = self.new_folder

                    # set the new instance as the active one
                    context.scene.meta_human_dna.rig_instance_list_active_index = (
                        len(context.scene.meta_human_dna.rig_instance_list) - 1
                    )

        return {"FINISHED"}

    def invoke(self, context: "Context", event: bpy.types.Event) -> set[str] | None:
        return context.window_manager.invoke_props_dialog(self, width=450)  # type: ignore[return-value]

    @classmethod
    def poll(cls, _: "Context") -> bool:
        return callbacks.get_active_rig_instance() is not None

    def draw(self, context: "Context"):
        if not self.layout:
            return

        self.layout.prop(self, "new_name")
        self.layout.prop(self, "new_folder")


class AddRigLogicTextureNode(bpy.types.Operator):
    """Add a new Rig Logic Texture Node to the active material. This is used to control the wrinkle map blending on Metahuman faces"""  # noqa: E501

    bl_idname = "meta_human_dna.add_rig_logic_texture_node"
    bl_label = "Add Rig Logic Texture Node"

    @classmethod
    def get_active_material(cls, context: "Context") -> bpy.types.Material | None:
        space = context.space_data
        if space and space.type == "NODE_EDITOR":
            node_tree = space.node_tree  # type: ignore[attr-defined]
            for material in bpy.data.materials:
                if material.node_tree == node_tree:
                    return material
        return None

    @classmethod
    def poll(cls, context: "Context") -> bool | None:
        space = context.space_data
        node_tree = getattr(space, "node_tree", None)
        if node_tree and node_tree.type == "SHADER":
            active_material = cls.get_active_material(context)
            if not active_material:
                return False

            return bool(not callbacks.get_head_texture_logic_node(active_material))
        return None

    def execute(self, context: "Context") -> set[str]:
        space = context.space_data
        node_tree = space.node_tree  # type: ignore[attr-defined]
        cursor_location = space.cursor_location  # type: ignore[attr-defined]

        active_material = self.get_active_material(context)
        if not active_material:
            self.report({"ERROR"}, "Could not find the active material")
            return {"CANCELLED"}

        texture_logic_node = utilities.import_head_texture_logic_node()
        if not texture_logic_node:
            self.report({"ERROR"}, "Could not import the Texture Logic Node")
            return {"CANCELLED"}

        node = node_tree.nodes.new(type="ShaderNodeGroup")
        node.name = f"{active_material.name}_{HEAD_TEXTURE_LOGIC_NODE_NAME}"
        node.label = f"{active_material.name} {HEAD_TEXTURE_LOGIC_NODE_LABEL}"
        node.node_tree = texture_logic_node
        node.location = cursor_location
        return {"FINISHED"}


class UILIST_ADDON_PREFERENCES_OT_extra_dna_entry_remove(GenericUIListOperator, bpy.types.Operator):
    """Remove the selected entry from the list"""

    bl_idname = "meta_human_dna.addon_preferences_extra_dna_entry_remove"
    bl_label = "Remove Selected Entry"

    def execute(self, context: "Context") -> set[str]:
        addon_preferences = utilities.get_addon_preferences()
        if not addon_preferences:
            return {"CANCELLED"}
        my_list = addon_preferences.extra_dna_folder_list
        active_index = addon_preferences.extra_dna_folder_list_active_index
        my_list.remove(active_index)
        to_index = min(active_index, len(my_list) - 1)
        addon_preferences.extra_dna_folder_list_active_index = to_index
        return {"FINISHED"}


class UILIST_ADDON_PREFERENCES_OT_extra_dna_entry_add(GenericUIListOperator, bpy.types.Operator):
    """Add an entry to the list after the current active item"""

    bl_idname = "meta_human_dna.addon_preferences_extra_dna_entry_add"
    bl_label = "Add Entry"

    def execute(self, context: "Context") -> set[str]:
        addon_preferences = utilities.get_addon_preferences()
        if not addon_preferences:
            return {"CANCELLED"}
        my_list = addon_preferences.extra_dna_folder_list
        active_index = addon_preferences.extra_dna_folder_list_active_index
        to_index = min(len(my_list), active_index + 1)
        my_list.add()
        my_list.move(len(my_list) - 1, to_index)
        addon_preferences.extra_dna_folder_list_active_index = to_index
        return {"FINISHED"}


class UILIST_RIG_INSTANCE_OT_entry_remove(GenericUIListOperator, bpy.types.Operator):
    """Remove the selected entry from the list"""

    bl_idname = "meta_human_dna.rig_instance_entry_remove"
    bl_label = "Remove Selected Entry"

    delete_associated_data: bpy.props.BoolProperty(
        name="Delete associated data",
        description="Delete all associated objects and collections linked to this rig instance",
        default=True,
    )  # pyright: ignore[reportInvalidTypeForm]

    def execute(self, context: "Context") -> set[str]:
        my_list = context.scene.meta_human_dna.rig_instance_list

        if self.delete_associated_data:
            instance = context.scene.meta_human_dna.rig_instance_list[self.active_index]
            for component_type in ["body", "head"]:
                for item in getattr(instance, f"output_{component_type}_item_list"):
                    if item.scene_object:
                        bpy.data.objects.remove(item.scene_object, do_unlink=True)
                    if item.image_object:
                        bpy.data.images.remove(item.image_object, do_unlink=True)

                # remove the collections for the component type
                for collection_name in [instance.name] + [
                    f"{instance.name}_{component_type}_lod{i}" for i in range(NUMBER_OF_HEAD_LODS)
                ]:
                    collection = bpy.data.collections.get(collection_name)
                    if collection:
                        bpy.data.collections.remove(collection, do_unlink=True)

        my_list.remove(self.active_index)
        to_index = min(self.active_index, len(my_list) - 1)
        context.scene.meta_human_dna.rig_instance_list_active_index = to_index
        return {"FINISHED"}

    def invoke(self, context: "Context", event: bpy.types.Event) -> set[str] | None:
        instance = context.scene.meta_human_dna.rig_instance_list[self.active_index]
        self.instance_name = instance.name if instance else "this instance"
        return context.window_manager.invoke_props_dialog(  # type: ignore[return-value]
            self, title=f"Remove: {self.instance_name}", confirm_text="Remove", width=400
        )

    def draw(self, context: "Context"):
        if not self.layout:
            return

        row = self.layout.row()
        row.label(text=f"Are you sure you want to remove the '{self.instance_name}' rig instance?", icon="ERROR")
        row = self.layout.row()
        row.prop(self, "delete_associated_data")


class UILIST_RIG_INSTANCE_OT_entry_add(GenericUIListOperator, bpy.types.Operator):
    """Add an entry to the list after the current active item"""

    bl_idname = "meta_human_dna.rig_instance_entry_add"
    bl_label = "Add Entry"

    def execute(self, context: "Context") -> set[str]:
        utilities.add_rig_instance()
        return {"FINISHED"}

    @classmethod
    def poll(cls, _: "Context") -> bool:
        return utilities.dependencies_are_valid()


class UILIST_RIG_INSTANCE_OT_entry_move(GenericUIListOperator, bpy.types.Operator):
    """Move an entry in the list up or down"""

    bl_idname = "meta_human_dna.rig_instance_entry_move"
    bl_label = "Move Entry"

    direction: bpy.props.EnumProperty(
        name="Direction",
        items=(
            ("UP", "UP", "UP"),
            ("DOWN", "DOWN", "DOWN"),
        ),
        default="UP",
    )  # pyright: ignore[reportInvalidTypeForm]

    def execute(self, context: "Context") -> set[str]:
        my_list = context.scene.meta_human_dna.rig_instance_list
        delta = {
            "DOWN": 1,
            "UP": -1,
        }[self.direction]

        to_index = (self.active_index + delta) % len(my_list)

        from_instance = context.scene.meta_human_dna.rig_instance_list[self.active_index]
        to_instance = context.scene.meta_human_dna.rig_instance_list[to_index]

        if from_instance.body_rig and to_instance.body_rig:
            to_x = to_instance.body_rig.location.x
            from_x = from_instance.body_rig.location.x

            # swap the x locations of the body rigs
            to_instance.body_rig.location.x = from_x
            from_instance.body_rig.location.x = to_x
            # swap the x locations of the head rigs
            to_instance.head_rig.location.x = from_x
            from_instance.head_rig.location.x = to_x
            # swap the x locations of the face boards
            to_instance.face_board.location.x += from_x - to_x
            from_instance.face_board.location.x += to_x - from_x

        elif from_instance.head_rig and to_instance.head_rig:
            to_x = to_instance.head_rig.location.x
            from_x = from_instance.head_rig.location.x

            # swap the x locations of the head rigs
            to_instance.head_rig.location.x = from_x
            from_instance.head_rig.location.x = to_x
            # swap the x locations of the face boards
            to_instance.face_board.location.x += from_x - to_x
            from_instance.face_board.location.x += to_x - from_x

        my_list.move(self.active_index, to_index)
        context.scene.meta_human_dna.rig_instance_list_active_index = to_index
        return {"FINISHED"}
