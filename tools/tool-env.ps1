# Load the installed GameTools into this PowerShell session.
# Usage:  . .\tools\tool-env.ps1
$manifest = Join-Path $env:LOCALAPPDATA "Programs\GameTools\tools.json"
if (-not (Test-Path $manifest)) {
    Write-Error "GameTools manifest not found at $manifest"
    return
}
$tools = Get-Content $manifest -Raw | ConvertFrom-Json
$dirs = @($tools | ForEach-Object { $_.path } | Where-Object { $_ -and (Test-Path $_) })
$env:GYPSY_TOOLS_MANIFEST = $manifest
$env:Path = ($dirs -join ";") + ";" + $env:Path
Write-Host ("GameTools loaded: " + $dirs.Count + " directories")
