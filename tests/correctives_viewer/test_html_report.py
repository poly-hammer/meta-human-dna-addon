"""Tests for the offline HTML report renderer.

Verifies the generated page is self-contained: the libraries and icons are
inlined and there are no external ``<script src>`` / CDN references.
"""

from __future__ import annotations

import json

from pathlib import Path

import pytest

from character_dna.editors.correctives_viewer import html_report
from character_dna.editors.correctives_viewer.graph import GraphData


@pytest.fixture
def _graph() -> GraphData:
    return GraphData(
        nodes=[
            {"data": {"id": "raw:0", "label": "jawOpen", "kind": "raw"}},
            {"data": {"id": "psd:3", "label": "Mstretch_Jopen", "kind": "corrective", "layer": 2}},
        ],
        edges=[{"data": {"id": "raw:0__psd:3", "source": "raw:0", "target": "psd:3"}}],
    )


def test_report_is_self_contained(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, _graph: GraphData) -> None:
    monkeypatch.setattr(html_report, "_output_dir", lambda: tmp_path)

    out = html_report.render_graph_html(_graph, "My Title", file_stem="report")
    assert out == tmp_path / "report.html"

    document = out.read_text(encoding="utf-8")

    # The libraries are inlined -- no external/CDN script or stylesheet loads.
    assert "<script src=" not in document
    assert "cdn.jsdelivr" not in document
    assert "unpkg" not in document
    assert 'src="http' not in document

    # Cytoscape is present (inlined), as are the icon data URIs.
    assert "cytoscape" in document
    assert "data:image/svg+xml;base64," in document

    # The vendored library is genuinely inlined (not just referenced by the app
    # code) -- guards against a dropped/typo'd ``{{CYTOSCAPE_JS}}`` placeholder.
    vendor_js = (html_report._VENDOR / "cytoscape.min.js").read_text(encoding="utf-8")
    assert vendor_js in document
    # The placeholder token must not survive unreplaced into the rendered page.
    assert "CYTOSCAPE_JS" not in document

    # The graph payload is embedded and parseable.
    start = document.index('<script type="application/json" id="graph-data">') + len(
        '<script type="application/json" id="graph-data">'
    )
    end = document.index("</script>", start)
    payload = json.loads(document[start:end].replace("<\\/", "</"))
    assert {n["data"]["id"] for n in payload["nodes"]} == {"raw:0", "psd:3"}


def test_report_escapes_script_breakout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(html_report, "_output_dir", lambda: tmp_path)
    # A (contrived) label containing a closing script tag must not break out.
    graph = GraphData(nodes=[{"data": {"id": "shape:0", "label": "a</script><b>", "kind": "shape"}}], edges=[])
    document = html_report.render_graph_html(graph, "t", file_stem="esc").read_text(encoding="utf-8")
    assert "a</script><b>" not in document
    assert "a<\\/script>" in document
