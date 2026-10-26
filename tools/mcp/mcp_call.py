#!/usr/bin/env python3
"""Minimal MCP stdio client for DSH/agent use.

DSH does not consume MCP natively, so this CLI is the bridge: it starts an MCP server over stdio,
lists its tools, or calls one with JSON arguments. Configure servers in servers.json.

Usage:
    python tools/mcp/mcp_call.py servers
    python tools/mcp/mcp_call.py list --server blender
    python tools/mcp/mcp_call.py call --server blender --tool get_scene_info --args '{}'
    python tools/mcp/mcp_call.py list --server godot --json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SERVERS = HERE / "servers.json"


def load_config():
    data = json.loads(SERVERS.read_text(encoding="utf-8"))
    for name, server in data.get("servers", {}).items():
        server["command"] = os.path.expandvars(server.get("command", ""))
        server["args"] = [os.path.expandvars(str(arg)) for arg in server.get("args", [])]
        server["env"] = {key: os.path.expandvars(str(value)) for key, value in (server.get("env") or {}).items()}
    return data


def dump(value):
    if hasattr(value, "model_dump"):
        value = value.model_dump()
    return json.dumps(value, indent=2, default=str)


async def run(args):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    config = load_config()
    servers = config.get("servers", {})
    if args.command == "servers":
        for name, server in servers.items():
            print(name + ": " + server["command"] + " " + " ".join(server["args"]))
        return 0
    if args.server not in servers:
        print("unknown server: " + args.server + "; available: " + ", ".join(servers), file=sys.stderr)
        return 1
    server = servers[args.server]
    env = dict(os.environ)
    env.update(server.get("env") or {})
    params = StdioServerParameters(command=server["command"], args=server["args"], env=env)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await asyncio.wait_for(session.initialize(), timeout=args.timeout)
            if args.command == "list":
                result = await asyncio.wait_for(session.list_tools(), timeout=args.timeout)
                print(dump(result))
                return 0
            if args.command == "call":
                arguments = json.loads(args.args or "{}")
                result = await asyncio.wait_for(session.call_tool(args.tool, arguments), timeout=args.timeout)
                print(dump(result))
                return 0
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="MCP stdio bridge")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("servers")
    for command in ("list", "call"):
        p = sub.add_parser(command)
        p.add_argument("--server", required=True)
        p.add_argument("--timeout", type=float, default=60.0)
        p.add_argument("--json", action="store_true")
        if command == "call":
            p.add_argument("--tool", required=True)
            p.add_argument("--args", default="{}")
    args = parser.parse_args()
    try:
        return asyncio.run(run(args))
    except Exception as exc:
        print("MCP ERROR: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
