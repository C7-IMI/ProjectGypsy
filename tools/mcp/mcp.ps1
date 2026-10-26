# MCP bridge wrapper.
param(
  [Parameter(Position = 0)][string]$Command = "servers",
  [string]$Server = "",
  [string]$Tool = "",
  [string]$Arguments = "{}",
  [double]$Timeout = 60
)
$ErrorActionPreference = "Continue"
$python = Join-Path $env:LOCALAPPDATA "Programs\GameTools\Mcp\venv\Scripts\python.exe"
$script = Join-Path $PSScriptRoot "mcp_call.py"
if (-not (Test-Path $python)) { throw "MCP bridge venv not found at $python" }
$runArgs = @($script, $Command)
if ($Server) { $runArgs += @("--server", $Server) }
if ($Tool) { $runArgs += @("--tool", $Tool) }
if ($Command -eq "call") { $runArgs += @("--args", $Arguments) }
if ($Server) { $runArgs += @("--timeout", $Timeout) }
& $python @runArgs
