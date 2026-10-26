#!/usr/bin/env python3
"""Generate an image through a local ComfyUI server (no cloud API).

ComfyUI runs at http://127.0.0.1:8188; the model is a local SD1.5 checkpoint. Every output gets a
provenance sidecar. Model licence: Stable Diffusion 1.5 OpenRAIL-M (commercial use with use-based
restrictions; not legal advice — review before shipping).

Usage:
    python tools/comfyui/generate.py --prompt "stylized fantasy sword icon, game asset" --steps 20
"""
from __future__ import annotations

import argparse
import json
import random
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

SERVER = "http://127.0.0.1:8188"
DEFAULT_CKPT = "v1-5-pruned-emaonly-fp16.safetensors"
LICENSE_NOTE = "SD1.5 OpenRAIL-M (use-based restrictions); model/source licence review required before shipping"


def get(path: str):
    with urllib.request.urlopen(SERVER + path, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def post(path: str, payload: dict):
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(SERVER + path, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def checkpoints():
    try:
        info = get("/object_info/CheckpointLoaderSimple")
        return info["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"][0]
    except (urllib.error.URLError, KeyError, json.JSONDecodeError, TypeError):
        return []


def workflow(prompt: str, negative: str, ckpt: str, width: int, height: int, steps: int, seed: int):
    return {
        "3": {"class_type": "KSampler", "inputs": {"seed": seed, "steps": steps, "cfg": 7.0, "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0, "model": ["4", 0], "positive": ["6", 0], "negative": ["7", 0], "latent_image": ["5", 0]}},
        "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt}},
        "5": {"class_type": "EmptyLatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["4", 1]}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["4", 1]}},
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
        "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "gypsy", "images": ["8", 0]}},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Local ComfyUI SD1.5 generation")
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--negative", default="blurry, low quality, watermark, text, extra limbs")
    parser.add_argument("--width", type=int, default=512)
    parser.add_argument("--height", type=int, default=512)
    parser.add_argument("--steps", type=int, default=20)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--ckpt", default="")
    parser.add_argument("--out", default="artifacts/comfyui")
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()
    seed = args.seed if args.seed is not None else random.randint(0, 2**31 - 1)
    available = checkpoints()
    ckpt = args.ckpt or (DEFAULT_CKPT if DEFAULT_CKPT in available else (available[0] if available else DEFAULT_CKPT))
    client_id = str(uuid.uuid4())
    prompt_id = post("/prompt", {"prompt": workflow(args.prompt, args.negative, ckpt, args.width, args.height, args.steps, seed), "client_id": client_id})["prompt_id"]
    started = time.time()
    history = None
    while time.time() - started < args.timeout:
        try:
            data = get("/history/" + prompt_id)
        except urllib.error.URLError:
            data = {}
        if prompt_id in data:
            history = data[prompt_id]
            break
        time.sleep(2)
    if history is None:
        raise SystemExit("ComfyUI generation timed out after " + str(args.timeout) + "s")
    outputs = history.get("outputs", {})
    images = []
    for node in outputs.values():
        for image in node.get("images", []):
            images.append(image)
    if not images:
        raise SystemExit("ComfyUI returned no images")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    saved = []
    for index, image in enumerate(images):
        query = urllib.parse.urlencode({"filename": image["filename"], "subfolder": image.get("subfolder", ""), "type": image.get("type", "output")})
        with urllib.request.urlopen(SERVER + "/view?" + query, timeout=60) as response:
            data = response.read()
        target = out / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + str(index) + "-" + Path(image["filename"]).name)
        target.write_bytes(data)
        sidecar = {
            "schema": "gypsy.artifact/v1",
            "kind": "image.comfyui.sd15",
            "artifact": str(target),
            "prompt": args.prompt,
            "negative": args.negative,
            "model": ckpt,
            "modelLicense": LICENSE_NOTE,
            "seed": seed,
            "steps": args.steps,
            "width": args.width,
            "height": args.height,
            "server": SERVER,
            "comfyPromptId": prompt_id,
            "generatedAt": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            "elapsedSeconds": round(time.time() - started, 1),
            "provenance": {"tool": "ComfyUI + SD1.5", "humanReviewRequired": True, "commercialUseRequiresLicenceReview": True},
        }
        target.with_suffix(target.suffix + ".json").write_text(json.dumps(sidecar, indent=2) + "\n", encoding="utf-8")
        saved.append(sidecar)
        print("WROTE " + str(target))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
