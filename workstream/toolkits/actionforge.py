#!/usr/bin/env python3
"""ActionForge toolkit plugin: fetch CC0 humanoid animation assets.

ActionForge (https://actionforge.app/) is a browser-based Mixamo alternative. Its animation
library is CC0 (no attribution required) and is fetched here as binary glTF files; the
ActionForge application code is (c) CGstuff and is not downloaded or redistributed.

This plugin is registered by workstream/toolkit.py (docs/ADR-015-actionforge-toolkit.md).
It does not shell out, does not write outside the target project, validates the GLB header
before writing, writes atomically and records SHA-256 provenance.

Fetched layout under --dest (default assets/actionforge):

    rig/rig-human.glb
    animations/<clip_id>.glb
    provenance.json
    NOTICE.md

The curated catalog below is a convenience list of known clip ids. fetch also accepts any
other known id that matches the safe id pattern, because the library grows independently.
Clip-loop hints are derived from the names and are not verified by playback.

Usage:
    python workstream/gypsy.py toolkit actionforge catalog [--json]
    python workstream/gypsy.py toolkit actionforge fetch --project DIR \
        --clips idle_loop,walk_loop --rig [--dest assets/actionforge] [--force] [--json]
"""
from __future__ import annotations

import json
import re
import struct
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import toolkit as toolkit_core

TOOLKIT_ID = "actionforge"
NAME = "ActionForge"
SUMMARY = "Fetch the CC0 ActionForge humanoid rig and animation GLBs with SHA-256 provenance."
LICENSE = (
    "Animation library CC0 (no attribution required); ActionForge app code (c) CGstuff"
)
STATUS = "partial"
KIND = "asset-library"
CAPABILITY = "toolkit.actionforge"
HOME = "https://actionforge.app/"
DOCS = "docs/ADR-015-actionforge-toolkit.md"

RIG_URL = "https://actionforge.app/assets/animation-library/rig/rig-human.glb"
ANIMATION_BASE = "https://actionforge.app/assets/animation-library/animations/"
DEFAULT_DEST = "assets/actionforge"
USER_AGENT = "Gypsy-Studio-Toolkit/1.0 (local CLI; +https://actionforge.app/)"
PROVENANCE_SCHEMA = "gypsy.actionforge-provenance/v1"
MAX_BYTES = 64 * 1024 * 1024
CLIP_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")

LICENSE_INFO = {
    "animations": "CC0",
    "attributionRequired": False,
    "appCode": "(c) CGstuff",
    "source": HOME,
    "note": (
        "Animation library is CC0. ActionForge application code is (c) CGstuff and is not "
        "downloaded or redistributed by Gypsy Studio. Provenance is recorded even though "
        "CC0 does not require attribution."
    ),
}

# Curated known clip ids. Keys are the upstream ids; the order groups related clips.
CLIPS = {
    "idle_loop": {"category": "idle", "loop": True, "description": "Idle loop"},
    "sword_idle": {"category": "idle", "loop": True, "description": "Sword idle"},
    "walk_loop": {"category": "locomotion", "loop": True, "description": "Walk cycle"},
    "jog_fwd_loop": {"category": "locomotion", "loop": True, "description": "Forward jog cycle"},
    "sprint_loop": {"category": "locomotion", "loop": True, "description": "Sprint cycle"},
    "slide_loop": {"category": "locomotion", "loop": True, "description": "Slide cycle"},
    "jump_loop": {"category": "locomotion", "loop": True, "description": "Jump loop"},
    "jump_start": {"category": "locomotion", "loop": False, "description": "Jump start"},
    "jump_land": {"category": "locomotion", "loop": False, "description": "Jump landing"},
    "sword_attack": {"category": "combat.sword", "loop": False, "description": "Sword attack"},
    "sword_regular_a": {"category": "combat.sword", "loop": False, "description": "Sword regular A"},
    "sword_regular_b": {"category": "combat.sword", "loop": False, "description": "Sword regular B"},
    "sword_regular_combo": {
        "category": "combat.sword",
        "loop": False,
        "description": "Sword regular combo",
    },
    "punch_jab": {"category": "combat.unarmed", "loop": False, "description": "Punch jab"},
    "melee_hook": {"category": "combat.unarmed", "loop": False, "description": "Melee hook"},
    "overhandthrow": {"category": "combat.unarmed", "loop": False, "description": "Overhand throw"},
    "hit_chest": {"category": "reaction", "loop": False, "description": "Hit reaction, chest"},
    "hit_head": {"category": "reaction", "loop": False, "description": "Hit reaction, head"},
    "hit_knockback": {"category": "reaction", "loop": False, "description": "Hit knockback"},
    "death01": {"category": "reaction", "loop": False, "description": "Death 01"},
}


def clip_url(clip_id: str) -> str:
    return ANIMATION_BASE + urllib.parse.quote(clip_id, safe="") + ".glb"


def _check_clip_id(clip_id) -> str:
    if not isinstance(clip_id, str):
        raise toolkit_core.ToolkitError("clip id must be a string")
    if not CLIP_ID_RE.match(clip_id):
        raise toolkit_core.ToolkitError(
            f"invalid clip id {clip_id!r}: use lowercase letters, digits and '_' "
            "(starting with a letter), 1-64 characters"
        )
    return clip_id


def clip_info(clip_id) -> dict:
    """Return catalog metadata for a curated or arbitrary known clip id."""
    clip_id = _check_clip_id(clip_id)
    item = CLIPS.get(clip_id)
    if item:
        return {
            "id": clip_id,
            "url": clip_url(clip_id),
            "category": item["category"],
            "loop": item["loop"],
            "description": item["description"],
            "curated": True,
        }
    return {
        "id": clip_id,
        "url": clip_url(clip_id),
        "category": "custom",
        "loop": None,
        "description": "not in the curated catalog; fetched by known clip id",
        "curated": False,
    }


def catalog() -> list:
    """The curated catalog, in grouping order."""
    return [clip_info(clip_id) for clip_id in CLIPS]


def parse_clips(clips) -> list:
    """Normalise a comma string or iterable into unique, validated clip ids."""
    if clips is None:
        return []
    pieces = [clips] if isinstance(clips, str) else list(clips)
    result = []
    for piece in pieces:
        if piece is None:
            continue
        for part in str(piece).split(","):
            candidate = part.strip()
            if not candidate:
                continue
            _check_clip_id(candidate)
            if candidate not in result:
                result.append(candidate)
    return result


def validate_glb(data: bytes) -> None:
    """Raise ToolkitError unless *data* is a complete binary glTF v2 payload."""
    if len(data) < 12:
        raise toolkit_core.ToolkitError("not a binary glTF: 12-byte header is missing")
    magic, version, length = struct.unpack("<4sII", data[:12])
    if magic != b"glTF":
        raise toolkit_core.ToolkitError("not a binary glTF: wrong magic")
    if version != 2:
        raise toolkit_core.ToolkitError(f"unsupported glTF version {version}; expected 2")
    if length != len(data):
        raise toolkit_core.ToolkitError(
            f"truncated or padded GLB: header declares {length} bytes, received {len(data)}"
        )


def _status_of(response):
    status = getattr(response, "status", None)
    if status is None:
        try:
            status = response.getcode()
        except Exception:
            status = None
    return status


def _close(response) -> None:
    close = getattr(response, "close", None)
    if callable(close):
        try:
            close()
        except Exception:
            pass


def _download(url: str, timeout: float = 30.0) -> bytes:
    """Fetch one URL with urllib (no shell). Caller validates the payload."""
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "model/gltf-binary,application/octet-stream;q=0.9,*/*;q=0.5",
        },
    )
    response = urllib.request.urlopen(request, timeout=timeout)
    try:
        status = _status_of(response)
        if status is not None and int(status) != 200:
            raise toolkit_core.ToolkitError(f"HTTP status {status}")
        chunks = []
        total = 0
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_BYTES:
                raise toolkit_core.ToolkitError(
                    f"download exceeds the {MAX_BYTES // (1024 * 1024)} MiB safety limit"
                )
            chunks.append(chunk)
    finally:
        _close(response)
    return b"".join(chunks)


def probe(opener=None, timeout: float = 10.0) -> dict:
    """Check the rig URL honestly; an unreachable network is reported, never hidden."""
    opener = opener or urllib.request.urlopen
    checked_at = toolkit_core.utc_now_iso()
    notes = ["Checks the rig URL with HEAD; the full clip catalog is not probed."]
    method = "HEAD"
    headers = {"User-Agent": USER_AGENT, "Accept": "model/gltf-binary,*/*;q=0.5"}
    try:
        try:
            status = _probe_status(opener, method, headers, timeout)
        except urllib.error.HTTPError as exc:
            if exc.code not in (405, 501):
                raise
            method = "GET"
            headers = dict(headers)
            headers["Range"] = "bytes=0-11"
            notes.append("HEAD was not allowed; the check retried with a ranged GET.")
            status = _probe_status(opener, method, headers, timeout)
    except Exception as exc:
        return {
            "toolkit": TOOLKIT_ID,
            "url": RIG_URL,
            "reachable": False,
            "status": getattr(exc, "code", None),
            "method": method,
            "checkedAt": checked_at,
            "error": f"{type(exc).__name__}: {exc}",
            "notes": notes,
        }
    reachable = status is None or 200 <= int(status) < 400
    return {
        "toolkit": TOOLKIT_ID,
        "url": RIG_URL,
        "reachable": reachable,
        "status": status,
        "method": method,
        "checkedAt": checked_at,
        "error": None if reachable else f"HTTP status {status}",
        "notes": notes,
    }


def _probe_status(opener, method, headers, timeout):
    request = urllib.request.Request(RIG_URL, method=method, headers=headers)
    response = opener(request, timeout=timeout)
    try:
        return _status_of(response)
    finally:
        _close(response)


def _sha256_file(path: Path) -> str:
    return toolkit_core.sha256_file(path)


def _project_rel(dest, relative) -> str:
    dest_path = Path(dest)
    combined = Path(relative) if dest_path == Path(".") else dest_path / relative
    return combined.as_posix()


def _provenance_entries(existing) -> dict:
    entries = {}
    if isinstance(existing, dict):
        files = existing.get("files")
        if isinstance(files, list):
            for entry in files:
                if isinstance(entry, dict) and isinstance(entry.get("path"), str):
                    entries[entry["path"]] = entry
    return entries


def _load_provenance(path: Path, warnings: list) -> dict:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        warnings.append(f"existing provenance is unreadable and will be rebuilt: {exc}")
        return {}
    if not isinstance(data, dict):
        warnings.append("existing provenance is not a JSON object and will be rebuilt")
        return {}
    return data


def _write_if_changed(path: Path, text: str) -> bool:
    if path.is_file():
        try:
            if path.read_text(encoding="utf-8") == text:
                return False
        except (OSError, UnicodeDecodeError):
            pass
    toolkit_core.atomic_write_text(path, text)
    return True


def _notice_text(entries) -> str:
    lines = [
        "# ActionForge assets - NOTICE",
        "",
        "This directory was populated by Gypsy Studio's ActionForge toolkit",
        "(`python workstream/gypsy.py toolkit actionforge fetch ...`) from",
        "<https://actionforge.app/>.",
        "",
        "## Licence",
        "",
        "- Animation library: **CC0** - no attribution required. Provenance is recorded anyway.",
        "- ActionForge application code: **(c) CGstuff**. Gypsy Studio does not download or",
        "  redistribute the application.",
        "- Gypsy Studio is not affiliated with ActionForge.",
        "",
        "## Files",
        "",
        "| Path | Kind | Clip | SHA-256 | Bytes |",
        "| --- | --- | --- | --- | --- |",
    ]
    for entry in entries:
        lines.append(
            "| {path} | {kind} | {clip} | `{sha}` | {bytes} |".format(
                path=entry.get("path", "?"),
                kind=entry.get("kind", "?"),
                clip=entry.get("clip") or "-",
                sha=entry.get("sha256") or "-",
                bytes=entry.get("bytes", "-"),
            )
        )
    lines.extend(
        [
            "",
            "`provenance.json` records the source URL, SHA-256 and retrieval time of each file.",
            "",
        ]
    )
    return "\n".join(lines)


def _write_target(root: Path, dest_path: Path, relative: Path, data: bytes) -> Path:
    target = dest_path / relative
    parent = target.parent
    parent.mkdir(parents=True, exist_ok=True)
    if not parent.resolve().is_relative_to(root):
        raise toolkit_core.ToolkitError(
            f"destination resolves outside the project root: {relative.as_posix()}"
        )
    toolkit_core.atomic_write_bytes(target, data)
    return target


def fetch(
    project,
    clips=None,
    rig: bool = False,
    dest=DEFAULT_DEST,
    force: bool = False,
    downloader=None,
    timeout: float = 30.0,
) -> dict:
    """Fetch selected ActionForge assets into *project* and record provenance.

    `downloader` is injectable for tests: it is called as downloader(url, timeout=...)
    and must return bytes. The default uses urllib, never a shell. Existing files with a
    different hash are not overwritten unless force=True; identical files count as
    unchanged, so a rerun is idempotent.
    """
    root = Path(project).expanduser().resolve()
    if not root.is_dir():
        raise toolkit_core.ToolkitError(f"project directory does not exist: {root}")
    dest_path = toolkit_core.resolve_within(root, dest, label="--dest")
    try:
        dest_path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise toolkit_core.ToolkitError(f"cannot create destination {dest_path}: {exc}") from exc
    if not dest_path.is_dir():
        raise toolkit_core.ToolkitError(f"destination is not a directory: {dest_path}")

    clip_ids = parse_clips(clips)
    if not clip_ids and not rig:
        raise toolkit_core.ToolkitError("select at least one clip with --clips or pass --rig")

    targets = []
    if rig:
        targets.append(
            {
                "kind": "rig",
                "clip": None,
                "url": RIG_URL,
                "relative": Path("rig") / "rig-human.glb",
            }
        )
    for clip_id in clip_ids:
        info = clip_info(clip_id)
        targets.append(
            {
                "kind": "clip",
                "clip": clip_id,
                "url": info["url"],
                "catalogued": info["curated"],
                "relative": Path("animations") / (clip_id + ".glb"),
            }
        )

    warnings = []
    for target in targets:
        if target["kind"] == "clip" and not target["catalogued"]:
            warnings.append(
                f"{target['clip']}: not in the curated catalog; treated as a known clip id"
            )
    download = downloader or _download
    dest_display = Path(dest).as_posix()
    files = []
    errors = []

    for target in targets:
        project_path = _project_rel(dest, target["relative"])
        absolute = dest_path / target["relative"]
        entry = {
            "kind": target["kind"],
            "path": project_path,
            "url": target["url"],
            "status": None,
        }
        if target["clip"] is not None:
            entry["clip"] = target["clip"]
            entry["catalogued"] = target["catalogued"]

        existing_hash = None
        if absolute.exists():
            if not absolute.is_file():
                message = f"{project_path}: exists and is not a regular file"
                errors.append(message)
                entry.update({"status": "error", "error": message})
                files.append(entry)
                continue
            existing_hash = _sha256_file(absolute)

        try:
            data = download(target["url"], timeout=timeout)
            validate_glb(data)
            digest = toolkit_core.sha256_hex(data)
        except Exception as exc:
            message = f"{project_path}: {type(exc).__name__}: {exc}"
            errors.append(message)
            entry.update({"status": "error", "error": message})
            files.append(entry)
            continue

        entry.update({"sha256": digest, "bytes": len(data)})
        if absolute.exists():
            if existing_hash == digest:
                entry["status"] = "unchanged"
            elif force:
                try:
                    _write_target(root, dest_path, target["relative"], data)
                except Exception as exc:
                    message = f"{project_path}: {type(exc).__name__}: {exc}"
                    errors.append(message)
                    entry.update({"status": "error", "error": message})
                    files.append(entry)
                    continue
                entry["status"] = "overwritten"
            else:
                message = (
                    f"{project_path}: refusing to overwrite a differing file "
                    "(pass --force to replace it)"
                )
                errors.append(message)
                entry.update({"status": "conflict", "error": message})
                files.append(entry)
                continue
        else:
            try:
                _write_target(root, dest_path, target["relative"], data)
            except Exception as exc:
                message = f"{project_path}: {type(exc).__name__}: {exc}"
                errors.append(message)
                entry.update({"status": "error", "error": message})
                files.append(entry)
                continue
            entry["status"] = "written"
        files.append(entry)

    provenance_path = dest_path / "provenance.json"
    notice_path = dest_path / "NOTICE.md"
    existing_doc = _load_provenance(provenance_path, warnings)
    entries = _provenance_entries(existing_doc)
    now = toolkit_core.utc_now_iso()
    changed = False
    for result in files:
        if result["status"] in ("written", "overwritten"):
            entries[result["path"]] = {
                "kind": result["kind"],
                **({"clip": result["clip"]} if "clip" in result else {}),
                "path": result["path"],
                "url": result["url"],
                "sha256": result["sha256"],
                "bytes": result["bytes"],
                **({"catalogued": result["catalogued"]} if "catalogued" in result else {}),
                "retrievedAt": now,
            }
            changed = True
        elif result["status"] == "unchanged":
            old = _provenance_entries(existing_doc).get(result["path"])
            if (
                isinstance(old, dict)
                and old.get("sha256") == result["sha256"]
                and old.get("url") == result["url"]
            ):
                entries[result["path"]] = old
            else:
                entries[result["path"]] = {
                    "kind": result["kind"],
                    **({"clip": result["clip"]} if "clip" in result else {}),
                    "path": result["path"],
                    "url": result["url"],
                    "sha256": result["sha256"],
                    "bytes": result["bytes"],
                    **({"catalogued": result["catalogued"]} if "catalogued" in result else {}),
                    "retrievedAt": now,
                }
                changed = True

    ordered = [entries[key] for key in sorted(entries)]
    provenance_written = None
    notice_written = None
    if ordered:
        retrieved_at = now if changed or not existing_doc.get("retrievedAt") else existing_doc["retrievedAt"]
        document = {
            "schema": PROVENANCE_SCHEMA,
            "toolkit": TOOLKIT_ID,
            "source": HOME,
            "dest": dest_display,
            "license": LICENSE_INFO,
            "retrievedAt": retrieved_at,
            "files": ordered,
        }
        payload = json.dumps(document, indent=2, ensure_ascii=False) + "\n"
        if _write_if_changed(provenance_path, payload):
            provenance_written = _project_rel(dest, "provenance.json")
        if _write_if_changed(notice_path, _notice_text(ordered)):
            notice_written = _project_rel(dest, "NOTICE.md")

    return {
        "toolkit": TOOLKIT_ID,
        "passed": not errors,
        "project": str(root),
        "dest": dest_display,
        "files": files,
        "errors": errors,
        "warnings": warnings,
        "provenance": _project_rel(dest, "provenance.json") if ordered else None,
        "notice": _project_rel(dest, "NOTICE.md") if ordered else None,
        "provenanceChanged": bool(provenance_written),
        "noticeChanged": bool(notice_written),
    }


def describe() -> dict:
    """Details and catalog for `gypsy toolkit show actionforge`."""
    return {
        "id": TOOLKIT_ID,
        "name": NAME,
        "summary": SUMMARY,
        "license": LICENSE,
        "status": STATUS,
        "kind": KIND,
        "capability": CAPABILITY,
        "home": HOME,
        "docs": DOCS,
        "source": {"rig": RIG_URL, "animations": ANIMATION_BASE},
        "defaultDest": DEFAULT_DEST,
        "layout": {
            "rig": "rig/rig-human.glb",
            "clips": "animations/<clip_id>.glb",
            "provenance": "provenance.json",
            "notice": "NOTICE.md",
        },
        "catalogCount": len(CLIPS),
        "catalog": catalog(),
        "customClipIds": (
            "Any other known clip id matching ^[a-z][a-z0-9_]{0,63}$ is accepted by fetch; "
            "it is marked catalogued=false in provenance."
        ),
        "notes": [
            "Animation authoring, retargeting and engine import remain manual; this toolkit only fetches the library.",
            "Loop hints are derived from the clip names and are not verified by playback.",
            "probe and fetch need network access; list/show/capabilities/catalog work offline.",
        ],
    }


def _configure_catalog(parser) -> None:
    return None


def _run_catalog(args):
    return 0, {
        "toolkit": TOOLKIT_ID,
        "rig": RIG_URL,
        "source": ANIMATION_BASE,
        "count": len(CLIPS),
        "clips": catalog(),
        "customClipIds": describe()["customClipIds"],
    }


def _render_catalog(payload) -> str:
    lines = [
        f"ActionForge catalog: {payload['count']} curated clips",
        f"rig: {payload['rig']}",
        f"animations: {payload['source']}<clip_id>.glb",
        "",
    ]
    for clip in payload["clips"]:
        loop = "loop" if clip.get("loop") else ("-" if clip.get("loop") is None else "one-shot")
        lines.append(
            f"  {clip['id']:24} {clip['category']:16} {loop:9} {clip['description']}"
        )
    lines.extend(["", payload["customClipIds"]])
    return "\n".join(lines)


def _configure_fetch(parser) -> None:
    parser.add_argument("--project", required=True, help="target project root")
    parser.add_argument("--clips", default="", help="comma-separated clip ids")
    parser.add_argument("--rig", action="store_true", help="fetch rig-human.glb")
    parser.add_argument("--dest", default=DEFAULT_DEST, help="project-relative destination")
    parser.add_argument("--force", action="store_true", help="overwrite differing files")
    parser.add_argument("--timeout", type=float, default=30.0, help="per-request seconds")


def _run_fetch(args):
    result = fetch(
        args.project,
        clips=args.clips,
        rig=args.rig,
        dest=args.dest,
        force=args.force,
        timeout=args.timeout,
    )
    return 0 if result["passed"] else 1, result


def _render_fetch(result) -> str:
    lines = [
        f"actionforge fetch: {'PASS' if result['passed'] else 'FAIL'}",
        f"project: {result['project']}",
        f"dest: {result['dest']}",
    ]
    for entry in result["files"]:
        status = entry["status"].upper()
        detail = entry.get("error") or (
            f"{entry.get('bytes', '?')} bytes sha256 {entry.get('sha256', '?')}"
        )
        lines.append(f"  {status:10} {entry['path']}  {detail}")
    if result.get("provenance"):
        lines.append(f"provenance: {result['provenance']}")
    if result.get("notice"):
        lines.append(f"notice: {result['notice']}")
    else:
        lines.append("provenance/notice: not written (no fetched or recorded files)")
    for warning in result.get("warnings", []):
        lines.append(f"WARN {warning}")
    for error in result.get("errors", []):
        lines.append(f"ERROR {error}")
    return "\n".join(lines)


COMMANDS = {
    "catalog": {
        "summary": "list the curated ActionForge clip catalog (offline)",
        "configure": _configure_catalog,
        "run": _run_catalog,
        "render": _render_catalog,
    },
    "fetch": {
        "summary": "fetch selected CC0 rig/animation GLBs and write provenance",
        "configure": _configure_fetch,
        "run": _run_fetch,
        "render": _render_fetch,
    },
}
