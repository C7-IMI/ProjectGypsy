# MCP bridge

DSH does not consume MCP natively; this directory is the bridge. `mcp_call.py` starts an MCP server over
stdio, lists its tools, or calls one. It uses the installed MCP Python SDK in
`%LOCALAPPDATA%\Programs\GameTools\Mcp\venv`.

~~~powershell
.\tools\mcp\mcp.ps1 servers
.\tools\mcp\mcp.ps1 list -Server blender
.\tools\mcp\mcp.ps1 call -Server blender -Tool get_scene_info -Arguments '{}'
.\tools\mcp\mcp.ps1 list -Server godot
~~~

Servers installed here:

- **Blender** — [ahujasid/mcp-for-blender](https://github.com/ahujasid/mcp-for-blender) (MIT, free, local).
  Addon installed and enabled in Blender 5.2.3; enable/verify in Blender under Edit → Preferences → Add-ons.
  The addon starts its socket server when Blender opens; tool calls require Blender running. Telemetry is disabled
  in `servers.json`. Optional asset/generation providers (Hyper3D, Sketchfab, AI 3D) are off unless keys are added.
- **Godot** — [Coding-Solo/godot-mcp](https://github.com/Coding-Solo/godot-mcp) (MIT, local), built under
  `GameTools\Mcp\godot-mcp`; `GODOT_PATH` points at the console binary. `get_godot_version` returns 4.7.2.

MCP is a protocol, not a subscription. The servers here are open source; only specific asset/generation providers
need accounts or keys (listed in ADR-008).
