"""Parameterized tests for the deterministic expression-dependency graph.

The ground truth is ``tests/test_files/json/expression_graphs/full.json`` -- the
expression DAG serialized by the MetaHuman Expression Editor. Every corrective
node declares its ``inputs`` (the expressions it depends on); its ``outputs``
and ``layer`` are derived quantities. These tests prove our graph algorithm
reproduces both deterministically, with NO reliance on name conventions, and
that the dependency chain (transitive inputs) is correct for the documented
combination/additive poses.
"""

from __future__ import annotations

import json

from pathlib import Path

import pytest

from character_dna.editors.shared.expression_graph import (
    base_ancestors,
    collect_upstream,
    derive_layers,
    derive_outputs,
    ordered_upstream,
)


# ---------------------------------------------------------------------------
# Load the ground-truth expression graph once.
# ---------------------------------------------------------------------------
_FULL_JSON = Path(__file__).parent.parent / "test_files" / "json" / "expression_graphs" / "full.json"
_NODES: dict[str, dict] = json.loads(_FULL_JSON.read_text())["nodes"]

_INPUTS_BY_NODE: dict[str, list[str]] = {name: list(node["inputs"]) for name, node in _NODES.items()}
# Intrinsic layer of every input-less source node (most are 0; the head
# turn/tilt drivers are authored at layer 1). Seeding these reproduces the
# authored layer of every downstream node via the 1+max propagation rule.
_SOURCE_LAYERS: dict[str, int] = {name: node["layer"] for name, node in _NODES.items() if not node["inputs"]}
_DERIVED_OUTPUTS = derive_outputs(_INPUTS_BY_NODE)
_DERIVED_LAYERS = derive_layers(_INPUTS_BY_NODE, _SOURCE_LAYERS)
_NODE_NAMES = sorted(_NODES)
# Nodes that declare at least one input -- the layer rule is exact for these.
_NODES_WITH_INPUTS = sorted(n for n, ins in _INPUTS_BY_NODE.items() if ins)


def test_full_json_loaded() -> None:
    """Sanity: the fixture exists and has the expected shape/scale."""
    assert _FULL_JSON.is_file()
    assert len(_NODES) == 351
    assert {node["layer"] for node in _NODES.values()} == {0, 1, 2, 3, 4, 5, 6}


# ---------------------------------------------------------------------------
# Outputs are 100% derivable from inputs (Maya sort_nodes_by_layer invariant).
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("name", _NODE_NAMES)
def test_outputs_derived_from_inputs(name: str) -> None:
    """``outputs`` is the exact reverse of every node's ``inputs`` -- never an
    independently authored field. This is what makes the graph deterministic."""
    assert sorted(_DERIVED_OUTPUTS[name]) == sorted(_NODES[name]["outputs"])


# ---------------------------------------------------------------------------
# Layer == topological depth for every node that has inputs.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("name", _NODES_WITH_INPUTS)
def test_layer_is_topological_depth(name: str) -> None:
    """For any node with inputs, ``layer == 1 + max(layer(input))``. Seeded by
    the intrinsic root layers and derived purely from the edges -- no name
    parsing, no per-node stored-layer trust."""
    assert _DERIVED_LAYERS[name] == _NODES[name]["layer"]


def test_every_layer_reproduced_from_roots() -> None:
    """Seeding only the input-less source nodes' layers reproduces EVERY node's
    authored layer via the 1+max propagation -- the whole-graph determinism
    guarantee."""
    mismatched = {name for name, node in _NODES.items() if _DERIVED_LAYERS[name] != node["layer"]}
    assert not mismatched


# ---------------------------------------------------------------------------
# Dependency chains (transitive inputs) for the documented poses.
# ---------------------------------------------------------------------------
# (node, expected base-expression ancestors). These are the deterministic
# co-activation sets the Raw Control Editor must drive. Verified against
# full.json by scratches/.../extract_examples.py.
_CHAIN_CASES = [
    # The canonical additive layer.
    ("jaw_openExtreme_tgt", {"jaw_open"}),
    # Five other combination/additive poses for manual verification.
    ("Jleft_Jopen_tgt", {"jaw_left", "jaw_open"}),
    ("Mstretch_Jopen_tgt", {"jaw_open", "mouth_stretch_left", "mouth_stretch_right"}),
    ("McornerPull_Jopen_tgt", {"jaw_open", "mouth_cornerPull_left", "mouth_cornerPull_right"}),
    (
        "NSwrinkle_Jopen_tgt",
        {"jaw_open", "nose_wrinkle_left", "nose_wrinkle_right"},
    ),
    (
        "MupperLipRaise_MlowerLipDepress_tgt",
        {
            "mouth_upperLipRaise_left",
            "mouth_upperLipRaise_right",
            "mouth_lowerLipDepress_left",
            "mouth_lowerLipDepress_right",
        },
    ),
]


@pytest.mark.parametrize(("node", "expected_bases"), _CHAIN_CASES)
def test_base_ancestors_match(node: str, expected_bases: set[str]) -> None:
    """The layer-0 base ancestors of each documented corrective are exactly the
    raw-control-backed expressions the artist co-activates."""
    assert base_ancestors(node, _INPUTS_BY_NODE) == expected_bases


@pytest.mark.parametrize(("node", "expected_bases"), _CHAIN_CASES)
def test_ordered_upstream_is_root_first(node: str, expected_bases: set[str]) -> None:
    """The activation order is ascending by layer (roots first) and ends just
    below the selected node; every base ancestor appears before any corrective."""
    chain = ordered_upstream(node, _INPUTS_BY_NODE, _DERIVED_LAYERS)
    layers = [_DERIVED_LAYERS[n] for n in chain]
    assert layers == sorted(layers)
    # All base ancestors are present and sit at the front (layer 0).
    front = {n for n in chain if _DERIVED_LAYERS[n] == 0}
    assert front == expected_bases


def test_deep_corrective_resolves_full_chain() -> None:
    """The deepest node (layer 6) resolves to the full 9-base-expression set,
    matching the DNA PSD matrix probe."""
    deep = "McornerPull_Mstretch_MupperLipRaise_MlowerLipDepress_JopenExtreme_tgt"
    assert _NODES[deep]["layer"] == 6
    assert base_ancestors(deep, _INPUTS_BY_NODE) == {
        "jaw_open",
        "mouth_cornerPull_left",
        "mouth_cornerPull_right",
        "mouth_lowerLipDepress_left",
        "mouth_lowerLipDepress_right",
        "mouth_stretch_left",
        "mouth_stretch_right",
        "mouth_upperLipRaise_left",
        "mouth_upperLipRaise_right",
    }
    # jaw_openExtreme is reached transitively (additive layer inside the chain).
    assert "jaw_openExtreme_tgt" in collect_upstream(deep, _INPUTS_BY_NODE)


def test_base_expression_has_no_chain() -> None:
    """A layer-0 base expression depends on nothing -> empty chain."""
    assert collect_upstream("jaw_open", _INPUTS_BY_NODE) == set()
    assert ordered_upstream("jaw_open", _INPUTS_BY_NODE, _DERIVED_LAYERS) == []
