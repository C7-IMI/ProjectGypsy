param(
  [Parameter(Mandatory = $true)][string]$Prompt,
  [double]$Seconds = 6,
  [string]$Out = ""
)
$ErrorActionPreference = "Continue"
$genHome = Join-Path $env:LOCALAPPDATA "Programs\GameTools\MusicGen"
$env:HF_HOME = Join-Path $genHome "hf-cache"
$env:PYTHONWARNINGS = "ignore"
$python = Join-Path $genHome "venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "MusicGen venv not installed at $python" }
$script = Join-Path $PSScriptRoot "generate.py"
$runArgs = @($script, "--prompt", $Prompt, "--seconds", $Seconds)
if ($Out) { $runArgs += @("--out", $Out) }
& $python @runArgs 2>&1 | ForEach-Object { Write-Host $_ }
if ($LASTEXITCODE -ne 0) { Write-Error "MusicGen failed with exit $LASTEXITCODE" }
