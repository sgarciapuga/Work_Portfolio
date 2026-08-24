#!/usr/bin/env pwsh
<#
.SYNOPSIS
Render all Quarto reports in the Work Portfolio project.

.DESCRIPTION
This script renders all Quarto reports (.qmd files) in the Work Portfolio.
It activates the env_quarto conda environment and executes Quarto render
for each report in sequence, optionally executing code cells.

.PARAMETER Execute
If specified, executes Python code cells during rendering. Otherwise, uses
cached results from previous renders.

.PARAMETER Reports
Comma-separated list of specific report paths to render. If not provided,
renders all reports listed in the AllReports array.

.EXAMPLE
# Render all reports without executing code
powershell -ExecutionPolicy Bypass -File .\scripts\render_all_reports.ps1

# Render all reports and execute code
powershell -ExecutionPolicy Bypass -File .\scripts\render_all_reports.ps1 -Execute

# Render specific reports
powershell -ExecutionPolicy Bypass -File .\scripts\render_all_reports.ps1 -Reports "index.qmd","fx-prime-brokerage-collateral/report.qmd"
#>

param(
    [switch]$Execute,
    [string[]]$Reports
)

# ============================================================================
# REPORT REGISTRY
# Add new reports here as you create them. Each entry should be the path to
# the .qmd file relative to the project root.
# ============================================================================
$AllReports = @(
    "index.qmd",
    "kyriba-transformation/report.qmd",
    "kyriba-transformation/accounting/report.qmd",
    "fx-prime-brokerage-collateral/report.qmd",
    "treasury-cashflow-simulation/report.qmd",
    "daily-fx-rates/report.qmd",
    "create-date-table/report.qmd"
)

# ============================================================================
# END OF REPORT REGISTRY - Do not modify below this line
# ============================================================================

# Determine which reports to render
if ($Reports.Count -gt 0) {
    $ReportsToRender = $Reports
    Write-Host "Rendering specified reports: $($Reports -join ', ')" -ForegroundColor Cyan
} else {
    $ReportsToRender = $AllReports
    Write-Host "Rendering all reports ($($AllReports.Count) total)" -ForegroundColor Cyan
}

# Activate conda environment
Write-Host "`nActivating env_quarto..." -ForegroundColor Yellow
& "C:\Users\44784\miniconda3\shell\condabin\conda-hook.ps1" | Out-Null
conda activate env_quarto
$env:QUARTO_PYTHON = 'C:\Users\44784\miniconda3\envs\env_quarto\python.exe'

# Track results
$SuccessCount = 0
$FailureCount = 0
$FailedReports = @()

# Render each report
foreach ($Report in $ReportsToRender) {
    Write-Host "`n------------------------------------------------------------" -ForegroundColor Gray
    Write-Host "Rendering: $Report" -ForegroundColor Green
    Write-Host "------------------------------------------------------------" -ForegroundColor Gray
    
    try {
        if ($Execute) {
            Write-Host "  [executing code cells]" -ForegroundColor Cyan
            quarto render $Report --execute
        } else {
            Write-Host "  [using cached results]" -ForegroundColor Cyan
            quarto render $Report
        }
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host "[SUCCESS]" -ForegroundColor Green
            $SuccessCount++
        } else {
            Write-Host "[FAILED] Exit code: $LASTEXITCODE" -ForegroundColor Red
            $FailureCount++
            $FailedReports += $Report
        }
    } catch {
        Write-Host "[ERROR] $_" -ForegroundColor Red
        $FailureCount++
        $FailedReports += $Report
    }
}

# Summary
Write-Host "`n============================================================" -ForegroundColor Cyan
Write-Host "Render Summary" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Successful: $SuccessCount" -ForegroundColor Green
Write-Host "Failed: $FailureCount" -ForegroundColor $(if ($FailureCount -gt 0) { "Red" } else { "Green" })

if ($FailedReports.Count -gt 0) {
    Write-Host "`nFailed reports:" -ForegroundColor Red
    foreach ($Report in $FailedReports) {
        Write-Host "  - $Report" -ForegroundColor Red
    }
}

Write-Host "============================================================" -ForegroundColor Cyan

# Exit with appropriate code
exit $(if ($FailureCount -gt 0) { 1 } else { 0 })

