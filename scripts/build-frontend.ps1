# build-frontend.ps1 — Build frontend with Vite
# Usage: .\build-frontend.ps1

$ErrorActionPreference = "Stop"

Write-Host "Installing frontend dependencies..."
npm install

Write-Host "Building frontend..."
npm run build

Write-Host "Done. Output in frontend-dist/"