"""Generate the tiny committed groom test fixture.

Produces ``eyelashes/Eyelashes_S_Sparse.cdgr`` + ``eyelashes/groom_manifest.json``:
six short, straight eyelash-like strands (13 points each, 0.83 cm long) in Unreal
space (cm, Z-up, left-handed), matching the real ``Eyelashes_S_Sparse`` groom's
proportions. The data is fully deterministic (no RNG) so the committed bytes are
reproducible across numpy versions.

Run from Blender's Python (it has numpy) so the add-on package imports:

    blender --background --python tests/test_files/groom/generate_fixture.py
"""

import json
import sys

from pathlib import Path

import numpy as np


# Make the add-on package importable when run via ``blender --python``.
REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src" / "addons"))

from character_dna.groom_io.io import GroomGeometry, write_groom_geometry  # noqa: E402


CURVE_COUNT = 6
POINTS_PER_CURVE = 13
STRAND_LENGTH_CM = 0.83  # approx. the real Eyelashes_S_Sparse strand length (cm)
STRAND_WIDTH_CM = 0.012


def build_geometry() -> GroomGeometry:
    sizes = np.full(CURVE_COUNT, POINTS_PER_CURVE, dtype=np.int32)
    offsets = np.concatenate([[0], np.cumsum(sizes)]).astype(np.int32)
    point_count = int(offsets[-1])

    positions = np.zeros((point_count, 3), dtype=np.float32)
    root_uv = np.zeros((CURVE_COUNT, 2), dtype=np.float32)
    for curve in range(CURVE_COUNT):
        # Root near a plausible eyelash location on the head (Unreal cm, Z-up).
        root = np.array([2.0 + 0.3 * curve, 8.5, 159.0], dtype=np.float32)
        for point in range(POINTS_PER_CURVE):
            t = point / (POINTS_PER_CURVE - 1)
            positions[offsets[curve] + point] = root + np.array([STRAND_LENGTH_CM * t, 0.0, 0.0], dtype=np.float32)
        root_uv[curve] = (0.5 + 0.01 * curve, 0.5)

    return GroomGeometry(
        curve_offsets=offsets,
        positions=positions,
        widths=np.full(point_count, STRAND_WIDTH_CM, dtype=np.float32),
        root_uv=root_uv,
        group_id=np.zeros(CURVE_COUNT, dtype=np.int32),
    )


def main() -> None:
    out_dir = Path(__file__).resolve().parent / "eyelashes"
    out_dir.mkdir(parents=True, exist_ok=True)

    geometry = build_geometry()
    write_groom_geometry(out_dir / "Eyelashes_S_Sparse.cdgr", geometry)

    manifest = {
        "format": "character_dna_groom",
        "version": 1,
        "source": "fixture",
        "space": {"units": "cm", "up_axis": "Z", "handedness": "left"},
        "grooms": [
            {
                "name": "Eyelashes_S_Sparse",
                "kind": "strands",
                "geometry": "Eyelashes_S_Sparse.cdgr",
                "group_id": 0,
                "lod": 0,
                "curve_count": geometry.curve_count,
                "point_count": geometry.point_count,
                "guide_count": 0,
                "binding": "Eyelashes_S_Sparse_Binding",
                "surface": "head",
            },
            # A lower-detail cards entry for the same groom, so discovery's
            # "highest detail wins" (strands over cards) is exercised by the test.
            {
                "name": "Eyelashes_S_Sparse",
                "kind": "cards",
                "geometry": "Eyelashes_S_Sparse_CardsMesh_Group0_LOD2.fbx",
                "lod": 2,
            },
        ],
    }
    (out_dir / "groom_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Wrote fixture to {out_dir}")


if __name__ == "__main__":
    main()
