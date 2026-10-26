param(
  [string]$Project = "unity/LeftBehind",
  [string]$Log = "artifacts/leftbehind/build.log",
  [string]$Unity = "C:\Program Files\Unity 6000.6.7f1\Editor\Unity.exe"
)
$ErrorActionPreference = "Continue"
$repo = Split-Path $PSScriptRoot -Parent
Set-Location $repo
$projectPath = Join-Path $repo $Project
$logPath = Join-Path $repo $Log
$tempLog = Join-Path $env:TEMP "leftbehind-build.log"
New-Item -ItemType Directory -Force -Path (Split-Path $logPath) | Out-Null
Remove-Item $tempLog -Force -ErrorAction SilentlyContinue
Remove-Item "$projectPath\Temp\UnityLockfile" -Force -ErrorAction SilentlyContinue
& $Unity -batchmode -quit -nographics -projectPath $projectPath -executeMethod BuildLeftBehind.Build -logFile $tempLog 2>&1 | Select-Object -Last 4
for ($i = 0; $i -lt 300; $i++) {
  Start-Sleep -Seconds 1
  if ((Test-Path $tempLog) -and (Select-String -Path $tempLog -Pattern "LEFTBEHIND_BUILD Succeeded" -Quiet -ErrorAction SilentlyContinue)) { break }
}
if (Test-Path $tempLog) { Copy-Item $tempLog $logPath -Force }
if (-not (Test-Path "$projectPath\Build\LeftBehind.exe")) { Write-Error "LeftBehind.exe missing"; exit 1 }
if (-not (Test-Path $tempLog) -or -not (Select-String -Path $tempLog -Pattern "LEFTBEHIND_BUILD Succeeded" -Quiet)) { Write-Error "Unity build did not report success"; exit 1 }
Write-Output "LEFTBEHIND_BUILD_OK path=$Project/Build/LeftBehind.exe"
exit 0
