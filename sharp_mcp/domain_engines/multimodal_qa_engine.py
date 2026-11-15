"""Multimodal Video, Audio Soundtest & Vision GUI QA Engine (Gemini + OpenRouter + Local DSP/CV2)."""

from __future__ import annotations

import asyncio
import base64
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any, Dict, List, Optional, Tuple
import wave

import aiohttp
import numpy as np
from PIL import Image, ImageDraw

try:
    import cv2  # type: ignore
except ImportError:  # pragma: no cover - optional fallback for minimal environments
    cv2 = None  # type: ignore

from ..credentials_store import resolve_provider_and_model
from .gui_engine import compute_visual_diff


VIDEO_MIME_TYPES: Dict[str, str] = {
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".webm": "video/webm",
    ".mkv": "video/x-matroska",
    ".avi": "video/x-msvideo",
}

AUDIO_MIME_TYPES: Dict[str, str] = {
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
}

IMAGE_MIME_TYPES: Dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}

FOCUS_RUBRICS: Dict[str, str] = {
    "playtest": (
        "Inspect this Roblox gameplay recording thoroughly. Evaluate: "
        "1) player/NPC spawning & floor grounding (no falling through floor or floating), "
        "2) asset collisions/clipping/glitches between map props, walls, and characters, "
        "3) responsive combat/interaction feedback (hit react, projectiles, prompts), "
        "4) frame stability / freezes / camera jerks, "
        "5) HUD readability during action and any dead-end or soft-lock states."
    ),
    "animation": (
        "Inspect this Roblox animation recording like a technical animator critic. Evaluate: "
        "1) anticipation, follow-through, and overlapping joint motion (non-robotic feel), "
        "2) foot sliding / ice-skating during stance/walk/block, "
        "3) weapon/shield grip alignment with limbs (`RightGripAttachment`/`LeftGripAttachment`), "
        "4) loop seam smoothness (no sudden snap on repeat), "
        "5) readable silhouette & clear timing."
    ),
    "soundtest": (
        "Inspect this Roblox audio / playtest sound recording. Evaluate: "
        "1) SFX clarity, transient punch, and synchronization with visual hits/UI clicks, "
        "2) clipping, harsh distortion, DC thump, or abrupt non-zero-crossing loop clicks, "
        "3) leading/trailing dead air harming responsiveness, "
        "4) balance between UI/SFX/BGM and genre mood cohesion."
    ),
    "gui_flow": (
        "Inspect this Roblox UI/UX recording or screenshot like an anti-slop senior game UI artist. Evaluate: "
        "1) typography hierarchy, legibility, stroke contrast, and spacing, "
        "2) touch target sizes (>=44px), safe zone / Roblox topbar clearance, and mobile ergonomics, "
        "3) anti-slop visual craft (layered gradients, borders, custom 2D icons/frames vs dull flat boxes), "
        "4) click feedback micro-animations (press tween, ripple/burst VFX) and layout clipping/overlap."
    ),
}


def find_ffmpeg_executable() -> Optional[str]:
    """Locate `ffmpeg` binary on PATH or standard WinGet link directory."""
    hit = shutil.which("ffmpeg")
    if hit:
        return hit
    if os.name == "nt":
        local_app = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
        cand = local_app / "Microsoft/WinGet/Links/ffmpeg.exe"
        if cand.is_file():
            return str(cand)
    return None


def _extract_json_block(text: str) -> Optional[Dict[str, Any]]:
    raw = (text or "").strip()
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(raw[start : end + 1])
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    return None


def _analyze_pcm_wav(wav_path: Path) -> Dict[str, Any]:
    """Run deterministic numpy DSP telemetry on a PCM WAV file."""
    with wave.open(str(wav_path), "rb") as wf:
        channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()
        nframes = wf.getnframes()
        raw = wf.readframes(nframes)

    if framerate <= 0 or nframes <= 0:
        return {
            "ok": False,
            "error": "Empty or corrupt WAV audio stream.",
            "duration_sec": 0.0,
        }

    if sampwidth == 1:
        arr = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif sampwidth == 2:
        arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif sampwidth == 4:
        arr = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"Unsupported WAV sample width: {sampwidth} bytes")

    if channels > 1:
        arr_2d = arr.reshape(-1, channels)
        mono = np.mean(arr_2d, axis=1)
    else:
        mono = arr

    duration_sec = round(float(len(mono)) / float(framerate), 4)
    abs_mono = np.abs(mono)
    peak = float(np.max(abs_mono)) if len(mono) else 0.0
    rms = float(np.sqrt(np.mean(np.square(mono)))) if len(mono) else 0.0
    dc_offset = float(np.mean(mono)) if len(mono) else 0.0

    peak_dbfs = round(20.0 * math.log10(max(peak, 1e-9)), 2)
    rms_dbfs = round(20.0 * math.log10(max(rms, 1e-9)), 2)
    crest_factor_db = round(peak_dbfs - rms_dbfs, 2) if rms > 1e-9 else 0.0

    clipping_samples = int(np.sum(abs_mono >= 0.995))
    silence_thresh = 0.005  # ~ -46 dBFS
    non_silent_idx = np.where(abs_mono >= silence_thresh)[0]
    silence_ratio = round(float(np.mean(abs_mono < silence_thresh)), 4)

    if len(non_silent_idx) > 0:
        leading_silence_ms = round(float(non_silent_idx[0]) * 1000.0 / float(framerate), 1)
        trailing_silence_ms = round(float(len(mono) - 1 - non_silent_idx[-1]) * 1000.0 / float(framerate), 1)
    else:
        leading_silence_ms = round(duration_sec * 1000.0, 1)
        trailing_silence_ms = round(duration_sec * 1000.0, 1)

    # Zero crossing rate & spectral centroid (bounded FFT window up to 65536 samples)
    win = mono[: min(len(mono), 65536)]
    if len(win) > 8:
        signs = np.signbit(win)
        zcr = float(np.mean(signs[1:] != signs[:-1]))
        spec = np.abs(np.fft.rfft(win * np.hanning(len(win))))
        freqs = np.fft.rfftfreq(len(win), d=1.0 / float(framerate))
        spec_sum = float(np.sum(spec))
        centroid_hz = round(float(np.sum(freqs * spec) / spec_sum), 1) if spec_sum > 1e-9 else 0.0
    else:
        zcr = 0.0
        centroid_hz = 0.0

    # Loop seam click heuristic: compare start/end 8 samples magnitude jump
    seam_jump = round(float(abs(float(mono[-1]) - float(mono[0]))), 4) if len(mono) >= 2 else 0.0

    findings: List[Dict[str, Any]] = []
    if rms_dbfs < -60.0 or silence_ratio >= 0.98:
        findings.append({
            "id": "AUDIO-SILENT-001",
            "severity": "BLOCKER",
            "message": f"Audio track is near-silent (rms={rms_dbfs} dBFS, silence_ratio={silence_ratio}).",
            "fix": "Ensure audio source is audible (-18 to -6 dBFS RMS) and connected to AudioDeviceOutput.",
        })
    if clipping_samples > max(4, int(0.0005 * len(mono))):
        findings.append({
            "id": "AUDIO-CLIP-001",
            "severity": "CRITICAL",
            "message": f"Detected {clipping_samples} clipped samples (>= -0.04 dBFS), risking digital harsh distortion.",
            "fix": "Insert AudioCompressor/Limiter before AudioDeviceOutput and trim gain by 2-3 dB.",
        })
    if abs(dc_offset) > 0.05:
        findings.append({
            "id": "AUDIO-DC-001",
            "severity": "MAJOR",
            "message": f"High DC offset ({dc_offset:.4f}) can cause audible pops when starting/stopping SFX.",
            "fix": "Apply high-pass filter (~30 Hz) or normalize DC offset to 0.",
        })
    if leading_silence_ms > 120.0 and len(non_silent_idx) > 0:
        findings.append({
            "id": "AUDIO-LAG-001",
            "severity": "MAJOR",
            "message": f"Leading silence of {leading_silence_ms} ms causes sluggish UI/hit responsiveness.",
            "fix": "Trim leading dead air to <= 20 ms for UI clicks and combat impacts.",
        })
    if seam_jump > 0.25:
        findings.append({
            "id": "AUDIO-SEAM-001",
            "severity": "MINOR",
            "message": f"Start/end waveform discontinuity ({seam_jump}) may click on seamless loops.",
            "fix": "Fade edges over 5-15 ms or slice at zero crossings.",
        })

    return {
        "ok": True,
        "duration_sec": duration_sec,
        "sample_rate": int(framerate),
        "channels": int(channels),
        "sample_width_bytes": int(sampwidth),
        "peak_dbfs": peak_dbfs,
        "rms_dbfs": rms_dbfs,
        "crest_factor_db": crest_factor_db,
        "dc_offset": round(dc_offset, 5),
        "clipping_samples": clipping_samples,
        "silence_ratio": silence_ratio,
        "leading_silence_ms": leading_silence_ms,
        "trailing_silence_ms": trailing_silence_ms,
        "zero_crossing_rate": round(zcr, 4),
        "spectral_centroid_hz": centroid_hz,
        "loop_seam_jump": seam_jump,
        "findings": findings,
        "telemetry_passed": not any(f["severity"] in ("BLOCKER", "CRITICAL") for f in findings),
    }


def _extract_video_telemetry_via_ffmpeg(
    video_path: Path,
    *,
    max_frames: int = 12,
    contact_sheet_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Fallback video frame sampler using ffmpeg CLI + Pillow when OpenCV (`cv2`) is unavailable."""
    ffmpeg = find_ffmpeg_executable()
    if not ffmpeg:
        return {
            "ok": False,
            "error": "Neither OpenCV (`cv2`) nor `ffmpeg` is available to decode video frames.",
        }
    with tempfile.TemporaryDirectory(prefix="sharp_vid_") as tmp_d:
        out_pat = Path(tmp_d) / "frame_%03d.png"
        cmd = [
            ffmpeg,
            "-y",
            "-i",
            str(video_path),
            "-vf",
            "fps=2,scale=640:-2",
            "-frames:v",
            str(max(1, max_frames)),
            str(out_pat),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        frame_files = sorted(Path(tmp_d).glob("frame_*.png"))
        if not frame_files:
            return {
                "ok": False,
                "error": f"ffmpeg decoded 0 frames from {video_path}: {proc.stderr[-300:]}",
            }
        sampled_frames: List[Tuple[int, float, np.ndarray]] = []
        for idx, fp in enumerate(frame_files):
            with Image.open(fp) as im:
                rgb = np.asarray(im.convert("RGB"))
            sampled_frames.append((idx, round(float(idx) * 0.5, 2), rgb))

    h0, w0 = sampled_frames[0][2].shape[:2]
    lumas: List[float] = []
    black_count = 0
    deltas: List[float] = []
    frozen_pairs = 0
    prev_small: Optional[np.ndarray] = None
    for _, _, rgb in sampled_frames:
        gray = 0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2]
        mean_luma = float(np.mean(gray))
        lumas.append(mean_luma)
        if mean_luma < 8.0:
            black_count += 1
        small = np.asarray(
            Image.fromarray(gray.astype(np.uint8)).resize((160, 90), Image.Resampling.BILINEAR),
            dtype=np.float32,
        )
        if prev_small is not None:
            mad = float(np.mean(np.abs(small - prev_small)))
            deltas.append(mad)
            if mad < 0.35:
                frozen_pairs += 1
        prev_small = small

    black_ratio = round(float(black_count) / float(len(sampled_frames)), 4)
    frozen_ratio = round(float(frozen_pairs) / float(max(1, len(deltas))), 4) if deltas else 0.0
    mean_motion = round(float(np.mean(deltas)), 3) if deltas else 0.0
    findings: List[Dict[str, Any]] = []
    if black_ratio >= 0.6:
        findings.append({
            "id": "VIDEO-BLACK-001",
            "severity": "CRITICAL",
            "message": f"{int(black_ratio * 100)}% of sampled frames are near-black.",
            "fix": "Ensure Viewport/Recording started after scene camera & lighting initialized.",
        })
    if len(deltas) >= 2 and frozen_ratio >= 0.85:
        findings.append({
            "id": "VIDEO-FROZEN-001",
            "severity": "MAJOR",
            "message": f"Video shows minimal motion ({frozen_pairs}/{len(deltas)} static intervals, mean_delta={mean_motion}).",
            "fix": "Verify animation playback/playtest bot movement actually triggers during the capture window.",
        })
    sheet_out: Optional[str] = None
    if contact_sheet_path is not None:
        contact_sheet_path.parent.mkdir(parents=True, exist_ok=True)
        n = len(sampled_frames)
        cols = min(4, max(1, int(math.ceil(math.sqrt(n)))))
        rows = int(math.ceil(float(n) / float(cols)))
        tile_w, tile_h = 384, 216
        sheet = Image.new("RGB", (cols * tile_w, rows * tile_h), (14, 16, 22))
        draw = ImageDraw.Draw(sheet)
        for i, (f_idx, sec, rgb) in enumerate(sampled_frames):
            tile = Image.fromarray(rgb).resize((tile_w - 8, tile_h - 24), Image.Resampling.LANCZOS)
            r_idx = i // cols
            c_idx = i % cols
            x0 = c_idx * tile_w + 4
            y0 = r_idx * tile_h + 20
            sheet.paste(tile, (x0, y0))
            draw.text((x0 + 4, r_idx * tile_h + 3), f"f={f_idx} t={sec:.2f}s", fill=(235, 240, 250))
        sheet.save(str(contact_sheet_path), format="PNG")
        sheet_out = str(contact_sheet_path)

    return {
        "ok": True,
        "video_path": str(video_path),
        "width": int(w0),
        "height": int(h0),
        "fps": 2.0,
        "total_frames": len(sampled_frames),
        "duration_sec": round(float(len(sampled_frames)) * 0.5, 3),
        "sampled_frame_count": len(sampled_frames),
        "mean_luma": round(float(np.mean(lumas)), 2),
        "black_frame_ratio": black_ratio,
        "frozen_interval_ratio": frozen_ratio,
        "mean_motion_delta": mean_motion,
        "contact_sheet_path": sheet_out,
        "findings": findings,
        "decoder": "ffmpeg_fallback",
    }


def _extract_video_telemetry_and_contact_sheet(
    video_path: Path,
    *,
    max_frames: int = 12,
    contact_sheet_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Sample frames via OpenCV (or ffmpeg fallback), measure motion/frozen/black frames, and save a contact sheet."""
    if cv2 is None:
        return _extract_video_telemetry_via_ffmpeg(
            video_path,
            max_frames=max_frames,
            contact_sheet_path=contact_sheet_path,
        )
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return {"ok": False, "error": f"Could not open video file: {video_path}"}

    try:
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
        if fps <= 0.0:
            fps = 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)

        sampled_frames: List[Tuple[int, float, np.ndarray]] = []
        if total_frames > 0:
            step = max(1, total_frames // max(1, max_frames))
            indices = list(range(0, total_frames, step))[:max_frames]
            if total_frames - 1 not in indices and len(indices) < max_frames:
                indices.append(total_frames - 1)
            for idx in indices:
                cap.set(cv2.CAP_PROP_POS_FRAMES, float(idx))
                ret, frame = cap.read()
                if ret and frame is not None:
                    sampled_frames.append((idx, round(float(idx) / fps, 2), frame))
        else:
            idx = 0
            while len(sampled_frames) < max_frames:
                ret, frame = cap.read()
                if not ret or frame is None:
                    break
                sampled_frames.append((idx, round(float(idx) / fps, 2), frame))
                idx += 1
            total_frames = max(total_frames, idx)
    finally:
        cap.release()

    if not sampled_frames:
        return {"ok": False, "error": f"Video decoded 0 frames: {video_path}"}

    duration_sec = round(float(total_frames) / fps, 3) if total_frames > 0 else round(sampled_frames[-1][1], 3)

    # Frame telemetry: luminance, black frames, frozen runs, inter-sample motion delta
    lumas: List[float] = []
    black_count = 0
    deltas: List[float] = []
    frozen_pairs = 0
    prev_small: Optional[np.ndarray] = None

    for _, _, bgr in sampled_frames:
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        mean_luma = float(np.mean(gray))
        lumas.append(mean_luma)
        if mean_luma < 8.0:
            black_count += 1
        small = cv2.resize(gray, (160, 90), interpolation=cv2.INTER_AREA).astype(np.float32)
        if prev_small is not None:
            mad = float(np.mean(np.abs(small - prev_small)))
            deltas.append(mad)
            if mad < 0.35:
                frozen_pairs += 1
        prev_small = small

    black_ratio = round(float(black_count) / float(len(sampled_frames)), 4)
    frozen_ratio = round(float(frozen_pairs) / float(max(1, len(deltas))), 4) if deltas else 0.0
    mean_motion = round(float(np.mean(deltas)), 3) if deltas else 0.0

    findings: List[Dict[str, Any]] = []
    if black_ratio >= 0.6:
        findings.append({
            "id": "VIDEO-BLACK-001",
            "severity": "CRITICAL",
            "message": f"{int(black_ratio * 100)}% of sampled frames are near-black.",
            "fix": "Ensure Viewport/Recording started after scene camera & lighting initialized.",
        })
    if len(deltas) >= 2 and frozen_ratio >= 0.85:
        findings.append({
            "id": "VIDEO-FROZEN-001",
            "severity": "MAJOR",
            "message": f"Video shows minimal motion ({frozen_pairs}/{len(deltas)} static intervals, mean_delta={mean_motion}).",
            "fix": "Verify animation playback/playtest bot movement actually triggers during the capture window.",
        })

    sheet_out: Optional[str] = None
    if contact_sheet_path is not None:
        contact_sheet_path.parent.mkdir(parents=True, exist_ok=True)
        n = len(sampled_frames)
        cols = min(4, max(1, int(math.ceil(math.sqrt(n)))))
        rows = int(math.ceil(float(n) / float(cols)))
        tile_w, tile_h = 384, 216
        sheet = Image.new("RGB", (cols * tile_w, rows * tile_h), (14, 16, 22))
        draw = ImageDraw.Draw(sheet)
        for i, (f_idx, sec, bgr) in enumerate(sampled_frames):
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            tile = Image.fromarray(rgb).resize((tile_w - 8, tile_h - 24), Image.Resampling.LANCZOS)
            r_idx = i // cols
            c_idx = i % cols
            x0 = c_idx * tile_w + 4
            y0 = r_idx * tile_h + 20
            sheet.paste(tile, (x0, y0))
            draw.text((x0 + 4, r_idx * tile_h + 3), f"f={f_idx} t={sec:.2f}s", fill=(235, 240, 250))
        sheet.save(str(contact_sheet_path), format="PNG")
        sheet_out = str(contact_sheet_path)

    return {
        "ok": True,
        "video_path": str(video_path),
        "width": width or int(sampled_frames[0][2].shape[1]),
        "height": height or int(sampled_frames[0][2].shape[0]),
        "fps": round(fps, 3),
        "total_frames": total_frames,
        "duration_sec": duration_sec,
        "sampled_frame_count": len(sampled_frames),
        "mean_luma": round(float(np.mean(lumas)), 2),
        "black_frame_ratio": black_ratio,
        "frozen_interval_ratio": frozen_ratio,
        "mean_motion_delta": mean_motion,
        "contact_sheet_path": sheet_out,
        "findings": findings,
    }


def _analyze_image_telemetry(image_path: Path, before_image_path: Optional[Path] = None) -> Dict[str, Any]:
    """Compute local image sharpness, color diversity, highlight clip, and optional pixel diff."""
    with Image.open(image_path) as im:
        rgb = im.convert("RGB")
        w, h = rgb.size
        arr = np.asarray(rgb, dtype=np.float32)

    gray = 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]
    if cv2 is not None:
        hsv = cv2.cvtColor(arr.astype(np.uint8), cv2.COLOR_RGB2HSV)
        sat_mean = round(float(np.mean(hsv[:, :, 1])) / 255.0, 4)
    else:
        cmax = np.max(arr, axis=2)
        cmin = np.min(arr, axis=2)
        sat_arr = np.where(cmax > 1e-3, (cmax - cmin) / np.maximum(cmax, 1e-3), 0.0)
        sat_mean = round(float(np.mean(sat_arr)), 4)
    luma_mean = round(float(np.mean(gray)) / 255.0, 4)
    luma_std = round(float(np.std(gray)) / 255.0, 4)

    # Edge density via Sobel magnitude
    gx = np.abs(np.diff(gray, axis=1))
    gy = np.abs(np.diff(gray, axis=0))
    edge_density = round(
        (float(np.mean(gx > 18.0)) + float(np.mean(gy > 18.0))) * 0.5,
        4,
    )
    blank_like = luma_std < 0.015 and edge_density < 0.005

    findings: List[Dict[str, Any]] = []
    if blank_like:
        findings.append({
            "id": "VIS-BLANK-001",
            "severity": "BLOCKER",
            "message": f"Screenshot appears nearly blank/uniform (luma_std={luma_std}, edge_density={edge_density}).",
            "fix": "Ensure ScreenGui.Enabled=true and UI elements rendered visibly before screenshot capture.",
        })
    if sat_mean < 0.05 and luma_mean < 0.22:
        findings.append({
            "id": "VIS-FLAT-001",
            "severity": "MAJOR",
            "message": f"Image is very dark and desaturated (luma={luma_mean}, sat={sat_mean}); check for flat dark slop.",
            "fix": "Apply game palette accents, UIGradient sheen, and bright legible stroke/text hierarchy.",
        })

    diff_res: Optional[Dict[str, Any]] = None
    if before_image_path is not None and before_image_path.is_file():
        diff_res = compute_visual_diff(str(before_image_path), str(image_path))

    return {
        "ok": True,
        "image_path": str(image_path),
        "width": w,
        "height": h,
        "aspect_ratio": round(float(w) / float(max(1, h)), 3),
        "luma_mean": luma_mean,
        "luma_std": luma_std,
        "saturation_mean": sat_mean,
        "edge_density": edge_density,
        "blank_like": blank_like,
        "findings": findings,
        "visual_diff": diff_res,
    }


class MultimodalQAEngine:
    """Video playtest/animation/soundtest & Gemini/OpenRouter Vision GUI quality auditor."""

    def __init__(self, *, credentials_path: Optional[str | Path] = None) -> None:
        self.credentials_path = credentials_path
        self.ffmpeg_path = find_ffmpeg_executable()

    async def _call_gemini_generate(
        self,
        *,
        api_key: str,
        model: str,
        parts: List[Dict[str, Any]],
        timeout_sec: float = 90.0,
    ) -> Dict[str, Any]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        payload = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
            },
        }
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        }
        timeout = aiohttp.ClientTimeout(total=timeout_sec)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                body_text = await resp.text()
                if resp.status >= 400:
                    return {
                        "ok": False,
                        "status": resp.status,
                        "error": f"Gemini HTTP {resp.status}: {body_text[:400]}",
                    }
                data = json.loads(body_text)
        candidates = data.get("candidates") or []
        text_parts: List[str] = []
        if candidates:
            content = candidates[0].get("content") or {}
            for p in content.get("parts") or []:
                if "text" in p:
                    text_parts.append(str(p["text"]))
        raw_text = "\n".join(text_parts).strip()
        return {
            "ok": True,
            "provider": "gemini",
            "model": model,
            "raw_text": raw_text,
            "parsed_json": _extract_json_block(raw_text),
            "usage": data.get("usageMetadata") or {},
        }

    async def _upload_and_analyze_gemini_file(
        self,
        *,
        api_key: str,
        model: str,
        file_path: Path,
        mime_type: str,
        prompt_text: str,
        timeout_sec: float = 120.0,
    ) -> Dict[str, Any]:
        """Upload media to Gemini Files API if >10MB, analyze, and delete remote file cleanly."""
        size_bytes = file_path.stat().st_size
        if size_bytes <= 10 * 1024 * 1024:
            b64 = await asyncio.to_thread(lambda: base64.b64encode(file_path.read_bytes()).decode("ascii"))
            return await self._call_gemini_generate(
                api_key=api_key,
                model=model,
                parts=[
                    {"inlineData": {"mimeType": mime_type, "data": b64}},
                    {"text": prompt_text},
                ],
                timeout_sec=timeout_sec,
            )

        timeout = aiohttp.ClientTimeout(total=timeout_sec)
        file_name_remote: Optional[str] = None
        file_uri: Optional[str] = None
        async with aiohttp.ClientSession(timeout=timeout) as session:
            init_headers = {
                "x-goog-api-key": api_key,
                "X-Goog-Upload-Protocol": "resumable",
                "X-Goog-Upload-Command": "start",
                "X-Goog-Upload-Header-Content-Length": str(size_bytes),
                "X-Goog-Upload-Header-Content-Type": mime_type,
                "Content-Type": "application/json",
            }
            async with session.post(
                "https://generativelanguage.googleapis.com/upload/v1beta/files",
                json={"file": {"display_name": file_path.name}},
                headers=init_headers,
            ) as init_resp:
                if init_resp.status >= 400:
                    return {"ok": False, "error": f"Gemini file upload init failed: HTTP {init_resp.status}"}
                upload_url = init_resp.headers.get("x-goog-upload-url") or init_resp.headers.get("X-Goog-Upload-URL")
            if not upload_url:
                return {"ok": False, "error": "Gemini file upload missing X-Goog-Upload-URL header."}

            raw_bytes = await asyncio.to_thread(file_path.read_bytes)
            up_headers = {
                "Content-Length": str(size_bytes),
                "X-Goog-Upload-Offset": "0",
                "X-Goog-Upload-Command": "upload, finalize",
            }
            async with session.post(upload_url, data=raw_bytes, headers=up_headers) as up_resp:
                up_body = await up_resp.text()
                if up_resp.status >= 400:
                    return {"ok": False, "error": f"Gemini file upload finalize failed: HTTP {up_resp.status}: {up_body[:300]}"}
                meta = json.loads(up_body).get("file") or {}
                file_name_remote = meta.get("name")
                file_uri = meta.get("uri")

            # Wait briefly if video still PROCESSING
            for _ in range(20):
                if not file_name_remote:
                    break
                async with session.get(
                    f"https://generativelanguage.googleapis.com/v1beta/{file_name_remote}",
                    headers={"x-goog-api-key": api_key},
                ) as st_resp:
                    if st_resp.status == 200:
                        st_json = await st_resp.json()
                        state = (st_json.get("state") or "").upper()
                        if state in ("ACTIVE", ""):
                            file_uri = st_json.get("uri") or file_uri
                            break
                        if state == "FAILED":
                            return {"ok": False, "error": "Gemini media processing returned state=FAILED."}
                await asyncio.sleep(1.5)

        try:
            if not file_uri:
                return {"ok": False, "error": "Gemini upload completed without file URI."}
            return await self._call_gemini_generate(
                api_key=api_key,
                model=model,
                parts=[
                    {"fileData": {"mimeType": mime_type, "fileUri": file_uri}},
                    {"text": prompt_text},
                ],
                timeout_sec=timeout_sec,
            )
        finally:
            if file_name_remote:
                try:
                    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15.0)) as del_sess:
                        await del_sess.delete(
                            f"https://generativelanguage.googleapis.com/v1beta/{file_name_remote}",
                            headers={"x-goog-api-key": api_key},
                        )
                except Exception:
                    pass

    async def _call_openrouter_vision(
        self,
        *,
        api_key: str,
        model: str,
        image_paths: List[Path],
        prompt_text: str,
        timeout_sec: float = 90.0,
    ) -> Dict[str, Any]:
        content_items: List[Dict[str, Any]] = [{"type": "text", "text": prompt_text}]
        for img_p in image_paths:
            ext = img_p.suffix.lower()
            mime = IMAGE_MIME_TYPES.get(ext, "image/png")
            b64 = await asyncio.to_thread(lambda p=img_p: base64.b64encode(p.read_bytes()).decode("ascii"))
            content_items.append({
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{b64}"},
            })

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/sharp-mcp",
            "X-Title": "Sharp MCP Quality Audit",
        }
        payload = {
            "model": model,
            "temperature": 0.2,
            "messages": [{"role": "user", "content": content_items}],
        }
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout_sec)) as session:
            async with session.post("https://openrouter.ai/api/v1/chat/completions", json=payload, headers=headers) as resp:
                body_text = await resp.text()
                if resp.status >= 400:
                    return {"ok": False, "status": resp.status, "error": f"OpenRouter HTTP {resp.status}: {body_text[:400]}"}
                data = json.loads(body_text)
        choices = data.get("choices") or []
        raw_text = ""
        if choices:
            msg = choices[0].get("message") or {}
            c = msg.get("content")
            if isinstance(c, str):
                raw_text = c
            elif isinstance(c, list):
                raw_text = "\n".join(str(x.get("text", "")) for x in c if isinstance(x, dict))
        return {
            "ok": True,
            "provider": "openrouter",
            "model": model,
            "raw_text": raw_text.strip(),
            "parsed_json": _extract_json_block(raw_text),
            "usage": data.get("usage") or {},
        }

    def _convert_media_to_wav_sync(self, media_path: Path, out_wav: Path) -> bool:
        if media_path.suffix.lower() == ".wav":
            shutil.copy2(media_path, out_wav)
            return True
        if not self.ffmpeg_path:
            return False
        proc = subprocess.run(
            [
                self.ffmpeg_path,
                "-y",
                "-i",
                str(media_path),
                "-vn",
                "-acodec",
                "pcm_s16le",
                "-ar",
                "22050",
                str(out_wav),
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        return proc.returncode == 0 and out_wav.is_file() and out_wav.stat().st_size > 44

    async def inspect_video(
        self,
        *,
        video_path: str,
        focus: str = "playtest",
        custom_prompt: str = "",
        max_frames: int = 12,
        include_audio_dsp: bool = True,
        output_dir: Optional[str | Path] = None,
        provider: str = "auto",
        model: Optional[str] = None,
        tier: str = "default",
        design_system: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Inspect a gameplay, animation, or UI video using CV2/ffmpeg telemetry + Gemini/OpenRouter."""
        src = Path(video_path).expanduser().resolve()
        if not src.is_file():
            return {"ok": False, "error": f"Video file not found: {src}"}

        norm_focus = (focus or "playtest").strip().lower()
        rubric = FOCUS_RUBRICS.get(norm_focus, FOCUS_RUBRICS["playtest"])
        sheet_dir = Path(output_dir).expanduser().resolve() if output_dir else src.parent
        sheet_path = sheet_dir / f"{src.stem}_qa_contact_sheet.png"

        telemetry = await asyncio.to_thread(
            _extract_video_telemetry_and_contact_sheet,
            src,
            max_frames=max(4, min(24, int(max_frames))),
            contact_sheet_path=sheet_path,
        )
        if not telemetry.get("ok"):
            return telemetry

        audio_telemetry: Optional[Dict[str, Any]] = None
        if include_audio_dsp and (src.suffix.lower() == ".wav" or self.ffmpeg_path):
            with tempfile.TemporaryDirectory() as tmp:
                wav_tmp = Path(tmp) / "extracted.wav"
                has_audio = await asyncio.to_thread(self._convert_media_to_wav_sync, src, wav_tmp)
                if has_audio:
                    audio_telemetry = await asyncio.to_thread(_analyze_pcm_wav, wav_tmp)

        ds_hint = ""
        if isinstance(design_system, dict):
            ds_hint = (
                f"Game design context: title='{design_system.get('game_title')}', "
                f"genre='{design_system.get('genre')}', "
                f"signature='{design_system.get('style_signature', {}).get('label', '')}', "
                f"primary='{design_system.get('palette', {}).get('primary')}'. "
            )

        prompt_text = (
            "You are a ruthless Roblox Studio QA & Game Art Critic. Return strict JSON ONLY with keys: "
            "verdict ('SHIP'|'FIX_FIRST'|'REJECT'), score (0-100), summary (string), "
            "findings ([{id, severity, timestamp_hint, message, fix}]), passed_checks ([string]).\n"
            f"Focus mode: {norm_focus}. {rubric}\n"
            f"{ds_hint}"
            + (f"Extra user prompt: {custom_prompt}\n" if custom_prompt else "")
        )

        route = resolve_provider_and_model(
            role="video",
            preferred_provider=provider,
            model_override=model,
            tier=tier,
            credentials_path=self.credentials_path,
        )
        ai_report: Optional[Dict[str, Any]] = None
        if route["key_configured"] and route["api_key"]:
            if route["provider"] == "gemini":
                mime = VIDEO_MIME_TYPES.get(src.suffix.lower(), "video/mp4")
                ai_report = await self._upload_and_analyze_gemini_file(
                    api_key=route["api_key"],
                    model=route["model"],
                    file_path=src,
                    mime_type=mime,
                    prompt_text=prompt_text,
                )
            else:
                ai_report = await self._call_openrouter_vision(
                    api_key=route["api_key"],
                    model=route["model"],
                    image_paths=[sheet_path],
                    prompt_text=(
                        prompt_text
                        + "\nNote: Reviewing extracted timestamped contact sheet keyframes from the video."
                    ),
                )

        combined_findings = list(telemetry.get("findings") or [])
        if isinstance(audio_telemetry, dict):
            combined_findings.extend(audio_telemetry.get("findings") or [])

        return {
            "ok": True,
            "mode": "inspect_video",
            "focus": norm_focus,
            "video_telemetry": telemetry,
            "audio_telemetry": audio_telemetry,
            "contact_sheet_path": str(sheet_path),
            "findings": combined_findings,
            "ai_routing": {
                "provider": route["provider"],
                "planned_provider": route["planned_provider"],
                "model": route["model"],
                "key_configured": route["key_configured"],
            },
            "ai_analysis": ai_report,
            "analysis_mode": "multimodal_ai_plus_telemetry" if (ai_report and ai_report.get("ok")) else "local_telemetry_plus_contact_sheet",
        }

    async def inspect_audio(
        self,
        *,
        audio_path: str,
        mode: str = "soundtest",
        custom_prompt: str = "",
        provider: str = "auto",
        model: Optional[str] = None,
        tier: str = "default",
        design_system: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Analyze Roblox SFX/BGM/soundtest files with numpy DSP metrics + optional Gemini native audio."""
        src = Path(audio_path).expanduser().resolve()
        if not src.is_file():
            return {"ok": False, "error": f"Audio file not found: {src}"}

        with tempfile.TemporaryDirectory() as tmp:
            wav_tmp = Path(tmp) / "audio.wav"
            ok_conv = await asyncio.to_thread(self._convert_media_to_wav_sync, src, wav_tmp)
            if not ok_conv:
                return {
                    "ok": False,
                    "error": (
                        f"Cannot decode audio '{src.suffix}': supply a .wav file or ensure ffmpeg is on PATH."
                    ),
                }
            dsp = await asyncio.to_thread(_analyze_pcm_wav, wav_tmp)

        ds_hint = ""
        if isinstance(design_system, dict):
            ds_hint = f"Target game genre='{design_system.get('genre')}', mood='{design_system.get('mood')}'. "

        prompt_text = (
            "You are a Roblox sound designer & QA critic. Return strict JSON ONLY with keys: "
            "verdict ('SHIP'|'FIX_FIRST'|'REJECT'), score (0-100), summary (string), "
            "findings ([{id, severity, timestamp_hint, message, fix}]), loudness_fit (string).\n"
            f"Soundtest mode: {mode}. {FOCUS_RUBRICS['soundtest']} {ds_hint}"
            f"Measured DSP telemetry: peak={dsp.get('peak_dbfs')} dBFS, rms={dsp.get('rms_dbfs')} dBFS, "
            f"crest={dsp.get('crest_factor_db')} dB, clipping_samples={dsp.get('clipping_samples')}, "
            f"leading_silence_ms={dsp.get('leading_silence_ms')}, centroid_hz={dsp.get('spectral_centroid_hz')}.\n"
            + (f"Extra user prompt: {custom_prompt}\n" if custom_prompt else "")
        )

        route = resolve_provider_and_model(
            role="audio",
            preferred_provider="gemini" if provider == "auto" else provider,
            model_override=model,
            tier=tier,
            credentials_path=self.credentials_path,
        )
        ai_report: Optional[Dict[str, Any]] = None
        if route["key_configured"] and route["api_key"] and route["provider"] == "gemini":
            mime = AUDIO_MIME_TYPES.get(src.suffix.lower(), "audio/wav")
            ai_report = await self._upload_and_analyze_gemini_file(
                api_key=route["api_key"],
                model=route["model"],
                file_path=src,
                mime_type=mime,
                prompt_text=prompt_text,
            )

        return {
            "ok": True,
            "mode": "inspect_audio",
            "soundtest_mode": mode,
            "audio_path": str(src),
            "dsp_telemetry": dsp,
            "findings": list(dsp.get("findings") or []),
            "ai_routing": {
                "provider": route["provider"],
                "planned_provider": route["planned_provider"],
                "model": route["model"],
                "key_configured": route["key_configured"],
            },
            "ai_analysis": ai_report,
            "analysis_mode": "gemini_audio_plus_dsp" if (ai_report and ai_report.get("ok")) else "local_dsp_telemetry",
        }

    async def inspect_gui_vision(
        self,
        *,
        image_path: str,
        before_image_path: Optional[str] = None,
        screen_name: str = "HUD",
        custom_prompt: str = "",
        provider: str = "auto",
        model: Optional[str] = None,
        tier: str = "default",
        design_system: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Run Anti-Slop GUI quality check combining pixel/diff telemetry + Gemini/OpenRouter Vision."""
        src = Path(image_path).expanduser().resolve()
        if not src.is_file():
            return {"ok": False, "error": f"Image file not found: {src}"}
        before_p = Path(before_image_path).expanduser().resolve() if before_image_path else None

        telemetry = await asyncio.to_thread(_analyze_image_telemetry, src, before_p)
        ds_hint = ""
        if isinstance(design_system, dict):
            pal = design_system.get("palette") or {}
            ds_hint = (
                f"Expected bespoke palette: primary={pal.get('primary')}, secondary={pal.get('secondary')}, "
                f"accent={pal.get('accent')}, surface={pal.get('surface')}, genre='{design_system.get('genre')}'. "
            )

        prompt_text = (
            "You are a ruthless Roblox anti-slop UI director. Inspect the screenshot(s) carefully.\n"
            "Return strict JSON ONLY with keys: verdict ('SHIP'|'FIX_FIRST'|'REJECT'), score (0-100), "
            "slop_risk ('low'|'medium'|'high'), summary (string), "
            "findings ([{id, severity, element, message, patch_hint}]), praise ([string]).\n"
            f"Target screen: {screen_name}. {FOCUS_RUBRICS['gui_flow']} {ds_hint}"
            "Reject generic flat dark-blue SaaS boxes, tiny unpadded buttons (<44px), clipped edges, "
            "overlapping HUD widgets, missing visual hierarchy, and low-contrast labels.\n"
            + (f"Extra user prompt: {custom_prompt}\n" if custom_prompt else "")
        )

        route = resolve_provider_and_model(
            role="vision",
            preferred_provider=provider,
            model_override=model,
            tier=tier,
            credentials_path=self.credentials_path,
        )
        ai_report: Optional[Dict[str, Any]] = None
        if route["key_configured"] and route["api_key"]:
            img_paths = [before_p, src] if (before_p and before_p.is_file()) else [src]
            if route["provider"] == "gemini":
                parts: List[Dict[str, Any]] = []
                for p in img_paths:
                    mime = IMAGE_MIME_TYPES.get(p.suffix.lower(), "image/png")
                    b64 = await asyncio.to_thread(lambda fp=p: base64.b64encode(fp.read_bytes()).decode("ascii"))
                    parts.append({"inlineData": {"mimeType": mime, "data": b64}})
                parts.append({"text": prompt_text})
                ai_report = await self._call_gemini_generate(
                    api_key=route["api_key"],
                    model=route["model"],
                    parts=parts,
                )
            else:
                ai_report = await self._call_openrouter_vision(
                    api_key=route["api_key"],
                    model=route["model"],
                    image_paths=img_paths,
                    prompt_text=prompt_text,
                )

        return {
            "ok": True,
            "mode": "inspect_gui_vision",
            "screen_name": screen_name,
            "image_telemetry": telemetry,
            "findings": list(telemetry.get("findings") or []),
            "ai_routing": {
                "provider": route["provider"],
                "planned_provider": route["planned_provider"],
                "model": route["model"],
                "key_configured": route["key_configured"],
            },
            "ai_analysis": ai_report,
            "analysis_mode": "vision_ai_plus_telemetry" if (ai_report and ai_report.get("ok")) else "local_image_telemetry",
        }
