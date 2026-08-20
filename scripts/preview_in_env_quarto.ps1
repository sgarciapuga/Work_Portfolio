#!/usr/bin/env pwsh
param(
    [string]$ReportPath = "treasury-cashflow-simulation/report.qmd"
)

# Activate env_quarto and run Quarto preview with QUARTO_PYTHON set.
& "C:\Users\44784\miniconda3\shell\condabin\conda-hook.ps1" | Out-Null
conda activate env_quarto
$env:QUARTO_PYTHON = 'C:\Users\44784\miniconda3\envs\env_quarto\python.exe'
quarto preview $ReportPath
