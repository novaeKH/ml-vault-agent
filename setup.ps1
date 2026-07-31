[CmdletBinding()]
param(
    [switch]$SkipModels,
    [switch]$SkipIndex
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Get-CompatiblePython {
    $candidates = @(
        @{ Command = "py"; Arguments = @("-3.14") },
        @{ Command = "py"; Arguments = @("-3.13") },
        @{ Command = "py"; Arguments = @("-3.12") },
        @{ Command = "py"; Arguments = @("-3.11") },
        @{ Command = "python"; Arguments = @() },
        @{ Command = "python3"; Arguments = @() }
    )

    foreach ($candidate in $candidates) {
        $command = [string]$candidate.Command
        if (-not (Get-Command $command -ErrorAction SilentlyContinue)) {
            continue
        }
        $arguments = [string[]]$candidate.Arguments
        & $command @arguments -c "import sys; raise SystemExit(0 if (3, 11) <= sys.version_info[:2] < (3, 15) else 1)" 2>$null
        if ($LASTEXITCODE -eq 0) {
            return [PSCustomObject]@{
                Command = $command
                Arguments = $arguments
            }
        }
    }
    return $null
}

function Test-Ollama {
    try {
        Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -Method Get -TimeoutSec 2 | Out-Null
        return $true
    }
    catch {
        return $false
    }
}

$python = Get-CompatiblePython
if ($null -eq $python) {
    throw "Python 3.11-3.14 is required. Install Python and enable Add python.exe to PATH."
}

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "-> Creating the local Python environment..."
    $pythonCommand = [string]$python.Command
    $pythonArguments = [string[]]$python.Arguments
    & $pythonCommand @pythonArguments -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create .venv."
    }
}

Write-Host "-> Installing the backend..."
& $venvPython -m pip install --disable-pip-version-check -e ".[dev]"
if ($LASTEXITCODE -ne 0) {
    throw "Failed to install Python dependencies."
}

if (-not $SkipModels) {
    if (-not (Get-Command "ollama" -ErrorAction SilentlyContinue)) {
        throw "Ollama was not found. Install it from https://ollama.com/download/windows and run setup again."
    }

    if (-not (Test-Ollama)) {
        Write-Host "-> Starting Ollama..."
        Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden | Out-Null
        foreach ($attempt in 1..30) {
            if (Test-Ollama) {
                break
            }
            Start-Sleep -Seconds 1
        }
    }
    if (-not (Test-Ollama)) {
        throw "Ollama is installed, but its local server did not start. Open Ollama from the Start menu and run setup again."
    }

    foreach ($model in @("qwen3:8b", "qwen3-embedding:0.6b")) {
        & ollama show $model *> $null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "OK $model is already installed"
        }
        else {
            Write-Host "-> Downloading $model (one-time download)..."
            & ollama pull $model
            if ($LASTEXITCODE -ne 0) {
                throw "Failed to download $model."
            }
        }
    }
}

if (-not $SkipIndex) {
    & $venvPython -c "from app.config import load_settings; raise SystemExit(0 if load_settings().vault_path else 1)"
    if ($LASTEXITCODE -eq 0) {
        Write-Host "-> Building the read-only Obsidian index..."
        & $venvPython -m app.cli reindex
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to build the index."
        }
    }
    else {
        Write-Host "-> No vault selected yet. Choose it in the web interface after startup."
    }
}

Write-Host ""
Write-Host "Setup complete. Start with: .\run.ps1"
Write-Host "Then open http://127.0.0.1:8787"
