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
    throw "Нужен Python 3.11–3.14. Установите Python и включите Add python.exe to PATH."
}

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "-> Создаю локальное Python-окружение..."
    $pythonCommand = [string]$python.Command
    $pythonArguments = [string[]]$python.Arguments
    & $pythonCommand @pythonArguments -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        throw "Не удалось создать .venv."
    }
}

Write-Host "-> Устанавливаю backend..."
& $venvPython -m pip install --disable-pip-version-check -e ".[dev]"
if ($LASTEXITCODE -ne 0) {
    throw "Не удалось установить Python-зависимости."
}

if (-not $SkipModels) {
    if (-not (Get-Command "ollama" -ErrorAction SilentlyContinue)) {
        throw "Ollama не найдена. Установите её с https://ollama.com/download/windows и повторите setup."
    }

    if (-not (Test-Ollama)) {
        Write-Host "-> Запускаю Ollama..."
        Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden | Out-Null
        foreach ($attempt in 1..30) {
            if (Test-Ollama) {
                break
            }
            Start-Sleep -Seconds 1
        }
    }
    if (-not (Test-Ollama)) {
        throw "Ollama установлена, но локальный сервер не запустился. Откройте Ollama из меню Start и повторите setup."
    }

    foreach ($model in @("qwen3:8b", "qwen3-embedding:0.6b")) {
        & ollama show $model *> $null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "OK $model уже установлена"
        }
        else {
            Write-Host "-> Загружаю $model (один раз)..."
            & ollama pull $model
            if ($LASTEXITCODE -ne 0) {
                throw "Не удалось загрузить $model."
            }
        }
    }
}

if (-not $SkipIndex) {
    & $venvPython -c "from app.config import load_settings; raise SystemExit(0 if load_settings().vault_path else 1)"
    if ($LASTEXITCODE -eq 0) {
        Write-Host "-> Строю read-only индекс Obsidian..."
        & $venvPython -m app.cli reindex
        if ($LASTEXITCODE -ne 0) {
            throw "Не удалось построить индекс."
        }
    }
    else {
        Write-Host "-> Vault пока не выбран. Укажите папку в web-интерфейсе после запуска."
    }
}

Write-Host ""
Write-Host "Готово. Запуск: .\run.ps1"
Write-Host "Затем откройте http://127.0.0.1:8787"
