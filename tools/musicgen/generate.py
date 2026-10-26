#!/usr/bin/env python3
"""Generate a short music clip locally with MusicGen (facebook/musicgen-small).

Prototype-only: the model is CC-BY-NC 4.0 (non-commercial). Do not ship generated audio in a commercial
game without a licence review. Every output gets a sidecar JSON with prompt, parameters, model identity,
hardware, and the licence note (ADR-004).

Usage:
    python tools/musicgen/generate.py --prompt "calm menu loop" --seconds 6
"""
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

MODEL = "facebook/musicgen-small"
MODEL_LICENSE = "CC-BY-NC-4.0 (non-commercial; prototype use only)"
TOKENS_PER_SECOND = 50
SILENCE_PEAK = 1e-3


def _stats(wav):
    import numpy as np

    finite = bool(np.isfinite(wav).all())
    peak = float(np.max(np.abs(wav))) if wav.size else 0.0
    rms = float(np.sqrt(np.mean(np.square(wav.astype(np.float64))))) if wav.size else 0.0
    return {"finite": finite, "peak": round(peak, 6), "rms": round(rms, 6)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Local MusicGen-small generation")
    parser.add_argument("--prompt", required=True, help="text description of the music")
    parser.add_argument("--seconds", type=float, default=6.0, help="clip length in seconds (default 6)")
    parser.add_argument("--out", default=None, help="output .wav path (default: artifacts/musicgen/)")
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--guidance", type=float, default=3.0)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--cpu", action="store_true", help="force CPU (slow; use if CUDA fails)")
    parser.add_argument("--dtype", choices=["auto", "float16", "float32"], default="auto")
    args = parser.parse_args()

    import numpy as np
    import scipy.io.wavfile
    import torch
    import transformers
    from transformers import AutoProcessor, MusicgenForConditionalGeneration

    requested_cuda = torch.cuda.is_available() and not args.cpu
    device = "cuda" if requested_cuda else "cpu"
    if args.dtype == "auto":
        dtype = torch.float16 if device == "cuda" else torch.float32
    else:
        dtype = torch.float16 if args.dtype == "float16" else torch.float32
    if args.seed is not None:
        torch.manual_seed(args.seed)

    started = time.time()
    processor = AutoProcessor.from_pretrained(args.model)
    model = MusicgenForConditionalGeneration.from_pretrained(args.model, torch_dtype=dtype).to(device)
    model.eval()
    inputs = processor(text=[args.prompt], padding=True, return_tensors="pt")
    max_new_tokens = max(64, int(round(args.seconds * TOKENS_PER_SECOND)))
    attempts = []

    def attempt(current_device, current_dtype):
        nonlocal model
        if str(current_dtype) != str(dtype):
            model = model.to(current_dtype)
        local_inputs = {key: value.to(current_device) for key, value in inputs.items()}
        begin = time.time()
        with torch.no_grad():
            audio = model.generate(
                **local_inputs,
                do_sample=True,
                guidance_scale=args.guidance,
                max_new_tokens=max_new_tokens,
            )
        array = audio[0].detach().cpu().float().numpy()
        if array.ndim > 1:
            array = array.reshape(-1)
        stats = _stats(array)
        record = {"device": current_device, "dtype": str(current_dtype), "seconds": round(time.time() - begin, 2), **stats}
        attempts.append(record)
        print("attempt", json.dumps(record), flush=True)
        return array, record

    wav = None
    used_device = device
    try:
        wav, _ = attempt(device, dtype)
    except (RuntimeError, torch.cuda.OutOfMemoryError) as exc:
        if device != "cuda":
            raise
        print(f"CUDA failed ({exc}); falling back to CPU float32", flush=True)
        torch.cuda.empty_cache()
        used_device = "cpu"
        model = model.to("cpu").to(torch.float32)
        wav, _ = attempt("cpu", torch.float32)

    last = attempts[-1]
    if not last["finite"] or last["peak"] < SILENCE_PEAK:
        print(f"generation produced silence/invalid samples ({last}); retrying float32", flush=True)
        if used_device == "cuda":
            torch.cuda.empty_cache()
        try:
            wav, _ = attempt(used_device, torch.float32)
        except (RuntimeError, torch.cuda.OutOfMemoryError) as exc:
            print(f"float32 on {used_device} failed ({exc}); retrying CPU float32", flush=True)
            torch.cuda.empty_cache()
            used_device = "cpu"
            model = model.to("cpu").to(torch.float32)
            wav, _ = attempt("cpu", torch.float32)
    if not attempts[-1]["finite"] or attempts[-1]["peak"] < SILENCE_PEAK:
        raise SystemExit("ERROR: MusicGen produced silence after retries; refusing to save a fake artifact")

    sample_rate = int(model.config.audio_encoder.sampling_rate)
    wav = np.clip(wav, -1.0, 1.0)
    if args.out:
        out = Path(args.out).expanduser()
    else:
        out = Path(os.environ.get("GYPSY_MUSICGEN_OUT", "artifacts/musicgen")) / (
            "musicgen-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".wav"
        )
    out.parent.mkdir(parents=True, exist_ok=True)
    scipy.io.wavfile.write(out, sample_rate, (wav * 32767.0).astype(np.int16))

    meta = {
        "schema": "gypsy.artifact/v1",
        "kind": "audio.musicgen",
        "artifact": str(out),
        "prompt": args.prompt,
        "model": args.model,
        "model_license": MODEL_LICENSE,
        "seconds_requested": args.seconds,
        "max_new_tokens": max_new_tokens,
        "duration_seconds": round(len(wav) / sample_rate, 3),
        "sample_rate": sample_rate,
        "device": attempts[-1]["device"],
        "dtype": attempts[-1]["dtype"],
        "guidance_scale": args.guidance,
        "seed": args.seed,
        "torch": torch.__version__,
        "transformers": transformers.__version__,
        "cuda": torch.version.cuda,
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "elapsed_seconds": round(time.time() - started, 2),
        "sample_stats": {k: attempts[-1][k] for k in ("finite", "peak", "rms")},
        "attempts": attempts,
        "provenance": {
            "tool": "MusicGen-small (transformers)",
            "human_review_required": True,
            "commercial_use_blocked_by_license": True,
        },
    }
    out.with_suffix(".json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(f"WROTE {out}")
    print(f"duration={meta['duration_seconds']}s sample_rate={sample_rate} device={meta['device']} dtype={meta['dtype']} elapsed={meta['elapsed_seconds']}s peak={meta['sample_stats']['peak']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
