# standard library imports
import logging
import struct

from dataclasses import dataclass
from pathlib import Path

# third party imports
import numpy as np


logger = logging.getLogger(__name__)


# Binary groom-geometry container. The Unreal commandlet (see
# ``tools/groom_exporter``) and the Python fixture generator write this format;
# :func:`read_groom_geometry` reads it. The matching JSON manifest that lists the
# per-groom geometry files lives next to these files (see ``discovery.py``).
#
# This module is deliberately free of ``bpy``/``constants`` imports so the codec
# can be exercised standalone (fixtures, the commandlet round-trip tests, plain
# ``python``). The Blender-specific conversion happens in ``curves_builder.py``.
#
# Little-endian throughout. Layout:
#
#   magic         char[4]        b"CDGR"
#   version       uint32         == FORMAT_VERSION
#   curve_count   uint32         N
#   point_count   uint32         P
#   flags         uint32         bitmask of FLAG_*
#   reserved      uint32         == 0
#   curve_offsets int32[N + 1]   offset-index topology ([0] == 0, [N] == P);
#                                 maps 1:1 onto Blender's CurvesGeometry offsets
#   positions     float32[P * 3] x, y, z per point, in the SOURCE space declared
#                                 by the manifest (Unreal: cm, Z-up, left-handed)
#   widths        float32[P]     per-point strand width (diameter), if FLAG_WIDTHS
#   root_uv       float32[N * 2] per-curve scalp/root UV, if FLAG_ROOT_UV
#   group_id      int32[N]       per-curve groom group id, if FLAG_GROUP_ID
#   guide         int32[N]       per-curve guide flag (1 == guide), if FLAG_GUIDE
MAGIC = b"CDGR"
FORMAT_VERSION = 1
_HEADER = struct.Struct("<4sIIIII")

FLAG_WIDTHS = 1 << 0
FLAG_ROOT_UV = 1 << 1
FLAG_GROUP_ID = 1 << 2
FLAG_GUIDE = 1 << 3


@dataclass
class GroomGeometry:
    """A single groom's curve geometry in its source coordinate space.

    ``positions`` are kept exactly as Unreal exported them (centimeters, Z-up,
    left-handed); the conversion into Blender's space happens in
    :mod:`curves_builder`, so the on-disk data stays a faithful copy of the
    source. Topology uses the same offset-index encoding as Blender's
    ``CurvesGeometry`` (``curve_offsets[i]..curve_offsets[i + 1]`` is curve *i*).
    """

    curve_offsets: np.ndarray  # int32, shape (curve_count + 1,)
    positions: np.ndarray  # float32, shape (point_count, 3)
    widths: np.ndarray | None = None  # float32, shape (point_count,)
    root_uv: np.ndarray | None = None  # float32, shape (curve_count, 2)
    group_id: np.ndarray | None = None  # int32, shape (curve_count,)
    guide: np.ndarray | None = None  # int32, shape (curve_count,)

    @property
    def curve_count(self) -> int:
        return int(self.curve_offsets.shape[0] - 1)

    @property
    def point_count(self) -> int:
        return int(self.positions.shape[0])

    @property
    def curve_sizes(self) -> np.ndarray:
        """Per-curve point counts, derived from the offset-index topology."""
        return np.diff(self.curve_offsets).astype(np.int32)


def _validate(geometry: GroomGeometry, source: Path | str) -> None:
    """Raise ``ValueError`` if the geometry's arrays are internally inconsistent."""
    offsets = geometry.curve_offsets
    if offsets.ndim != 1 or offsets.shape[0] < 1:
        raise ValueError(f"'{source}' has a malformed curve offset array.")
    if int(offsets[0]) != 0:
        raise ValueError(f"'{source}' curve offsets must start at 0.")
    if geometry.positions.ndim != 2 or geometry.positions.shape[1] != 3:
        raise ValueError(f"'{source}' positions must have shape (point_count, 3).")
    if int(offsets[-1]) != geometry.point_count:
        raise ValueError(
            f"'{source}' last curve offset ({int(offsets[-1])}) does not match the point count "
            f"({geometry.point_count})."
        )
    if np.any(np.diff(offsets) < 0):
        raise ValueError(f"'{source}' curve offsets are not monotonically increasing.")

    count = geometry.curve_count
    points = geometry.point_count
    for name, array, expected in (
        ("widths", geometry.widths, (points,)),
        ("root_uv", geometry.root_uv, (count, 2)),
        ("group_id", geometry.group_id, (count,)),
        ("guide", geometry.guide, (count,)),
    ):
        if array is not None and tuple(array.shape) != expected:
            raise ValueError(f"'{source}' {name} array has shape {tuple(array.shape)}, expected {expected}.")


def read_groom_geometry(file_path: Path | str) -> GroomGeometry:
    """Read a ``.cdgr`` groom-geometry file into a :class:`GroomGeometry`."""
    file_path = Path(file_path)
    data = file_path.read_bytes()
    if len(data) < _HEADER.size:
        raise ValueError(f"'{file_path}' is too small to be a groom geometry file.")

    magic, version, curve_count, point_count, flags, _reserved = _HEADER.unpack_from(data, 0)
    if magic != MAGIC:
        raise ValueError(f"'{file_path}' is not a groom geometry file (unexpected magic {magic!r}).")
    if version != FORMAT_VERSION:
        raise ValueError(
            f"'{file_path}' uses groom format version {version}, but this add-on only reads version {FORMAT_VERSION}."
        )

    cursor = _HEADER.size

    def take(dtype: type, count: int) -> np.ndarray:
        nonlocal cursor
        little_endian = np.dtype(dtype).newbyteorder("<")
        array = np.frombuffer(data, dtype=little_endian, count=count, offset=cursor)
        cursor += array.nbytes
        # Copy out of the read-only file buffer so downstream code can reshape/edit freely.
        return np.asarray(array, dtype=dtype).copy()

    curve_offsets = take(np.int32, curve_count + 1)
    positions = take(np.float32, point_count * 3).reshape(-1, 3)
    widths = take(np.float32, point_count) if flags & FLAG_WIDTHS else None
    root_uv = take(np.float32, curve_count * 2).reshape(-1, 2) if flags & FLAG_ROOT_UV else None
    group_id = take(np.int32, curve_count) if flags & FLAG_GROUP_ID else None
    guide = take(np.int32, curve_count) if flags & FLAG_GUIDE else None

    geometry = GroomGeometry(
        curve_offsets=curve_offsets,
        positions=positions,
        widths=widths,
        root_uv=root_uv,
        group_id=group_id,
        guide=guide,
    )
    _validate(geometry, file_path)
    return geometry


def _to_little_endian_bytes(array: np.ndarray, dtype: type) -> bytes:
    return np.ascontiguousarray(array, dtype=np.dtype(dtype).newbyteorder("<")).tobytes()


def write_groom_geometry(file_path: Path | str, geometry: GroomGeometry) -> None:
    """Write a :class:`GroomGeometry` to a ``.cdgr`` file.

    Mirrors the layout the Unreal commandlet emits; used by the fixture
    generator and the round-trip tests.
    """
    file_path = Path(file_path)
    _validate(geometry, file_path)

    flags = 0
    if geometry.widths is not None:
        flags |= FLAG_WIDTHS
    if geometry.root_uv is not None:
        flags |= FLAG_ROOT_UV
    if geometry.group_id is not None:
        flags |= FLAG_GROUP_ID
    if geometry.guide is not None:
        flags |= FLAG_GUIDE

    chunks = [
        _HEADER.pack(MAGIC, FORMAT_VERSION, geometry.curve_count, geometry.point_count, flags, 0),
        _to_little_endian_bytes(geometry.curve_offsets, np.int32),
        _to_little_endian_bytes(geometry.positions, np.float32),
    ]
    if geometry.widths is not None:
        chunks.append(_to_little_endian_bytes(geometry.widths, np.float32))
    if geometry.root_uv is not None:
        chunks.append(_to_little_endian_bytes(geometry.root_uv, np.float32))
    if geometry.group_id is not None:
        chunks.append(_to_little_endian_bytes(geometry.group_id, np.int32))
    if geometry.guide is not None:
        chunks.append(_to_little_endian_bytes(geometry.guide, np.int32))

    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(b"".join(chunks))
    logger.info(
        "Wrote groom geometry '%s' (%d curves, %d points).", file_path, geometry.curve_count, geometry.point_count
    )
