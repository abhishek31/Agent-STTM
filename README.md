# lineage-mcp

An MCP server that extracts data lineage from SQL scripts and XML ETL packages
(SSIS/.dtsx, Informatica PowerCenter mapping exports, or generic/custom XML),
in either `source_to_target` or `target_to_source` direction.

Parsing is fully deterministic (sqlglot for SQL, lxml tree-walking for XML) -
no LLM calls are made during extraction, so results are reproducible and don't
hallucinate. An MCP client (Claude Desktop, Claude Code, etc.) calls the tools
below and can then explain/summarize/visualize the returned lineage.

## What it can parse

**SQL** (dialect-aware via [sqlglot](https://github.com/tobymao/sqlglot)):
- `CREATE TABLE/VIEW ... AS SELECT`
- `INSERT INTO ... SELECT ...` (including through CTEs)
- `MERGE INTO ... USING ...`
- `UPDATE ... FROM ...`
- Table-level lineage covers all of the above. Column-level lineage is
  best-effort for CTAS/INSERT-SELECT with explicit (non `SELECT *`) column
  lists, resolved transitively through CTEs. `SELECT *` and MERGE/UPDATE
  column-level mapping are out of scope (would require schema knowledge to
  resolve reliably) - those still get full table-level lineage.

**XML**:
- **SSIS / `.dtsx`** - Data Flow Task `<component>`/`<path>` graphs; source
  and destination components are linked to the physical table/query they
  read from or write to (via `OpenRowset`, `SqlCommand`, `TableOrViewName`, etc.)
- **Informatica PowerCenter** mapping exports - `SOURCE`/`TARGET`/`MAPPING`/
  `CONNECTOR` give exact column-level chains through every transformation
- **Generic/custom XML** - heuristic parser that looks for the common
  `<source>`/`<target>` (or `from`/`to`, `input`/`output`) idiom. This is a
  best-effort starting point; if you have a real sample of your schema, a
  purpose-built parser (following the pattern in `src/lineage_mcp/xml/ssis.py`
  or `informatica.py`) will be far more accurate.

Format is auto-detected from content/extension; you can override with
`file_type` / `xml_format`.

## Setup

Requires Python 3.10+.

```bash
cd Agent-STTM
python -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
```

Optional, only needed for the Excel "Flow Diagram" sheet: install
[Graphviz](https://graphviz.org/download/) (e.g. `winget install Graphviz.Graphviz`
on Windows) so its `dot` executable is available. Everything else works
without it.

Run the test suite:

```bash
.venv\Scripts\pytest -q
```

## Registering the server with an MCP client

The server communicates over stdio. Point your client at the venv's Python
running the `lineage_mcp.server` module.

### Claude Code

Add to `.mcp.json` in this project (or run `claude mcp add`):

```json
{
  "mcpServers": {
    "lineage-mcp": {
      "command": "C:\\Users\\abhis\\OneDrive\\Documents\\Agent-STTM\\.venv\\Scripts\\python.exe",
      "args": ["-m", "lineage_mcp.server"],
      "cwd": "C:\\Users\\abhis\\OneDrive\\Documents\\Agent-STTM"
    }
  }
}
```

### Claude Desktop

Add the same block under `mcpServers` in `claude_desktop_config.json`
(Windows: `%APPDATA%\Claude\claude_desktop_config.json`), then restart Claude
Desktop.

## Tools exposed

### `analyze_lineage`

| Arg | Default | Notes |
|---|---|---|
| `file_path` | - | Path to the `.sql`/`.xml`/`.dtsx` file. Provide this or `content`. |
| `content` | - | Raw file text, if the client doesn't have a server-visible path. |
| `file_type` | `"auto"` | `"auto"`, `"sql"`, or `"xml"`. |
| `direction` | `"source_to_target"` | or `"target_to_source"`. |
| `detail_level` | `"table"` | `"table"` collapses to physical table-to-table lineage; `"full"` keeps column/component-level detail. |
| `output_formats` | all | subset of `["graph", "mermaid", "report", "excel"]`. |
| `dialect` | `"tsql"` | sqlglot dialect (`snowflake`, `postgres`, `bigquery`, `mysql`, ...). |
| `xml_format` | `"auto"` | `"auto"`, `"ssis"`, `"informatica"`, or `"generic"`. |
| `excel_path` | - | Where to write the `.xlsx` when `"excel"` is requested. Defaults to `output/<file_path stem>_lineage.xlsx` (created relative to the current directory, kept separate from your input files); required if only `content` was given. |

Returns `source_type`, `format_detected`, `direction`, `detail_level`,
`errors` (non-fatal parse issues - e.g. one bad statement in an otherwise
valid SQL file), and any requested `graph` (JSON nodes/edges), `mermaid`
(flowchart text), `report` (markdown table + summary), `excel_path` (path to
the written workbook).

### Excel (STTM) output

`excel` produces a clean source-to-target mapping workbook with up to three
sheets, always collapsed past any intermediate CTE/transformation-instance
hops regardless of `detail_level`:

- **Flow Diagram** - a rendered boxes-and-arrows flowchart image of the
  table-level lineage (via [Graphviz](https://graphviz.org/download/); needs
  its `dot` executable installed and importable - if it's missing, this sheet
  is skipped and a note is added to the response's `errors`, the other sheets
  are unaffected).
- **Table Lineage** - one row per physical source table -> target table.
- **Column Lineage** - one row per physical source column -> target column
  (added only when the parser produced column-level detail - SQL and
  Informatica do; SSIS is component-level only, so it won't have this sheet).

`direction` controls which side is presented first - leftmost columns in the
table/column sheets, left-to-right flow in the diagram (`source_to_target`
puts Source first; `target_to_source` puts Target first) - the values
themselves are always the true physical source/target, never swapped.

From the CLI:
```bash
lineage-cli path\to\file.sql --format excel --output C:\reports\mapping.xlsx
```

### `list_supported_formats`

Returns the SQL dialects/statement types and XML formats currently supported.

## Project layout

```
src/lineage_mcp/
  graph.py           # LineageGraph: nodes/edges, direction flip, collapse-to-boundary
  analyzer.py         # file-type detection + orchestration
  render.py           # Mermaid + markdown report rendering
  excel.py            # clean source-to-target mapping (.xlsx) rendering
  diagram.py           # Graphviz PNG flowchart rendering (used by excel.py)
  sql/parser.py        # sqlglot-based SQL lineage extraction
  xml/
    detect.py          # SSIS vs Informatica vs generic sniffing
    ssis.py             # .dtsx component/path parser
    informatica.py       # PowerCenter SOURCE/TARGET/MAPPING/CONNECTOR parser
    generic.py           # heuristic source/target tag parser
  server.py            # FastMCP tool definitions / entrypoint
tests/                  # pytest suite + fixtures for all three XML formats + SQL
input/                  # drop your own .sql/.xml/.dtsx files here to analyze
output/                 # generated reports/diagrams/workbooks land here by default
```

## Extending

To add a purpose-built parser for a custom XML schema, add a new module
under `src/lineage_mcp/xml/` following the shape of `informatica.py` (build a
`LineageGraph` by walking the tree with `lxml`), wire it into
`xml/__init__.py`'s `parsers` dict, and add a detection rule in
`xml/detect.py`.
