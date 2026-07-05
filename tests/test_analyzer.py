from pathlib import Path

import pytest

from lineage_mcp.analyzer import analyze

FIXTURES = Path(__file__).parent / "fixtures"


def test_analyze_sql_file_end_to_end():
    result = analyze(file_path=str(FIXTURES / "sample.sql"))
    assert result["source_type"] == "sql"
    assert result["detail_level"] == "table"
    assert "mermaid" in result and "flowchart LR" in result["mermaid"]
    assert "report" in result
    node_labels = {n["label"] for n in result["graph"]["nodes"]}
    assert "raw.customers" in node_labels
    assert "stg.customers" in node_labels


def test_analyze_xml_file_end_to_end_target_to_source():
    result = analyze(file_path=str(FIXTURES / "sample.dtsx"), direction="target_to_source")
    assert result["source_type"] == "xml"
    assert result["format_detected"] == "ssis"
    edges = result["graph"]["edges"]
    assert any(e["relation"] == "derived_from" for e in edges)


def test_analyze_with_inline_content_and_explicit_file_type():
    sql = "INSERT INTO t2 SELECT a FROM t1;"
    result = analyze(content=sql, file_type="sql", output_formats=["graph"])
    assert "graph" in result
    assert "mermaid" not in result
    assert "report" not in result


def test_analyze_requires_file_path_or_content():
    with pytest.raises(ValueError):
        analyze()


def test_analyze_full_detail_level_keeps_columns():
    result = analyze(file_path=str(FIXTURES / "sample.sql"), detail_level="full", output_formats=["graph"])
    kinds = {n["kind"] for n in result["graph"]["nodes"]}
    assert "column" in kinds
