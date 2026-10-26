param(
  [string]$GameDir = "game",
  [string]$Out = "build/ProjectGypsy.apk",
  [string]$Sdk = "$env:LOCALAPPDATA\Programs\GameTools\AndroidSdk",
  [string]$Jdk = "$env:LOCALAPPDATA\Programs\GameTools\Java\jdk17\jdk-17.0.20.1+1",
  [string]$Preset = "Android"
)
$ErrorActionPreference = "Continue"
$repo = Split-Path $PSScriptRoot -Parent
Set-Location $repo
if (-not (Test-Path $Sdk)) { throw "Android SDK not found: $Sdk" }
if (-not (Test-Path $Jdk)) { throw "JDK 17 not found: $Jdk" }
$godot = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Links\godot_console.exe"
if (-not (Test-Path $godot)) { throw "Godot console binary not found: $godot" }
$env:JAVA_HOME = $Jdk
$env:ANDROID_HOME = $Sdk
$env:ANDROID_SDK_ROOT = $Sdk
$env:Path = "$Jdk\bin;$Sdk\platform-tools;$Sdk\build-tools\35.0.0;$env:Path"
$keystore = Join-Path $env:APPDATA "Godot\keystores\debug.keystore"
if (-not (Test-Path $keystore)) {
  New-Item -ItemType Directory -Force -Path (Split-Path $keystore) | Out-Null
  & "$Jdk\bin\keytool.exe" -genkeypair -keystore $keystore -storepass android -alias androiddebugkey -keypass android -dname "CN=Android Debug,O=Android,C=US" -keyalg RSA -keysize 2048 -validity 10000 | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "keytool failed" }
}
New-Item -ItemType Directory -Force -Path (Split-Path (Join-Path $repo $Out)) | Out-Null
$fullOut = Join-Path $repo $Out
if (Test-Path $fullOut) { Remove-Item $fullOut -Force }
& $godot --headless --path $GameDir --export-debug $Preset $fullOut 2>&1 | Select-Object -Last 8
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $fullOut)) { throw "Android export failed (exit $LASTEXITCODE)" }
$apk = Get-Item $fullOut
$badging = & "$Sdk\build-tools\35.0.0\aapt2.exe" dump badging $fullOut 2>$null | Select-String -Pattern "^package:|^launchable-activity:|^native-code:"
$sig = & "$Jdk\bin\java.exe" -jar "$Sdk\build-tools\35.0.0\lib\apksigner.jar" verify --print-certs $fullOut 2>&1
if ($LASTEXITCODE -ne 0) { throw "APK signature verification failed" }
$sig = $sig | Select-Object -First 4
Write-Output "ANDROID_BUILD_OK bytes=$($apk.Length) path=$Out"
$badging | ForEach-Object { Write-Output $_.Line }
$sig | ForEach-Object { Write-Output $_ }