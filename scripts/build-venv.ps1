# build-venv.ps1 — Build Python venv with pre-installed dependencies
# Usage: .\build-venv.ps1 -PythonPath "C:\Python312" -OutputPath ".\venv"

param(
    [Parameter(Mandatory=$true)]
    [string]$PythonPath,

    [Parameter(Mandatory=$true)]
    [string]$OutputPath
)

$ErrorActionPreference = "Stop"

Write-Host "Creating venv at $OutputPath..."
& $PythonPath\python.exe -m venv $OutputPath

Write-Host "Upgrading pip..."
& "$OutputPath\Scripts\pip.exe" install --upgrade pip

Write-Host "Installing requirements..."
& "$OutputPath\Scripts\pip.exe" install -r backend\requirements.txt

Write-Host "Verifying key packages..."
& "$OutputPath\Scripts\python.exe" -c "import waitress; import flask; import loguru; print('All packages OK')"

Write-Host "Done. Venv ready at $OutputPath"