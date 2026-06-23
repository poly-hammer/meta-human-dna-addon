# standard library imports
import json
import logging

from dataclasses import dataclass, field
from pathlib import Path

# local imports
from ..constants import GROOM_GEOMETRY_EXTENSION, GROOM_MANIFEST_FILE_NAME


logger = logging.getLogger(__name__)


# Coordinate space the Unreal commandlet exports in: centimeters, Z-up,
# left-handed. Used when a folder has loose ``.cdgr`` files but no manifest, or
# when a manifest omits the ``space`` block. ``curves_builder`` converts from
# this into Blender's space (meters, Z-up, right-handed).
DEFAULT_SPACE = {"units": "cm", "up_axis": "Z", "handedness": "left"}

# Manifest ``kind`` values.
KIND_STRANDS = "strands"
KIND_CARDS = "cards"


@dataclass
class GroomSource:
    """One groom representation discovered in the export folder.

    The manifest written by the Unreal commandlet (``tools/groom_exporter``)
    lists one of these per groom. ``geometry_path`` points at a binary
    ``.cdgr`` file for ``kind == "strands"`` or at an ``.fbx`` for
    ``kind == "cards"``.
    """

    name: str
    kind: str
    geometry_path: Path
    space: dict = field(default_factory=lambda: dict(DEFAULT_SPACE))
    group_id: int = 0
    lod: int = 0
    surface: str | None = None
    binding: str | None = None
    curve_count: int | None = None
    point_count: int | None = None
    guide_count: int | None = None

    @property
    def is_strands(self) -> bool:
        return self.kind == KIND_STRANDS

    @property
    def is_cards(self) -> bool:
        return self.kind == KIND_CARDS


def read_manifest(folder: Path) -> dict | None:
    """Return the parsed groom manifest in ``folder``, or ``None`` if absent.

    Raises ``ValueError`` if the manifest exists but is not valid JSON.
    """
    manifest_path = Path(folder) / GROOM_MANIFEST_FILE_NAME
    if not manifest_path.is_file():
        return None
    try:
        return json.loads(manifest_path.read_text())
    except json.JSONDecodeError as error:
        raise ValueError(f"'{manifest_path}' is not valid JSON: {error}") from error


def _sources_from_manifest(folder: Path, manifest: dict) -> list[GroomSource]:
    default_space = {**DEFAULT_SPACE, **(manifest.get("space") or {})}
    sources: list[GroomSource] = []
    for entry in manifest.get("grooms", []):
        geometry = entry.get("geometry")
        if not geometry:
            logger.warning("Skipping groom '%s' with no geometry file in the manifest.", entry.get("name"))
            continue
        sources.append(
            GroomSource(
                name=entry.get("name") or Path(geometry).stem,
                kind=entry.get("kind", KIND_STRANDS),
                geometry_path=folder / geometry,
                space={**default_space, **(entry.get("space") or {})},
                group_id=int(entry.get("group_id", 0)),
                lod=int(entry.get("lod", 0)),
                surface=entry.get("surface"),
                binding=entry.get("binding"),
                curve_count=entry.get("curve_count"),
                point_count=entry.get("point_count"),
                guide_count=entry.get("guide_count"),
            )
        )
    return sources


def _sources_from_glob(folder: Path) -> list[GroomSource]:
    """Fallback when there is no manifest: treat every ``.cdgr`` file as a groom."""
    return [
        GroomSource(
            name=geometry_path.stem,
            kind=KIND_STRANDS,
            geometry_path=geometry_path,
            space=dict(DEFAULT_SPACE),
        )
        for geometry_path in sorted(folder.glob(f"*{GROOM_GEOMETRY_EXTENSION}"))
    ]


def _highest_detail(sources: list[GroomSource]) -> list[GroomSource]:
    """Keep only the highest-detail representation of each groom.

    Strands always win over cards (strands are the full-resolution geometry);
    within a kind, the lowest LOD index is the highest detail (LOD0). Grooms are
    keyed by name so a groom that ships both strands and cards collapses to its
    strands entry.
    """
    best: dict[str, GroomSource] = {}
    for source in sources:
        current = best.get(source.name)
        if current is None:
            best[source.name] = source
            continue
        # Prefer strands over cards, then the lower (higher-detail) LOD index.
        current_rank = (0 if current.is_strands else 1, current.lod)
        candidate_rank = (0 if source.is_strands else 1, source.lod)
        if candidate_rank < current_rank:
            best[source.name] = source
    return [best[name] for name in sorted(best)]


def discover_grooms(folder: Path) -> list[GroomSource]:
    """Walk ``folder`` and return the highest-detail source for each groom.

    Reads ``groom_manifest.json`` when present, otherwise falls back to globbing
    ``*.cdgr`` files. The returned list contains at most one entry per groom
    name (strands preferred over cards, LOD0 preferred within a kind).
    """
    folder = Path(folder)
    manifest = read_manifest(folder)
    if manifest is not None:
        sources = _sources_from_manifest(folder, manifest)
    else:
        logger.info(
            "No '%s' found in '%s'; falling back to '*%s' files.",
            GROOM_MANIFEST_FILE_NAME,
            folder,
            GROOM_GEOMETRY_EXTENSION,
        )
        sources = _sources_from_glob(folder)
    return _highest_detail(sources)
