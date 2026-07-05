# Automating Source-to-Target Mapping: An AI Agent for Data Lineage That Actually Ships an STTM

**TL;DR** — I built [lineage-mcp](https://github.com/abhishek31/Agent-STTM) (Agent-STTM), an MCP server + CLI that reads real SQL scripts and XML ETL exports (SSIS, Informatica PowerCenter, or a custom schema) and deterministically produces a source-to-target mapping (STTM): a flow diagram, a table-lineage sheet, and a column-lineage sheet, in a clean Excel workbook, in either direction. No LLM guesswork in the extraction step — just real parsers, real graphs, and an agent on top that can explain and drive the whole thing conversationally. Full code, sample inputs, and generated outputs are linked throughout this post.

---

## The problem: STTM is the least glamorous, most necessary artifact in data engineering

If you've worked on a data warehouse, a regulatory reporting stack, or any non-trivial ETL estate, you know the document even if you've never used the acronym: the **Source-to-Target Mapping**. It's the spreadsheet that says, for every column in every target table, exactly which source table(s) and column(s) it comes from, and what transformation sits in between.

It's boring. It's also load-bearing for almost everything important:

- **Migrations.** You cannot move a reporting stack from Informatica or SQL Server to Snowflake (or anywhere else) without first knowing, precisely, what the current system does. The STTM *is* the functional spec for the new build.
- **Regulatory and compliance audits.** Frameworks like BCBS 239 explicitly require banks to trace any number on a regulatory report back to its originating source system, field by field.
- **Impact analysis.** "If I change this column's type, what breaks?" is an STTM question in disguise.
- **Onboarding.** New engineers inherit pipelines nobody fully documented, and spend their first weeks reverse-engineering exactly this mapping by reading stored procedures line by line.

And yet, in most organizations, this document is built the same way it was built twenty years ago: an engineer opens the SSIS package or the Informatica mapping or the stored procedure, traces the logic by eye, and types the results into an Excel template. It takes days per subject area. It's error-prone. And it's stale the moment someone changes the pipeline, because nobody re-does this by hand more than once.

That's the gap this project closes.

## What it is

[**lineage-mcp**](https://github.com/abhishek31/Agent-STTM) is an [MCP](https://modelcontextprotocol.io/) (Model Context Protocol) server — meaning it exposes tools that an AI assistant like Claude can call directly — plus a standalone CLI for when you just want to run it yourself. You point it at a `.sql` file, a `.dtsx` (SSIS) package, or an Informatica PowerCenter mapping export, and it gives you back lineage in either direction:

- **`source_to_target`** — "if I change this source, what does it eventually affect?" (migration planning, impact analysis)
- **`target_to_source`** — "where does this report column actually come from?" (audits, debugging, reverse engineering)

The key design decision is that **the extraction itself is 100% deterministic** — there is no LLM in the loop reading your SQL and guessing at lineage. SQL is parsed into a real abstract syntax tree with [sqlglot](https://github.com/tobymao/sqlglot); XML is walked as a real tree with `lxml`. The same input always produces the same output, and every edge in the resulting graph traces back to an actual `INSERT`/`MERGE`/`CONNECTOR`/`CTE` in the source file, not a language model's best guess. For something that compliance teams and migration engineers are going to treat as ground truth, that distinction matters enormously — a hallucinated lineage edge is worse than a missing one, because it looks just as authoritative.

The MCP layer is what turns this from "a script I run" into "an agent I talk to." Because it's exposed as MCP tools, an assistant like Claude Code or Claude Desktop can call `analyze_lineage` directly inside a conversation — you can ask it to look at a folder of stored procedures and explain what feeds a given report, and it'll reach for real parsed lineage instead of reading the SQL itself and summarizing.

## What comes out the other end

Four output formats, generated from the same underlying lineage graph:

| Format | What it's for |
|---|---|
| **JSON graph** | Feed it into a data catalog, a lineage viewer, or your own tooling |
| **Mermaid flowchart** | Drop straight into markdown docs / a PR description |
| **Markdown report** | A quick human-readable summary + table |
| **Excel workbook** | The actual deliverable you hand to a stakeholder or auditor |

The Excel workbook is the one that matters most in practice, so it gets the most polish: it has a **Flow Diagram** sheet (an actual rendered image, not text), a **Table Lineage** sheet, and a **Column Lineage** sheet — collapsed past every intermediate CTE or transformation-instance hop, so what you see is the clean physical-table-to-physical-table and physical-column-to-physical-column picture, not fifty rows of internal plumbing.

## Walkthrough: the same business logic, two different systems

To make this concrete, I built two sample inputs modeling the *same* banking data-warehouse scenario — a branch dimension, a customer dimension with SCD2 history, a transactions fact table, a daily aggregate, and a reporting view — implemented two different ways, on purpose:

1. **[`input/sample_banking_dw_lineage.sql`](https://github.com/abhishek31/Agent-STTM/blob/main/input/sample_banking_dw_lineage.sql)** — hand-written stored procedures, the way you'd find them in a SQL Server or Snowflake shop.
2. **[`input/sample_informatica_mapping_lineage.xml`](https://github.com/abhishek31/Agent-STTM/blob/main/input/sample_informatica_mapping_lineage.xml)** — the *same* scenario, as an Informatica PowerCenter mapping export, complete with source qualifiers, joiners, lookups, expression transforms, and an update strategy.

Running the CLI against the SQL version:

```bash
lineage-cli input/sample_banking_dw_lineage.sql --format excel
```

produces this Flow Diagram, straight out of the Excel sheet:

![Banking DW flow diagram](https://raw.githubusercontent.com/abhishek31/Agent-STTM/main/docs/images/sample_banking_dw_flow_diagram.png)

And against the Informatica mapping:

```bash
lineage-cli input/sample_informatica_mapping_lineage.xml --format excel
```

![Informatica flow diagram](https://raw.githubusercontent.com/abhishek31/Agent-STTM/main/docs/images/sample_informatica_flow_diagram.png)

Same underlying business relationships, extracted from two completely different artifact types, with two completely different parsers under the hood — because in a real migration project, "the current system" is rarely just one technology, and your lineage tool needs to meet it wherever it lives.

Full generated workbooks (Flow Diagram + Table Lineage + Column Lineage sheets) are in the repo, ready to open:
- [`output/sample_banking_dw_lineage_mapping.xlsx`](https://github.com/abhishek31/Agent-STTM/blob/main/output/sample_banking_dw_lineage_mapping.xlsx)
- [`output/sample_informatica_mapping.xlsx`](https://github.com/abhishek31/Agent-STTM/blob/main/output/sample_informatica_mapping.xlsx)

## Use case 1: forward engineering a migration (Informatica/SQL Server → Snowflake)

This is the scenario that motivated the project. A client wants to retire Informatica and SQL Server-based reporting and rebuild it on Snowflake. Before a single Snowflake object gets created, someone has to answer: *what does the current system actually do, exactly?*

Traditionally, that's weeks of an engineer reading mappings and procedures and manually filling in a spreadsheet — and it's usually done once, badly, under deadline pressure, and it goes stale immediately.

With this agent, the workflow becomes:

1. Point it at every existing Informatica mapping export and/or SQL Server stored procedure in the subject area.
2. Get back a consistent STTM Excel per pipeline — a **Flow Diagram** for the kickoff conversation with stakeholders ("does this match your understanding of the system?"), a **Table Lineage** sheet for sequencing the migration (which targets depend on which, so you build in the right order), and a **Column Lineage** sheet that becomes the literal field-by-field spec for the engineers writing the new Snowflake SQL or dbt models.
3. Because the same lineage is also available as JSON, it can feed straight into code generation (scaffolding a dbt model per target table from its mapped source columns) or into a data catalog, without anyone re-typing anything.

What used to be a multi-week documentation phase *before* migration work could even start becomes a same-day automated first pass — engineers spend their time validating and refining a draft, instead of transcribing one from scratch.

## Use case 2: reverse engineering and governance on the existing estate

The `target_to_source` direction exists specifically for the other half of this problem: you don't always need the whole picture, sometimes you need to answer one question fast — *"where does this specific number on this specific report actually come from?"* That's exactly what a regulator asks during a BCBS 239 audit, exactly what an engineer asks before changing a shared dimension table, and exactly what a new hire asks on their first week inheriting someone else's pipeline.

```bash
lineage-cli input/sample_banking_dw_lineage.sql --direction target_to_source --format report
```

gives you, directly, "this report column comes from these upstream columns, through these tables" — without anyone having to read the stored procedure first.

## A few design decisions worth calling out

- **Deterministic parsing over LLM inference, for the facts.** The AST/tree-walking approach means lineage is auditable — you can point at the exact `INSERT`/`CONNECTOR`/`CTE` that produced any edge. The LLM's job is to converse about the result, not to invent it.
- **Graceful degradation everywhere.** One malformed SQL statement in a 500-line stored procedure doesn't kill lineage extraction for the other 30 statements. A hand-written XML comment that technically violates the XML spec (a stray `--`, common in real exported files) doesn't block the whole file. Missing Graphviz just means you get the Table/Column sheets without the diagram — never a hard failure.
- **Direction is a presentation concern, not a re-parse.** The graph is built once; `source_to_target` vs `target_to_source` is just how you choose to read the same edges, so switching direction never risks producing a *different* answer, only a differently-oriented view of the same one.
- **Clean by construction.** Real ETL tools produce lineage that's naturally multi-hop — through CTEs in SQL, through source qualifiers/lookups/expression transforms in Informatica. The tool explicitly collapses these down to direct physical-table/physical-column relationships, so the STTM you hand to a stakeholder is the clean picture, not fifty rows of internal transformation plumbing.

## Try it

The full project — MCP server, CLI, both sample inputs, both generated Excel workbooks, and the test suite — is here:

**[github.com/abhishek31/Agent-STTM](https://github.com/abhishek31/Agent-STTM)**

```bash
git clone https://github.com/abhishek31/Agent-STTM.git
cd Agent-STTM
python -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
.venv\Scripts\lineage-cli.exe input\sample_banking_dw_lineage.sql --format excel
```

It also registers as an MCP server (see [`README.md`](https://github.com/abhishek31/Agent-STTM/blob/main/README.md) for Claude Code / Claude Desktop config), so if you're already working inside an MCP-aware assistant, you can just ask it to analyze a file in plain language.

Currently supported: T-SQL/Snowflake/Postgres/MySQL/BigQuery-family SQL (CTAS, INSERT-SELECT, MERGE, UPDATE), SSIS `.dtsx` packages, and Informatica PowerCenter mapping exports, plus a heuristic parser for custom XML schemas as a starting point. Adding support for another ETL tool's export format is a matter of writing one more tree-walker following the pattern in `xml/informatica.py` — the graph model, collapsing, rendering, and Excel/diagram output are all already shared infrastructure.

If your team is sitting on a pile of undocumented Informatica mappings or stored procedures and a migration deadline, this is the tool I wish had existed the first time I had to build an STTM by hand.
