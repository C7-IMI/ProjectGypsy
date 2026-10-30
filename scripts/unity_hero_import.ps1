param(
  [string]$Project = "unity/LeftBehind",
  [string]$Fbx = "assets/hero/wayfarer.fbx",
  [string]$Unity = "C:\Program Files\Unity 6000.6.7f1\Editor\Unity.exe",
  [string]$Report = "artifacts/unity-hero-import/hero-import-report.json",
  [string]$Log = "artifacts/unity-hero-import/unity-hero-import.log"
)
$ErrorActionPreference = "Continue"
$repo = Split-Path $PSScriptRoot -Parent
Set-Location $repo
$projectPath = Join-Path $repo $Project
$fbxPath = Join-Path $repo $Fbx
$reportPath = Join-Path $repo $Report
$logPath = Join-Path $repo $Log
$tempLog = Join-Path $env:TEMP "unity-hero-import.log"
New-Item -ItemType Directory -Force -Path (Split-Path $reportPath), (Split-Path $logPath) | Out-Null

if (-not (Test-Path $Unity)) { Write-Error "Unity editor missing: $Unity"; exit 1 }
if (-not (Test-Path $fbxPath)) { Write-Error "FBX missing: $fbxPath"; exit 1 }
if (-not (Test-Path $projectPath)) { Write-Error "Unity project missing: $projectPath"; exit 1 }
Remove-Item $reportPath, $tempLog -Force -ErrorAction SilentlyContinue
Remove-Item "$projectPath\Temp\UnityLockfile" -Force -ErrorAction SilentlyContinue

# Unity 6000.6.7f1 returns 127 for this project run when launched through
# Start-Process in a nested PowerShell, so use the call operator (the documented
# pattern in scripts/build_unity_leftbehind.ps1). Paths go through the environment
# because custom -heroFbx/-heroReport args are not honoured reliably in batchmode.
$env:GYPSY_HERO_FBX = $fbxPath
$env:GYPSY_HERO_REPORT = $reportPath
$unityArguments = @(
  "-batchmode", "-nographics", "-quit",
  "-projectPath", ('"' + $projectPath + '"'),
  "-executeMethod", "HeroImportProof.Run",
  "-logFile", ('"' + $tempLog + '"')
) -join " "
Write-Output "UNITY_HERO_IMPORT_START project=$Project fbx=$Fbx"
$started = Get-Date
# Start-Process without -Wait, then an explicit WaitForExit(): Windows PowerShell 5.1
# treats Unity.exe as a GUI subsystem app and the call operator returns immediately.
$process = Start-Process -FilePath $Unity -ArgumentList $unityArguments -PassThru
if ($null -eq $process) {
  Write-Output "UNITY_HERO_IMPORT_FAIL could not start Unity: $Unity"
  exit 1
}
$process.WaitForExit()
$exitCode = $process.ExitCode
$seconds = [math]::Round(((Get-Date) - $started).TotalSeconds, 1)
if (Test-Path $tempLog) { Copy-Item $tempLog $logPath -Force }
Remove-Item Env:GYPSY_HERO_FBX, Env:GYPSY_HERO_REPORT -ErrorAction SilentlyContinue
Write-Output "unity_exit=$exitCode seconds=$seconds log=$Log"

if (-not (Test-Path $reportPath)) {
  Write-Output "UNITY_HERO_IMPORT_FAIL report missing: $Report"
  if (Test-Path $logPath) {
    Get-Content $logPath -Tail 50
    $license = Select-String -Path $logPath -Pattern 'license|Licensing|Aborting' -ErrorAction SilentlyContinue | Select-Object -Last 5
    if ($license) { $license | ForEach-Object { $_.Line } }
  }
  exit 1
}

try {
  # Note: do not name this $report; Windows PowerShell treats it as the same variable as
  # the $Report parameter and the parse assignment case-collides.
  $parsedReport = Get-Content $reportPath -Raw | ConvertFrom-Json
} catch {
  Write-Output "UNITY_HERO_IMPORT_FAIL report unreadable: $_"
  exit 1
}

$clipNames = @($parsedReport.model.clips | ForEach-Object { $_.name }) -join ','
$textureNames = @($parsedReport.model.textures | ForEach-Object { $_.name }) -join ','
$summary = "passed=$($parsedReport.passed) bones=$($parsedReport.model.boneCount) clips=$clipNames blendShapes=$(@($parsedReport.model.blendShapes) -join ',') materials=$(@($parsedReport.model.materials).Count) textures=$textureNames height=$([math]::Round($parsedReport.model.heightMeters, 3))m"
if ($parsedReport.passed -and $exitCode -eq 0) {
  Write-Output "UNITY_HERO_IMPORT_OK $summary report=$reportPath"
  exit 0
}

Write-Output "UNITY_HERO_IMPORT_FAIL exit=$exitCode $summary report=$reportPath"
$failed = @($parsedReport.checks | Where-Object { -not $_.passed })
foreach ($check in $failed) {
  Write-Output ("  FAILED CHECK " + $check.name + " expected=" + $check.expected + " actual=" + $check.actual)
}
if ($parsedReport.errors) { $parsedReport.errors | Select-Object -First 5 }
if (Test-Path $logPath) { Write-Output "--- log tail ---"; Get-Content $logPath -Tail 30 }
exit 1
