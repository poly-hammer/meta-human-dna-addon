# Type checking utilities for the MetaHuman DNA addon.

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    import bpy

    from bpy.types import bpy_prop_collection, bpy_struct

    from .bindings import riglogic  # pyright: ignore[reportAttributeAccessIssue] # noqa: TC004
    from .components.body import MetaHumanComponentBody  # noqa: TC004
    from .components.head import MetaHumanComponentHead  # noqa: TC004
    from .editors.backup_manager.properties import DnaBackupEntry  # noqa: TC004
    from .editors.pose_editor.properties import (  # noqa: TC004
        RBFDrivenBoneSelectionItem,
        RBFDrivenData,
        RBFDriverData,
        RBFPoseData,
        RBFSolverData,
    )
    from .operators import BakeAnimationBase, DuplicateRigInstance  # noqa: TC004
    from .properties import (
        ExtraDnaFolder,
        MetahumanAddonProperties,  # noqa: TC004
        MetahumanImportProperties,  # noqa: TC004
        MetahumanSceneProperties,  # noqa: TC004
        MetahumanWindowMangerProperties as _MetahumanWindowMangerProperties,
    )
    from .rig_instance import OutputData, RigInstance as _RigInstanceBase, ShapeKeyData  # noqa: TC004

    # =========================================================================
    # Custom Collections
    # =========================================================================
    class ExtraDnaFolders(bpy_prop_collection[ExtraDnaFolder], bpy_struct):
        def add(self) -> ExtraDnaFolder: ...
        def move(self, src_index: int, dst_index: int) -> None: ...
        def remove(self, index: int) -> None: ...
        def clear(self) -> None: ...

    class DnaBackupEntrys(bpy_prop_collection[DnaBackupEntry], bpy_struct):
        def add(self) -> DnaBackupEntry: ...
        def move(self, src_index: int, dst_index: int) -> None: ...
        def remove(self, index: int) -> None: ...
        def clear(self) -> None: ...

    class RBFSolvers(bpy_prop_collection[RBFSolverData], bpy_struct):
        def add(self) -> RBFSolverData: ...
        def move(self, src_index: int, dst_index: int) -> None: ...
        def remove(self, index: int) -> None: ...
        def clear(self) -> None: ...

    # =========================================================================
    # Extended RigInstance with dynamically assigned editor properties
    # These are added at runtime in properties.py register() function
    # =========================================================================
    class RigInstance(_RigInstanceBase):
        """Extended RigInstance type with dynamically registered properties."""

        dna_backup_list: DnaBackupEntrys
        dna_backup_list_active_index: int
        rbf_solver_list: RBFSolvers
        rbf_solver_list_active_index: int

    # =========================================================================
    # Extended MetahumanWindowMangerProperties with dynamically assigned editor
    # properties these are added at runtime in properties.py register() function
    # =========================================================================
    class MetahumanWindowMangerProperties(_MetahumanWindowMangerProperties):
        """Extended WindowManager properties with Pose Editor properties."""

        add_pose_driven_bones: bpy_prop_collection[RBFDrivenBoneSelectionItem]
        add_pose_driven_bones_active_index: int

    # =========================================================================
    # Addon Preferences Types
    # =========================================================================
    class _MetaHumanAddonPreferences(MetahumanAddonProperties, bpy.types.AddonPreferences):
        """Typed addon preferences for MetaHuman DNA."""

        bl_idname: str
        metrics_collection: bool
        show_pose_editor_viewport_overlay: bool
        enable_auto_dna_backups: bool
        max_dna_backups: int
        next_metrics_consent_timestamp: float
        extra_dna_folder_list: ExtraDnaFolders
        extra_dna_folder_list_active_index: int

    class _MetaHumanAddon:
        """Typed addon module reference."""

        preferences: _MetaHumanAddonPreferences

    class _MetaHumanAddons(bpy.types.bpy_prop_collection[bpy.types.Addon]):
        """Typed addons collection with MetaHuman DNA addon."""

        def get(self, name: str, default: _MetaHumanAddon | None = None) -> _MetaHumanAddon | None: ...
        def __getitem__(self, name: str) -> _MetaHumanAddon: ...
        def __contains__(self, name: str) -> bool: ...

    # =========================================================================
    # Patch bpy.types.Preferences
    # =========================================================================
    class Preferences(bpy.types.Preferences):
        """Extended Preferences type with typed addons access."""

        addons: _MetaHumanAddons

    # =========================================================================
    # Patch bpy.types.Scene
    # =========================================================================
    class Scene(bpy.types.Scene):
        """Extended Scene type with MetaHuman DNA properties."""

        meta_human_dna: MetahumanSceneProperties

    # =========================================================================
    # Patch bpy.types.WindowManager
    # =========================================================================
    class WindowManager(bpy.types.WindowManager):
        """Extended WindowManager type with MetaHuman DNA properties."""

        meta_human_dna: MetahumanWindowMangerProperties

    # =========================================================================
    # Patch bpy.types.Context
    # =========================================================================
    class Context(bpy.types.Context):
        """Extended Context type with typed properties."""

        window_manager: WindowManager
        preferences: Preferences
        scene: Scene

    __all__ = [
        "BakeAnimationBase",
        "Context",
        "DnaBackupEntry",
        "DuplicateRigInstance",
        "MetaHumanComponentBody",
        "MetaHumanComponentHead",
        "MetahumanAddonProperties",
        "MetahumanImportProperties",
        "MetahumanSceneProperties",
        "MetahumanWindowMangerProperties",
        "OutputData",
        "Preferences",
        "RBFDrivenBoneSelectionItem",
        "RBFDrivenData",
        "RBFDriverData",
        "RBFPoseData",
        "RBFSolverData",
        "RigInstance",
        "Scene",
        "ShapeKeyData",
        "WindowManager",
        "riglogic",
    ]
