# Kyriba TMS Transformation

A source-traceable case study of a Kyriba Treasury Management System (TMS) transformation, covering functional design, core data and access setup, integration and connectivity, and post-go-live optimisation.

Unlike the other projects in this portfolio, this is a narrative case study built from a supplied presentation and build specification rather than a code pipeline — there is no data-generation script to run.

## Report

- [View the rendered report](../docs/kyriba-transformation/report.html)
- [Report source](report.qmd)
- [Presentation (PDF)](presentation/kyriba-transformation.pdf) / [PowerPoint](presentation/kyriba-transformation.pptx)

### Deep dives

- [Accounting](accounting/report.qmd) — under development.

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
├── presentation/
│   ├── kyriba-transformation.pdf
│   └── kyriba-transformation.pptx
├── Kyriba_Quarto_Report_AI_Build_Specification.docx
└── Project Overview.docx
```

## Adding another deep dive

Follow the pattern used for `accounting/`:

1. Create a new subfolder with its own `report.qmd` (reuse `../styles.css`).
2. Register it in the root `_quarto.yml` under `project.render`, and add it to the `Kyriba Transformation` navbar dropdown menu.
3. Link to it from the "Related deep dives" section in the overview [report.qmd](report.qmd).

## Notes

The portfolio-wide visual theme (`styles/portfolio.css` at the repository root) is combined automatically with this project's own `styles.css` when the site renders.
