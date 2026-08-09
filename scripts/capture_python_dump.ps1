<#
Simple ProcDump helper for capturing a full native crash dump of python.exe

Run this script as Administrator from the repository root. Example:
  Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
  .\scripts\capture_python_dump.ps1 -EnvName env_1 -ReportPath 'treasury-cashflow-simulation/report.qmd'

This script will download ProcDump (if missing), start it watching for python.exe,
run Quarto in the named conda env, and list any produced .dmp files in C:\temp\python_dumps.
#>

param(
    [string]$EnvName = 'env_1',
    [string]$ReportPath = 'treasury-cashflow-simulation/report.qmd',
    [string]$ProcDumpDir = "$PSScriptRoot\procdump",
    [string]$DumpDir = 'C:\temp\python_dumps'
)

function Assert-Admin {
    $isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $isAdmin) {
        Write-Error 'This script must be run as Administrator. Right-click PowerShell and choose Run as administrator.'
        exit 1
    }
}

Assert-Admin

Write-Host "Preparing dump directory: $DumpDir"
New-Item -ItemType Directory -Force -Path $DumpDir | Out-Null
New-Item -ItemType Directory -Force -Path $ProcDumpDir | Out-Null

$procDumpExe = Join-Path $ProcDumpDir 'procdump.exe'
if (-not (Test-Path $procDumpExe)) {
    Write-Host "ProcDump not found in $ProcDumpDir - downloading..."
    $zip = Join-Path $ProcDumpDir 'Procdump.zip'
    $url = 'https://download.sysinternals.com/files/Procdump.zip'
    try {
        Invoke-WebRequest -Uri $url -OutFile $zip -ErrorAction Stop
        Expand-Archive -Path $zip -DestinationPath $ProcDumpDir -Force
        Remove-Item $zip -Force
    } catch {
        Write-Error "Failed to download or extract ProcDump: $_"
        exit 2
    }
}

if (-not (Test-Path $procDumpExe)) {
    Write-Error "procdump.exe not found after download. Check $ProcDumpDir"
    exit 3
}

Write-Host "Starting ProcDump to monitor python.exe (dumps -> $DumpDir)."
$dumpPrefix = Join-Path $DumpDir ("python_crash_{0}" -f $EnvName)
$args = @('-accepteula','-ma','-e','-w','python.exe',$dumpPrefix)
$pdProcess = Start-Process -FilePath $procDumpExe -ArgumentList $args -PassThru -WindowStyle Hidden
Start-Sleep -Seconds 2

Write-Host ("ProcDump started (PID: {0}). Now activating conda env: {1}" -f $pdProcess.Id, $EnvName)

# Source conda hook then activate requested env in this session
& 'C:\Users\44784\miniconda3\shell\condabin\conda-hook.ps1' | Out-Null
try {
    conda activate $EnvName
} catch {
    Write-Error ("Failed to activate conda env '{0}'. Ensure the env exists and conda is available." -f $EnvName)
    # Stop ProcDump if running
    Get-Process procdump -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    exit 4
}

$env:QUARTO_PYTHON = Join-Path $Env:CONDA_PREFIX 'python.exe'
Write-Host ("Using QUARTO_PYTHON={0}" -f $env:QUARTO_PYTHON)

Write-Host ("Running: quarto render {0} --execute" -f $ReportPath)
try {
    quarto render $ReportPath --execute --log-level debug
    $renderExit = $LASTEXITCODE
} catch {
    Write-Warning ("Quarto render threw an exception: {0}" -f $_)
    $renderExit = 1
}

Write-Host ("Render finished (exit code {0}). Waiting 2s for ProcDump to flush dumps." -f $renderExit)
Start-Sleep -Seconds 2

Write-Host "Listing dumps in $DumpDir"
Get-ChildItem -Path $DumpDir -Filter '*.dmp' -File -ErrorAction SilentlyContinue | Select-Object FullName,Length,LastWriteTime | Format-Table -AutoSize

Write-Host 'Stopping ProcDump (if still running).'
Get-Process procdump -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue

Write-Host 'Done. If a .dmp file was produced, upload it or tell me its path and I will analyze the native stack.'

exit $renderExit
