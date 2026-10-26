# ADR-004 — Generative media: YuE2 blocked by hardware, MusicGen-small installed for prototyping

**Status:** Accepted, amended 2026-10-25 after the MusicGen-small runtime was installed and smoke-tested · **Decision owner:** operator · **Reviewer:** Lead
**Scope:** generative music and image models on this workstream's hardware.
**Related:** [TOOL-INVENTORY.md](../TOOL-INVENTORY.md) · [DEFERRED.md](../DEFERRED.md) PG-D10 (YuE2), PG-D11
(hardware) · [ADR-002](ADR-002-art-pipeline.md) (asset pipeline and provenance).

## Context
1. **What was wanted:** generated songs for the game (YuE2-class, with vocals) and generated images for concepts
   and references. Neither is required to start the pipeline; both are bounded by this machine.
2. **The machine:** NVIDIA T600 Laptop, **4096 MiB VRAM** (verified with `nvidia-smi`), Windows, 64 GB RAM,
   D: 52.6 GB free. It is a managed work machine (SentinelOne/Intune/ConnectWise), which matters for any cloud
   route that uploads prompts or assets.
3. **YuE2 cannot run here.** Its README states: **"Linux · Python 3.12 · NVIDIA GPU with BF16 support and 24 GB
   VRAM."** YuE2 also produces 48 kHz stereo audio without quantization ([repository](https://github.com/multimodal-art-projection/YuE)).
   This machine is Windows, and the T600 is a 4 GB Turing card (no BF16 class of support, per the inventory), so a
   local install would download model files on first use and still not run. That is registered as **PG-D10**, and
   §11.6 forbids installing a capability that cannot work. **No fake local install** — nothing YuE2-related is
   downloaded, and no "it runs" claim is made.
4. **Licences bind as hard as VRAM.** Verified 2026-10-25: YuE2 code is Apache-2.0, **model weights are CC BY-NC
   4.0 with additional creator permission**, free for academic non-commercial use, and companies must contact the
   authors for a commercial licence ([MODEL_LICENSE](https://github.com/multimodal-art-projection/YuE/blob/main/MODEL_LICENSE)).
   MusicGen code is MIT but its **weights are CC-BY-NC 4.0**
   ([model card](https://github.com/facebookresearch/audiocraft/blob/main/model_cards/MUSICGEN_MODEL_CARD.md)).
   FLUX.1 [dev] carries a **non-commercial licence**; FLUX.1 [schnell] is Apache-2.0
   ([repo](https://github.com/black-forest-labs/flux)); SDXL is OpenRAIL++
   ([model](https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0)).
5. **The capability state is measured, not assumed.** `generative.yue2.generate` is **blocked** (hardware gate
   below). `audio.musicgen.generate` is **partial but installed**: `facebook/musicgen-small` runs locally through
   `tools/musicgen/generate.py` in a Python 3.10 venv (torch 2.11.0+cu128, transformers 5.20.2, model cache under
   `%LOCALAPPDATA%\Programs\GameTools\MusicGen\hf-cache`). A 6-second clip was generated on the T600: 5.94 s,
   32 kHz mono, RMS 0.146, 35.5 s wall time, after the float16 attempt produced NaNs and the generator detected the
   silence and retried in float32. The model licence is CC-BY-NC 4.0, so the output is prototype-only. LMMS/Audacity
   remain the human audio path; FFmpeg converts.

## Decision
**No heavy generative model is installed; a small local fallback is.** YuE2 is rejected on this hardware (Windows,
T600, 4 GB VRAM, no BF16) and no weights are downloaded. MusicGen-small **is installed and smoke-tested** as an
instrumental prototyping fallback only. Generative media otherwise comes from documented cloud/online runbooks when
the operator approves, and every generated file enters the pipeline as an imported source with a provenance record.

### D1 — Record the hardware gate instead of guessing around it
| Capability | Gate that must be met first | Basis |
| --- | --- | --- |
| YuE2, local or cloud-native | Linux (or WSL2 with CUDA), Python 3.12, NVIDIA GPU with BF16 and **24 GB+ VRAM** | repository README |
| FLUX.1, local | 11.9B parameters ≈ **22.2 GiB (23.8 GB)** of bf16 weights alone, before activations → 24 GB class | HF model inventory, 2026-10-25 |
| SDXL, local | 2.57B parameters, ≈4.8 GiB (5.1 GB) of fp16 weights plus activations → more than 4 GiB, practically 8 GiB+ | HF model inventory, arithmetic from parameter count |
| MusicGen, local | **Met on this machine for short clips**: 4 GB GPU, fp32 generation, single 6 s clip; CPU possible but slow | AudioCraft docs and the measured T600 run in Evidence |
| Image workloads generally | VRAM plus disk for checkpoints; D: has 52.6 GB free (PG-D11) | `Get-PSDrive`, inventory |

A future local install must re-run `art.probe` (ADR-002, Phase 1) and amend this ADR; no model is installed against
a gate that is not met.

### D2 — Music generation options, in the order they will be tried
| # | Route | What it needs | Cost in hardware/account terms | Verdict |
| --- | --- | --- | --- | --- |
| 1 | Free hosted demo the repository links ([yue.noizai.net](https://yue.noizai.net/)) | a browser; no install | free; its own terms and limits are not documented in the README and were not tested here; weights are CC BY-NC, so no commercial grant | ideation only — capture prompt, date and output immediately, do not depend on the service |
| 2 | Official ComfyUI YuE2 workflow on a rented GPU ([workflow](https://github.com/Comfy-Org/workflow_templates/blob/main/templates/audio_yue2_text2music.json)) | cloud GPU with 24 GB+; ComfyUI; model download on first use | hourly rental, account and payment, storage and egress; corporate policy on uploads | best repeatable route when a song is actually needed |
| 3 | Rented GPU instance running `examples/generate.py` | Linux, Python 3.12, 24 GB BF16 GPU, repo checkout, disk for weights | same hourly rental plus setup time; full control of prompts/seeds | fallback to option 2; needed for parameter-level reproducibility |
| 4 | MusicGen-small locally (**installed and smoke-tested**; `tools/musicgen/generate.py`, wrapper `tools/musicgen/musicgen.ps1`) | 4 GB GPU; short clips; fp32 after an fp16 NaN; CPU possible but slow | free; published checkpoint ~591M parameters, ~1.4 GB cache; measured 35.5 s for 6 s audio on the T600; weights CC-BY-NC 4.0 | **not a YuE2 substitute**: instrumental only (no vocals/lyrics), 32 kHz, lower quality; prototyping only |

YuE2's 48 kHz stereo output versus MusicGen's 32 kHz generation means the fallback cannot stand in for a vocal
track. Both model licences are non-commercial, so neither output ships in a sold game without a licence. Downloading YuE2 weights is only worth doing once option 1,
2 or 3 exists.

### D3 — Image generation
| # | Route | What it needs | Cost | Note |
| --- | --- | --- | --- | --- |
| 1 | Cloud SDXL through ComfyUI on a rented GPU | 8 GB+ practical, 12 GB+ comfortable (rule of thumb) | hourly rental, account | SDXL is OpenRAIL++ |
| 2 | Cloud FLUX.1 [schnell] | 24 GB class for bf16 | hourly, highest of the options | Apache-2.0 licence is the commercial-friendly route |
| 3 | Cloud FLUX.1 [dev] | 24 GB class | hourly | **non-commercial licence** — do not ship the output in a sold game |
| 4 | Local SD1.5 | 4 GB with low-VRAM flags, 512 px native | free, slow, low quality and consistency | only if a prototype truly needs an image; not a production path |
| 5 | Local SDXL/FLUX now | 8–24 GB | — | rejected: the gate in D1 is not met |

The operating rule: **4 GB VRAM is below a practical SDXL/FLUX setup**, so local image generation is SD1.5-only
and prototyping-only. Do not install model stacks until the hardware exists; cloud generation is the practical
route, and **every** generated asset needs provenance and a licence check before it is used (D4).

### D4 — How generated media enters the asset pipeline
Generated output is an **imported source with an external-generator record**, never a "derived" artefact: the
pipeline cannot regenerate it, so §2.5's regenerate-and-check does not apply to the bytes, only to their record.

- Stored under `assets/ref/generated/` (references) or `assets/src/generated/` (files kept as sources), with the
  provenance record in `records/`.
- Record fields: service or model and version/hash; prompt and any seed/parameters the service exposes; date;
  output licence and terms version; `ai-generated` flag; human approver; every later edit (Audacity, image editor)
  as a derived file with its own record.
- **A human approves** before the file is promoted to a source; approval is recorded, never implied.
- **No generated art or music without provenance.** A missing or incomplete record is a validator failure
  (ADR-002, D4 "Provenance"), not a warning.
- Non-commercial model terms mean the output cannot ship in a commercial release until licensed or replaced. A
  hosted demo's terms may add restrictions beyond the model licence; record the terms you relied on and the date.
- Keep the output file, not just the prompt: a service that changes its model later cannot reproduce it.

### D5 — Deferred now, written down rather than half-built
| Deferred item | What it will be | Unblocks when |
| --- | --- | --- |
| Cloud YuE2 runbook | step-by-step ComfyUI/official-workflow or `generate.py` run: account, GPU class, cost estimate, weight download, provenance capture, instance cleanup | operator approves cloud spend and the corporate policy on uploading prompts |
| Cloud image runbook | SDXL/FLUX runbook with the model licence recorded per run | the same approval |
| MusicGen-small quality evaluation | compare short generated clips against placeholder/licensed audio for menu and ambient beds; explicitly non-commercial | there is a concrete need for a prototype music bed |
| Hardware upgrade | eGPU/desktop meeting the D1 gate (PG-D11) | operator measures the bottleneck first |

These sit under PG-D10/PG-D11/PG-D13 today (PG-D13 added with this amendment).

## Consequences
- **Today there is a local prototype music path, not a produced soundtrack.** MusicGen-small can produce short
  instrumental beds for prototyping; production music still comes from LMMS/Audacity work or licensed
  tracks; visuals from human art, licensed assets or CC0 libraries (Poly Haven is a web service, not installed).
- **Cost moves from capex to hourly cloud spend**, with an account, payment method and probably an IT policy
  decision about uploading game material — all of which need the operator.
- **Licences stay unresolved**: YuE2, MusicGen and FLUX.1 [dev] outputs cannot ship commercially without a licence,
  even when they run in the cloud. That is a product decision, not a technical one.
- **Reproducibility is weaker**: a hosted demo may expose no seed and can change or disappear; the record and the
  saved output are the reproducibility, not the service.
- **Disk cost is bounded**: the MusicGen venv plus the cached checkpoint are small enough for C: (a few GB); YuE2
  remains offline because its weights would be tens of GB for hardware that cannot run them.
- **The distracting middle is contained, not mistaken for delivery**: MusicGen-small is installed **as a prototype
  tool**, labelled non-commercial in its capability manifest, and cannot be promoted to a shipping standard without
  a licence review — §11.6's failure would be claiming it as production audio.

## Alternatives rejected
| Alternative | Why rejected |
| --- | --- |
| Install YuE2 locally anyway | it cannot run: Windows, no BF16, 4 GB; the download would be tens of gigabytes of unusable weights (PG-D10) |
| Buy a 24 GB GPU now | capex before measuring that generative media is the bottleneck; PG-D11 asks for measurement first |
| Use the free hosted demo as the production pipeline | no batch, no SLA, no guaranteed seed, terms undocumented in the repo, output still non-commercial |
| Local SD1.5 as the production image path | 512 px, weak consistency; a production standard built on it would be a fake capability |
| Skip provenance for "just a prototype" | prototypes become assets; an untraceable file is the exact failure ADR-002 D5 exists to stop |
| Wait for hardware and document nothing | the operator needs a runbook the day the spend is approved; the gate and options are cheap to write now |

## Open decisions and next steps
- **O1 Commercial intent.** Will the game be sold? If yes, CC BY-NC outputs (YuE2, MusicGen, FLUX.1 [dev]) need a
  commercial licence, replacement models, or licensed music/art. This decides which options are usable at all.
- **O2 Cloud budget and provider.** RunPod/Lambda/AWS choice, hourly budget, data residency — and the managed-machine
  policy on sending prompts or unreleased assets to a third party. Operator/IT decision.
- **O3 Who approves generated assets**, and where the approval is recorded (same question as ADR-002 O7).
- **O4 Resolved:** MusicGen-small is installed and smoke-tested for instrumental prototyping. It remains CC BY-NC,
  so it is not a commercial fallback; decide separately whether the prototype quality is worth using.
- **O5 Which image model** is the commercial route: FLUX.1 [schnell] (Apache-2.0, 24 GB) or SDXL (OpenRAIL++,
  8 GB+)? It narrows the cloud GPU class.
- **O6 Deferral id.** PG-D10 covers YuE2; **PG-D13** now covers the cloud runbooks (added with this amendment).
- **Next steps, in order:** (1) accept this ADR; (2) answer O1 and O2; (3) write the chosen runbook(s) and record
  their costs; (4) carry the provenance fields into the ADR-002 descriptor/record schema; (5) revisit when PG-D11
  is resolved.

## Evidence
| Claim | Observation |
| --- | --- |
| YuE2 hardware requirement | README fetched 2026-10-25: "Linux · Python 3.12 · NVIDIA GPU with BF16 support and 24 GB VRAM", 48 kHz stereo |
| YuE2 licence | README license table and [MODEL_LICENSE](https://github.com/multimodal-art-projection/YuE/blob/main/MODEL_LICENSE): code Apache-2.0, weights CC BY-NC 4.0 + additional creator permission; commercial use by companies requires a licence |
| Free demo and official workflow | README links: free NOIZ-hosted demo at yue.noizai.net; native ComfyUI nodes and the Comfy-Org workflow template |
| `examples/generate.py` exists | the README quick start runs "python examples/generate.py --output outputs/first-song" |
| MusicGen sizes and licence | AudioCraft docs: small 300M, medium 1.5B, large 3.3B; 16 GB recommended for medium; model card: code MIT, weights CC-BY-NC 4.0; HF inventory for `facebook/musicgen-small` totals 591,087,174 parameters |
| FLUX and SDXL scale/licence | HF API: FLUX.1-dev 11,901,408,320 parameters, licence "other" (non-commercial per repo), schnell Apache-2.0; SDXL base 2,567,463,684 parameters, OpenRAIL++ |
| Machine | `nvidia-smi`: NVIDIA T600 Laptop GPU, 4096 MiB; `Get-PSDrive`: D: 52.6 GB free, 2026-10-25 |
| YuE2 not installed | no YuE2 weights downloaded; `generative.yue2.generate` remains **blocked** in the capability manifests |
| MusicGen installed and run | Python 3.10 venv with torch 2.11.0+cu128, transformers 5.20.2; `facebook/musicgen-small` cached; `generate.py --seconds 6 --seed 42`: **5.94 s, 32 kHz mono, RMS 0.146, peak 0.427, 35.5 s wall time on CUDA**; metadata sidecar written next to the WAV |
| Silence is treated as failure | the first fp16 attempt produced non-finite samples; the generator detected `peak=NaN`, retried in float32, and refuses to save if silence persists |
| What was **not** tested | no cloud instance rented; the free YuE2 demo was not used; no image model was installed or run; no listening-quality judgement (automated RMS/peak and duration checks only) |
