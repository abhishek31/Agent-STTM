"""Ties file-type detection, parsing, graph collapsing, and rendering together
into the single entrypoint the MCP tool calls."""

from __future__ import annotations

from pathlib import Path

from lineage_mcp import diagram
from lineage_mcp.excel import to_excel_workbook
from lineage_mcp.graph import LineageGraph, NodeKind
from lineage_mcp.render import to_mermaid, to_report
from lineage_mcp.sql.parser import parse_sql_lineage
from lineage_mcp.xml import parse_xml_lineage

_SQL_EXTENSIONS = {".sql"}
_XML_EXTENSIONS = {".xml", ".dtsx"}


def analyze(
    file_path: str | None = None,
    content: str | None = None,
    file_type: str = "auto",
    direction: str = "source_to_target",
    detail_level: str = "table",
    output_formats: list[str] | None = None,
    dialect: str = "tsql",
    xml_format: str = "auto",
    excel_path: str | None = None,
) -> dict:
    if direction not in ("source_to_target", "target_to_source"):
        raise ValueError("direction must be 'source_to_target' or 'target_to_source'")
    if detail_level not in ("table", "full"):
        raise ValueError("detail_level must be 'table' or 'full'")

    if content is None:
        if not file_path:
            raise ValueError("Either file_path or content must be provided")
        content = Path(file_path).read_text(encoding="utf-8-sig")

    resolved_type = file_type if file_type != "auto" else _detect_file_type(file_path, content)

    errors: list[str] = []
    format_detected: str | None = None

    if resolved_type == "sql":
        result = parse_sql_lineage(content, dialect=dialect)
        full_graph = result.graph
        errors.extend(result.errors)
    elif resolved_type == "xml":
        xml_result = parse_xml_lineage(content, xml_format=xml_format)
        full_graph = xml_result.graph
        format_detected = xml_result.format_detected
        errors.extend(xml_result.errors)
    else:
        raise ValueError(
            f"Could not auto-detect file_type from {file_path!r}; pass file_type='sql' or 'xml' explicitly"
        )

    display_graph: LineageGraph = full_graph if detail_level == "full" else full_graph.collapse_to_kind(NodeKind.TABLE)

    requested = output_formats or ["graph", "mermaid", "report"]
    response: dict = {
        "source_type": resolved_type,
        "format_detected": format_detected,
        "direction": direction,
        "detail_level": detail_level,
        "errors": errors,
    }
    if "graph" in requested:
        response["graph"] = display_graph.to_dict(direction=direction)
    if "mermaid" in requested:
        response["mermaid"] = to_mermaid(display_graph, direction=direction)
    if "report" in requested:
        response["report"] = to_report(display_graph, direction=direction)
    if "excel" in requested:
        if not diagram.is_available():
            errors.append("Graphviz 'dot' executable not found - the workbook was written without a Flow Diagram sheet (Table/Column Lineage sheets are unaffected). Install Graphviz and ensure 'dot' is on PATH to include it.")
        save_path = excel_path or _default_excel_path(file_path)
        workbook = to_excel_workbook(full_graph, direction=direction)
        workbook.save(save_path)
        response["excel_path"] = str(save_path)

    return response


def _default_excel_path(file_path: str | None) -> str:
    if not file_path:
        raise ValueError("excel_path must be provided when generating 'excel' output from inline content (no file_path to derive a name from)")
    src = Path(file_path)
    return str(src.with_name(f"{src.stem}_lineage.xlsx"))


def _detect_file_type(file_path: str | None, content: str) -> str | None:
    if file_path:
        ext = Path(file_path).suffix.lower()
        if ext in _SQL_EXTENSIONS:
            return "sql"
        if ext in _XML_EXTENSIONS:
            return "xml"
    stripped = content.lstrip()
    if stripped.startswith("<"):
        return "xml"
    if stripped:
        return "sql"
    return None
