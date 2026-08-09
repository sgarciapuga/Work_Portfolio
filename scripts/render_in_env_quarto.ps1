#!/usr/bin/env pwsh
param(
    [string]$ReportPath = "treasury-cashflow-simulation/report.qmd",
    [switch]$Execute
)

# Activate env_quarto and run Quarto render with QUARTO_PYTHON set.
& "C:\Users\44784\miniconda3\shell\condabin\conda-hook.ps1" | Out-Null
conda activate env_quarto
$env:QUARTO_PYTHON = 'C:\Users\44784\miniconda3\envs\env_quarto\python.exe'
if ($Execute) {
    quarto render $ReportPath --execute
} else {
    quarto render $ReportPath
}
