<#
.SYNOPSIS
    Start the Docker Stack Profiler

.DESCRIPTION
    This script sets up a Python virtual environment, creates the Kibana dashboard,
    and runs the Docker Stack Profiler to monitor container performance in real-time.

.PARAMETER CollectionInterval
    Seconds between metric collections (default: 5)

.PARAMETER EsHost
    Elasticsearch host URL (default: http://localhost:9201)

.PARAMETER SkipDashboard
    Skip dashboard creation (default: false)

.EXAMPLE
    .\Start-Profiler.ps1
    
.EXAMPLE
    .\Start-Profiler.ps1 -CollectionInterval 2 -EsHost "http://localhost:9201"
#>

param(
    [int]$CollectionInterval = 5,
    [string]$EsHost = "http://localhost:9201",
    [switch]$SkipDashboard
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Push-Location $ScriptDir
try {
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host "  Docker Stack Profiler - Container Performance Monitor" -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host ""

    # Check if virtual environment exists
    if (-not (Test-Path ".venv")) {
        Write-Host "Creating virtual environment..." -ForegroundColor Yellow
        python -m venv .venv
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to create virtual environment"
        }
    }

    # Activate virtual environment
    Write-Host "Activating virtual environment..." -ForegroundColor Yellow
    & ".venv\Scripts\Activate.ps1"

    # Install dependencies
    Write-Host "Installing dependencies..." -ForegroundColor Yellow
    pip install -q -r requirements.txt
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install dependencies"
    }

    # Create dashboard unless skipped
    if (-not $SkipDashboard) {
        Write-Host ""
        Write-Host "Creating Kibana dashboard..." -ForegroundColor Yellow
        python create_dashboard.py
        Write-Host ""
    }

    Write-Host "Starting profiler with:" -ForegroundColor Green
    Write-Host "  - Elasticsearch: $EsHost" -ForegroundColor Green
    Write-Host "  - Collection Interval: ${CollectionInterval}s" -ForegroundColor Green
    Write-Host ""

    # Set environment variables
    $env:ES_HOST = $EsHost
    $env:COLLECTION_INTERVAL = $CollectionInterval

    # Run the profiler
    python profiler.py
}
finally {
    Pop-Location
}
