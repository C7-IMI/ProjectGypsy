$ErrorActionPreference = "Continue"
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
Set-Location $repo
$godot = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Links\godot_console.exe"
$log = Join-Path $repo "artifacts\hero\systems.log"
New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null
& $godot --headless --path game res://scenes/hero_integration_check.tscn *>&1 | Tee-Object -FilePath $log
if ($LASTEXITCODE -ne 0) { Write-Error "hero systems check failed"; exit 1 }
if (-not (Select-String -Path $log -Pattern "HERO_SYSTEMS_OK" -Quiet)) { Write-Error "HERO_SYSTEMS_OK missing"; exit 1 }
$ok = Join-Path $repo "artifacts\hero\systems.ok"
[System.IO.File]::WriteAllText($ok, "HERO_SYSTEMS_OK`n", [System.Text.UTF8Encoding]::new($false))
Write-Output "HERO_SYSTEMS_CHECK_OK"
exit 0
