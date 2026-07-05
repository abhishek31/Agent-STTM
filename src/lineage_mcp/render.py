"""Render a LineageGraph as a Mermaid flowchart or a markdown lineage report."""

from __future__ import annotations

import re

from lineage_mcp.graph import LineageGraph


def _mermaid_id(node_id: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]", "_", node_id)


def to_mermaid(graph: LineageGraph, direction: str = "source_to_target") -> str:
    lines = ["flowchart LR"]
    for node in graph.nodes.values():
        label = node.label.replace('"', "'")
        lines.append(f'    {_mermaid_id(node.id)}["{label}"]')
    for edge in graph.oriented_edges(direction):
        lines.append(f"    {_mermaid_id(edge.source)} --> {_mermaid_id(edge.target)}")
    return "\n".join(lines)


def to_report(graph: LineageGraph, direction: str = "source_to_target") -> str:
    edges = graph.oriented_edges(direction)
    if not edges:
        return "No lineage relationships found."

    header = "| From | To | Detail |\n|---|---|---|"
    rows = []
    for e in edges:
        from_label = graph.nodes[e.source].label if e.source in graph.nodes else e.source
        to_label = graph.nodes[e.target].label if e.target in graph.nodes else e.target
        rows.append(f"| {from_label} | {to_label} | {e.detail or ''} |")

    grouped: dict[str, list[str]] = {}
    for e in edges:
        to_label = graph.nodes[e.target].label if e.target in graph.nodes else e.target
        from_label = graph.nodes[e.source].label if e.source in graph.nodes else e.source
        grouped.setdefault(to_label, []).append(from_label)

    verb = "derived from" if direction == "source_to_target" else "feeds into"
    summary_lines = [f"### Lineage ({direction.replace('_', ' ')})", ""]
    for target, froms in grouped.items():
        summary_lines.append(f"- **{target}** {verb}: {', '.join(sorted(set(froms)))}")

    return "\n".join(summary_lines) + "\n\n" + header + "\n" + "\n".join(rows)
