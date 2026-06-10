"""Background video transcoding for the admin Videos panel.

When an upload arrives we want to:

1. Save the file as the user uploaded it.
2. If the container/codec isn't broadly browser-friendly (anything other
   than an MP4 with H.264 video), kick off an ffmpeg transcode in a
   worker thread to produce ``<name>.mp4`` (H.264 + AAC + faststart).
3. Once the transcode finishes, replace the original with the mp4 and
   move the source to ``static/videos/originals/`` for safe-keeping.

ffmpeg is optional — if it isn't installed, we just leave the file as
uploaded and the videos page's HEVC-detection message will tell viewers
to use Safari.

Job status is kept in a process-local dict so the admin Videos page can
show a "Transcoding…" badge for files that are mid-conversion.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import threading
from typing import Optional

logger = logging.getLogger(__name__)

# Status: name -> 'pending' | 'running' | 'done' | 'failed' | 'skipped'
_jobs: dict[str, str] = {}
_jobs_lock = threading.Lock()


def have_ffmpeg() -> bool:
    return bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def video_codec(path: str) -> Optional[str]:
    """Return the first video stream codec name (e.g. 'h264', 'hevc'),
    or None if ffprobe is unavailable / fails."""
    if not shutil.which("ffprobe"):
        return None
    try:
        out = subprocess.check_output(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=codec_name",
                "-of", "default=nw=1:nk=1",
                path,
            ],
            stderr=subprocess.DEVNULL, timeout=15,
        ).decode().strip()
        return out or None
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return None


def needs_transcode(path: str) -> bool:
    """An ``.mp4`` with H.264 video plays everywhere; everything else
    (HEVC mp4, .mov, .m4v, .webm in some browsers) gets converted."""
    ext = os.path.splitext(path)[1].lower()
    if ext != ".mp4":
        return True
    codec = video_codec(path)
    # If we can't tell, err on the side of NOT transcoding — H.264 mp4
    # is by far the most common case and we don't want to needlessly
    # re-encode it just because ffprobe is missing.
    if not codec:
        return False
    return codec.lower() != "h264"


def get_status(name: str) -> Optional[str]:
    with _jobs_lock:
        return _jobs.get(name)


def all_statuses() -> dict[str, str]:
    with _jobs_lock:
        return dict(_jobs)


def _set(name: str, status: str) -> None:
    with _jobs_lock:
        _jobs[name] = status


def _clear(name: str) -> None:
    with _jobs_lock:
        _jobs.pop(name, None)


def maybe_transcode_async(src_path: str, video_dir: str) -> Optional[str]:
    """Kick off a background transcode for ``src_path`` if needed.

    Returns the status the file was placed in: ``'skipped'`` if no
    conversion is required (or ffmpeg is missing), ``'pending'`` if a
    job was queued. The actual conversion runs on a daemon thread so
    the request returns immediately.
    """
    name = os.path.basename(src_path)
    if not needs_transcode(src_path):
        _set(name, "skipped")
        return "skipped"
    if not have_ffmpeg():
        logger.warning(
            "Uploaded %s needs transcoding but ffmpeg isn't installed; "
            "leaving the file as-is.", name,
        )
        _set(name, "skipped")
        return "skipped"

    _set(name, "pending")
    t = threading.Thread(
        target=_run_job, args=(src_path, video_dir, name), daemon=True,
    )
    t.start()
    return "pending"


def _run_job(src_path: str, video_dir: str, name: str) -> None:
    """Worker: ffmpeg -> swap files -> archive original."""
    _set(name, "running")
    stem, _ = os.path.splitext(name)
    # If the source is already an .mp4 that needs transcoding (HEVC),
    # we still need a different output name to avoid clobbering the
    # input mid-encode. Use a temp name and rename at the end.
    tmp_out = os.path.join(video_dir, f"{stem}.h264.mp4.part")
    final_out = os.path.join(video_dir, f"{stem}.mp4")

    cmd = [
        "ffmpeg", "-y", "-nostdin", "-i", src_path,
        "-map", "0:v:0", "-map", "0:a:0?",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k",
        "-movflags", "+faststart",
        "-f", "mp4",
        tmp_out,
    ]
    logger.info("Transcoding %s -> %s", name, os.path.basename(final_out))
    try:
        res = subprocess.run(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            timeout=60 * 60,  # 1 hour cap per file
        )
    except subprocess.TimeoutExpired:
        logger.error("Transcode timed out for %s", name)
        _safe_unlink(tmp_out)
        _set(name, "failed")
        return
    except Exception as e:
        logger.exception("Transcode raised for %s: %s", name, e)
        _safe_unlink(tmp_out)
        _set(name, "failed")
        return

    if res.returncode != 0:
        logger.error(
            "ffmpeg failed for %s (exit=%s): %s",
            name, res.returncode, (res.stderr or b"")[-400:].decode("utf-8", "replace"),
        )
        _safe_unlink(tmp_out)
        _set(name, "failed")
        return

    # Move the source aside so the new mp4 is what gets served.
    originals_dir = os.path.join(video_dir, "originals")
    os.makedirs(originals_dir, exist_ok=True)
    archived = os.path.join(originals_dir, name)
    if os.path.abspath(src_path) != os.path.abspath(final_out):
        # Different filename (e.g. uploaded as .mov): archive the source.
        if os.path.exists(archived):
            archived = os.path.join(
                originals_dir,
                f"{stem}_{int(os.path.getmtime(src_path))}{os.path.splitext(name)[1]}",
            )
        try:
            os.rename(src_path, archived)
        except OSError as e:
            logger.warning("Could not archive %s: %s", name, e)
    else:
        # Source IS the final filename (HEVC mp4 case). Remove it so
        # the rename below succeeds.
        if os.path.exists(archived):
            archived = os.path.join(originals_dir, f"{stem}_orig.mp4")
        try:
            os.rename(src_path, archived)
        except OSError as e:
            logger.warning("Could not archive %s: %s", name, e)
            _safe_unlink(tmp_out)
            _set(name, "failed")
            return

    try:
        os.rename(tmp_out, final_out)
    except OSError as e:
        logger.error("Could not promote %s: %s", tmp_out, e)
        _set(name, "failed")
        return

    logger.info("Transcoded %s -> %s OK", name, os.path.basename(final_out))
    _set(name, "done")
    # Also expose status under the new name so the UI can find it after
    # a refresh that lists the new mp4 instead of the original.
    if os.path.basename(final_out) != name:
        _set(os.path.basename(final_out), "done")


def _safe_unlink(path: str) -> None:
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass
    except OSError as e:
        logger.warning("Could not remove %s: %s", path, e)
