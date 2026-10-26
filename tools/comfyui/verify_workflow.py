#!/usr/bin/env python3
"""Verify the importable SD1.5 ComfyUI workflow against the local server.

Checks the UI workflow graph, converts it to the ComfyUI API prompt, runs it, and saves the
result plus a sidecar under artifacts/comfyui/. No cloud calls.
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

SERVER = "http://127.0.0.1:8188"
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_WORKFLOW = ROOT / "tools" / "comfyui" / "workflows" / "projectgypsy-sd15-basic.json"
OUT = ROOT / "artifacts" / "comfyui"


def get(path):
    with urllib.request.urlopen(SERVER + path, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def post(path, payload):
    request = urllib.request.Request(
        SERVER + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def validate(workflow):
    errors = []
    if workflow.get("version") not in (0.4, 0.3):
        errors.append("unexpected workflow version")
    nodes = {node.get("id"): node for node in workflow.get("nodes", [])}
    links = workflow.get("links", [])
    if not nodes:
        errors.append("workflow has no nodes")
    for link in links:
        if len(link) != 6:
            errors.append("bad link " + repr(link))
            continue
        link_id, origin, origin_slot, target, target_slot, kind = link
        if origin not in nodes or target not in nodes:
            errors.append("link " + str(link_id) + " points at a missing node")
            continue
        out = nodes[origin].get("outputs", [])
        if origin_slot >= len(out) or out[origin_slot].get("type") != kind:
            errors.append("link " + str(link_id) + " origin slot/type mismatch")
        ins = nodes[target].get("inputs", [])
        if target_slot >= len(ins) or ins[target_slot].get("type") != kind:
            errors.append("link " + str(link_id) + " target slot/type mismatch")
    required = ["CheckpointLoaderSimple", "CLIPTextEncode", "KSampler", "VAEDecode", "SaveImage", "EmptyLatentImage"]
    present = {node.get("type") for node in nodes.values()}
    for kind in required:
        if kind not in present:
            errors.append("missing node type " + kind)
    return errors


def api_prompt(workflow):
    nodes = {node["id"]: node for node in workflow["nodes"]}
    by_type = {}
    for node in nodes.values():
        by_type.setdefault(node["type"], []).append(node)

    def widget(node, index):
        return (node.get("widgets_values") or [])[index]

    checkpoint = by_type["CheckpointLoaderSimple"][0]
    ckpt = widget(checkpoint, 0)
    positive = by_type["CLIPTextEncode"][0]
    negative = by_type["CLIPTextEncode"][1]
    latent = by_type["EmptyLatentImage"][0]
    sampler = by_type["KSampler"][0]
    decode = by_type["VAEDecode"][0]
    save = by_type["SaveImage"][0]
    prompt = {
        str(checkpoint["id"]): {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt}},
        str(positive["id"]): {"class_type": "CLIPTextEncode", "inputs": {"text": widget(positive, 0), "clip": [str(checkpoint["id"]), 1]}},
        str(negative["id"]): {"class_type": "CLIPTextEncode", "inputs": {"text": widget(negative, 0), "clip": [str(checkpoint["id"]), 1]}},
        str(latent["id"]): {"class_type": "EmptyLatentImage", "inputs": {"width": widget(latent, 0), "height": widget(latent, 1), "batch_size": widget(latent, 2)}},
        str(sampler["id"]): {"class_type": "KSampler", "inputs": {
            "seed": widget(sampler, 0), "steps": widget(sampler, 2), "cfg": widget(sampler, 3),
            "sampler_name": widget(sampler, 4), "scheduler": widget(sampler, 5), "denoise": widget(sampler, 6),
            "model": [str(checkpoint["id"]), 0], "positive": [str(positive["id"]), 0],
            "negative": [str(negative["id"]), 0], "latent_image": [str(latent["id"]), 0],
        }},
        str(decode["id"]): {"class_type": "VAEDecode", "inputs": {"samples": [str(sampler["id"]), 0], "vae": [str(checkpoint["id"]), 2]}},
        str(save["id"]): {"class_type": "SaveImage", "inputs": {"filename_prefix": widget(save, 0), "images": [str(decode["id"]), 0]}},
    }
    return prompt, ckpt


def main():
    parser = argparse.ArgumentParser(description="Verify the local SD1.5 ComfyUI workflow")
    parser.add_argument("--workflow", default=str(DEFAULT_WORKFLOW))
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()
    workflow = json.loads(Path(args.workflow).read_text(encoding="utf-8"))
    errors = validate(workflow)
    if errors:
        raise SystemExit("workflow invalid: " + "; ".join(errors))
    checkpoints = get("/object_info/CheckpointLoaderSimple")["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"][0]
    prompt, ckpt = api_prompt(workflow)
    if ckpt not in checkpoints:
        raise SystemExit("checkpoint not installed: " + ckpt)
    prompt_id = post("/prompt", {"prompt": prompt, "client_id": str(uuid.uuid4())})["prompt_id"]
    started = time.time()
    history = None
    while time.time() - started < args.timeout:
        data = get("/history/" + prompt_id)
        if prompt_id in data:
            history = data[prompt_id]
            break
        time.sleep(2)
    if history is None:
        raise SystemExit("generation timed out")
    images = [image for node in history.get("outputs", {}).values() for image in node.get("images", [])]
    if not images:
        raise SystemExit("no images returned")
    OUT.mkdir(parents=True, exist_ok=True)
    saved = []
    for index, image in enumerate(images):
        query = urllib.parse.urlencode({"filename": image["filename"], "subfolder": image.get("subfolder", ""), "type": image.get("type", "output")})
        with urllib.request.urlopen(SERVER + "/view?" + query, timeout=60) as response:
            data = response.read()
        target = OUT / (time.strftime("%Y%m%dT%H%M%S") + "-workflow-" + str(index) + ".png")
        target.write_bytes(data)
        sidecar = {
            "schema": "gypsy.artifact/v1",
            "kind": "image.comfyui.workflow",
            "workflow": str(Path(args.workflow)),
            "checkpoint": ckpt,
            "promptId": prompt_id,
            "artifact": str(target),
            "seconds": round(time.time() - started, 1),
            "modelLicense": "SD1.5 OpenRAIL-M; review before shipping",
            "humanReviewRequired": True,
        }
        target.with_suffix(".png.json").write_text(json.dumps(sidecar, indent=2) + "\n", encoding="utf-8")
        saved.append(str(target))
    print("WORKFLOW_OK checkpoint=" + ckpt + " images=" + str(len(saved)))
    for path in saved:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
