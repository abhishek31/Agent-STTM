"""Render a LineageGraph as a flowchart image (PNG) via Graphviz, so it can be
embedded directly in the Excel workbook (or saved standalone).

Graphviz's `dot` binary is a system dependency (not a pip package) and may not
be on PATH yet in a shell session started before install, even though it's
installed - so this checks common Windows install locations as a fallback
rather than assuming a stale PATH means it's missing.
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

import graphviz

from lineage_mcp.graph import LineageGraph


def _safe_id(node_id: str) -> str:
    # DOT interprets a bare ":" as a node:port reference, which corrupts
    # graph node ids like "table:stg.customers" - so ids are sanitized to
    # plain alphanumerics before being handed to graphviz.
    return re.sub(r"[^a-zA-Z0-9_]", "_", node_id)

_COMMON_WINDOWS_DOT_DIRS = [
    r"C:\Program Files\Graphviz\bin",
    r"C:\Program Files (x86)\Graphviz\bin",
]


def is_available() -> bool:
    return _ensure_dot_on_path()


def _ensure_dot_on_path() -> bool:
    if shutil.which("dot"):
        return True
    for d in _COMMON_WINDOWS_DOT_DIRS:
        if (Path(d) / "dot.exe").exists():
            os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
            return True
    return False


def render_flow_diagram_png(graph: LineageGraph, direction: str = "source_to_target") -> bytes | None:
    """Returns PNG bytes of a left-to-right boxes-and-arrows flowchart, or None
    if Graphviz's `dot` executable isn't available (caller should degrade
    gracefully rather than fail the whole export)."""
    if not _ensure_dot_on_path():
        return None

    dot = graphviz.Digraph(graph_attr={"rankdir": "LR", "bgcolor": "white", "splines": "spline"})
    dot.attr("node", shape="box", style="rounded,filled", fillcolor="#DCE6F1", color="#305496", fontname="Segoe UI", fontsize="10")
    dot.attr("edge", color="#305496", arrowsize="0.7", fontname="Segoe UI", fontsize="9")

    edges = graph.oriented_edges(direction)
    # A flowchart should only show things that actually flow - nodes with no
    # edges at all (e.g. a SOURCE/TARGET declared in the file but never wired
    # into a mapping) are noise, not lineage, so they're left out here even
    # though they may still exist in graph.nodes.
    connected_ids = {e.source for e in edges} | {e.target for e in edges}

    for node_id in connected_ids:
        node = graph.nodes[node_id]
        dot.node(_safe_id(node.id), node.label)
    for edge in edges:
        dot.edge(_safe_id(edge.source), _safe_id(edge.target))

    return dot.pipe(format="png")
