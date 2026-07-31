$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    throw "Run .\setup.ps1 first."
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

if ((Get-Command "ollama" -ErrorAction SilentlyContinue) -and -not (Test-Ollama)) {
    Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden | Out-Null
    foreach ($attempt in 1..30) {
        if (Test-Ollama) {
            break
        }
        Start-Sleep -Seconds 1
    }
}

Write-Host "ML Vault Agent: http://127.0.0.1:8787"
Write-Host "Stop with: Ctrl+C"
& $venvPython -m uvicorn app.main:app --host 127.0.0.1 --port 8787
if ($LASTEXITCODE -ne 0) {
    throw "ML Vault Agent exited with an error."
}
