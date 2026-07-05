"""MCP server exposing SQL/XML data lineage extraction as tools.

Run directly with `lineage-mcp` (after `pip install -e .`), or point an MCP
client (Claude Desktop, Claude Code, etc.) at this module - see README.md for
client configuration.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from lineage_mcp.analyzer import analyze

mcp = FastMCP("lineage-mcp")


@mcp.tool()
def analyze_lineage(
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
    """Extract data lineage from a SQL script or an XML ETL package (SSIS/DTSX,
    Informatica PowerCenter mapping export, or a generic/custom XML schema).

    Args:
        file_path: Path to the .sql/.xml/.dtsx file to analyze. Provide this
            or `content`, not both.
        content: Raw file text, if you don't have a filesystem path the server
            can read (e.g. content pasted by the user).
        file_type: "auto" (detect from extension/content), "sql", or "xml".
        direction: "source_to_target" (default) or "target_to_source" - which
            way the returned edges/report/diagram read, and (for "excel")
            which entity - source or target - is presented in the leftmost
            columns of each sheet.
        detail_level: "table" (default, collapses to physical table-to-table
            lineage) or "full" (keeps column-level and intermediate
            transformation/component nodes where the parser produced them).
            Does not affect "excel" output, which always includes both a
            table-level sheet and a column-level sheet (when available).
        output_formats: subset of ["graph", "mermaid", "report", "excel"] to
            include in the response. Defaults to graph/mermaid/report.
        dialect: SQL dialect for sqlglot when file_type resolves to "sql"
            (e.g. "tsql", "snowflake", "postgres", "bigquery", "mysql").
        xml_format: "auto" (detect), "ssis", "informatica", or "generic" -
            force a specific XML parser instead of auto-detecting.
        excel_path: Where to write the .xlsx workbook when "excel" is in
            output_formats. Defaults to "<file_path stem>_lineage.xlsx" next
            to the input file; required if only `content` was provided.

    Returns:
        A dict with: source_type, format_detected (for XML), direction,
        detail_level, errors (list of non-fatal parse issues), and any of
        graph (JSON nodes/edges), mermaid (flowchart text), report (markdown),
        excel_path (path to the written .xlsx workbook - a clean source-to-target
        mapping with a Table Lineage sheet and, when available, a Column
        Lineage sheet).
    """
    return analyze(
        file_path=file_path,
        content=content,
        file_type=file_type,
        direction=direction,
        detail_level=detail_level,
        output_formats=output_formats,
        dialect=dialect,
        xml_format=xml_format,
        excel_path=excel_path,
    )


@mcp.tool()
def list_supported_formats() -> dict:
    """List the SQL dialects and XML formats this server knows how to parse."""
    return {
        "sql": {
            "dialects": ["tsql", "snowflake", "postgres", "mysql", "bigquery", "ansi", "..."],
            "statements": ["CREATE TABLE/VIEW AS SELECT", "INSERT ... SELECT", "MERGE INTO ... USING", "UPDATE ... FROM"],
            "notes": "Column-level lineage is best-effort for CTAS/INSERT-SELECT with explicit column lists (including through CTEs); SELECT * and MERGE/UPDATE column mapping are table-level only.",
        },
        "xml": {
            "formats": {
                "ssis": "SSIS/.dtsx Data Flow Task packages (component + path based)",
                "informatica": "Informatica PowerCenter mapping XML exports (SOURCE/TARGET/MAPPING/CONNECTOR)",
                "generic": "Heuristic parser for custom XML using source/target-like tags (source, target, from, to, input, output, ...)",
            },
            "notes": "Format is auto-detected by default; pass xml_format explicitly to override.",
        },
        "output_formats": {
            "graph": "JSON nodes/edges",
            "mermaid": "flowchart text",
            "report": "markdown table + summary",
            "excel": "clean source-to-target mapping workbook (.xlsx) with a Table Lineage sheet and, when column-level data is available, a Column Lineage sheet",
        },
    }


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
