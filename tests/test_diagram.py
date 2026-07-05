import pytest

from lineage_mcp import diagram
from lineage_mcp.graph import LineageGraph, NodeKind


def test_render_flow_diagram_omits_disconnected_nodes():
    if not diagram.is_available():
        pytest.skip("Graphviz 'dot' executable not available in this environment")

    graph = LineageGraph()
    graph.add_node("table:a", NodeKind.TABLE, "a")
    graph.add_node("table:b", NodeKind.TABLE, "b")
    graph.add_node("table:orphan", NodeKind.TABLE, "orphan")  # declared but never wired into any flow
    graph.add_edge("table:a", "table:b")

    png = diagram.render_flow_diagram_png(graph)
    assert png is not None

    dot_source = _rebuild_dot_source(graph)
    assert '"orphan"' not in dot_source.replace("label=", "").replace(" ", " ")


def _rebuild_dot_source(graph: LineageGraph) -> str:
    # render_flow_diagram_png only returns PNG bytes, so re-derive the DOT
    # source the same way to inspect which nodes were actually emitted.
    import graphviz as gv

    dot = gv.Digraph()
    edges = graph.oriented_edges("source_to_target")
    connected_ids = {e.source for e in edges} | {e.target for e in edges}
    for node_id in connected_ids:
        dot.node(node_id, graph.nodes[node_id].label)
    return dot.source


def test_render_flow_diagram_returns_none_without_graphviz(monkeypatch):
    monkeypatch.setattr(diagram, "_ensure_dot_on_path", lambda: False)
    graph = LineageGraph()
    graph.add_node("table:a", NodeKind.TABLE, "a")
    graph.add_node("table:b", NodeKind.TABLE, "b")
    graph.add_edge("table:a", "table:b")
    assert diagram.render_flow_diagram_png(graph) is None
