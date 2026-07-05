"""Command-line entrypoint for ad-hoc lineage analysis, independent of MCP.

Usage:
    lineage-cli path/to/file.sql
    lineage-cli path/to/package.dtsx --direction target_to_source
    lineage-cli path/to/mapping.xml --format mermaid --detail-level full
    lineage-cli path/to/file.sql --format excel --output C:\\reports\\mapping.xlsx
"""

from __future__ import annotations

import argparse
import json
import sys

from lineage_mcp.analyzer import analyze


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract source/target data lineage from a SQL or XML file.")
    parser.add_argument("file_path", help="Path to the .sql/.xml/.dtsx file to analyze")
    parser.add_argument("--direction", choices=["source_to_target", "target_to_source"], default="source_to_target")
    parser.add_argument("--detail-level", choices=["table", "full"], default="table")
    parser.add_argument("--format", choices=["report", "mermaid", "json", "excel", "all"], default="report")
    parser.add_argument("--output", "-o", help="Output .xlsx path when --format excel/all (default: output/<input file>_lineage.xlsx, created relative to the current directory)")
    parser.add_argument("--file-type", choices=["auto", "sql", "xml"], default="auto")
    parser.add_argument("--dialect", default="tsql", help="SQL dialect for sqlglot (tsql, snowflake, postgres, bigquery, mysql, ...)")
    parser.add_argument("--xml-format", choices=["auto", "ssis", "informatica", "generic"], default="auto")
    args = parser.parse_args()

    if args.format == "all":
        output_formats = ["graph", "mermaid", "report", "excel"]
    elif args.format == "json":
        output_formats = ["graph"]
    else:
        output_formats = [args.format]

    result = analyze(
        file_path=args.file_path,
        file_type=args.file_type,
        direction=args.direction,
        detail_level=args.detail_level,
        output_formats=output_formats,
        dialect=args.dialect,
        xml_format=args.xml_format,
        excel_path=args.output,
    )

    if result.get("errors"):
        for err in result["errors"]:
            print(f"[warn] {err}", file=sys.stderr)

    print(f"# source_type={result['source_type']} format_detected={result.get('format_detected')} direction={result['direction']}\n")

    if args.format == "report":
        print(result["report"])
    elif args.format == "mermaid":
        print(result["mermaid"])
    elif args.format == "json":
        print(json.dumps(result["graph"], indent=2))
    elif args.format == "excel":
        print(f"Wrote {result['excel_path']}")
    else:
        print(result["report"])
        print("\n```mermaid")
        print(result["mermaid"])
        print("```\n")
        print(json.dumps(result["graph"], indent=2))
        print(f"\nWrote {result['excel_path']}")


if __name__ == "__main__":
    main()
