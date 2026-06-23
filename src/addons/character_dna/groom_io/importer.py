# standard library imports
import logging

from collections.abc import Callable
from pathlib import Path

# third party imports
import bpy

# local imports
from .curves_builder import build_curves_object
from .discovery import discover_grooms
from .io import read_groom_geometry


logger = logging.getLogger(__name__)


class GroomImporter:
    """Import MetaHuman/Unreal grooms (exported by ``tools/groom_exporter``) as
    Blender hair ``Curves`` objects.

    Mirrors :class:`~character_dna.dna_io.exporter.DNAExporter`: construct with
    the scene data it needs, then call :meth:`run`, which returns the same
    ``(valid, title, message, fix)`` tuple the operators consume.
    """

    def __init__(
        self,
        folder_path: str | Path,
        surface_object: bpy.types.Object | None = None,
        collection_name: str | None = None,
        attach_to_surface: bool = True,
        import_cards: bool = True,
    ):
        self._folder = Path(bpy.path.abspath(str(folder_path)))
        self._surface_object = surface_object
        self._collection_name = collection_name
        self._attach_to_surface = attach_to_surface
        self._import_cards = import_cards
        self.imported_objects: list[bpy.types.Object] = []

    def _get_or_create_collection(self) -> bpy.types.Collection | None:
        """Return the destination collection, clearing it first so re-imports
        replace rather than duplicate the grooms."""
        if not self._collection_name:
            return None

        collection = bpy.data.collections.get(self._collection_name)
        if collection is None:
            collection = bpy.data.collections.new(self._collection_name)
            if bpy.context.scene:
                bpy.context.scene.collection.children.link(collection)
            return collection

        # Existing collection: remove its objects (and orphaned data) so the
        # re-import starts clean.
        for scene_object in list(collection.objects):
            data = scene_object.data
            bpy.data.objects.remove(scene_object, do_unlink=True)
            if isinstance(data, bpy.types.Curves) and data.users == 0:
                bpy.data.hair_curves.remove(data)
        return collection

    def _import_card_fbx(self, geometry_path: Path, collection: bpy.types.Collection | None) -> list[bpy.types.Object]:
        """Import a hair-cards FBX (Unreal's native export) into ``collection``."""
        if not geometry_path.exists():
            logger.warning("Groom cards FBX '%s' is missing; skipping.", geometry_path)
            return []
        try:
            before = set(bpy.data.objects)
            bpy.ops.import_scene.fbx(filepath=str(geometry_path))
        except Exception as error:
            logger.error("Failed to import groom cards FBX '%s': %s", geometry_path, error)
            return []

        new_objects = [scene_object for scene_object in bpy.data.objects if scene_object not in before]
        if collection is not None:
            for scene_object in new_objects:
                for user_collection in list(scene_object.users_collection):
                    user_collection.objects.unlink(scene_object)
                collection.objects.link(scene_object)
        return new_objects

    def run(self) -> tuple[bool, str, str, Callable | None]:
        if not self._folder.exists():
            return (False, "Groom Folder Not Found", f'The groom folder "{self._folder}" does not exist.', None)
        if not self._folder.is_dir():
            return (False, "Invalid Groom Folder", f'"{self._folder}" is not a folder.', None)

        try:
            sources = discover_grooms(self._folder)
        except ValueError as error:
            return (False, "Invalid Groom Manifest", str(error), None)

        if not sources:
            return (
                False,
                "No Grooms Found",
                f'No groom manifest or "*.cdgr" files were found in "{self._folder}".',
                None,
            )

        collection = self._get_or_create_collection()
        built: list[str] = []
        skipped: list[str] = []

        for source in sources:
            if source.is_cards:
                if not self._import_cards:
                    skipped.append(f"{source.name} (cards)")
                    continue
                card_objects = self._import_card_fbx(source.geometry_path, collection)
                if card_objects:
                    self.imported_objects.extend(card_objects)
                    built.append(f"{source.name} (cards)")
                else:
                    skipped.append(f"{source.name} (cards)")
                continue

            if not source.geometry_path.exists():
                logger.warning("Groom geometry '%s' is missing; skipping.", source.geometry_path)
                skipped.append(source.name)
                continue

            try:
                geometry = read_groom_geometry(source.geometry_path)
            except ValueError as error:
                logger.error("Failed to read groom '%s': %s", source.name, error)
                skipped.append(source.name)
                continue

            curves_object = build_curves_object(
                source,
                geometry,
                collection=collection,
                surface_object=self._surface_object,
                attach_to_surface=self._attach_to_surface,
            )
            self.imported_objects.append(curves_object)
            built.append(f"{source.name} ({geometry.curve_count} curves)")

        if not self.imported_objects:
            return (
                False,
                "Groom Import Failed",
                "No grooms could be imported. See the system console for details.",
                None,
            )

        message = f"Imported {len(self.imported_objects)} groom(s): " + ", ".join(built)
        if skipped:
            message += f". Skipped: {', '.join(skipped)}"
        logger.info(message)
        return (True, "Success", message, None)
