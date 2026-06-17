# standard library imports
import logging  # noqa: I001
import math

from pathlib import Path
from pprint import pformat

# third party imports
import bpy

from mathutils import Euler, Matrix, Quaternion, Vector

# local imports
from . import utilities
from .constants import FLOATING_POINT_PRECISION, IS_BLENDER_5, SCALE_FACTOR, SHAPE_KEY_NAME_MAX_LENGTH, ToolInfo
from .ui import callbacks
from .typing import *  # noqa: F403


MEMORY_RESOURCE_SIZE = 1024 * 1024 * 4  # 4MB
MEMORY_RESOURCE_ALIGNMENT = 16
ATTR_COUNT_PER_QUATERNION_JOINT = 10
ATTR_COUNT_PER_EULER_JOINT = 9

logger = logging.getLogger(__name__)

# Deferred evaluation state: Handlers can run in a restricted context that blocks writes to
# content ID classes (pose bones,shape keys, materials). We collect pending evaluations in the
# handler and apply them via a zero-delay timer callback which runs in the main event loop with full write access.
#
# We store the rig instance *name* (its unique identifier) rather than the RigInstance
# PropertyGroup wrapper itself. An undo can free and reallocate the rig_instance_list
# collection items between the time the handler queues an evaluation and the time the timer
# fires, which would leave a dangling wrapper and crash when its RNA data is accessed.
_pending_evaluations: list[tuple[str, "ComponentType"]] = []


def cancel_pending_evaluations() -> None:
    """Cancel any queued deferred evaluation and unregister the timer.

    Called before operations that can invalidate the queued rig instances (e.g. undo or
    loading a new file) so the timer never dereferences freed data.
    """
    if bpy.app.timers.is_registered(_apply_deferred_evaluation):
        bpy.app.timers.unregister(_apply_deferred_evaluation)
    _pending_evaluations.clear()


def _apply_deferred_evaluation() -> None:
    """Timer callback that applies pending rig evaluations in a writable context."""
    pending = list(_pending_evaluations)
    _pending_evaluations.clear()

    addon_window_manager: "CharacterWindowManagerProperties | None" = getattr(  # noqa: UP037
        bpy.context.window_manager, ToolInfo.NAME, None
    )
    # Bail if the addon state is gone, an undo is in progress, or evaluation is disabled.
    if not addon_window_manager or addon_window_manager.is_undoing:
        return
    if not addon_window_manager.evaluate_dependency_graph:
        return

    scene_properties = getattr(bpy.context.scene, ToolInfo.NAME, None)
    if not scene_properties:
        return

    for name, component in pending:
        # Re-resolve the instance by name; it may have been removed by an undo or edit.
        instance = scene_properties.rig_instance_list.get(name)
        if not instance:
            continue
        try:
            instance.evaluate(component=component)
        except ReferenceError:
            # The underlying data was freed out from under us; skip it.
            continue
        except Exception as error:
            logger.exception(f"Error evaluating rig instance '{name}': {error}")


def _compute_body_input_signature(
    instance: "RigInstance", dependency_graph: bpy.types.Depsgraph | None
) -> tuple | None:
    """Build a comparable signature of the body's driver (input) bone rotations.

    The body rig's driver bones are the only inputs to RigLogic's body evaluation. The
    driven/twist/swing bones it writes back are a disjoint set, so when ``evaluate`` writes
    those outputs Blender re-tags the body armature's transform and the listener fires again
    for an update it caused itself. Comparing this input signature lets the listener tell a
    genuine user change from that self-induced echo and break the feedback loop.

    Returns ``None`` when the signature can't be determined yet (e.g. the instance has never
    been evaluated, so the driver bone names aren't cached), in which case the caller should
    evaluate rather than risk skipping a real update.
    """
    driver_bone_names = instance.data.get(instance.cache_key("body", "driver_bone_names"))
    body_rig = instance.body_rig
    if not driver_bone_names or not body_rig:
        return None

    evaluated = body_rig.evaluated_get(dependency_graph) if dependency_graph else body_rig
    if not evaluated or not evaluated.pose:
        return None

    signature = []
    for name in driver_bone_names:
        pose_bone = evaluated.pose.bones.get(name)
        if not pose_bone:
            continue
        quaternion = utilities.get_pose_bone_local_quaternion(pose_bone)
        signature.append(
            (name, round(quaternion.w, 6), round(quaternion.x, 6), round(quaternion.y, 6), round(quaternion.z, 6))
        )
    return tuple(signature)


def rig_instance_listener(_: "Scene", dependency_graph: bpy.types.Depsgraph, is_frame_change: bool = False):  # noqa: PLR0912
    addon_window_manager = utilities.get_addon_window_manager_properties()
    if not addon_window_manager:
        return

    # this condition prevents constant evaluation
    if not addon_window_manager.evaluate_dependency_graph:
        return

    # this condition prevents 2 evaluations per frame change, causes issues with
    # render threads accessing data while it's being updated, and causing a crash.
    if addon_window_manager.is_rendering and not is_frame_change:
        return

    # this condition prevents evaluation after an undo operation
    if addon_window_manager.is_undoing:
        addon_window_manager.is_undoing = False
        return

    scene_properties = utilities.get_addon_scene_properties()
    if not scene_properties:
        return

    # track the minimal set of instances that need to be updated and their components
    instance_updates = set()

    # only evaluate if in pose mode or if animation is
    if is_frame_change or bpy.context.mode == "POSE":
        for update in dependency_graph.updates:
            if not update.id:
                continue

            data_type = update.id.bl_rna.name  # type: ignore[attr-defined]
            if data_type == "Action":
                for instance in scene_properties.rig_instance_list:
                    # Check if the action is being used by the face board
                    if (
                        instance.auto_evaluate
                        and instance.auto_evaluate_head
                        and instance.face_board
                        and instance.face_board.animation_data
                        and instance.face_board.animation_data.action
                        and instance.face_board.animation_data.action.name == update.id.name
                    ) or (
                        instance.auto_evaluate
                        and instance.auto_evaluate_head
                        and instance.face_board
                        and instance.face_board.animation_data
                        and any(
                            strip.action and strip.action.name == update.id.name
                            for track in instance.face_board.animation_data.nla_tracks
                            for strip in track.strips
                        )
                    ):
                        instance_updates.add((instance, "head"))
                    # Check if the action is being used by the body rig
                    elif (
                        (
                            instance.auto_evaluate
                            and instance.auto_evaluate_body
                            and instance.body_rig
                            and instance.body_rig.animation_data
                            and instance.body_rig.animation_data.action
                            and instance.body_rig.animation_data.action.name == update.id.name
                        )
                        or (
                            instance.auto_evaluate
                            and instance.auto_evaluate_body
                            and instance.control_rig
                            and instance.control_rig.animation_data
                            and instance.control_rig.animation_data.action
                            and instance.control_rig.animation_data.action.name == update.id.name
                        )
                        or (
                            instance.auto_evaluate
                            and instance.auto_evaluate_body
                            and instance.body_rig
                            and instance.body_rig.animation_data
                            and any(
                                strip.action and strip.action.name == update.id.name
                                for track in instance.body_rig.animation_data.nla_tracks
                                for strip in track.strips
                            )
                        )
                        or (
                            instance.auto_evaluate
                            and instance.auto_evaluate_body
                            and instance.control_rig
                            and instance.control_rig.animation_data
                            and any(
                                strip.action and strip.action.name == update.id.name
                                for track in instance.control_rig.animation_data.nla_tracks
                                for strip in track.strips
                            )
                        )
                    ):
                        # heads have rbf driven bones that move based on neck quaternions, so if head rig is present,
                        # evaluate all
                        if instance.head_rig and instance.auto_evaluate_head and instance.evaluate_rbfs:
                            instance_updates.add((instance, "all"))
                        else:
                            instance_updates.add((instance, "body"))

            elif data_type == "Armature" and update.is_updated_transform:
                for instance in scene_properties.rig_instance_list:
                    armature_name = update.id.name

                    # Check if the armature is the face board
                    if (
                        instance.auto_evaluate
                        and instance.auto_evaluate_head
                        and instance.face_board
                        and instance.face_board.data
                        and instance.face_board.data.name == armature_name
                    ):
                        instance_updates.add((instance, "head"))
                    # Check if the armature is the body rig
                    elif (
                        instance.auto_evaluate
                        and instance.auto_evaluate_body
                        and instance.body_rig
                        and instance.body_rig.data
                        and instance.body_rig.data.name == armature_name
                    ) or (
                        instance.auto_evaluate
                        and instance.auto_evaluate_body
                        and instance.control_rig
                        and instance.control_rig.data
                        and instance.control_rig.data.name == armature_name
                    ):
                        # The body armature is both driven and written by RigLogic: evaluate()
                        # writes the driven/twist/swing bones, which re-tags this armature's
                        # transform and fires this listener again. Compare the driver (input)
                        # bone rotations to the signature from the last queued evaluation; if the
                        # inputs are unchanged this update is that self-induced echo, so skip it
                        # to break the feedback loop. A None signature means we can't tell yet
                        # (never evaluated), so fall through and evaluate.
                        input_signature = _compute_body_input_signature(instance, dependency_graph)
                        if input_signature is not None:
                            if input_signature == instance.data.get(instance.cache_key("body", "input_signature")):
                                continue
                            instance.data[instance.cache_key("body", "input_signature")] = input_signature

                        # heads have rbf driven bones that move based on neck quaternions, so if head rig
                        # is present, evaluate all
                        if instance.head_rig and instance.auto_evaluate_head and instance.evaluate_rbfs:
                            instance_updates.add((instance, "all"))
                        else:
                            instance_updates.add((instance, "body"))

    # reduce redundant updates if 'all' components are being updated anyway, no need to
    # update head/body again separately
    final_instance_updates = set()
    for instance, component in instance_updates:
        if (instance, "all") in instance_updates:
            final_instance_updates.add((instance, "all"))
        else:
            final_instance_updates.add((instance, component))

    # Defer evaluation to a timer callback where Blender allows writing to ID data.
    # Queue instances by name so an undo that reallocates the collection can't leave us
    # holding a dangling PropertyGroup wrapper.
    _pending_evaluations.clear()
    for instance, component in final_instance_updates:
        _pending_evaluations.append((instance.name, component))

    if _pending_evaluations and not bpy.app.timers.is_registered(_apply_deferred_evaluation):
        bpy.app.timers.register(_apply_deferred_evaluation, first_interval=0)


def frame_change_handler(scene: "Scene", dependency_graph: bpy.types.Depsgraph):
    rig_instance_listener(scene, dependency_graph, is_frame_change=True)


def stop_listening():
    # Cancel any pending deferred evaluation
    cancel_pending_evaluations()

    for handler in bpy.app.handlers.depsgraph_update_post:
        if handler.__name__ == rig_instance_listener.__name__:
            bpy.app.handlers.depsgraph_update_post.remove(handler)

    for handler in bpy.app.handlers.frame_change_post:
        if handler.__name__ == frame_change_handler.__name__:
            bpy.app.handlers.frame_change_post.remove(handler)


def start_listening():
    stop_listening()
    logger.info("Listening for Rig Logic...")
    context: "Context" = bpy.context  # pyright: ignore[reportAssignmentType]  # noqa: UP037
    callbacks.update_head_output_items(None, context)
    bpy.app.handlers.depsgraph_update_post.append(rig_instance_listener)  # type: ignore[call-arg]
    bpy.app.handlers.frame_change_post.append(frame_change_handler)  # type: ignore[call-arg]


class RigInstance(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(
        default="my_metahuman",
        description=(
            "The name associated with this Rig Instance. This is also the unique identifier "
            "for all data associated with the MetaHuman"
        ),
        update=callbacks.update_instance_name,  # type: ignore[call-arg]
    )  # pyright: ignore[reportInvalidTypeForm]
    auto_evaluate: bpy.props.BoolProperty(
        default=True,
        name="Auto Evaluate",
        description="Whether to automatically evaluate this rig instance when the scene is updated",
    )  # pyright: ignore[reportInvalidTypeForm]
    auto_evaluate_head: bpy.props.BoolProperty(
        default=True,
        name="Auto Evaluate Head",
        description=(
            "Whether to automatically evaluate the head components on this rig instance when the scene is updated"
        ),
    )  # pyright: ignore[reportInvalidTypeForm]
    auto_evaluate_body: bpy.props.BoolProperty(
        default=True,
        name="Auto Evaluate Body",
        description=(
            "Whether to automatically evaluate the body components on this rig instance when the scene is updated"
        ),
    )  # pyright: ignore[reportInvalidTypeForm]
    evaluate_bones: bpy.props.BoolProperty(
        default=True,
        name="Evaluate Bones",
        description="Whether to evaluate bone positions based on the face board controls",
    )  # pyright: ignore[reportInvalidTypeForm]
    evaluate_shape_keys: bpy.props.BoolProperty(
        default=True,
        name="Evaluate Shape Keys",
        description="Whether to evaluate shape keys based on the face board controls",
    )  # pyright: ignore[reportInvalidTypeForm]
    evaluate_texture_masks: bpy.props.BoolProperty(
        default=True,
        name="Evaluate Texture Masks",
        description="Whether to evaluate texture masks based on the face board controls",
    )  # pyright: ignore[reportInvalidTypeForm]
    evaluate_rbfs: bpy.props.BoolProperty(
        default=True,
        name="Evaluate RBFs",
        description="Whether to evaluate RBFs based on the driver bones quaternion rotations",
        update=callbacks.update_evaluate_rbfs_value,  # type: ignore[call-arg]
    )  # pyright: ignore[reportInvalidTypeForm]
    face_board: bpy.props.PointerProperty(
        type=bpy.types.Object,
        name="Face Board",
        description="The face board that rig logic reads control positions from",
        poll=callbacks.poll_face_boards,
    )  # pyright: ignore[reportInvalidTypeForm]
    control_rig: bpy.props.PointerProperty(
        type=bpy.types.Object,
        name="Control Rig",
        description="The control rig that drives the body rig",
        poll=callbacks.poll_control_rig,
    )  # pyright: ignore[reportInvalidTypeForm]
    head_dna_file_path: bpy.props.StringProperty(
        name="Head DNA File",
        description="The path to the head DNA file that rig logic reads from when evaluating the face board controls",
        subtype="FILE_PATH",
        options={"PATH_SUPPORTS_BLEND_RELATIVE"},
    )  # pyright: ignore[reportInvalidTypeForm]
    head_mesh: bpy.props.PointerProperty(
        type=bpy.types.Object,
        name="Head Mesh",
        description="The head mesh with the shape keys that rig logic will evaluate",
        poll=callbacks.poll_head_mesh,
        update=callbacks.update_head_output_items,  # type: ignore[call-arg]
    )  # pyright: ignore[reportInvalidTypeForm]
    head_rig: bpy.props.PointerProperty(
        type=bpy.types.Object,
        name="Head Rig",
        description="The armature object that rig logic will evaluate",
        poll=callbacks.poll_head_rig,
        update=callbacks.update_head_output_items,  # type: ignore[call-arg]
    )  # pyright: ignore[reportInvalidTypeForm]
    head_material: bpy.props.PointerProperty(
        type=bpy.types.Material,
        name="Head Material",
        description="The head material that has a node with wrinkle map sliders that rig logic will evaluate",
        poll=callbacks.poll_head_materials,
        update=callbacks.update_head_output_items,  # type: ignore[call-arg]
    )  # pyright: ignore[reportInvalidTypeForm]
    body_dna_file_path: bpy.props.StringProperty(
        name="Body DNA File",
        description="The path to the body DNA file",
        subtype="FILE_PATH",
        options={"PATH_SUPPORTS_BLEND_RELATIVE"},
    )  # pyright: ignore[reportInvalidTypeForm]
    body_mesh: bpy.props.PointerProperty(
        type=bpy.types.Object,
        name="Body Mesh",
        description="The body mesh",
        poll=callbacks.poll_body_mesh,
        update=callbacks.update_body_output_items,  # type: ignore[call-arg]
    )  # pyright: ignore[reportInvalidTypeForm]
    body_rig: bpy.props.PointerProperty(
        type=bpy.types.Object,
        name="Body Rig",
        description="The armature object for the body that RBF will evaluate",
        poll=callbacks.poll_body_rig,
        update=callbacks.update_body_output_items,  # type: ignore[call-arg]
    )  # pyright: ignore[reportInvalidTypeForm]
    body_material: bpy.props.PointerProperty(
        type=bpy.types.Material,
        name="Body Material",
        description="The body material",
        poll=callbacks.poll_body_materials,
        update=callbacks.update_body_output_items,  # type: ignore[call-arg]
    )  # pyright: ignore[reportInvalidTypeForm]

    # ----- Internal Properties -----
    head_to_body_constraint_influence: bpy.props.FloatProperty(
        name="Constrain Head to Body",
        default=0.0,
        description="The influence of the head to body constraint",
        update=callbacks.update_head_to_body_constraint_influence,  # type: ignore[call-arg]
        min=0.0,
        max=1.0,
        subtype="FACTOR",
    )  # pyright: ignore[reportInvalidTypeForm]

    old_name: bpy.props.StringProperty(default="")  # pyright: ignore[reportInvalidTypeForm]

    # this holds the rig logic references
    data = {}

    warning_messages = []

    def cache_key(self, component: str, descriptor: str) -> str:
        return f"{self.name}_{component}_{descriptor}"

    def get_shape_key(self, mesh_index: int) -> bpy.types.Key | None:
        shape_key = self.data.get(self.cache_key("head", "shape_key"), {}).get(mesh_index)
        try:
            if shape_key:
                return shape_key
        except ReferenceError:
            return None

    def get_shape_key_block(self, mesh_index: int, name: str) -> bpy.types.ShapeKey | None:
        cached_shape_key = self.get_shape_key(mesh_index)
        try:
            if cached_shape_key and cached_shape_key.key_blocks:
                return cached_shape_key.key_blocks.get(name)
        except ReferenceError:
            pass

        mesh_object = self.head_mesh_index_lookup.get(mesh_index)
        if mesh_object:
            self.data[self.cache_key("head", "shape_key")] = self.data.get(self.cache_key("head", "shape_key"), {})
            for shape_key in bpy.data.shape_keys:
                if shape_key.user == mesh_object.data:
                    key_block = shape_key.key_blocks.get(name)
                    if key_block:
                        # store the shape key in the shape key property so we don't have to search for it again
                        self.data[self.cache_key("head", "shape_key")][mesh_index] = shape_key
                        return key_block
        return None

    def apply_dependency_graph_update(self, dependency_graph: bpy.types.Depsgraph | None = None):
        if not dependency_graph:
            dependency_graph = bpy.context.evaluated_depsgraph_get()

        if self.head_rig:
            self.data[self.cache_key("head", "rig_evaluated")] = self.head_rig.evaluated_get(dependency_graph)
        if self.body_rig:
            self.data[self.cache_key("body", "rig_evaluated")] = self.body_rig.evaluated_get(dependency_graph)

    @property
    def head_rig_evaluated(self) -> bpy.types.Object | None:
        result = self.data.get(self.cache_key("head", "rig_evaluated"))
        if result is not None:
            return result
        # Lazy fallback: only call evaluated_depsgraph_get() when the cached value is missing.
        # Temporarily disable the dependency graph flag to prevent re-entrant handler execution,
        # since evaluated_depsgraph_get() can trigger depsgraph_update_post handlers.
        if self.head_rig:
            window_manager_properties = utilities.get_addon_window_manager_properties()
            prev_flag = window_manager_properties.evaluate_dependency_graph if window_manager_properties else True
            if window_manager_properties:
                window_manager_properties.evaluate_dependency_graph = False
            try:
                result = self.head_rig.evaluated_get(bpy.context.evaluated_depsgraph_get())
            finally:
                if window_manager_properties:
                    window_manager_properties.evaluate_dependency_graph = prev_flag
        return result

    @property
    def body_rig_evaluated(self) -> bpy.types.Object | None:
        result = self.data.get(self.cache_key("body", "rig_evaluated"))
        if result is not None:
            return result
        # Lazy fallback: only call evaluated_depsgraph_get() when the cached value is missing.
        # Temporarily disable the dependency graph flag to prevent re-entrant handler execution,
        # since evaluated_depsgraph_get() can trigger depsgraph_update_post handlers.
        if self.body_rig:
            window_manager_properties = utilities.get_addon_window_manager_properties()
            prev_flag = window_manager_properties.evaluate_dependency_graph if window_manager_properties else True
            if window_manager_properties:
                window_manager_properties.evaluate_dependency_graph = False
            try:
                result = self.body_rig.evaluated_get(bpy.context.evaluated_depsgraph_get())
            finally:
                if window_manager_properties:
                    window_manager_properties.evaluate_dependency_graph = prev_flag
        return result

    @property
    def is_pro(self) -> bool:
        return utilities.pro_features_visible()

    @property
    def head_valid(self) -> bool:
        logged_warning = self.data.get(self.cache_key("head", "logged_validation_warning"), False)

        if not self.head_dna_file_path:
            if not logged_warning:
                logger.warning(
                    f"The Head DNA file path is not set. The Rig Instance {self.name} will not be initialized."
                )
                self.data[self.cache_key("head", "logged_validation_warning")] = True
            return False
        dna_file_path = Path(bpy.path.abspath(self.head_dna_file_path))
        if not dna_file_path.is_file():
            if not logged_warning:
                logger.warning(
                    f'The Head DNA file path "{dna_file_path}" is not a file. The Rig Instance {self.name} '
                    "will not be initialized."
                )
                self.data[self.cache_key("head", "logged_validation_warning")] = True
            return False

        if not dna_file_path.exists():
            if not logged_warning:
                logger.warning(
                    f'The Head DNA file path "{dna_file_path}" does not exist. The Rig Instance {self.name} '
                    "will not be initialized."
                )
                self.data[self.cache_key("head", "logged_validation_warning")] = True
            return False
        if not self.face_board:
            if not logged_warning:
                logger.warning(f"The Face board is not set. The Rig Instance {self.name} will not be initialized.")
                self.data[self.cache_key("head", "logged_validation_warning")] = True
            return False
        return True

    @property
    def body_valid(self) -> bool:
        logged_warning = self.data.get(self.cache_key("body", "logged_validation_warning"), False)
        if not self.body_dna_file_path:
            if not logged_warning:
                logger.warning(
                    f"The Body DNA file path is not set. The Rig Instance {self.name} will not be initialized."
                )
                self.data[self.cache_key("body", "logged_validation_warning")] = True
            return False

        dna_file_path = Path(bpy.path.abspath(self.body_dna_file_path))
        if not dna_file_path.is_file():
            if not logged_warning:
                logger.warning(
                    f'The Body DNA file path "{dna_file_path}" is not a file. The Rig Instance {self.name}'
                    " will not be initialized."
                )
                self.data[self.cache_key("body", "logged_validation_warning")] = True
            return False

        if not dna_file_path.exists():
            if not logged_warning:
                logger.warning(
                    f'The Body DNA file path "{dna_file_path}" does not exist. The Rig Instance {self.name} '
                    "will not be initialized."
                )
                self.data[self.cache_key("body", "logged_validation_warning")] = True
            return False
        return True

    @property
    def head_texture_masks_node(self) -> bpy.types.ShaderNodeGroup | None:
        # first check if the texture masks node is set
        if not self.head_material:
            return None

        return callbacks.get_head_texture_logic_node(self.head_material)

    @property
    def head_initialized(self) -> bool:
        return bool(self.data.get(self.cache_key("head", "initialized")))

    @property
    def body_initialized(self) -> bool:
        return bool(self.data.get(self.cache_key("body", "initialized")))

    @property
    def head_use_eye_aim(self) -> bool:
        look_at_switch = self.face_board.pose.bones.get("CTRL_lookAtSwitch")
        return look_at_switch and look_at_switch.location.y >= 0.99

    @property
    def head_mesh_index_lookup(self) -> dict[int, bpy.types.Object]:
        if not self.head_dna_reader:
            return {}

        mesh_index_lookup = self.data.get(self.cache_key("head", "mesh_index_lookup"), {})
        if mesh_index_lookup:
            return mesh_index_lookup

        for mesh_index in range(self.head_dna_reader.getMeshCount()):
            dna_mesh_name = self.head_dna_reader.getMeshName(mesh_index)
            mesh_object = bpy.data.objects.get(f"{self.name}_{dna_mesh_name}")
            if mesh_object:
                mesh_index_lookup[mesh_index] = mesh_object

        self.data[self.cache_key("head", "mesh_index_lookup")] = mesh_index_lookup
        return self.data[self.cache_key("head", "mesh_index_lookup")]

    @property
    def head_channel_name_to_index_lookup(self) -> dict[str, int]:
        if not self.head_dna_reader:
            return {}

        channel_name_to_index_lookup = self.data.get(self.cache_key("head", "channel_name_to_index_lookup"), {})
        if channel_name_to_index_lookup:
            return channel_name_to_index_lookup

        for mesh_index in self.head_dna_reader.getMeshIndicesForLOD(0):
            mesh_name = self.head_dna_reader.getMeshName(mesh_index)
            for index in range(self.head_dna_reader.getBlendShapeTargetCount(mesh_index)):
                channel_index = self.head_dna_reader.getBlendShapeChannelIndex(mesh_index, index)
                shape_key_name = self.head_dna_reader.getBlendShapeChannelName(channel_index)
                channel_name_to_index_lookup[f"{mesh_name}__{shape_key_name}"] = channel_index

        self.data[self.cache_key("head", "channel_name_to_index_lookup")] = channel_name_to_index_lookup
        return self.data[self.cache_key("head", "channel_name_to_index_lookup")]

    @property
    def head_channel_index_to_mesh_index_lookup(self) -> dict[int, int]:
        if not self.head_dna_reader:
            return {}

        mesh_shape_key_index_lookup = self.data.get(self.cache_key("head", "mesh_shape_key_index_lookup"), {})
        if mesh_shape_key_index_lookup:
            return mesh_shape_key_index_lookup

        # build a lookup dictionary of shape key index to mesh index
        for mesh_index in self.head_dna_reader.getMeshIndicesForLOD(0):
            for index in range(self.head_dna_reader.getBlendShapeTargetCount(mesh_index)):
                channel_index = self.head_dna_reader.getBlendShapeChannelIndex(mesh_index, index)
                mesh_shape_key_index_lookup[channel_index] = mesh_index
        self.data[self.cache_key("head", "mesh_shape_key_index_lookup")] = mesh_shape_key_index_lookup
        return mesh_shape_key_index_lookup

    @property
    def head_manager(self) -> "riglogic.RigLogic":
        return self.data.get(self.cache_key("head", "manager"))  # pyright: ignore[reportReturnType]

    @property
    def head_instance(self) -> "riglogic.RigInstance":
        return self.data.get(self.cache_key("head", "instance"))  # pyright: ignore[reportReturnType]

    @property
    def head_dna_reader(self) -> "dna.BinaryStreamReader":
        return self.data.get(self.cache_key("head", "dna_reader"))  # pyright: ignore[reportReturnType]

    @property
    def body_manager(self) -> "riglogic.RigLogic":
        return self.data.get(self.cache_key("body", "manager"))  # pyright: ignore[reportReturnType]

    @property
    def body_instance(self) -> "riglogic.RigInstance":
        return self.data.get(self.cache_key("body", "instance"))  # pyright: ignore[reportReturnType]

    @property
    def body_dna_reader(self) -> "dna.BinaryStreamReader":
        return self.data.get(self.cache_key("body", "dna_reader"))  # pyright: ignore[reportReturnType]

    @property
    def head_shape_key_blocks(self) -> dict[int, list[bpy.types.ShapeKey]]:
        if not self.head_dna_reader:
            return {}

        shape_key_blocks = self.data.get(self.cache_key("head", "shape_key_blocks"))
        if shape_key_blocks is None:
            mesh_index = 0  # this is the head lod 0 mesh index
            shape_key_blocks = {}
            # Ordered, namespaced block names backing the UI shape key list. Kept as plain
            # strings (undo-safe) and written to the scene-side `shape_key_list` collection
            # separately by `sync_shape_key_list`. This getter only writes to `self.data`
            # (never ID data), so it is safe to call from a property getter / UI draw -- e.g.
            # when undo clears the volatile block cache via `destroy_references`.
            shape_key_block_names: list[str] = []

            # Note: That lod 0 is the only lod that has shape keys
            failed_to_cache_count = 0
            for mesh_index in self.head_dna_reader.getMeshIndicesForLOD(0):
                mesh_object = self.head_mesh_index_lookup.get(mesh_index)
                if not mesh_object:
                    logger.warning(f'The mesh object for mesh index "{mesh_index}" was not found')
                    continue

                for target_index in range(self.head_dna_reader.getBlendShapeTargetCount(mesh_index)):
                    channel_index = self.head_dna_reader.getBlendShapeChannelIndex(mesh_index, target_index)
                    name = self.head_dna_reader.getBlendShapeChannelName(channel_index)
                    dna_mesh_name = mesh_object.name.replace(f"{self.name}_", "")
                    shape_key_block_name = f"{dna_mesh_name}__{name}"
                    shape_key_block = self.get_shape_key_block(mesh_index=mesh_index, name=shape_key_block_name)
                    if shape_key_block:
                        # remember the block name for the UI list (built in a write-safe context)
                        shape_key_block_names.append(shape_key_block_name)

                        # store the shape key block in a list on the dictionary
                        key_block_list = shape_key_blocks.get(channel_index, [])
                        key_block_list.append(shape_key_block)
                        shape_key_blocks[channel_index] = key_block_list

                    elif len(shape_key_block_name) <= SHAPE_KEY_NAME_MAX_LENGTH:
                        failed_to_cache_count += 1

            if failed_to_cache_count > 0:
                logger.warning(
                    f"Rig Instance {self.name} did not cache {failed_to_cache_count} shape key blocks, "
                    "because they are not in the scene. However they are in the DNA file. Import all shape "
                    "keys to cache them."
                )

            self.data[self.cache_key("head", "shape_key_block_names")] = shape_key_block_names
            self.data[self.cache_key("head", "shape_key_blocks")] = shape_key_blocks

        return self.data[self.cache_key("head", "shape_key_blocks")]

    def sync_shape_key_list(self) -> None:
        """Rebuild the UI shape-key list -- a ``CollectionProperty`` on the scene-stored
        ``ShapeKeyEditorProperties`` -- from the cached block names.

        This writes ID data, so it must only be called from a write-safe context such as
        ``head_initialize`` or an operator, never from a property getter or UI draw. The
        list is undo-tracked by Blender, so it does not need rebuilding on undo; only the
        volatile ``shape_key_blocks`` wrapper cache does (see ``destroy_references``)."""
        shape_key_editor: ShapeKeyEditorProperties | None = getattr(self, "shape_key_editor", None)
        if not shape_key_editor:
            return

        # Ensure the block cache (and its ordered names) exist before mirroring them.
        self.head_shape_key_blocks  # noqa: B018
        shape_key_block_names = self.data.get(self.cache_key("head", "shape_key_block_names"), [])

        shape_key_editor.shape_key_list.clear()
        for shape_key_block_name in shape_key_block_names:
            shape_key_item = shape_key_editor.shape_key_list.add()
            shape_key_item.name = shape_key_block_name

    @property
    def head_rest_pose(self) -> dict[str, tuple[Vector, Euler, Vector, Matrix]]:
        rest_pose = self.data.get(self.cache_key("head", "rest_pose"), {})
        if rest_pose:
            return rest_pose

        # make sure the rig bone are using the correct rotation mode
        if self.head_rig_evaluated and self.head_rig_evaluated.pose:
            for pose_bone in self.head_rig_evaluated.pose.bones:
                if pose_bone.name in self.head_driver_bone_names:
                    pose_bone.rotation_mode = "QUATERNION"
                else:
                    pose_bone.rotation_mode = "XYZ"
                # save the rest pose and their parent space matrix so we don't have to calculate it again
                rest_pose[pose_bone.name] = utilities.get_bone_rest_transformations(pose_bone.bone)

        # save the rest pose so we don't have to calculate it again
        self.data[self.cache_key("head", "rest_pose")] = rest_pose
        # return a copy so the original rest position is not modified
        return self.data[self.cache_key("head", "rest_pose")]

    @property
    def head_driven_bone_names(self) -> list[str]:
        driven_bone_names = self.data.get(self.cache_key("head", "driven_bone_names"), [])
        if driven_bone_names:
            return driven_bone_names

        # get the head rbf driven bone names
        for solver_index in range(self.head_dna_reader.getRBFSolverCount()):
            for pose_index in self.head_dna_reader.getRBFSolverPoseIndices(solver_index):
                for attr_index in self.head_dna_reader.getRBFPoseJointOutputIndices(pose_index):
                    joint_index = attr_index // ATTR_COUNT_PER_EULER_JOINT
                    driven_bone_names.append(self.head_dna_reader.getJointName(joint_index))

        # save the driven bone names so we don't have to query them again
        self.data[self.cache_key("head", "driven_bone_names")] = list(set(driven_bone_names))
        return self.data[self.cache_key("head", "driven_bone_names")]

    @property
    def head_driver_bone_names(self) -> list[str]:
        driver_bone_names = self.data.get(self.cache_key("head", "driver_bone_names"), [])
        if driver_bone_names:
            return driver_bone_names

        driver_bone_names = set()
        for index in range(self.head_dna_reader.getRawControlCount()):
            full_name = self.head_dna_reader.getRawControlName(index)
            control_name, axis = full_name.split(".")
            if axis.startswith("q"):
                driver_bone_names.add(control_name)

        # save the raw control bone names so we don't have to query them again
        self.data[self.cache_key("head", "driver_bone_names")] = list(driver_bone_names)
        # return a copy so the original raw control bone names are not modified
        return self.data[self.cache_key("head", "driver_bone_names")]

    @property
    def body_rest_pose(self) -> dict[str, tuple[Vector, Euler, Vector, Matrix]]:
        rest_pose = self.data.get(self.cache_key("body", "rest_pose"), {})
        if rest_pose:
            return rest_pose

        # make sure the rig bone are using the correct rotation mode
        if self.body_rig_evaluated and self.body_rig_evaluated.pose:
            for pose_bone in self.body_rig_evaluated.pose.bones:
                # make sure the body bones are using the correct rotation mode
                if pose_bone.name in self.body_driver_bone_names:
                    pose_bone.rotation_mode = "QUATERNION"
                else:
                    pose_bone.rotation_mode = "XYZ"

                # save the rest pose and their parent space matrix so we don't have to calculate it again
                rest_pose[pose_bone.name] = utilities.get_bone_rest_transformations(pose_bone.bone, rotation_mode="XYZ")

        # save the rest pose so we don't have to calculate it again
        self.data[self.cache_key("body", "rest_pose")] = rest_pose
        # return a copy so the original rest position is not modified
        return self.data[self.cache_key("body", "rest_pose")]

    @property
    def body_twist_bone_names(self) -> list[str]:
        twist_bone_names = self.data.get(self.cache_key("body", "twist_bone_names"), [])
        if twist_bone_names:
            return twist_bone_names

        # get the updated twist bone names
        for twist_index in range(self.body_dna_reader.getTwistCount()):
            for output_index in self.body_dna_reader.getTwistOutputJointIndices(twist_index):
                twist_bone_names.append(self.body_dna_reader.getJointName(output_index))

        # save the updated bone names so we don't have to query them again
        self.data[self.cache_key("body", "twist_bone_names")] = list(set(twist_bone_names))
        return self.data[self.cache_key("body", "twist_bone_names")]

    @property
    def body_swing_bone_names(self) -> list[str]:
        swing_bone_names = self.data.get(self.cache_key("body", "swing_bone_names"), [])
        if swing_bone_names:
            return swing_bone_names

        # get the body swing bone names
        for swing_index in range(self.body_dna_reader.getSwingCount()):
            for output_index in self.body_dna_reader.getSwingOutputJointIndices(swing_index):
                swing_bone_names.append(self.body_dna_reader.getJointName(output_index))

        # save the updated bone names so we don't have to query them again
        self.data[self.cache_key("body", "swing_bone_names")] = list(set(swing_bone_names))
        return self.data[self.cache_key("body", "swing_bone_names")]

    @property
    def body_driven_bone_names(self) -> list[str]:
        driven_bone_names = self.data.get(self.cache_key("body", "driven_bone_names"), [])
        if driven_bone_names:
            return driven_bone_names

        # get the body rbf driven bone names
        for solver_index in range(self.body_dna_reader.getRBFSolverCount()):
            for pose_index in self.body_dna_reader.getRBFSolverPoseIndices(solver_index):
                for attr_index in self.body_dna_reader.getRBFPoseJointOutputIndices(pose_index):
                    joint_index = attr_index // ATTR_COUNT_PER_EULER_JOINT
                    driven_bone_names.append(self.body_dna_reader.getJointName(joint_index))

        # save the driven bone names so we don't have to query them again
        self.data[self.cache_key("body", "driven_bone_names")] = list(set(driven_bone_names))
        return self.data[self.cache_key("body", "driven_bone_names")]

    @property
    def body_driver_bone_names(self) -> list[str]:
        if not self.body_rig:
            return []

        # check if we have already cached the driver bone names
        driver_bone_names = self.data.get(self.cache_key("body", "driver_bone_names"), [])
        if driver_bone_names:
            return driver_bone_names

        # get the rbf driver bone names
        driver_bone_names = {
            self.body_dna_reader.getRawControlName(i).split(".")[0]
            for i in range(self.body_dna_reader.getRawControlCount())
        }
        # also include the head driver bone names since they are stored in the head DNA, but the
        # body rig uses those same bones (neck_01, neck_02, head)
        if self.head_dna_reader:
            for bone_name in self.head_driver_bone_names:
                # only add the driver bone if it exists in the body rig
                if self.body_rig.pose.bones.get(bone_name):
                    driver_bone_names.add(bone_name)

        # save the driver bone names so we don't have to query them again
        self.data[self.cache_key("body", "driver_bone_names")] = list(driver_bone_names)
        return self.data[self.cache_key("body", "driver_bone_names")]

    def head_initialize(self, update_raw_control_list: bool = True):
        from .bindings import riglogic  # pyright: ignore[reportAttributeAccessIssue]
        from .dna_io import get_dna_reader

        if not self.head_valid:
            return

        # ---- Initialize the Head Rig Instance ---
        # set the dna reader
        self.data[self.cache_key("head", "dna_reader")] = get_dna_reader(
            file_path=Path(bpy.path.abspath(self.head_dna_file_path)).absolute(), memory_resource=None
        )

        # make sure the rig bones are using the correct rotation mode
        if self.head_rig and self.head_rig.pose:
            for pose_bone in self.head_rig.pose.bones:
                if pose_bone.name.startswith("FACIAL_"):
                    pose_bone.rotation_mode = "XYZ"
                else:
                    pose_bone.rotation_mode = "QUATERNION"

        # set the rig logic manager and instance
        self.data[self.cache_key("head", "manager")] = riglogic.RigLogic.create(
            self.head_dna_reader, riglogic.Configuration(), None
        )
        self.data[self.cache_key("head", "instance")] = riglogic.RigInstance.create(
            rigLogic=self.head_manager, memRes=None
        )

        # populate the body rbf solver list
        if update_raw_control_list:
            self.update_head_raw_control_list()

        # calling theses properties will cache their values
        self.head_texture_masks_node  # noqa: B018
        self.head_mesh_index_lookup  # noqa: B018
        self.head_channel_name_to_index_lookup  # noqa: B018
        self.head_channel_index_to_mesh_index_lookup  # noqa: B018
        self.head_shape_key_blocks  # noqa: B018
        # Mirror the cached blocks into the scene-side UI list now (write-safe context).
        self.sync_shape_key_list()
        self.head_driven_bone_names  # noqa: B018
        self.head_driver_bone_names  # noqa: B018
        self.head_rest_pose  # noqa: B018

        self.data[self.cache_key("head", "initialized")] = True

    def body_initialize(self, update_rbf_solver_list: bool = True):
        from .bindings import riglogic  # pyright: ignore[reportAttributeAccessIssue]
        from .dna_io import get_dna_reader

        if not self.body_valid:
            return

        # ---- Initialize the Body Rig Instance ---
        # set the body dna reader
        self.data[self.cache_key("body", "dna_reader")] = get_dna_reader(
            file_path=Path(bpy.path.abspath(self.body_dna_file_path)).absolute(), memory_resource=None
        )

        # make sure the body bones are using the correct rotation mode
        if self.body_rig and self.body_rig.pose:
            for pose_bone in self.body_rig.pose.bones:
                if pose_bone.name in self.body_driver_bone_names:
                    pose_bone.rotation_mode = "QUATERNION"
                else:
                    pose_bone.rotation_mode = "XYZ"

        # set the rig logic manager and instance
        body_config = riglogic.Configuration()
        body_config.calculationType = riglogic.CalculationType_AnyVector
        body_config.loadJoints = True
        body_config.loadBlendShapes = True
        body_config.loadAnimatedMaps = True
        body_config.loadMachineLearnedBehavior = True
        body_config.loadRBFBehavior = True
        body_config.loadTwistSwingBehavior = True
        body_config.translationType = riglogic.TranslationType_Vector
        body_config.rotationType = riglogic.RotationType_Quaternions
        body_config.scaleType = riglogic.ScaleType_Vector
        self.data[self.cache_key("body", "manager")] = riglogic.RigLogic.create(self.body_dna_reader, body_config, None)
        self.data[self.cache_key("body", "instance")] = riglogic.RigInstance.create(
            rigLogic=self.body_manager, memRes=None
        )

        # populate the body rbf solver list
        if update_rbf_solver_list:
            self.update_body_rbf_solver_list()

        # calling theses properties will cache their values
        self.body_rest_pose  # noqa: B018
        self.body_twist_bone_names  # noqa: B018
        self.body_swing_bone_names  # noqa: B018
        self.body_driven_bone_names  # noqa: B018
        self.body_driver_bone_names  # noqa: B018

        self.data[self.cache_key("body", "initialized")] = True

    def initialize(self):
        self.head_initialize()
        self.body_initialize()
        if self.is_pro:
            from .editors.backup_manager.core import sync_backup_list_with_disk as _sync_backup_list_with_disk

            _sync_backup_list_with_disk(instance=self)  # pyright: ignore[reportArgumentType]

    def destroy_head(self):
        # clear the head rig logic data, this frees them up to be garbage collected
        for key in list(self.data.keys()):
            if key.startswith(f"{self.name}_head_"):
                del self.data[key]
        self.data[self.cache_key("head", "initialized")] = False

    def destroy_body(self):
        # clear the body rig logic data, this frees them up to be garbage collected
        for key in list(self.data.keys()):
            if key.startswith(f"{self.name}_body_"):
                del self.data[key]
        self.data[self.cache_key("body", "initialized")] = False

    def destroy_references(self):
        # The `data` cache dict survives an undo/redo, but the live `bpy` RNA wrappers it
        # holds do not: undo can free and reallocate the underlying objects, leaving these
        # entries pointing at removed StructRNA. Any later access then raises
        # `ReferenceError: StructRNA of type Object has been removed`. Drop only the
        # wrapper-holding caches so they lazily rebuild from fresh wrappers on next access.
        # The RigLogic C++ instances and the plain value-copy caches (rest pose, bone-name
        # lists, channel lookups) are undo-safe, so the component stays initialized.
        reference_descriptors = (
            ("head", "mesh_index_lookup"),
            ("head", "shape_key"),
            ("head", "shape_key_blocks"),
            ("head", "rig_evaluated"),
            ("body", "rig_evaluated"),
        )
        for component, descriptor in reference_descriptors:
            self.data.pop(self.cache_key(component, descriptor), None)

    def destroy(self):
        self.destroy_head()
        self.destroy_body()

    def update_head_switch_values(self):  # noqa: PLR0912
        if not self.face_board:
            return

        # update the head follow body switch constraint influence
        face_gui_control = self.face_board.pose.bones.get("CTRL_faceGUI")
        face_follow_head_switch = self.face_board.pose.bones.get("CTRL_faceGUIfollowHead")
        if face_follow_head_switch and face_gui_control:
            constraint = None
            for existing_constraint in face_gui_control.constraints:
                if existing_constraint.type == "CHILD_OF":
                    constraint = existing_constraint
                    break
            if constraint and round(constraint.influence, 3) != round(face_follow_head_switch.location.y, 3):
                constraint.influence = face_follow_head_switch.location.y

        # update the eye aim follow head switch constraint influence
        eye_aim_control = self.face_board.pose.bones.get("CTRL_C_eyesAim")
        eye_aim_follow_head_switch = self.face_board.pose.bones.get("CTRL_eyesAimFollowHead")
        if eye_aim_follow_head_switch and eye_aim_control:
            constraint = None
            for existing_constraint in eye_aim_control.constraints:
                if existing_constraint.type == "CHILD_OF":
                    constraint = existing_constraint
                    break
            if constraint and round(constraint.influence, 3) != round(eye_aim_follow_head_switch.location.y, 3):
                constraint.influence = eye_aim_follow_head_switch.location.y

        # update the eye aim control visibility if needed
        # Note: In Blender 5.0+, the hide property moved from Bone to PoseBone
        if eye_aim_control:
            current_hide = eye_aim_control.hide if IS_BLENDER_5 else eye_aim_control.bone.hide
            if self.head_use_eye_aim == current_hide:
                if IS_BLENDER_5:
                    eye_aim_control.hide = not self.head_use_eye_aim
                else:
                    eye_aim_control.bone.hide = not self.head_use_eye_aim

            for child in eye_aim_control.children_recursive:
                if not child.name.startswith(("GRP_", "LOC_")):
                    child_hide = child.hide if IS_BLENDER_5 else child.bone.hide
                    if self.head_use_eye_aim == child_hide:
                        if IS_BLENDER_5:
                            child.hide = not self.head_use_eye_aim
                        else:
                            child.bone.hide = not self.head_use_eye_aim

    def get_head_gui_control_values_from_eye_aim(self) -> dict[str, dict[str, float]]:
        values = {}
        if not self.face_board:
            return values

        for target_name, eye_bone_name, control_name in [
            ("CTRL_L_eyeAim", "FACIAL_L_Eye", "CTRL_L_eye"),
            ("CTRL_R_eyeAim", "FACIAL_R_Eye", "CTRL_R_eye"),
        ]:
            target = self.face_board.pose.bones.get(target_name)
            eye = self.head_rig.pose.bones.get(eye_bone_name)
            if target and eye:
                eye_rest_matrix = self.face_board.matrix_world @ eye.bone.matrix_local

                # Current eye-to-target direction in world space
                eye_pos = self.face_board.matrix_world @ eye.head
                target_pos = self.face_board.matrix_world @ target.head
                look_direction = target_pos - eye_pos

                if look_direction.length < FLOATING_POINT_PRECISION:
                    continue

                look_direction.normalize()

                # Convert look direction to eye's local space
                eye_matrix_inv = eye_rest_matrix.inverted()
                local_look_direction = (eye_matrix_inv.to_3x3() @ look_direction).normalized()

                # Calculate horizontal distance (projection onto XZ plane)
                horizontal_dist = math.sqrt(local_look_direction.x**2 + local_look_direction.z**2)

                if horizontal_dist > FLOATING_POINT_PRECISION:
                    # Remap yaw to continuous range centered on forward direction (-Z)
                    # Instead of atan2(x, -z), we use the normalized x component directly
                    # This gives us a smooth -1 to 1 range for horizontal movement
                    x_normalized = local_look_direction.x / horizontal_dist

                    # For better control, we can use asin which gives -90° to 90° range
                    yaw = math.asin(max(-1.0, min(1.0, x_normalized)))
                else:
                    # Looking straight up/down, yaw is undefined
                    yaw = 0.0

                # Pitch is the angle from the horizontal plane
                pitch = math.atan2(local_look_direction.y, horizontal_dist)

                # Map angles to -1..1 range based on max rotation
                x_max_rad = math.radians(60.0)
                y_max_rad = math.radians(30.0)

                x_control = max(-1.0, min(1.0, yaw / x_max_rad))
                y_control = max(-1.0, min(1.0, pitch / y_max_rad))

                values[control_name] = {"x": x_control, "y": y_control}

        return values

    def update_head_raw_control_values(self, override_values: dict[str, dict[str, float]] | None = None):
        # skip if the body rig is not set
        if not self.head_rig or not self.head_rig_evaluated or not self.head_dna_reader:
            return

        # skip if the rest pose is not initialized
        if not self.head_rest_pose:
            return

        if not self.head_rig_evaluated.pose:
            return

        missing_raw_controls = []
        converted_quaternions = {}

        # convert the quaternion values to the correct coordinate system
        for pose_bone in self.head_rig_evaluated.pose.bones:
            if pose_bone.name in self.head_driver_bone_names:
                # get the local quaternion, but from the world matrix to account for constraints, since we
                # can't always assume the local quaternion value is what is driving the bone rotation. For
                # example, if the body is driving the head bone transforms via constraints.
                # TODO: This math might have performance implications, so we might want review this later.
                quaternion = utilities.get_pose_bone_local_quaternion(pose_bone)
                converted_quaternions[pose_bone.name] = quaternion

        for index in range(self.head_dna_reader.getRawControlCount()):
            full_name = self.head_dna_reader.getRawControlName(index)
            control_name, axis = full_name.split(".")
            # only process quaternions
            if not axis.startswith("q"):
                continue

            axis = axis.rsplit("q", -1)[-1].lower()
            if self.head_rig_evaluated:
                # override the values can be provided to update values based on them vs current head rig bone locations
                # This can be used for baking the values to an action
                if override_values:
                    value = override_values.get(control_name, {}).get(axis)
                    if value is not None:
                        self.head_instance.setRawControl(index, value)
                else:
                    quaternion = converted_quaternions.get(control_name)
                    if quaternion:
                        value = getattr(quaternion, axis)
                        self.head_instance.setRawControl(index, value)
                    else:
                        missing_raw_controls.append(control_name)

        if missing_raw_controls and not self.data.get(self.cache_key("head", "logged_missing_raw_controls")):
            logger.warning(
                f'The following raw controls are missing on "{self.head_rig.name}":\n{pformat(missing_raw_controls)}.'
            )
            logger.warning(f"You are not listening to {len(missing_raw_controls)} raw controls")
            logger.warning(
                f"This is most likely due to the these bones being missing from the rig {self.head_rig.name}."
            )
            self.data[self.cache_key("head", "logged_missing_raw_controls")] = True

    def update_head_gui_control_values(self, override_values: dict[str, dict[str, float]] | None = None):  # noqa: PLR0912
        # skip if the face board is not set
        if not self.face_board or not self.head_dna_reader:
            return

        missing_gui_controls = []

        center_eye_control = self.face_board.pose.bones.get("CTRL_C_eye")

        eye_aim_override_values = {}
        if self.head_use_eye_aim:
            eye_aim_override_values = self.get_head_gui_control_values_from_eye_aim()

        for index in range(self.head_dna_reader.getGUIControlCount()):
            full_name = self.head_dna_reader.getGUIControlName(index)
            control_name, axis = full_name.split(".")
            axis = axis.rsplit("t", -1)[-1].lower()
            if self.face_board:
                # Override values can be provided to update values based on them vs current face board
                # bone locations. This can be used for baking the values to an action.
                if override_values:
                    value = override_values.get(control_name, {}).get(axis)
                    if value is not None:
                        self.head_instance.setGUIControl(index, value)
                else:
                    pose_bone = self.face_board.pose.bones.get(control_name)
                    if pose_bone:
                        value = getattr(pose_bone.location, axis)
                        # special case for the eye controls, if the center eye control is above 0,
                        # use that value instead
                        if control_name in ["CTRL_L_eye", "CTRL_R_eye"]:
                            center_value = eye_aim_override_values.get(control_name, {}).get(axis)
                            if center_value is not None:
                                if abs(center_value) > FLOATING_POINT_PRECISION:
                                    value = center_value
                            elif center_eye_control:
                                center_value = getattr(center_eye_control.location, axis)
                                if abs(center_value) > FLOATING_POINT_PRECISION:
                                    value = center_value

                        self.head_instance.setGUIControl(index, value)
                    else:
                        missing_gui_controls.append(control_name)

        if missing_gui_controls and not self.data.get(self.cache_key("head", "logged_missing_gui_controls")):
            logger.warning(
                f'The following GUI controls are missing on "{self.face_board.name}":\n{pformat(missing_gui_controls)}.'
            )
            logger.warning(f"You are not listening to {len(missing_gui_controls)} GUI controls")
            logger.warning(
                "This is most likely due to the DNA file being an older version then what "
                "the face board currently supports."
            )
            logger.warning(
                "Using a new .dna file created from the latest version of MetaHuman Creator will probably resolve this."
            )
            self.data[self.cache_key("head", "logged_missing_gui_controls")] = True

        # set the active LOD level for the head instance to optimize performance
        self.head_instance.setLOD(level=int(self.view_options.active_lod[-1]))  # pyright: ignore[reportAttributeAccessIssue]
        # map the GUI changes to the raw controls
        self.head_manager.mapGUIToRawControls(self.head_instance)

        if self.evaluate_rbfs:
            self.update_head_raw_control_values()

        # calculate the controls
        self.head_manager.calculate(self.head_instance)

    def apply_gui_controls_to_face_board(self):
        if not self.face_board or not self.head_dna_reader or not self.head_instance:
            return

        for index in range(self.head_dna_reader.getGUIControlCount()):
            full_name = self.head_dna_reader.getGUIControlName(index)
            control_name, axis = full_name.split(".")
            axis = axis.rsplit("t", -1)[-1].lower()
            pose_bone = self.face_board.pose.bones.get(control_name)
            if pose_bone:
                setattr(pose_bone.location, axis, self.head_instance.getGUIControl(index))

    def solo_head_shape_key_value(self, shape_key: bpy.types.ShapeKey):
        # skip if the head mesh is not set
        if not self.head_mesh or not self.head_dna_reader:
            return

        # skip if there are no shape keys
        if len(bpy.data.shape_keys) == 0:
            return

        # make all other shape keys 0.0
        for index, _ in enumerate(self.head_instance.getBlendShapeOutputs()):
            for _shape_key in self.head_shape_key_blocks.get(index, []):
                if _shape_key and _shape_key != shape_key:
                    _shape_key.value = 0.0

        # set the provided shape key value to 1.0
        shape_key.value = 1.0

    def update_head_shape_keys(self) -> list[tuple[bpy.types.ShapeKey, float]]:
        # skip if the head mesh is not set
        if not self.head_mesh or not self.head_dna_reader:
            return []

        # skip if there are no shape keys
        if len(bpy.data.shape_keys) == 0:
            return []

        missing_shape_keys = []
        shape_key_values = []

        # update blend shapes
        for index, value in enumerate(self.head_instance.getBlendShapeOutputs()):
            for shape_key in self.head_shape_key_blocks.get(index, []):
                if shape_key:
                    try:
                        shape_key.value = value
                    except AttributeError as error:
                        logger.error(
                            f'Failed to update the shape key "{shape_key.name}" on "{self.head_mesh.name}": {error}'
                        )
                        return []
                    shape_key_values.append((shape_key, value))
                else:
                    missing_shape_keys.append(index)

        if missing_shape_keys and not self.data.get(self.cache_key("head", "logged_missing_shape_keys")):
            name_lookup = {v: k for k, v in self.head_channel_name_to_index_lookup.items()}
            missing_data = {}
            # group the missing shape keys by mesh object
            for index in missing_shape_keys:
                missing_name = name_lookup[index]
                mesh_index = self.head_channel_index_to_mesh_index_lookup[index]
                mesh_object = self.head_mesh_index_lookup[mesh_index]
                if len(missing_name) > SHAPE_KEY_NAME_MAX_LENGTH:
                    # skip warning the user about any missing shape keys names being too long.

                    # Currently, Blender has a limit of 63 characters for shape key names.
                    # This is something that the user might be able to overcome by changing blender
                    # source and recompiling. However, this is not something that we can fix in the addon.

                    # Because this limitation there are 42 missing shape keys from the MetaHuman creator DNA files
                    # that can't be imported because their names are too long. However these are extreme
                    # combinations and for most people this will not be an issue.
                    continue

                missing_data[mesh_object.name] = missing_data.get(mesh_object.name, [])
                missing_data[mesh_object.name].append(missing_name)

            for mesh_name, missing_names in missing_data.items():
                logger.warning(
                    f'The following shape key blocks are missing on "{mesh_name}":\n{pformat(missing_names)}.'
                )

            if len(missing_data.keys()) > 0:
                logger.warning(
                    f"A total of {len(missing_data.keys())} shape key blocks are not being updated by Rig Logic."
                )

            self.data[self.cache_key("head", "logged_missing_shape_keys")] = True

        return shape_key_values

    def update_head_texture_masks(self) -> list[tuple[str, float]]:
        # skip if the material is not set
        if not self.head_material or not self.head_dna_reader:
            return []

        head_texture_masks_node = self.head_texture_masks_node
        # if the texture masks node is not set, we can't update the texture masks
        if not head_texture_masks_node:
            logger.warning(f'The texture masks node was not found on the material "{self.head_material.name}"')
            return []

        texture_mask_values = []

        # update texture masks values
        for index, value in enumerate(self.head_instance.getAnimatedMapOutputs()):
            name = self.head_dna_reader.getAnimatedMapName(index)
            slider_name = f"{name.split('.')[0].split('_')[1].lower().replace('cm', 'wm')}.{name.split('.')[-1]}_msk"

            mask_slider = head_texture_masks_node.inputs.get(slider_name)
            if mask_slider:
                try:
                    mask_slider.default_value = value  # type: ignore[attr-defined]
                except AttributeError as error:
                    logger.error(
                        f'Failed to update the texture mask slider "{slider_name}" on '
                        f'"{self.head_material.name}": {error}'
                    )
                    return []
                texture_mask_values.append((slider_name, value))
            else:
                logger.warning(
                    f'The texture mask slider "{slider_name}" was not found on the material "{self.head_material.name}"'
                )

        return texture_mask_values

    def update_head_bone_transforms(self) -> list[tuple[str, Vector, Euler, Vector]]:
        """Update head bone transforms from RigLogic joint outputs.

        Returns:
            A list of (bone_name, location, rotation_euler, scale) tuples for each updated bone.
        """
        # skip if the head rig is not set
        if not self.head_rig or not self.head_dna_reader:
            return []

        # skip if the rest pose is not initialized
        # https://github.com/poly-hammer/character-dna-addon/issues/58
        if not self.head_rest_pose:
            return []

        bone_transforms: list[tuple[str, Vector, Euler, Vector]] = []

        raw_joint_output = self.head_instance.getJointOutputs()
        # update joint transforms
        for index in range(self.head_dna_reader.getJointCount()):
            # get the bone
            name = self.head_dna_reader.getJointName(index)

            # only update the facial bones or non-driver bones
            if name in self.head_driver_bone_names:
                continue

            pose_bone = self.head_rig.pose.bones.get(name)
            if pose_bone:
                # get the rest pose values that we saved during initialization
                rest_location, rest_rotation, rest_scale, rest_to_parent_matrix = self.head_rest_pose[pose_bone.name]

                # get the values
                matrix_index = (index + 1) * 9
                values = raw_joint_output[(index * 9) : matrix_index]

                # extract the delta values
                location_delta = Vector([values[0] / SCALE_FACTOR, values[1] / SCALE_FACTOR, values[2] / SCALE_FACTOR])
                rotation_delta = Euler([math.radians(values[3]), math.radians(values[4]), math.radians(values[5])])
                scale_delta = Vector(values[6:9])

                # update the transformations using the rest pose and the delta values
                # we need to copy the vectors so we don't modify the original rest pose
                location = Vector(
                    [
                        rest_location.x + location_delta.x,
                        rest_location.y + location_delta.y,
                        rest_location.z + location_delta.z,
                    ]
                )
                rotation = Euler(
                    [
                        rest_rotation.x + rotation_delta.x,
                        rest_rotation.y + rotation_delta.y,
                        rest_rotation.z + rotation_delta.z,
                    ],
                    "XYZ",
                )
                scale = Vector(
                    [rest_scale.x + scale_delta.x, rest_scale.y + scale_delta.y, rest_scale.z + scale_delta.z]
                )

                # update the bone matrix
                modified_matrix = Matrix.LocRotScale(location[:], rotation, scale[:])
                try:
                    pose_bone.matrix_basis = rest_to_parent_matrix.inverted_safe() @ modified_matrix
                except AttributeError as error:
                    logger.error(f'Failed to update the bone "{name}" on "{self.head_rig.name}": {error}')
                    continue

                # if the bone is not a leaf bone, we need to update the rotation again
                if pose_bone.children:
                    pose_bone.rotation_euler = rotation_delta

                # for non-leaf bones use the rotation_delta as the final euler, for leaf bones decompose
                # from the matrix_basis
                final_rotation = rotation_delta if pose_bone.children else pose_bone.matrix_basis.to_euler("XYZ")
                final_location = pose_bone.matrix_basis.to_translation()
                final_scale = pose_bone.matrix_basis.to_scale()

                bone_transforms.append((name, final_location, final_rotation, final_scale))
            else:
                logger.warning(
                    f'The bone "{name}" was not found on "{self.head_rig.name}". Rig Logic will not update the bone.'
                )

        return bone_transforms

    def reset_body_raw_control_values(self):
        # skip if the body rig is not set
        if not self.body_initialized:
            self.body_initialize()

        if not self.body_dna_reader:
            logger.warning("The body DNA reader is not set. The body raw control values will not be reset.")
            return

        if not self.evaluate_rbfs:
            # reset all raw controls to 0.0
            for index in range(self.body_dna_reader.getRawControlCount()):
                full_name = self.body_dna_reader.getRawControlName(index)
                _, axis = full_name.split(".")
                axis = axis.rsplit("q", -1)[-1].lower()
                if axis == "w":
                    self.body_instance.setRawControl(index, 1.0)
                else:
                    self.body_instance.setRawControl(index, 0.0)

            self.body_instance.setLOD(level=int(self.view_options.active_lod[-1]))  # pyright: ignore[reportAttributeAccessIssue]
            self.body_manager.calculate(self.body_instance)
        else:
            self.update_body_raw_control_values()

        self.update_body_bone_transforms()

    def reset_head_raw_control_values(self):
        # skip if the head rig is not set
        if not self.head_initialized:
            self.head_initialize()

        if not self.head_dna_reader:
            logger.warning("The head DNA reader is not set. The head raw control values will not be reset.")
            return

        if not self.evaluate_rbfs:
            # reset all raw controls to 0.0
            for index in range(self.head_dna_reader.getRawControlCount()):
                full_name = self.head_dna_reader.getRawControlName(index)
                control_name, axis = full_name.split(".")
                if control_name in self.head_driver_bone_names:
                    axis = axis.rsplit("q", -1)[-1].lower()
                    if axis == "w":
                        self.head_instance.setRawControl(index, 1.0)
                    else:
                        self.head_instance.setRawControl(index, 0.0)

            self.head_instance.setLOD(level=int(self.view_options.active_lod[-1]))  # pyright: ignore[reportAttributeAccessIssue]
            self.head_manager.calculate(self.head_instance)
        else:
            self.update_head_raw_control_values()
            self.head_instance.setLOD(level=int(self.view_options.active_lod[-1]))  # pyright: ignore[reportAttributeAccessIssue]
            self.head_manager.calculate(self.head_instance)

        self.update_head_bone_transforms()

    def update_body_raw_control_values(self, override_values: dict[str, dict[str, float]] | None = None):
        # skip if the body rig is not set
        if not self.body_rig or not self.body_rig_evaluated or not self.body_dna_reader:
            return

        # skip if the rest pose is not initialized
        if not self.body_rest_pose:
            return

        if not self.body_rig_evaluated.pose:
            return

        missing_raw_controls = []
        converted_quaternions = {}

        # convert the quaternion values to the correct coordinate system
        for pose_bone in self.body_rig_evaluated.pose.bones:
            if pose_bone.name in self.body_driver_bone_names:
                # get the local quaternion, but from the world matrix to account for constraints, since we
                # can't always assume the local quaternion value is what is driving the bone rotation. For
                # example, a control rig might be driving the body bone rotation via constraints.
                # TODO: This math might have performance implications, so we might want review this later.
                quaternion = utilities.get_pose_bone_local_quaternion(pose_bone)
                converted_quaternions[pose_bone.name] = quaternion

        for index in range(self.body_dna_reader.getRawControlCount()):
            full_name = self.body_dna_reader.getRawControlName(index)
            control_name, axis = full_name.split(".")
            axis = axis.rsplit("q", -1)[-1].lower()
            if self.body_rig_evaluated:
                # override the values can be provided to update values based on them vs current body rig bone locations
                # This can be used for baking the values to an action
                if override_values:
                    value = override_values.get(control_name, {}).get(axis)
                    if value is not None:
                        self.body_instance.setRawControl(index, value)
                else:
                    quaternion = converted_quaternions.get(control_name)
                    if quaternion:
                        value = getattr(quaternion, axis)
                        self.body_instance.setRawControl(index, value)
                    else:
                        missing_raw_controls.append(control_name)

        if missing_raw_controls and not self.data.get(self.cache_key("body", "logged_missing_raw_controls")):
            logger.warning(
                f'The following raw controls are missing on "{self.body_rig.name}":\n{pformat(missing_raw_controls)}.'
            )
            logger.warning(f"You are not listening to {len(missing_raw_controls)} raw controls")
            logger.warning(
                f"This is most likely due to the these bones being missing from the rig {self.body_rig.name}."
            )
            self.data[self.cache_key("body", "logged_missing_raw_controls")] = True

        # set the active LOD level for the body instance to optimize performance
        self.body_instance.setLOD(level=int(self.view_options.active_lod[-1]))  # pyright: ignore[reportAttributeAccessIssue]

        # calculate the changes
        self.body_manager.calculate(self.body_instance)

    def update_body_bone_transforms(self) -> list[tuple[str, Vector, Euler, Vector]]:
        """Update body bone transforms from RigLogic joint outputs.

        Returns:
            A list of (bone_name, location, rotation_euler, scale) tuples for each updated bone.
        """
        # skip if the body rig is not set
        if not self.body_rig or not self.body_dna_reader:
            return []

        # skip if the rest pose is not initialized
        if not self.body_rest_pose:
            return []

        bone_transforms: list[tuple[str, Vector, Euler, Vector]] = []

        # get the delta values
        D = self.body_instance.getJointOutputs()

        # update joint transforms
        for joint_index in range(self.body_dna_reader.getJointCount()):
            # skip the root joint
            if joint_index == 0:
                continue

            # get the bone
            name = self.body_dna_reader.getJointName(joint_index)
            pose_bone = self.body_rig.pose.bones.get(name)
            if pose_bone:
                # Only update bones that are updated via RBFs, twists, or swings
                if name not in (self.body_driven_bone_names + self.body_swing_bone_names + self.body_twist_bone_names):
                    continue

                # get the values
                attr_index = joint_index * ATTR_COUNT_PER_QUATERNION_JOINT
                # get the rest pose values that we saved during initialization
                rest_location, rest_rotation, rest_scale, rest_to_parent_matrix = self.body_rest_pose[pose_bone.name]
                # extract the delta values
                location_delta = Vector(
                    [D[attr_index] / SCALE_FACTOR, D[attr_index + 1] / SCALE_FACTOR, D[attr_index + 2] / SCALE_FACTOR]
                )
                rotation_delta = Quaternion(
                    [D[attr_index + 6], D[attr_index + 3], D[attr_index + 4], D[attr_index + 5]]
                )
                scale_delta = Vector([D[attr_index + 7], D[attr_index + 8], D[attr_index + 9]])

                # update the transformations using the rest pose and the delta values
                # we need to copy the vectors so we don't modify the original rest pose
                location = Vector(
                    [
                        rest_location.x + location_delta.x,
                        rest_location.y + location_delta.y,
                        rest_location.z + location_delta.z,
                    ]
                )

                rotation = rest_rotation.to_quaternion() @ rotation_delta

                scale = Vector(
                    [rest_scale.x + scale_delta.x, rest_scale.y + scale_delta.y, rest_scale.z + scale_delta.z]
                )

                # update the bone matrix
                modified_matrix = Matrix.LocRotScale(location[:], rotation, scale[:])
                try:
                    pose_bone.matrix_basis = rest_to_parent_matrix.inverted_safe() @ modified_matrix
                except AttributeError as error:
                    logger.error(f'Failed to update the bone "{name}" on "{self.body_rig.name}": {error}')
                    continue

                # decompose the final matrix_basis for baking output
                final_location = pose_bone.matrix_basis.to_translation()
                final_rotation = pose_bone.matrix_basis.to_euler("XYZ")
                final_scale = pose_bone.matrix_basis.to_scale()

                bone_transforms.append((name, final_location, final_rotation, final_scale))
            else:
                logger.warning(
                    f'The bone "{name}" was not found on "{self.body_rig.name}". Rig Logic will not update the bone.'
                )

        return bone_transforms

    def update_body_rbf_solver_list(self):
        try:
            from .editors.rbf_editor.callbacks import update_body_rbf_solver_list as _update

            _update(self)  # pyright: ignore[reportArgumentType]
        except ImportError:
            logger.debug("Could not import the RBF editor module to update the body RBF solver list.")

    def update_head_raw_control_list(self):
        try:
            from .editors.raw_control_editor.callbacks import update_head_raw_control_list as _update

            _update(self)  # pyright: ignore[reportArgumentType]
        except ImportError:
            logger.debug("Could not import the raw control editor module to update the head raw control list.")

    def evaluate(self, component: "ComponentType" = "all", dependency_graph: bpy.types.Depsgraph | None = None):
        window_manager_properties = utilities.get_addon_window_manager_properties()
        # this condition prevents constant evaluation
        if window_manager_properties.evaluate_dependency_graph:
            # turn off the dependency graph evaluation so we can update the controls without triggering an update
            window_manager_properties.evaluate_dependency_graph = False

            try:
                if not self.head_initialized:
                    self.head_initialize()

                if not self.body_initialized:
                    self.body_initialize()

                # apply the dependency graph update so we have the latest evaluated bone transforms
                self.apply_dependency_graph_update(dependency_graph)

                if component in ("body", "all") and self.body_initialized:
                    if self.evaluate_rbfs:
                        self.update_body_raw_control_values()

                    # apply the changes
                    if self.evaluate_bones:
                        self.update_body_bone_transforms()

                if component in ("head", "all") and self.head_initialized:
                    # update the gui controls
                    self.update_head_switch_values()
                    self.update_head_gui_control_values()

                    # apply the changes
                    if self.evaluate_bones:
                        self.update_head_bone_transforms()
                    if self.evaluate_shape_keys:
                        self.update_head_shape_keys()
                    if self.evaluate_texture_masks:
                        self.update_head_texture_masks()
            finally:
                # always restore the flag so evaluation isn't permanently disabled by an exception
                window_manager_properties.evaluate_dependency_graph = True
