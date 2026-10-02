# Kyriba TMS Transformation

A source-traceable case study of a Kyriba Treasury Management System (TMS) transformation, covering functional design, core data and access setup, integration and connectivity, and post-go-live optimisation.

Unlike the other projects in this portfolio, this is a narrative case study built from a supplied presentation and build specification rather than a code pipeline — there is no data-generation script to run.

## Report

- [View the rendered report](../docs/kyriba-transformation/report.html)
- [Report source](report.qmd)
- [Presentation (PDF)](presentation/kyriba-transformation.pdf) / [PowerPoint](presentation/kyriba-transformation.pptx)

### Deep dives

- [Accounting](accounting/report.qmd) — under development.
- [Case 01: FX Platform Integration](Case_01_FX_Integration/report.qmd) — an FX workflow redesign connecting Kyriba and a trading platform.
- [Case 02: Payments Connectivity](Case_02_Payments_Connectivity/report.qmd) — netting and payment-flow redesign with direct connectivity to two core banks.

## Evidence discipline

The report only includes statements traceable to the supplied presentation. It avoids invented metrics, dates, licence counts or financial values, and clearly separates functional contribution from claims of technical infrastructure ownership. See the "Evidence boundary" callout at the top of the report for the full scope statement.

## Project structure

```text
kyriba-transformation/
├── README.md
├── report.qmd
├── styles.css
├── accounting/
│   └── report.qmd            # sub-project deep dive
├── Case_01_FX_Integration/
│   ├── README.md
│   ├── report.qmd
│   └── presentation/         # case source files
├── Case_02_Payments_Connectivity/
│   ├── README.md
│   ├── report.qmd
│   └── presentation/         # case source files
├── presentation/
│   ├── kyriba-transformation.pdf
│   └── kyriba-transformation.pptx
├── Kyriba_Quarto_Report_AI_Build_Specification.docx
└── Project Overview.docx
```

## Adding another deep dive

Follow the pattern used for `accounting/` or the `Case_0x_*` folders:

1. Create a new subfolder with its own `report.qmd` (reuse `../styles.css`) and a short README.
2. Register it in the root `_quarto.yml` under `project.render`, add it to the `Kyriba Transformation` navbar dropdown menu, and add it to `$AllReports` in `scripts/render_all_reports.ps1`.
3. Link to it from the "Related deep dives" section in the overview [report.qmd](report.qmd) and from the Kyriba card in the root `index.qmd`.

## Notes

The portfolio-wide visual theme (`styles/portfolio.css` at the repository root) is combined automatically with this project's own `styles.css` when the site renders.
