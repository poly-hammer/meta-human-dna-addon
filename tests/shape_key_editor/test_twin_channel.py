"""Tests for the pure-DNA twin-channel resolver used by mirror-on-commit.

``resolve_twin_channel`` maps a sided blend shape channel to its mirror twin
channel using only the DNA: the channel's single driving raw control, that
control's mirrored name, and the channel the twin control drives. Center
channels and combination correctives (multi-raw PSDs) have no twin.
"""

from __future__ import annotations

import pytest

from character_dna.editors.shape_key_editor.core import resolve_twin_channel


_PREFIX = "CTRL_expressions."


class _FakeBehaviorReader:
    """Minimal behavior reader surface used by the twin resolver + backsolve."""

    def __init__(
        self,
        *,
        raw_control_names: list[str],
        channel_names: list[str],
        bsc_input_indices: list[int],
        bsc_output_indices: list[int],
        psd_rows: list[int],
        psd_columns: list[int],
    ) -> None:
        self._raw = raw_control_names
        self._channels = channel_names
        self._bsc_in = bsc_input_indices
        self._bsc_out = bsc_output_indices
        self._psd_rows = psd_rows
        self._psd_cols = psd_columns

    def getRawControlCount(self) -> int:
        return len(self._raw)

    def getRawControlName(self, index: int) -> str:
        return self._raw[index]

    def getBlendShapeChannelCount(self) -> int:
        return len(self._channels)

    def getBlendShapeChannelName(self, index: int) -> str:
        return self._channels[index]

    def getBlendShapeChannelInputIndices(self) -> list[int]:
        return self._bsc_in

    def getBlendShapeChannelOutputIndices(self) -> list[int]:
        return self._bsc_out

    def getPSDRowIndices(self) -> list[int]:
        return self._psd_rows

    def getPSDColumnIndices(self) -> list[int]:
        return self._psd_cols


def _build_reader() -> _FakeBehaviorReader:
    """A rig with a sided pair (brow_down_L/R), a center channel (jaw_open), and
    a combination corrective (jaw_openExtreme_cor driven by a PSD).

    control space: raw [0,4) | psd [4,5)
      raw 0 = browDownL, 1 = browDownR, 2 = jawOpen, 3 = jawOpenExtreme
      psd 4 = jawOpen * jawOpenExtreme (columns 2, 3)
    channels:
      0 brow_down_L          <- raw 0
      1 brow_down_R          <- raw 1
      2 jaw_open             <- raw 2
      3 jaw_openExtreme_cor  <- psd 4
    """
    return _FakeBehaviorReader(
        raw_control_names=[
            _PREFIX + "browDownL",
            _PREFIX + "browDownR",
            _PREFIX + "jawOpen",
            _PREFIX + "jawOpenExtreme",
        ],
        channel_names=["brow_down_L", "brow_down_R", "jaw_open", "jaw_openExtreme_cor"],
        bsc_input_indices=[0, 1, 2, 4],
        bsc_output_indices=[0, 1, 2, 3],
        psd_rows=[4, 4],
        psd_columns=[2, 3],
    )


def test_sided_channel_resolves_to_twin_left() -> None:
    reader = _build_reader()
    assert resolve_twin_channel(reader, "brow_down_L") == ("brow_down_R", "L")


def test_sided_channel_resolves_to_twin_right() -> None:
    reader = _build_reader()
    assert resolve_twin_channel(reader, "brow_down_R") == ("brow_down_L", "R")


def test_center_channel_has_no_twin() -> None:
    reader = _build_reader()
    assert resolve_twin_channel(reader, "jaw_open") is None


def test_combination_corrective_has_no_twin() -> None:
    reader = _build_reader()
    assert resolve_twin_channel(reader, "jaw_openExtreme_cor") is None


def test_unknown_channel_has_no_twin() -> None:
    reader = _build_reader()
    assert resolve_twin_channel(reader, "does_not_exist") is None


# ---------------------------------------------------------------------------
# Real-rig round trip -- the shipped Ada head DNA
# ---------------------------------------------------------------------------
def test_real_ada_dna_twin_round_trips() -> None:
    from character_dna.dna_io import get_dna_reader
    from character_dna.editors.raw_control_editor.core import classify_raw_control_side
    from character_dna.editors.shared.dependency_chain import resolve_blend_shape_raw_controls
    from constants import HEAD_DNA_FILE

    reader = get_dna_reader(file_path=HEAD_DNA_FILE, file_format="binary", data_layer="All")
    raw_count = int(reader.getRawControlCount())
    known = {
        str(reader.getRawControlName(i)).removeprefix(_PREFIX)
        for i in range(raw_count)
        if str(reader.getRawControlName(i)).startswith(_PREFIX)
    }

    def left_side(channel_name: str) -> bool:
        raw_indices = resolve_blend_shape_raw_controls(reader, channel_name)
        if len(raw_indices) != 1:
            return False
        short = str(reader.getRawControlName(raw_indices[0])).removeprefix(_PREFIX)
        return classify_raw_control_side(short, known) == "L"

    checked = 0
    for channel_index in range(int(reader.getBlendShapeChannelCount())):
        name = str(reader.getBlendShapeChannelName(channel_index))
        if not left_side(name):
            continue
        twin = resolve_twin_channel(reader, name)
        assert twin is not None, f"{name!r} (L) should have a twin"
        twin_name, side = twin
        assert side == "L"
        assert twin_name != name
        # The twin must round-trip back to the original as the R side.
        back = resolve_twin_channel(reader, twin_name)
        assert back == (name, "R"), f"{twin_name!r} did not round-trip to ({name!r}, 'R'); got {back!r}"
        checked += 1
        if checked >= 10:
            break

    assert checked > 0, "no left-sided channels found in the Ada head DNA"


@pytest.mark.parametrize("channel", ["jaw_open", "jaw_openExtreme_cor"])
def test_real_ada_dna_center_channels_have_no_twin(channel: str) -> None:
    from character_dna.dna_io import get_dna_reader
    from constants import HEAD_DNA_FILE

    reader = get_dna_reader(file_path=HEAD_DNA_FILE, file_format="binary", data_layer="All")
    assert resolve_twin_channel(reader, channel) is None
