#!/usr/bin/env python3
"""
Assemble a finished Mode VO Google Flow episode master with incremental per-shot hot-rebuild cache:
- Tracks signed URL clip identity (`raw/<id>.url`) so re-rolling a single broken shot automatically re-downloads ONLY that shot
- Caches per-shot encoded segments (`seg-<id>.mp4` + `.sig`) so unchanged shots are skipped in 0ms on rebuilds
- Losslessly stream-copies (`-c:v copy`) uniform segments into the master (seconds even for 10-minute 80-shot films!)
- Asserts audio/video sync (< 0.35s), muxes multi-language soft subtitles, and renders a 5x3 15-frame QA contact sheet
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys


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


def probe_stream_dur(path: str, stream_sel: str) -> float:
    out = subprocess.check_output(
        [
            "ffprobe", "-v", "error", "-select_streams", stream_sel,
            "-show_entries", "stream=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", path,
        ],
        text=True,
    ).strip().splitlines()
    for line in out:
        if line and line != "N/A":
            return float(line)
    return probe_dur(path)


def file_sig(path: str) -> str:
    st = os.stat(path)
    return f"{os.path.abspath(path)}:{st.st_size}:{st.st_mtime_ns}"


def compute_sig(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


def resolve_clip_source(src: str, sid: str, raw_dir: str, force: bool) -> str:
    if src.startswith("http://") or src.startswith("https://"):
        local_raw = os.path.join(raw_dir, f"{sid}.mp4")
        url_tag_file = os.path.join(raw_dir, f"{sid}.url")
        canonical_url = src.split("?", 1)[0]
        prev_url = open(url_tag_file, encoding="utf-8").read().strip() if os.path.exists(url_tag_file) else ""
        needs_download = (
            force
            or not os.path.exists(local_raw)
            or os.path.getsize(local_raw) < 100_000
            or (prev_url and prev_url != canonical_url)
        )
        if needs_download:
            rc = subprocess.call(["curl", "-fsSL", "-o", local_raw, src])
            if rc != 0:
                sys.exit(
                    f"Error: failed to download scene '{sid}' from Flow CDN (curl exit {rc}). "
                    f"Signed URLs expire after ~6 hours—re-read video.currentSrc in the Flow project."
                )
            with open(url_tag_file, "w", encoding="utf-8") as uf:
                uf.write(canonical_url + "\n")
        elif not prev_url:
            with open(url_tag_file, "w", encoding="utf-8") as uf:
                uf.write(canonical_url + "\n")
        return local_raw

    if not os.path.exists(src):
        sys.exit(f"Error: local video file for '{sid}' not found: {src}")
    return src


def ensure_bottom_gradient(path: str, width: int, height: int):
    if os.path.exists(path):
        return
    y_start = int(round(height * 0.708))
    span = max(1, height - y_start)
    subprocess.check_call(
        [
            "ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=black:s={width}x{height}:d=1",
            "-vf", f"format=rgba,geq=r=0:g=0:b=0:a='if(lt(Y,{y_start}),0, min(165, 165*pow((Y-{y_start})/{span}, 1.5)))'",
            "-frames:v", "1", path,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def render_contact_sheet(video_path: str, out_png: str, total_dur: float, width: int, height: int):
    usable = max(1.0, total_dur * 0.96)
    fps_val = 15.8 / usable
    thumb_w = 270 if height >= width else 384
    thumb_h = int(round(thumb_w * height / width / 2) * 2)
    vf = f"fps={fps_val:.6f},scale={thumb_w}:{thumb_h},tile=5x3:padding=4:margin=4:color=0x10161d"
    subprocess.check_call(
        [
            "ffmpeg", "-y", "-ss", f"{total_dur * 0.02:.2f}", "-i", video_path,
            "-vf", vf, "-frames:v", "1", out_png,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def main():
    ap = argparse.ArgumentParser(description="Assemble a finished Mode VO Google Flow episode master.")
    ap.add_argument("--timeline", required=True, help="Path to episode timeline.json")
    ap.add_argument("--audio", required=True, help="Path to episode audio-master.wav")
    ap.add_argument("--endslate", required=True, help="Path to endslate PNG")
    ap.add_argument("--mapping", required=True, help="JSON map { 's01': 'https://... or /path.mp4', ... }")
    ap.add_argument("--srt-dir", required=True, help="Directory containing <slug>.<lang>.srt files")
    ap.add_argument("--out-dir", required=True, help="Output directory for raw clips, masters, and QA frames")
    ap.add_argument("--size", default="1080x1920", help="Target output resolution WxH (default: 1080x1920)")
    ap.add_argument("--fps", type=int, default=30, help="Target frame rate (default: 30)")
    ap.add_argument("--force", action="store_true", help="Ignore segment cache and re-encode all shots")
    args = ap.parse_args()

    require_bin("ffmpeg")
    require_bin("ffprobe")
    require_bin("curl")

    width, height = [int(v) for v in args.size.lower().split("x")]

    with open(args.timeline, encoding="utf-8") as f:
        tl = json.load(f)
    slug = tl["slug"]
    with open(args.mapping, encoding="utf-8") as f:
        mapping = json.load(f)

    scenes = tl["scenes"]
    missing = [sc["id"] for sc in scenes if sc.get("voStart") is not None and sc["id"] not in mapping]
    if missing:
        sys.exit(f"Error: mapping.json is missing scene IDs: {', '.join(missing)}")

    raw_dir = os.path.join(args.out_dir, "raw")
    os.makedirs(raw_dir, exist_ok=True)

    grad_png = os.path.join(args.out_dir, f"bottom-grad-{width}x{height}.png")
    ensure_bottom_gradient(grad_png, width, height)

    seg_paths = []
    cached_count = 0
    rebuilt_count = 0

    for idx, sc in enumerate(scenes):
        sid = sc["id"]
        target_dur = round(sc["end"] - sc["start"], 3)
        out_seg = os.path.join(args.out_dir, f"seg-{sid}.mp4")
        sig_file = os.path.join(args.out_dir, f"seg-{sid}.sig")

        if sc.get("voStart") is None:
            sig = compute_sig({
                "kind": "endslate",
                "endslate": file_sig(args.endslate),
                "dur": target_dur,
                "size": f"{width}x{height}",
                "fps": args.fps,
            })
            if not args.force and os.path.exists(out_seg) and os.path.exists(sig_file) and open(sig_file).read().strip() == sig:
                cached_count += 1
            else:
                vf = (
                    f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1,"
                    f"fade=t=in:st=0:d=0.60,fade=t=out:st={max(0.1, target_dur - 0.70):.3f}:d=0.70,format=yuv420p"
                )
                subprocess.check_call(
                    [
                        "ffmpeg", "-y", "-loop", "1", "-t", str(target_dur), "-i", args.endslate,
                        "-r", str(args.fps), "-vf", vf,
                        "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p", "-an", out_seg,
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                with open(sig_file, "w", encoding="utf-8") as sf:
                    sf.write(sig + "\n")
                rebuilt_count += 1
        else:
            src_file = resolve_clip_source(mapping[sid], sid, raw_dir, args.force)
            is_last_story = idx == len(scenes) - 2
            sig = compute_sig({
                "kind": "story",
                "src": file_sig(src_file),
                "dur": target_dur,
                "size": f"{width}x{height}",
                "fps": args.fps,
                "idx_role": "first" if idx == 0 else ("last_story" if is_last_story else "mid"),
            })
            if not args.force and os.path.exists(out_seg) and os.path.exists(sig_file) and open(sig_file).read().strip() == sig:
                cached_count += 1
            else:
                src_dur = probe_dur(src_file)
                pts_factor = (target_dur / src_dur) if target_dur > src_dur else 1.0
                fade_in = "fade=t=in:st=0:d=0.45" if idx == 0 else "fade=t=in:st=0:d=0.25"
                fade_out = (
                    f"fade=t=out:st={max(0.1, target_dur - 0.18):.3f}:d=0.18"
                    if is_last_story
                    else f"fade=t=out:st={max(0.1, target_dur - 0.28):.3f}:d=0.28"
                )
                fc = (
                    f"[0:v]setpts={pts_factor:.5f}*PTS,"
                    f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1,fps={args.fps}[v0];"
                    f"[v0][1:v]overlay=0:0,{fade_in},{fade_out},format=yuv420p[out]"
                )
                subprocess.check_call(
                    [
                        "ffmpeg", "-y", "-i", src_file, "-i", grad_png, "-t", str(target_dur),
                        "-filter_complex", fc, "-map", "[out]",
                        "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p", "-an", out_seg,
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                with open(sig_file, "w", encoding="utf-8") as sf:
                    sf.write(sig + "\n")
                rebuilt_count += 1
        seg_paths.append(out_seg)

    concat_txt = os.path.join(args.out_dir, "concat.txt")
    with open(concat_txt, "w", encoding="utf-8") as f:
        for p in seg_paths:
            f.write(f"file '{os.path.abspath(p)}'\n")

    # All seg-*.mp4 share identical codec/profile/fps/resolution -> fast lossless stream copy for video!
    clean_master = os.path.join(args.out_dir, f"{slug}-flow-clean-master.mp4")
    subprocess.check_call(
        [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_txt, "-i", args.audio,
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-shortest", clean_master,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    v_dur = probe_stream_dur(clean_master, "v:0")
    a_dur = probe_stream_dur(clean_master, "a:0")
    if abs(v_dur - a_dur) >= 0.35:
        sys.exit(f"Error: audio/video sync drift detected in {clean_master} (video={v_dur:.3f}s, audio={a_dur:.3f}s)")

    srt_specs = [
        ("eng", "English", os.path.join(args.srt_dir, f"{slug}.en.srt")),
        ("jpn", "日本語", os.path.join(args.srt_dir, f"{slug}.ja.srt")),
        ("zho", "简体中文", os.path.join(args.srt_dir, f"{slug}.zh-Hans.srt")),
        ("zho", "繁體中文", os.path.join(args.srt_dir, f"{slug}.zh-Hant.srt")),
        ("kor", "한국어", os.path.join(args.srt_dir, f"{slug}.ko.srt")),
    ]
    present_srts = [(code, title, p) for code, title, p in srt_specs if os.path.exists(p)]
    multilang_mp4 = os.path.join(args.out_dir, f"{slug}-flow-multilang-softsubs.mp4")
    if present_srts:
        cmd = ["ffmpeg", "-y", "-i", clean_master]
        for _, _, p in present_srts:
            cmd += ["-i", p]
        cmd += ["-map", "0:v", "-map", "0:a"]
        for i in range(len(present_srts)):
            cmd += ["-map", f"{i + 1}:s"]
        cmd += ["-c:v", "copy", "-c:a", "copy", "-c:s", "mov_text"]
        for i, (code, title, _) in enumerate(present_srts):
            cmd += [f"-metadata:s:s:{i}", f"language={code}", f"-metadata:s:s:{i}", f"title={title}"]
        cmd += ["-disposition:s:0", "default", "-movflags", "+faststart", multilang_mp4]
        subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    story_scenes = [s for s in scenes if s.get("voStart") is not None]
    if story_scenes:
        climax_sc = story_scenes[min(len(story_scenes) - 1, max(0, len(story_scenes) - 3))]
        for sc, fname in [(story_scenes[0], "qa-s01.png"), (climax_sc, "qa-climax.png")]:
            ts = sc["start"] + min(2.2, (sc["end"] - sc["start"]) * 0.45)
            subprocess.check_call(
                [
                    "ffmpeg", "-y", "-ss", f"{ts:.2f}", "-i", clean_master, "-frames:v", "1",
                    os.path.join(args.out_dir, fname),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    render_contact_sheet(clean_master, os.path.join(args.out_dir, "qa-contact-5x3.png"), v_dur, width, height)

    print(f"ASSEMBLE_OK {slug} ({v_dur:.2f}s, cached={cached_count}, rebuilt={rebuilt_count}) -> {clean_master}")


if __name__ == "__main__":
    main()
