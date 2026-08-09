#!/usr/bin/env pwsh
param(
    [Parameter(Position = 0)]
    [string]$ReportPath = "treasury-cashflow-simulation/report.qmd",

    [string]$EnvironmentName = "quarto_render",

    [switch]$Execute
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

& "$env:USERPROFILE\miniconda3\shell\condabin\conda-hook.ps1" | Out-Null
conda activate $EnvironmentName

if (-not $env:CONDA_PREFIX) {
    throw "Could not activate conda environment '$EnvironmentName'."
}

$env:QUARTO_PYTHON = Join-Path $env:CONDA_PREFIX "python.exe"
$env:MPLBACKEND = "Agg"

$renderArgs = @("render", $ReportPath)
if ($Execute) {
    $renderArgs += "--execute"
}
$renderArgs += "--log-level"
$renderArgs += "info"

quarto @renderArgs
