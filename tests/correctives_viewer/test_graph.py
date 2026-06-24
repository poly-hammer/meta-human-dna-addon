"""Tests for the pure Correctives Viewer dependency-graph builders.

These exercise :mod:`character_dna.editors.correctives_viewer.graph` against a
tiny synthetic DNA reader + rig definition (no Blender, no real DNA): two stacked
correctives ``Mstretch`` (layer 1) and ``Mstretch_Jopen`` (layer 2) over three
raw controls. They cover the layered node model, the subset-covering edges, the
baked ``shapeKeys`` and the focused selected-corrective sub-tree.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from character_dna.editors.correctives_viewer.graph import (
    build_dependency_graph,
    build_selected_subgraph,
    extract_subgraph,
    find_corrective_node_id,
)


class _Reader:
    """Minimal DNA reader exposing the raw-control table and blend-shape behavior
    the graph builder + ``build_psd_corrective_rows`` use."""

    _raw = ["CTRL_expressions.jawOpen", "CTRL_expressions.mouthStretchL", "CTRL_expressions.mouthStretchR"]
    _channels = ["jaw_open", "mouth_stretch_L", "mouth_stretch_R", "Mstretch", "Mstretch_Jopen"]

    def getRawControlCount(self) -> int:
        return len(self._raw)

    def getRawControlName(self, index: int) -> str:
        return self._raw[index]

    def getBlendShapeChannelCount(self) -> int:
        return len(self._channels)

    def getBlendShapeChannelName(self, index: int) -> str:
        return self._channels[index]

    def getBlendShapeChannelOutputIndices(self) -> list[int]:
        return [0, 1, 2, 3, 4]

    def getBlendShapeChannelInputIndices(self) -> list[int]:
        # jaw_open<-0, mouth_stretch_L<-1, mouth_stretch_R<-2; Mstretch<-PSD 3, Mstretch_Jopen<-PSD 4
        return [0, 1, 2, 3, 4]


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


@dataclass
class _PsdInput:
    expression: str


@dataclass
class _PsdNet:
    psd_definition: str
    inputs: list[_PsdInput]


@dataclass
class _RigDefinition:
    expressions: list[_Expr] = field(default_factory=list)
    psd_definitions: list[_PsdDef] = field(default_factory=list)
    psd_nets: list[_PsdNet] = field(default_factory=list)
    db_name: str = "test"


def _rig_definition() -> _RigDefinition:
    blend = [_Deformer("BlendShapesOnly")]
    return _RigDefinition(
        expressions=[
            _Expr("jaw_open", "CTRL_expressions.jawOpen", blend),
            _Expr("mouth_stretch_L", "CTRL_expressions.mouthStretchL", blend),
            _Expr("mouth_stretch_R", "CTRL_expressions.mouthStretchR", blend),
            _Expr("Mstretch_tgt", None, blend),
            _Expr("Mstretch_Jopen_tgt", None, [_Deformer("JointsAndBlendShapes")]),
        ],
        psd_definitions=[
            _PsdDef("Mstretch", target="Mstretch_tgt", layer=1),
            _PsdDef("Mstretch_Jopen", target="Mstretch_Jopen_tgt", layer=2),
        ],
        psd_nets=[
            _PsdNet("Mstretch", [_PsdInput("mouth_stretch_L"), _PsdInput("mouth_stretch_R")]),
            _PsdNet(
                "Mstretch_Jopen",
                [_PsdInput("jaw_open"), _PsdInput("mouth_stretch_L"), _PsdInput("mouth_stretch_R")],
            ),
        ],
    )


def _node(graph, node_id: str) -> dict:
    return next(n["data"] for n in graph.nodes if n["data"]["id"] == node_id)


def _edge_pairs(graph) -> set[tuple[str, str]]:
    return {(e["data"]["source"], e["data"]["target"]) for e in graph.edges}


def test_layered_nodes_kinds_layers_labels() -> None:
    graph = build_dependency_graph(_Reader(), _rig_definition())

    ids = {n["data"]["id"] for n in graph.nodes}
    assert ids == {"raw:0", "raw:1", "raw:2", "c:Mstretch_tgt", "c:Mstretch_Jopen_tgt"}

    assert _node(graph, "raw:0")["kind"] == "raw"
    assert _node(graph, "raw:0")["layer"] == 0
    # Raw labels strip the CTRL_expressions. prefix.
    assert _node(graph, "raw:0")["label"] == "jawOpen"

    top = _node(graph, "c:Mstretch_Jopen_tgt")
    assert top["kind"] == "shape"  # drives blend shapes
    assert top["layer"] == 2
    assert top["target"] == "Mstretch_Jopen_tgt"
    # Label prefers the rig-definition name over the `_tgt` target.
    assert top["label"] == "Mstretch_Jopen"
    assert _node(graph, "c:Mstretch_tgt")["label"] == "Mstretch"


def test_subset_covering_edges_point_left_to_right() -> None:
    graph = build_dependency_graph(_Reader(), _rig_definition())
    # Mstretch (L1) is wired straight from its two raw controls; Mstretch_Jopen
    # (L2) reaches mouth_stretch via the Mstretch corrective and jaw_open direct.
    assert _edge_pairs(graph) == {
        ("raw:1", "c:Mstretch_tgt"),
        ("raw:2", "c:Mstretch_tgt"),
        ("c:Mstretch_tgt", "c:Mstretch_Jopen_tgt"),
        ("raw:0", "c:Mstretch_Jopen_tgt"),
    }


def test_baked_shape_keys() -> None:
    graph = build_dependency_graph(_Reader(), _rig_definition())
    assert _node(graph, "raw:0")["shapeKeys"] == ["jaw_open"]
    assert _node(graph, "c:Mstretch_Jopen_tgt")["shapeKeys"] == ["Mstretch_Jopen"]


def test_selected_subtree_is_focused() -> None:
    graph = build_dependency_graph(_Reader(), _rig_definition())
    node_id = find_corrective_node_id(graph, "Mstretch_tgt")
    assert node_id == "c:Mstretch_tgt"

    sub = extract_subgraph(graph, node_id)
    ids = {n["data"]["id"] for n in sub.nodes}
    # Ancestors (its 2 raw inputs) + root + descendant (Mstretch_Jopen), but NOT
    # jaw_open (raw:0), which only feeds the descendant.
    assert ids == {"raw:1", "raw:2", "c:Mstretch_tgt", "c:Mstretch_Jopen_tgt"}
    assert "raw:0" not in ids


def test_build_selected_subgraph_matches_by_target() -> None:
    sub = build_selected_subgraph(_Reader(), _rig_definition(), "Mstretch_Jopen_tgt", [0, 1, 2])
    ids = {n["data"]["id"] for n in sub.nodes}
    assert ids == {"raw:0", "raw:1", "raw:2", "c:Mstretch_tgt", "c:Mstretch_Jopen_tgt"}


def test_build_selected_subgraph_fallback_for_rbf_corrective() -> None:
    # A corrective with no node in the layered graph (e.g. an RBF head-pose
    # corrective) synthesizes a minimal graph from its base controls.
    sub = build_selected_subgraph(_Reader(), _rig_definition(), "head_turnUp_tgt", [0, 1])
    kinds = {n["data"]["id"]: n["data"]["kind"] for n in sub.nodes}
    assert kinds == {"c:head_turnUp_tgt": "corrective", "raw:0": "raw", "raw:1": "raw"}
    assert _edge_pairs(sub) == {("raw:0", "c:head_turnUp_tgt"), ("raw:1", "c:head_turnUp_tgt")}


def test_empty_when_no_reader_or_no_correctives() -> None:
    assert build_dependency_graph(None) == build_dependency_graph(None)
    assert build_dependency_graph(None).nodes == []
    # No rig definition -> no correctives -> empty graph.
    assert build_dependency_graph(_Reader(), rig_definition=None).nodes == []
