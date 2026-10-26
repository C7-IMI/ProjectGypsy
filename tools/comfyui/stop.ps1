# Stop only the ComfyUI process started by start.ps1.
$ErrorActionPreference = "Stop"
$pidFile = Join-Path $env:LOCALAPPDATA "Programs\GameTools\ComfyUI\server.pid"
if (-not (Test-Path $pidFile)) { Write-Host "no ComfyUI pid file"; exit 0 }
$processId = Get-Content $pidFile
$process = Get-Process -Id $processId -ErrorAction SilentlyContinue
if (-not $process) { Remove-Item $pidFile -Force; Write-Host "ComfyUI not running"; exit 0 }
if ($process.Path -notlike "*ComfyUI*") { throw "refusing to kill unexpected process $processId ($($process.Path))" }
Stop-Process -Id $processId -Force
Remove-Item $pidFile -Force
Write-Host "ComfyUI stopped (pid $processId)"
