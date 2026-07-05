"""Command-line entrypoint for ad-hoc lineage analysis, independent of MCP.

Usage:
    lineage-cli path/to/file.sql
    lineage-cli path/to/package.dtsx --direction target_to_source
    lineage-cli path/to/mapping.xml --format mermaid --detail-level full
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
    parser.add_argument("--format", choices=["report", "mermaid", "json", "all"], default="report")
    parser.add_argument("--file-type", choices=["auto", "sql", "xml"], default="auto")
    parser.add_argument("--dialect", default="tsql", help="SQL dialect for sqlglot (tsql, snowflake, postgres, bigquery, mysql, ...)")
    parser.add_argument("--xml-format", choices=["auto", "ssis", "informatica", "generic"], default="auto")
    args = parser.parse_args()

    output_formats = ["graph", "mermaid", "report"] if args.format == "all" else (
        ["graph"] if args.format == "json" else [args.format]
    )

    result = analyze(
        file_path=args.file_path,
        file_type=args.file_type,
        direction=args.direction,
        detail_level=args.detail_level,
        output_formats=output_formats,
        dialect=args.dialect,
        xml_format=args.xml_format,
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
    else:
        print(result["report"])
        print("\n```mermaid")
        print(result["mermaid"])
        print("```\n")
        print(json.dumps(result["graph"], indent=2))


if __name__ == "__main__":
    main()
