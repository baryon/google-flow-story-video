#!/usr/bin/env python3
"""
Build a low-cost Storyboard Animatic MP4 BEFORE spending Google Flow video credits on long-form (5-10 min) projects:
- Combines `timeline.json` + `<slug>-audio-master.wav` + `.srt` tracks (from `build_audio_and_srt.py`)
- Uses per-scene keyframe images (`<frames-dir>/<scene_id>.png|.jpg`) or shared Ingredient images,
  automatically generating clean dark slate cards for any scene without an image yet
- Applies subtle push-in motion, mixes the full voiceover + ambient audio master, muxes multi-language soft subtitles,
  and outputs `<slug>-animatic.mp4` in seconds so pacing and framing can be approved at zero video-credit cost.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys


def require_bin(name: str):
    if not shutil.which(name):
        sys.exit(f"Error: required binary '{name}' not found in PATH.")


def find_scene_image(sc: dict, frames_dir: str, ingredients_dir: str) -> str | None:
    sid = sc["id"]
    if frames_dir and os.path.isdir(frames_dir):
        for ext in (".png", ".jpg", ".jpeg", ".webp"):
            p = os.path.join(frames_dir, f"{sid}{ext}")
            if os.path.exists(p):
                return p
    if ingredients_dir and os.path.isdir(ingredients_dir):
        ings = sc.get("ingredients", [])
        if ings:
            p = os.path.join(ingredients_dir, ings[0])
            if os.path.exists(p):
                return p
        mode = sc.get("flow_mode", "")
        if "(" in mode and ")" in mode:
            first_ing = mode.split("(", 1)[1].split(")", 1)[0].split(",")[0].strip()
            p = os.path.join(ingredients_dir, first_ing)
            if os.path.exists(p):
                return p
    return None


def main():
    ap = argparse.ArgumentParser(description="Build a zero-credit Storyboard Animatic MP4 for pre-Flow pacing review.")
    ap.add_argument("--timeline", required=True, help="Path to episode timeline.json")
    ap.add_argument("--audio", required=True, help="Path to episode audio-master.wav")
    ap.add_argument("--endslate", default="", help="Optional path to endslate PNG")
    ap.add_argument("--frames-dir", default="", help="Optional directory with per-scene <id>.png/.jpg keyframes")
    ap.add_argument("--ingredients-dir", default="", help="Optional directory with shared Ingredient images")
    ap.add_argument("--srt-dir", default="", help="Optional directory containing <slug>.<lang>.srt")
    ap.add_argument("--out", required=True, help="Output animatic MP4 path")
    ap.add_argument("--size", default="720x1280", help="Animatic preview resolution WxH (default: 720x1280)")
    ap.add_argument("--fps", type=int, default=24, help="Animatic frame rate (default: 24)")
    args = ap.parse_args()

    require_bin("ffmpeg")
    require_bin("ffprobe")

    width, height = [int(v) for v in args.size.lower().split("x")]
    with open(args.timeline, encoding="utf-8") as f:
        tl = json.load(f)
    slug = tl["slug"]

    work_dir = os.path.join(os.path.dirname(os.path.abspath(args.out)), f".animatic-{slug}")
    os.makedirs(work_dir, exist_ok=True)

    seg_paths = []
    for idx, sc in enumerate(tl["scenes"]):
        sid = sc["id"]
        dur = max(0.5, round(sc["end"] - sc["start"], 3))
        seg_mp4 = os.path.join(work_dir, f"anim-{idx:02d}-{sid}.mp4")

        img = args.endslate if (sc.get("voStart") is None and args.endslate and os.path.exists(args.endslate)) else find_scene_image(sc, args.frames_dir, args.ingredients_dir)

        if img:
            # Gentle 5% push-in across scene duration
            overscale_w = int(round(width * 1.06 / 2) * 2)
            overscale_h = int(round(height * 1.06 / 2) * 2)
            vf = (
                f"scale={overscale_w}:{overscale_h}:force_original_aspect_ratio=increase,"
                f"crop={width}:{height}:x='(iw-{width})/2':y='(ih-{height})/2 - (ih-{height})*0.35*(t/{dur:.3f})',"
                f"setsar=1,fade=t=in:st=0:d=0.20,fade=t=out:st={max(0.1, dur - 0.20):.3f}:d=0.20,format=yuv420p"
            )
            subprocess.check_call(
                [
                    "ffmpeg", "-y", "-loop", "1", "-t", f"{dur:.3f}", "-i", img,
                    "-r", str(args.fps), "-vf", vf,
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-an", seg_mp4,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            palette = ["#0b2230", "#13293d", "#1b263b", "#0f2027", "#1a2a3a"]
            bg = "#06131c" if sc.get("voStart") is None else palette[idx % len(palette)]
            vf = f"fade=t=in:st=0:d=0.20,fade=t=out:st={max(0.1, dur - 0.20):.3f}:d=0.20,format=yuv420p"
            subprocess.check_call(
                [
                    "ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c={bg}:s={width}x{height}:d={dur:.3f}:r={args.fps}",
                    "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p", "-an", seg_mp4,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        seg_paths.append(seg_mp4)

    concat_txt = os.path.join(work_dir, "concat.txt")
    with open(concat_txt, "w", encoding="utf-8") as f:
        for p in seg_paths:
            f.write(f"file '{os.path.abspath(p)}'\n")

    raw_anim = os.path.join(work_dir, "base-animatic.mp4")
    subprocess.check_call(
        [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_txt, "-i", args.audio,
            "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest", raw_anim,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    srt_specs = [
        ("eng", "English", os.path.join(args.srt_dir, f"{slug}.en.srt")) if args.srt_dir else ("", "", ""),
        ("jpn", "日本語", os.path.join(args.srt_dir, f"{slug}.ja.srt")) if args.srt_dir else ("", "", ""),
        ("zho", "简体中文", os.path.join(args.srt_dir, f"{slug}.zh-Hans.srt")) if args.srt_dir else ("", "", ""),
    ]
    present_srts = [(c, t, p) for c, t, p in srt_specs if p and os.path.exists(p)]

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    if present_srts:
        cmd = ["ffmpeg", "-y", "-i", raw_anim]
        for _, _, p in present_srts:
            cmd += ["-i", p]
        cmd += ["-map", "0:v", "-map", "0:a"]
        for i in range(len(present_srts)):
            cmd += ["-map", f"{i + 1}:s"]
        cmd += ["-c:v", "copy", "-c:a", "copy", "-c:s", "mov_text"]
        for i, (c, t, _) in enumerate(present_srts):
            cmd += [f"-metadata:s:s:{i}", f"language={c}", f"-metadata:s:s:{i}", f"title={t}"]
        cmd += ["-disposition:s:0", "default", "-movflags", "+faststart", args.out]
        subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        shutil.move(raw_anim, args.out)

    shutil.rmtree(work_dir, ignore_errors=True)
    print(f"ANIMATIC_OK {slug} -> {args.out}")


if __name__ == "__main__":
    main()
