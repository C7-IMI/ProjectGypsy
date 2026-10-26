#!/usr/bin/env python3
"""Download free CC0 assets from Poly Haven (no API key).

Poly Haven's public API requires no authentication. Each download writes a provenance JSON sidecar
with the asset id, licence (CC0), source URL, SHA-256 and retrieval time.

Usage:
    python tools/polyhaven/polyhaven.py list --type textures --search brick
    python tools/polyhaven/polyhaven.py info brick_wall_02
    python tools/polyhaven/polyhaven.py download brick_wall_02 --resolution 1k --slot Diffuse --dest artifacts/polyhaven
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API = "https://api.polyhaven.com"
LICENSE = "CC0"


def fetch_json(url: str):
    request = urllib.request.Request(url, headers={"User-Agent": "gypsy-workstream/0.1"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def list_assets(asset_type: str, search: str):
    data = fetch_json(API + "/assets?t=" + urllib.parse.quote(asset_type))
    rows = []
    for asset_id, asset in data.items():
        name = asset.get("name", asset_id)
        tags = " ".join(asset.get("tags", []))
        if search and not re.search(re.escape(search), (asset_id + " " + name + " " + tags).lower(), re.I):
            continue
        rows.append({"id": asset_id, "name": name, "categories": asset.get("categories", []), "tags": asset.get("tags", [])[:8]})
    return sorted(rows, key=lambda item: item["id"])


def info(asset_id: str):
    return {"asset": fetch_json(API + "/info/" + urllib.parse.quote(asset_id)), "files": fetch_json(API + "/files/" + urllib.parse.quote(asset_id))}


def pick_file(files, resolution: str, slot: str, preferred_exts):
    node = files
    if slot:
        if slot not in node:
            keys = ", ".join(k for k in node.keys())
            raise SystemExit("slot " + slot + " not found; available: " + keys)
        node = node[slot]
    if resolution:
        if resolution not in node:
            keys = ", ".join(k for k in node.keys())
            raise SystemExit("resolution " + resolution + " not found; available: " + keys)
        node = node[resolution]
    if not isinstance(node, dict):
        raise SystemExit("unexpected file node: " + str(node)[:200])
    for extension in preferred_exts:
        for key, value in node.items():
            if isinstance(value, dict) and key.get("url") if isinstance(key, dict) else key.lower().endswith(extension):
                pass
    candidates = []
    for key, value in node.items():
        if isinstance(value, dict) and value.get("url"):
            candidates.append((key, value))
    if not candidates:
        raise SystemExit("no downloadable files at this slot/resolution")
    for extension in preferred_exts:
        for key, value in candidates:
            if key.lower().endswith(extension):
                return key, value
    return candidates[0]


def download(asset_id: str, resolution: str, slot: str, dest: Path):
    payload = info(asset_id)
    files = payload["files"]
    key, value = pick_file(files, resolution, slot, [".png", ".jpg", ".jpeg", ".exr", ".hdr", ".gltf", ".glb", ".blend", ".fbx", ".zip"])
    url = value["url"]
    filename = asset_id + "__" + slot.replace(" ", "_") + "__" + resolution + "__" + Path(urllib.parse.urlparse(url).path).name
    dest.mkdir(parents=True, exist_ok=True)
    target = dest / filename
    request = urllib.request.Request(url, headers={"User-Agent": "gypsy-workstream/0.1"})
    with urllib.request.urlopen(request, timeout=300) as response, open(target, "wb") as handle:
        data = response.read()
        handle.write(data)
    digest = hashlib.sha256(data).hexdigest()
    record = {
        "schema": "gypsy.artifact/v1",
        "kind": "asset.polyhaven",
        "asset": asset_id,
        "name": (payload["asset"].get("name") if isinstance(payload.get("asset"), dict) else asset_id),
        "slot": slot,
        "resolution": resolution,
        "source": url,
        "license": LICENSE,
        "licenseUrl": "https://polyhaven.com/license",
        "retrievedAt": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "sha256": digest,
        "bytes": len(data),
        "path": str(target),
        "humanReviewRequired": True,
    }
    (target.with_suffix(target.suffix + ".json")).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description="Poly Haven CC0 asset downloader")
    sub = parser.add_subparsers(dest="command", required=True)
    list_parser = sub.add_parser("list")
    list_parser.add_argument("--type", default="textures", choices=["textures", "models", "hdris", "all"])
    list_parser.add_argument("--search", default="")
    info_parser = sub.add_parser("info")
    info_parser.add_argument("asset")
    dl = sub.add_parser("download")
    dl.add_argument("asset")
    dl.add_argument("--resolution", default="1k")
    dl.add_argument("--slot", default="")
    dl.add_argument("--dest", default="artifacts/polyhaven")
    args = parser.parse_args()
    try:
        if args.command == "list":
            for row in list_assets(args.type, args.search):
                print(row["id"] + " | " + row["name"] + " | " + ", ".join(row["categories"]))
        elif args.command == "info":
            print(json.dumps(info(args.asset), indent=2))
        elif args.command == "download":
            record = download(args.asset, args.resolution, args.slot, Path(args.dest))
            print(json.dumps(record, indent=2))
    except Exception as exc:
        print("POLYHAVEN ERROR: " + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
