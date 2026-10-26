# Start the local ComfyUI server (SD1.5 checkpoint) on 127.0.0.1:8188.
$ErrorActionPreference = "Stop"
$base = Join-Path $env:LOCALAPPDATA "Programs\GameTools\ComfyUI\portable\ComfyUI_windows_portable"
$python = Join-Path $base "python_embeded\python.exe"
$main = Join-Path $base "ComfyUI\main.py"
$pidFile = Join-Path $env:LOCALAPPDATA "Programs\GameTools\ComfyUI\server.pid"
$logFile = Join-Path $env:LOCALAPPDATA "Programs\GameTools\ComfyUI\server.log"
$errFile = Join-Path $env:LOCALAPPDATA "Programs\GameTools\ComfyUI\server.err.log"
if (-not (Test-Path $python) -or -not (Test-Path $main)) { throw "ComfyUI portable not found at $base" }
if (Test-Path $pidFile) {
    $existing = Get-Process -Id (Get-Content $pidFile) -ErrorAction SilentlyContinue
    if ($existing) { Write-Host "ComfyUI already running (pid $($existing.Id))"; exit 0 }
}
$process = Start-Process -FilePath $python -ArgumentList @("-s", $main, "--windows-standalone-build", "--lowvram", "--port", "8188", "--listen", "127.0.0.1") -WorkingDirectory $base -WindowStyle Hidden -RedirectStandardOutput $logFile -RedirectStandardError $errFile -PassThru
$process.Id | Set-Content $pidFile
for ($i = 0; $i -lt 120; $i++) {
    if ($process.HasExited) { throw "ComfyUI exited with code $($process.ExitCode); see $logFile / $errFile" }
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:8188/system_stats" -UseBasicParsing -TimeoutSec 2
        if ($response.StatusCode -eq 200) { Write-Host "ComfyUI ready (pid $($process.Id))"; exit 0 }
    } catch { Start-Sleep -Seconds 2 }
}
throw "ComfyUI did not become ready in 240s (pid $($process.Id))"
