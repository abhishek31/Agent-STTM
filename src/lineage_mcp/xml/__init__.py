from __future__ import annotations

from dataclasses import dataclass, field

from lxml import etree

from lineage_mcp.graph import LineageGraph
from lineage_mcp.xml.detect import detect_xml_format
from lineage_mcp.xml.generic import parse_generic
from lineage_mcp.xml.informatica import parse_informatica
from lineage_mcp.xml.ssis import parse_ssis


@dataclass
class XmlParseResult:
    graph: LineageGraph
    format_detected: str
    errors: list[str] = field(default_factory=list)


def parse_xml_lineage(xml_text: str, xml_format: str = "auto") -> XmlParseResult:
    try:
        root = etree.fromstring(xml_text.encode("utf-8"))
    except etree.XMLSyntaxError as exc:
        return XmlParseResult(graph=LineageGraph(), format_detected="unknown", errors=[f"XML parse error: {exc}"])

    fmt = xml_format if xml_format != "auto" else detect_xml_format(root)

    parsers = {
        "ssis": parse_ssis,
        "informatica": parse_informatica,
        "generic": parse_generic,
    }
    parser = parsers.get(fmt)
    if parser is None:
        return XmlParseResult(graph=LineageGraph(), format_detected=fmt, errors=[f"Unknown xml_format: {fmt!r}"])

    graph = parser(root)
    errors = []
    if graph.is_empty():
        errors.append(f"No lineage relationships found (detected format: {fmt}). If this is a custom schema, a sample would help tailor the parser.")
    return XmlParseResult(graph=graph, format_detected=fmt, errors=errors)
