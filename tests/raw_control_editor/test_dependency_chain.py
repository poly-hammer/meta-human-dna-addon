"""Tests for the deterministic dependency-chain resolver (rig-definition name graph).

The pure graph algorithm is validated against ``full.json`` in
``test_expression_graph.py``. These tests cover the resolver that maps that
algorithm onto the live DNA via node names -- ``CTRL_expressions.*`` for raw
controls and ``*_tgt`` targets for PSD combination correctives -- using only the
rig definition (``expressions`` + ``psd_definitions`` + ``psd_nets``), never name
parsing.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from character_dna.editors.shared.dependency_chain import (
    activation_raw_indices,
    build_psd_corrective_rows,
    clear_graph_cache,
    has_dependencies,
    raw_control_node_name,
    resolve_activation_chain,
    resolve_dependency_chain,
)


_PREFIX = "CTRL_expressions."


@pytest.fixture(autouse=True)
def _isolate_graph_cache():
    """The resolver caches one graph per ``db_name``; clear it around every test
    so fixtures with reused names never see a stale graph."""
    clear_graph_cache()
    yield
    clear_graph_cache()


# ---------------------------------------------------------------------------
# Fakes mirroring the minimal riglogic reader + rig-definition surface.
# ---------------------------------------------------------------------------
class _FakeReader:
    def __init__(self, raw_control_names: list[str]) -> None:
        self._names = raw_control_names

    def getRawControlCount(self) -> int:
        return len(self._names)

    def getRawControlName(self, index: int) -> str:
        return self._names[index]


@dataclass
class _Deformer:
    deformation_type: str


@dataclass
class _Expr:
    name: str
    control: str | None = None
    mesh_deformers: list[_Deformer] = field(default_factory=list)


@dataclass
class _PsdDef:
    name: str
    target: str
    layer: int = 1
    corrective: str = ""


@dataclass
class _PsdInput:
    expression: str


@dataclass
class _PsdNet:
    output_expression: str
    psd_definition: str
    inputs: list[_PsdInput] = field(default_factory=list)


@dataclass
class _FakeRigDefinition:
    expressions: list[_Expr]
    psd_definitions: list[_PsdDef]
    psd_nets: list[_PsdNet]
    db_name: str = "test"


def _names(*shorts: str) -> list[str]:
    return [_PREFIX + s for s in shorts]


def _ctrl(short: str) -> str:
    return _PREFIX + short


def _shorts(chain) -> list[str]:
    return [step.short_name for step in chain]


def _blend(name: str, ctrl: str | None = None) -> _Expr:
    """A base raw-control / corrective expression that drives blend shapes."""
    return _Expr(name, ctrl, [_Deformer("JointsAndBlendShapes")])


def _joints(name: str, ctrl: str | None = None) -> _Expr:
    """A combination-only raw-control expression that drives joints only (no
    blend shapes) -- the signature of a control that requires a prerequisite."""
    return _Expr(name, ctrl, [_Deformer("JointsOnly")])


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
def _additive_rig() -> tuple[_FakeReader, _FakeRigDefinition]:
    """The canonical combination-only layer ``jawOpenExtreme -> jawOpen``: the
    dependent control drives joints only (no blend shapes) and shares a psd_net
    with its blend-driving base."""
    reader = _FakeReader(_names("jawOpen", "jawOpenExtreme", "browDownL"))
    rig = _FakeRigDefinition(
        db_name="additive",
        expressions=[
            _blend("jaw_open", _ctrl("jawOpen")),
            _joints("jaw_openExtreme", _ctrl("jawOpenExtreme")),
            _blend("brow_down_L", _ctrl("browDownL")),
        ],
        psd_definitions=[
            _PsdDef("jaw_openExtreme", target="jawOpenExtreme_tgt", layer=1, corrective="jaw_openExtreme_cor"),
        ],
        psd_nets=[
            _PsdNet(
                "jaw_openExtreme_cor",
                "jaw_openExtreme",
                [_PsdInput("jaw_open"), _PsdInput("jaw_openExtreme")],
            ),
        ],
    )
    return reader, rig


def _combo_rig() -> tuple[_FakeReader, _FakeRigDefinition]:
    """A single combination corrective ``Mstretch_Jopen_tgt`` driven by three
    base raw controls (jawOpen + the two mouthStretch sides)."""
    reader = _FakeReader(_names("jawOpen", "mouthStretchL", "mouthStretchR"))
    rig = _FakeRigDefinition(
        db_name="combo",
        expressions=[
            _blend("jaw_open", _ctrl("jawOpen")),
            _blend("mouth_stretch_L", _ctrl("mouthStretchL")),
            _blend("mouth_stretch_R", _ctrl("mouthStretchR")),
            _Expr("Mstretch_Jopen_tgt", None, [_Deformer("BlendShapesOnly")]),
        ],
        psd_definitions=[
            _PsdDef("Mstretch_Jopen", target="Mstretch_Jopen_tgt", layer=2, corrective="Mstretch_Jopen_cor"),
        ],
        psd_nets=[
            _PsdNet(
                "Mstretch_Jopen_cor",
                "Mstretch_Jopen",
                [_PsdInput("jaw_open"), _PsdInput("mouth_stretch_L"), _PsdInput("mouth_stretch_R")],
            ),
        ],
    )
    return reader, rig


def _layered_rig() -> tuple[_FakeReader, _FakeRigDefinition]:
    """Two stacked correctives where ``Mstretch_Jopen_tgt`` (layer 2) covers
    ``Mstretch_tgt`` (layer 1) -- exercising the subset-covering reconstruction
    of an intermediate corrective parent plus a leftover raw control."""
    reader = _FakeReader(_names("jawOpen", "mouthStretchL", "mouthStretchR"))
    rig = _FakeRigDefinition(
        db_name="layered",
        expressions=[
            _blend("jaw_open", _ctrl("jawOpen")),
            _blend("mouth_stretch_L", _ctrl("mouthStretchL")),
            _blend("mouth_stretch_R", _ctrl("mouthStretchR")),
            _Expr("Mstretch_tgt", None, [_Deformer("BlendShapesOnly")]),
            _Expr("Mstretch_Jopen_tgt", None, [_Deformer("JointsAndBlendShapes")]),
        ],
        psd_definitions=[
            _PsdDef("Mstretch", target="Mstretch_tgt", layer=1, corrective="Mstretch_cor"),
            _PsdDef("Mstretch_Jopen", target="Mstretch_Jopen_tgt", layer=2, corrective="Mstretch_Jopen_cor"),
        ],
        psd_nets=[
            _PsdNet("Mstretch_cor", "Mstretch", [_PsdInput("mouth_stretch_L"), _PsdInput("mouth_stretch_R")]),
            _PsdNet(
                "Mstretch_Jopen_cor",
                "Mstretch_Jopen",
                [_PsdInput("jaw_open"), _PsdInput("mouth_stretch_L"), _PsdInput("mouth_stretch_R")],
            ),
        ],
    )
    return reader, rig


def _icon_rig() -> tuple[_FakeReader, _FakeRigDefinition]:
    """Two sibling correctives over the same base controls: one drives a blend
    shape, the other is joints-only -- to assert ``deforms_blends``."""
    reader = _FakeReader(_names("a", "b"))
    rig = _FakeRigDefinition(
        db_name="icon",
        expressions=[
            _blend("ea", _ctrl("a")),
            _blend("eb", _ctrl("b")),
            _Expr("blend_tgt", None, [_Deformer("BlendShapesOnly")]),
            _Expr("bone_tgt", None, [_Deformer("JointsOnly")]),
        ],
        psd_definitions=[
            _PsdDef("blend", target="blend_tgt", layer=1, corrective="blend_cor"),
            _PsdDef("bone", target="bone_tgt", layer=1, corrective="bone_cor"),
        ],
        psd_nets=[
            _PsdNet("blend_cor", "blend", [_PsdInput("ea"), _PsdInput("eb")]),
            _PsdNet("bone_cor", "bone", [_PsdInput("ea"), _PsdInput("eb")]),
        ],
    )
    return reader, rig


# ---------------------------------------------------------------------------
# Combination-only raw controls (JointsOnly + universal co-occurrence, no name parsing)
# ---------------------------------------------------------------------------
def test_additive_layer_resolves_via_psd_definition() -> None:
    reader, rig = _additive_rig()
    chain = resolve_dependency_chain(reader, _ctrl("jawOpenExtreme"), rig)
    assert _shorts(chain) == ["jawOpen"]
    assert chain[0].is_raw is True
    assert chain[0].raw_index == 0
    assert chain[0].layer == 0
    assert chain[0].activation == 1.0


def test_additive_layer_name_alone_is_not_enough() -> None:
    """Without the rig definition the name ``jawOpenExtreme`` must NOT resolve to
    a parent -- proving we never rely on the suffix heuristic."""
    reader, _ = _additive_rig()
    assert resolve_dependency_chain(reader, _ctrl("jawOpenExtreme"), None) == []
    assert has_dependencies(reader, _ctrl("jawOpenExtreme"), None) is False


def test_base_control_has_no_parents() -> None:
    reader, rig = _additive_rig()
    assert resolve_dependency_chain(reader, _ctrl("jawOpen"), rig) == []
    assert has_dependencies(reader, _ctrl("jawOpen"), rig) is False
    assert has_dependencies(reader, _ctrl("jawOpenExtreme"), rig) is True


def test_unrelated_extreme_named_control_has_no_parent() -> None:
    """A control whose name merely ends in 'Extreme' but has no psd_definition
    edge resolves to no parents (the old heuristic would have invented one)."""
    reader = _FakeReader(_names("somethingExtreme"))
    rig = _FakeRigDefinition(db_name="empty", expressions=[], psd_definitions=[], psd_nets=[])
    assert resolve_dependency_chain(reader, _ctrl("somethingExtreme"), rig) == []


# ---------------------------------------------------------------------------
# PSD combination correctives (rig-definition psd_definitions + psd_nets)
# ---------------------------------------------------------------------------
def test_combination_corrective_resolves_to_raw_controls() -> None:
    reader, rig = _combo_rig()
    chain = resolve_dependency_chain(reader, "Mstretch_Jopen_tgt", rig)
    assert {step.short_name for step in chain} == {"jawOpen", "mouthStretchL", "mouthStretchR"}
    assert all(step.is_raw for step in chain)
    assert sorted(step.raw_index for step in chain) == [0, 1, 2]


def test_layered_corrective_parents_via_subset_covering() -> None:
    reader, rig = _layered_rig()
    chain = resolve_dependency_chain(reader, "Mstretch_Jopen_tgt", rig)
    # Full upstream: the three base raw controls plus the intermediate
    # corrective Mstretch_tgt (its parents being the two mouthStretch sides).
    assert {step.short_name for step in chain} == {
        "jawOpen",
        "mouthStretchL",
        "mouthStretchR",
        "Mstretch_tgt",
    }
    corrective = next(step for step in chain if step.short_name == "Mstretch_tgt")
    assert corrective.is_raw is False
    assert corrective.layer == 1
    # Root-first ordering: every layer-0 raw control precedes the layer-1 node.
    corrective_position = _shorts(chain).index("Mstretch_tgt")
    assert all(step.layer == 0 for step in chain[:corrective_position])


def test_resolve_without_rig_definition_is_safe() -> None:
    reader, _ = _combo_rig()
    assert resolve_dependency_chain(reader, "Mstretch_Jopen_tgt", None) == []
    assert has_dependencies(reader, "Mstretch_Jopen_tgt", None) is False


# ---------------------------------------------------------------------------
# Activation chain (parents + leaf) and raw-index extraction
# ---------------------------------------------------------------------------
def test_activation_chain_appends_additive_leaf() -> None:
    reader, rig = _additive_rig()
    chain = resolve_activation_chain(reader, _ctrl("jawOpenExtreme"), rig)
    assert _shorts(chain) == ["jawOpen", "jawOpenExtreme"]
    assert chain[-1].is_leaf is True
    assert chain[-1].layer == 1
    assert all(step.activation == 1.0 for step in chain)
    # Both the parent and the dependent layer are raw controls to drive to 1.0.
    assert activation_raw_indices(chain) == [0, 1]


def test_activation_chain_appends_corrective_leaf() -> None:
    reader, rig = _combo_rig()
    chain = resolve_activation_chain(reader, "Mstretch_Jopen_tgt", rig)
    leaf = chain[-1]
    assert leaf.is_leaf is True
    assert leaf.short_name == "Mstretch_Jopen_tgt"
    assert leaf.is_raw is False
    assert leaf.raw_index == -1
    # Only the base raw controls get driven; the computed corrective leaf does not.
    assert sorted(activation_raw_indices(chain)) == [0, 1, 2]


def test_activation_chain_without_rig_returns_leaf_only() -> None:
    reader, _ = _additive_rig()
    chain = resolve_activation_chain(reader, _ctrl("jawOpenExtreme"), None)
    assert len(chain) == 1
    assert chain[0].is_leaf is True
    assert chain[0].short_name == "jawOpenExtreme"


# ---------------------------------------------------------------------------
# raw_control_node_name
# ---------------------------------------------------------------------------
def test_raw_control_node_name_round_trips() -> None:
    reader, _ = _additive_rig()
    assert raw_control_node_name(reader, 1) == _ctrl("jawOpenExtreme")


# ---------------------------------------------------------------------------
# PSD corrective listing (names are the symmetric `_tgt` targets)
# ---------------------------------------------------------------------------
def test_build_psd_corrective_rows_names_by_target() -> None:
    reader, rig = _combo_rig()
    rows = build_psd_corrective_rows(reader, rig)
    assert len(rows) == 1
    row = rows[0]
    assert row.name == "Mstretch_Jopen_tgt"
    assert row.layer == 2
    assert row.base_control_indices == (0, 1, 2)
    assert row.deforms_blends is True


def test_build_psd_corrective_rows_excludes_additive_layer() -> None:
    """The combination-only raw control jawOpenExtreme owns a dedicated 1:1
    corrective (psd_def named after it); that is represented by the raw-control
    row, so it must not appear in the computed corrective listing."""
    reader, rig = _additive_rig()
    assert build_psd_corrective_rows(reader, rig) == []


def test_build_psd_corrective_rows_sorted_by_layer_then_name() -> None:
    reader, rig = _layered_rig()
    rows = build_psd_corrective_rows(reader, rig)
    assert [(row.name, row.layer) for row in rows] == [
        ("Mstretch_tgt", 1),
        ("Mstretch_Jopen_tgt", 2),
    ]


def test_build_psd_corrective_rows_without_rig_is_empty() -> None:
    reader, _ = _combo_rig()
    assert build_psd_corrective_rows(reader, None) == []


def test_deforms_blends_distinguishes_blend_and_joint_correctives() -> None:
    reader, rig = _icon_rig()
    rows = {row.name: row for row in build_psd_corrective_rows(reader, rig)}
    assert rows["blend_tgt"].deforms_blends is True
    assert rows["bone_tgt"].deforms_blends is False


# ---------------------------------------------------------------------------
# Combination-only edge cases
# ---------------------------------------------------------------------------
def test_combination_only_with_no_psd_net_edits_solo() -> None:
    """A joints-only control (e.g. a teeth control) that participates in no psd
    combination has no prerequisite -- it edits solo."""
    reader = _FakeReader(_names("teethUpU", "jawOpen"))
    rig = _FakeRigDefinition(
        db_name="solo",
        expressions=[_joints("teeth_upU", _ctrl("teethUpU")), _blend("jaw_open", _ctrl("jawOpen"))],
        psd_definitions=[],
        psd_nets=[],
    )
    assert resolve_dependency_chain(reader, _ctrl("teethUpU"), rig) == []
    assert has_dependencies(reader, _ctrl("teethUpU"), rig) is False


def test_prerequisite_must_be_a_blend_driving_base() -> None:
    """Two joints-only controls sharing a psd_net: neither is a valid prerequisite
    for the other, because a prerequisite must itself be an independent base that
    drives blend shapes."""
    reader = _FakeReader(_names("aJoints", "bJoints"))
    rig = _FakeRigDefinition(
        db_name="joints_pair",
        expressions=[_joints("a_joints", _ctrl("aJoints")), _joints("b_joints", _ctrl("bJoints"))],
        psd_definitions=[],
        psd_nets=[_PsdNet("ab_cor", "ab", [_PsdInput("a_joints"), _PsdInput("b_joints")])],
    )
    assert resolve_dependency_chain(reader, _ctrl("aJoints"), rig) == []
    assert resolve_dependency_chain(reader, _ctrl("bJoints"), rig) == []


def test_only_universal_co_occurrence_is_a_prerequisite() -> None:
    """jawOpenExtreme appears in two combos: [jawOpen, jawOpenExtreme] and
    [jawOpen, mouthStretchL, jawOpenExtreme]. Only jawOpen is present in BOTH, so
    it is the sole prerequisite (mouthStretchL is not)."""
    reader = _FakeReader(_names("jawOpen", "mouthStretchL", "jawOpenExtreme"))
    rig = _FakeRigDefinition(
        db_name="universal",
        expressions=[
            _blend("jaw_open", _ctrl("jawOpen")),
            _blend("mouth_stretch_L", _ctrl("mouthStretchL")),
            _joints("jaw_openExtreme", _ctrl("jawOpenExtreme")),
        ],
        psd_definitions=[],
        psd_nets=[
            _PsdNet("a", "a", [_PsdInput("jaw_open"), _PsdInput("jaw_openExtreme")]),
            _PsdNet("b", "b", [_PsdInput("jaw_open"), _PsdInput("mouth_stretch_L"), _PsdInput("jaw_openExtreme")]),
        ],
    )
    assert _shorts(resolve_dependency_chain(reader, _ctrl("jawOpenExtreme"), rig)) == ["jawOpen"]


# ---------------------------------------------------------------------------
# Real MH.6 rig definition -- the canonical raw-control -> raw-control
# dependencies, verified against the gzip by
# scratches/raw-control-editor/multi-expression-support/probe_all_raw_deps.py.
# ---------------------------------------------------------------------------

# (combination-only control, sorted prerequisite controls). These are the COMPLETE
# set of raw-control -> raw-control dependencies in MH.6: a control that drives
# joints only (no blend shapes) and universally co-occurs with a blend-driving base.
_REAL_RAW_DEPENDENCIES = [
    ("eyeLidPressL", ["eyeBlinkL"]),
    ("eyeLidPressR", ["eyeBlinkR"]),
    ("jawOpenExtreme", ["jawOpen"]),
    ("mouthStretchLipsCloseL", ["mouthStretchL"]),
    ("mouthStretchLipsCloseR", ["mouthStretchR"]),
    ("noseWrinkleUpperL", ["noseWrinkleL"]),
    ("noseWrinkleUpperR", ["noseWrinkleR"]),
]

# Independent BASE controls (drive blend shapes) -- must have NO dependency.
_REAL_BASE_CONTROLS = [
    "jawOpen",
    "eyeBlinkL",
    "eyeBlinkR",
    "mouthStretchL",
    "noseWrinkleL",
    "eyeSquintInnerR",
    "eyeCheekRaiseR",
    "mouthCornerPullL",
    "browDownL",
]

# Joints-only controls that are independent (no universal base co-occurrence).
_REAL_SOLO_CONTROLS = ["teethUpU", "teethBackD", "eyelashesDownINL", "mouthLipsTogetherUL"]


@pytest.fixture(scope="module")
def real_rig():
    from character_dna.rig_definition.head import HeadRigDefinition

    return HeadRigDefinition.load()


def _real_reader(rig) -> _FakeReader:
    """A reader exposing every CTRL_expressions.* control on the real rig."""
    return _FakeReader(sorted({e.control for e in rig.expressions if e.control}))


@pytest.mark.parametrize(("control", "expected_parents"), _REAL_RAW_DEPENDENCIES)
def test_real_combination_only_dependencies(real_rig, control, expected_parents) -> None:
    reader = _real_reader(real_rig)
    chain = resolve_dependency_chain(reader, _ctrl(control), real_rig)
    assert _shorts(chain) == expected_parents
    # The activation chain drives every prerequisite AND the control itself to 1.0.
    activation = resolve_activation_chain(reader, _ctrl(control), real_rig)
    driven = sorted(step.short_name for step in activation if step.is_raw and step.raw_index >= 0)
    assert driven == sorted([*expected_parents, control])


@pytest.mark.parametrize("control", _REAL_BASE_CONTROLS)
def test_real_base_controls_have_no_dependency(real_rig, control) -> None:
    reader = _real_reader(real_rig)
    assert resolve_dependency_chain(reader, _ctrl(control), real_rig) == []
    assert has_dependencies(reader, _ctrl(control), real_rig) is False


@pytest.mark.parametrize("control", _REAL_SOLO_CONTROLS)
def test_real_solo_joints_controls_have_no_dependency(real_rig, control) -> None:
    reader = _real_reader(real_rig)
    assert resolve_dependency_chain(reader, _ctrl(control), real_rig) == []


def test_real_dependency_set_is_exactly_the_seven(real_rig) -> None:
    """Guard against over-triggering: scanning EVERY raw control on the real MH.6
    rig yields exactly the seven verified dependencies -- no more, no less."""
    reader = _real_reader(real_rig)
    found: dict[str, list[str]] = {}
    for index in range(reader.getRawControlCount()):
        name = reader.getRawControlName(index)
        chain = resolve_dependency_chain(reader, name, real_rig)
        if chain:
            found[name.replace(_PREFIX, "")] = sorted(step.short_name for step in chain)
    assert found == {control: sorted(parents) for control, parents in _REAL_RAW_DEPENDENCIES}
