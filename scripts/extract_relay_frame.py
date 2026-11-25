#!/usr/bin/env python3
"""
Extract a crisp, non-black tail frame from a finished Google Flow video clip (signed URL or local .mp4)
for 'Last-Frame Relay' (feeding as the Start Frame in Flow's `Frames` mode to continue a scene past 15s
at full 1st-generation sharpness without SceneBuilder 3rd-extend blur, or to re-roll only the next 8s beat).
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile


def require_bin(name: str):
    if not shutil.which(name):
        sys.exit(f"Error: required binary '{name}' not found in PATH.")


def probe_dur(path: str) -> float:
    out = subprocess.check_output(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", path,
        ],
        text=True,
    ).strip()
    return float(out)


def frame_yavg(png_path: str) -> float:
    proc = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-nostats", "-i", png_path,
            "-vf", "signalstats,metadata=print:file=-", "-f", "null", "-",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    m = re.search(r"lavfi\.signalstats\.YAVG=([0-9.]+)", proc.stdout + proc.stderr)
    return float(m.group(1)) if m else 128.0


def main():
    ap = argparse.ArgumentParser(description="Extract the sharpest clean tail frame from a video clip for Last-Frame Relay.")
    ap.add_argument("--src", required=True, help="Local .mp4 path or signed https://flow-content.google/video/... URL")
    ap.add_argument("--out", required=True, help="Output PNG path (e.g., .tmp-flow-ingredients/relay-act1.png)")
    ap.add_argument("--window", type=float, default=0.28, help="Tail window in seconds to sample candidates from (default: 0.28)")
    args = ap.parse_args()

    require_bin("ffmpeg")
    require_bin("ffprobe")
    require_bin("curl")

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="flow-relay-") as tmp:
        if args.src.startswith("http://") or args.src.startswith("https://"):
            video_path = os.path.join(tmp, "source.mp4")
            rc = subprocess.call(["curl", "-fsSL", "-o", video_path, args.src])
            if rc != 0:
                sys.exit(f"Error: failed to download source clip (curl exit {rc}).")
        else:
            if not os.path.exists(args.src):
                sys.exit(f"Error: source video not found: {args.src}")
            video_path = args.src

        dur = probe_dur(video_path)
        offsets = [0.05, 0.11, 0.18, min(args.window, 0.26)]
        best_png = None
        best_score = -1.0
        best_ts = 0.0

        for idx, off in enumerate(offsets):
            ts = max(0.0, dur - off)
            cand = os.path.join(tmp, f"cand-{idx}.png")
            subprocess.check_call(
                [
                    "ffmpeg", "-y", "-ss", f"{ts:.3f}", "-i", video_path,
                    "-frames:v", "1", cand,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if not os.path.exists(cand):
                continue
            yavg = frame_yavg(cand)
            # Reject faded-to-black frames (YAVG < 18 in 0..255 luma) unless all candidates are dark
            size_score = float(os.path.getsize(cand))
            brightness_ok = 1.0 if yavg >= 18.0 else 0.15
            # Lossless PNG byte size correlates strongly with high-frequency edge detail (less motion blur = larger PNG)
            score = size_score * brightness_ok
            if score > best_score:
                best_score = score
                best_png = cand
                best_ts = ts

        if not best_png:
            sys.exit("Error: could not extract any tail frame from source clip.")

        shutil.copy2(best_png, args.out)
        print(f"RELAY_FRAME_OK ts={best_ts:.3f}s/{dur:.3f}s out={args.out}")


if __name__ == "__main__":
    main()
