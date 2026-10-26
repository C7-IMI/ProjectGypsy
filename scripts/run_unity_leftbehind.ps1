param(
  [ValidateSet("demo","capture")]
  [string]$Mode = "demo",
  [string]$Log = "artifacts/leftbehind/player.log",
  [string]$Capture = "artifacts/leftbehind/frame.png"
)
$ErrorActionPreference = "Continue"
$repo = Split-Path $PSScriptRoot -Parent
Set-Location $repo
$build = Join-Path $repo "unity/LeftBehind/Build"
$player = Join-Path $build "LeftBehind.exe"
if (-not (Test-Path $player)) { Write-Error "LeftBehind.exe missing; run the build first"; exit 1 }
$tempLog = Join-Path $env:TEMP ("leftbehind-" + $Mode + ".log")
$tempFrame = Join-Path $env:TEMP "leftbehind-frame.png"
Remove-Item $tempLog,$tempFrame -Force -ErrorAction SilentlyContinue
if ($Mode -eq "capture") {
  $arguments = @("--demo", "--capture=$tempFrame", "-screen-fullscreen", "0", "-screen-width", "1280", "-screen-height", "720", "-logFile", $tempLog)
} else {
  $arguments = @("-batchmode", "-nographics", "--demo", "-logFile", $tempLog)
}
$windowStyle = if ($Mode -eq "capture") { "Normal" } else { "Hidden" }
$process = Start-Process -FilePath $player -WorkingDirectory $build -ArgumentList $arguments -PassThru -WindowStyle $windowStyle
for ($i = 0; $i -lt 90; $i++) {
  Start-Sleep -Seconds 1
  if ($process.HasExited) { break }
}
if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force; Write-Error "player did not exit"; exit 1 }
New-Item -ItemType Directory -Force -Path (Split-Path (Join-Path $repo $Log)) | Out-Null
if (Test-Path $tempLog) { Copy-Item $tempLog (Join-Path $repo $Log) -Force }
if (-not (Test-Path $tempLog) -or -not (Select-String -Path $tempLog -Pattern "GYPSY_DEMO_OK collected=3" -Quiet)) { Write-Error "demo marker missing"; exit 1 }
if ($Mode -eq "capture") {
  if (-not (Test-Path $tempFrame)) { Write-Error "capture missing"; exit 1 }
  New-Item -ItemType Directory -Force -Path (Split-Path (Join-Path $repo $Capture)) | Out-Null
  Copy-Item $tempFrame (Join-Path $repo $Capture) -Force
}
Write-Output "LEFTBEHIND_$($Mode.ToUpper())_OK"
exit 0
