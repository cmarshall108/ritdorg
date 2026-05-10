#!/usr/bin/env python3
"""Transcode videos in static/videos/ to browser-friendly H.264 + AAC MP4.

iPhone-recorded ``.mov`` files are usually HEVC (H.265), which only
Safari can decode. This script re-encodes any non-MP4 (or MP4 that's
still HEVC) into MP4/H.264/AAC with ``+faststart`` so they stream over
HTTP.

Originals are moved to ``static/videos/originals/`` so nothing is lost.

Usage:
    python3 tools/transcode_videos.py            # transcode all eligible
    python3 tools/transcode_videos.py --dry-run  # show what would happen
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

VIDEO_DIR = Path(__file__).resolve().parent.parent / "static" / "videos"
ORIGINALS_DIR = VIDEO_DIR / "originals"
SOURCE_EXTS = {".mov", ".m4v", ".webm", ".mp4"}


def have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def codec_of(path: Path) -> str | None:
    """Return the video codec name (e.g. 'hevc', 'h264') or None."""
    try:
        out = subprocess.check_output(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=codec_name",
                "-of", "default=nw=1:nk=1",
                str(path),
            ],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
        return out or None
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def needs_transcode(path: Path) -> bool:
    if path.suffix.lower() != ".mp4":
        return True
    codec = codec_of(path)
    # Anything other than h264 in an mp4 container won't play widely.
    return codec is not None and codec.lower() != "h264"


def transcode(src: Path, dst: Path) -> bool:
    """Run ffmpeg. Returns True on success."""
    cmd = [
        "ffmpeg", "-y", "-i", str(src),
        "-map", "0:v:0", "-map", "0:a:0?",   # drop QuickTime metadata streams
        "-c:v", "libx264", "-preset", "slow", "-crf", "20",
        "-pix_fmt", "yuv420p",               # max compatibility
        "-c:a", "aac", "-b:a", "160k",
        "-movflags", "+faststart",
        "-f", "mp4",                          # force container; .part has no ext
        str(dst),
    ]
    print(f"  $ {' '.join(cmd)}")
    res = subprocess.run(cmd)
    return res.returncode == 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="Show what would be done, don't change anything.")
    args = ap.parse_args()

    if not have("ffmpeg") or not have("ffprobe"):
        print("ERROR: ffmpeg/ffprobe not found in PATH.", file=sys.stderr)
        print("Install with: brew install ffmpeg", file=sys.stderr)
        return 1

    if not VIDEO_DIR.is_dir():
        print(f"ERROR: {VIDEO_DIR} does not exist.", file=sys.stderr)
        return 1

    candidates = sorted(
        p for p in VIDEO_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in SOURCE_EXTS
    )
    if not candidates:
        print("No videos found.")
        return 0

    print(f"Found {len(candidates)} file(s) in {VIDEO_DIR}:")
    plan = []
    for src in candidates:
        codec = codec_of(src) or "?"
        if needs_transcode(src):
            dst = VIDEO_DIR / (src.stem + ".mp4")
            if dst.exists() and dst != src:
                # Avoid clobbering an existing transcode
                dst = VIDEO_DIR / (src.stem + "_h264.mp4")
            print(f"  TRANSCODE  {src.name}  (codec={codec})  ->  {dst.name}")
            plan.append((src, dst))
        else:
            print(f"  SKIP       {src.name}  (codec={codec})")

    if args.dry_run:
        print("\nDry run; nothing changed.")
        return 0
    if not plan:
        print("\nNothing to do.")
        return 0

    ORIGINALS_DIR.mkdir(exist_ok=True)
    failures: list[str] = []
    for src, dst in plan:
        print(f"\n→ {src.name}")
        # Write to a temp name so a failed run doesn't leave a partial
        # file that looks valid to the static handler.
        tmp = dst.with_suffix(dst.suffix + ".part")
        if not transcode(src, tmp):
            print(f"  FAILED: {src.name}")
            failures.append(src.name)
            try:
                tmp.unlink()
            except FileNotFoundError:
                pass
            continue
        tmp.replace(dst)

        # Move the original out of the served directory so the new mp4
        # is what gets listed on the videos page.
        if src != dst:
            archived = ORIGINALS_DIR / src.name
            if archived.exists():
                archived = ORIGINALS_DIR / f"{src.stem}_{int(src.stat().st_mtime)}{src.suffix}"
            src.rename(archived)
            print(f"  archived original -> {archived.relative_to(VIDEO_DIR.parent.parent)}")

    print()
    if failures:
        print(f"Done with {len(failures)} failure(s): {', '.join(failures)}")
        return 2
    print(f"Done. Transcoded {len(plan)} file(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
