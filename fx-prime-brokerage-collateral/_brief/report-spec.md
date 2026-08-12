# FX Prime Brokerage Collateral Quarto Report Specification

Status: Draft for approval

## Audience and purpose

- Audience: analysts, reviewers, and portfolio readers who need to understand how the synthetic FX collateral pipeline works.
- Primary purpose: make the project reproducible and explain how its data model, DAX measures, and dashboard visuals answer collateral-monitoring questions.
- Success criteria: every important Python step is shown with a real output; sign conventions and collateral rules are explicit; Power BI documentation is tied to the existing PBIP/TMDL model; charts are readable in the rendered HTML.

## Report scope

1. **Pipeline walkthrough**
   - dependency setup and generator entry point
   - portfolio, limits, mark-to-market, and collateral-report generation
   - selected source code excerpts with executed outputs
   - output file inventory and row-count/data-quality checks

2. **Collateral mechanics**
   - initial margin, variation margin, collateral required, posted collateral, and excess/deficit
   - sign convention from `generate_mtm_report.py`
   - one-day collateral movement logic, buffer, minimum move, and rounding rules
   - time-series and counterparty/currency visualisations from the generated CSVs

3. **Power BI implementation guide**
   - PBIP/TMDL project structure and table grain
   - relationships around `dim_date`, `mtm_report`, `fx_portfolio`, `limits`, and dimensions
   - existing DAX measures with explanations, including inverse measures, previous-day logic, daily change, moving averages, and jump flags
   - recommended visual mapping: KPI cards, collateral trend, margin composition, counterparty limit utilisation, and detail table
   - refresh/deployment notes and modelling caveats

## Design direction

- Tone: technical research notebook with a restrained risk-monitoring feel.
- Signature: alternating evidence blocks, where each code block is immediately followed by its observed table or chart output.
- Quarto format: HTML with a table of contents, code folding, and executed Python cells.
- Visual language: dark ink, warm paper surface, green favourable / red adverse semantics, and blue for neutral analytical series. Avoid decorative dashboard cards in the documentation itself.

## Data and model facts

- Main fact tables: `fx_portfolio`, `limits`, `mtm_report`; supporting dimensions include `dim_date`, `dim_banks`, and `dim_currencies`.
- Primary collateral grain: one row per `report_date` in `mtm_report`.
- Current measure table: `Measures_Table`.
- Existing PBIP: `dashboard/fx-prime-brokerage-collateral.pbip`.
- Existing model source: PostgreSQL partitions in the TMDL definitions.

## Dependencies and validation

- Quarto: required to render the report.
- Python: required for executable cells; use the active project environment and `fx-prime-brokerage-collateral/requirements.txt`.
- Power BI Desktop: useful for validating the existing PBIP visually, but not required to render the Quarto documentation.
- Power BI modelling/authoring MCP: not required for this documentation-only deliverable; DAX will be documented from the checked-in TMDL.
- Fabric publishing: out of scope.

## Approval gate

Do not replace the current `report.qmd` until the user approves this scope or requests changes.
