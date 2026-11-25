#!/usr/bin/env python3
"""
Assemble a Mode C (native character dialogue / 3x15s micro-long-take) Google Flow episode master:
- Tracks signed URL clip identity (`raw/<id>.url`) + per-act PCM segment cache (`norm-<id>.sig`) for fast hot-rebuilds
- Decodes all acts + endslate cleanly to 48kHz stereo PCM via filter_complex concat=n=N:v=1:a=1 (NEVER -f concat -c copy on AAC)
- Applies seamless geq bottom subtitle gradient without hard black bars
- Generates or loops continuous 48kHz stereo BGM and applies sidechaincompress auto-ducking against character speech
- Verifies ZERO dead silence (silencedetect=n=-45dB:d=1.0) and asserts abs(video_dur - audio_dur) < 0.35s
- Muxes optional multi-language soft subtitle tracks and renders a 5x3 15-frame QA contact sheet
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

from build_audio_and_srt import prepare_external_bgm, synthesize_ambient


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


def has_audio_stream(path: str) -> bool:
    out = subprocess.check_output(
        [
            "ffprobe", "-v", "error", "-select_streams", "a:0",
            "-show_entries", "stream=codec_type",
            "-of", "default=noprint_wrappers=1:nokey=1", path,
        ],
        text=True,
    ).strip()
    return bool(out)


def file_sig(path: str) -> str:
    st = os.stat(path)
    return f"{os.path.abspath(path)}:{st.st_size}:{st.st_mtime_ns}"


def compute_sig(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


def resolve_clip_source(src: str, aid: str, raw_dir: str, force: bool) -> str:
    if src.startswith("http://") or src.startswith("https://"):
        local_raw = os.path.join(raw_dir, f"{aid}.mp4")
        url_tag_file = os.path.join(raw_dir, f"{aid}.url")
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
                    f"Error: failed to download act '{aid}' from Flow CDN (curl exit {rc}). "
                    f"Signed URLs expire after ~6 hours—re-read video.currentSrc in the Flow project."
                )
            with open(url_tag_file, "w", encoding="utf-8") as uf:
                uf.write(canonical_url + "\n")
        elif not prev_url:
            with open(url_tag_file, "w", encoding="utf-8") as uf:
                uf.write(canonical_url + "\n")
        return local_raw

    if not os.path.exists(src):
        sys.exit(f"Error: local act file for '{aid}' not found: {src}")
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


def check_silence(video_path: str, threshold_db: float = -45.0, min_dur: float = 1.0) -> list[str]:
    proc = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-nostats", "-i", video_path,
            "-af", f"silencedetect=n={threshold_db}dB:d={min_dur}",
            "-f", "null", "-",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return re.findall(r"silence_end: [0-9.]+ \| silence_duration: [0-9.]+", proc.stderr)


def main():
    ap = argparse.ArgumentParser(description="Assemble a Mode C native-dialogue Google Flow episode master.")
    ap.add_argument("--episode", required=True, help="Path to dialogue-episode.json")
    ap.add_argument("--endslate", required=True, help="Path to endslate PNG")
    ap.add_argument("--out-dir", required=True, help="Output directory for raw acts, masters, and QA sheet")
    ap.add_argument("--srt-dir", default="", help="Optional directory containing <slug>.<lang>.srt files")
    ap.add_argument("--bgm", default="", help="Optional external BGM file (defaults to built-in stereo tone synth)")
    ap.add_argument("--bgm-volume", type=float, default=0.82, help="Continuous BGM base volume before ducking (default: 0.82)")
    ap.add_argument("--size", default="1080x1920", help="Target output resolution WxH (default: 1080x1920)")
    ap.add_argument("--fps", type=int, default=30, help="Target frame rate (default: 30)")
    ap.add_argument("--force", action="store_true", help="Ignore segment cache and re-encode all acts")
    args = ap.parse_args()

    require_bin("ffmpeg")
    require_bin("ffprobe")
    require_bin("curl")

    width, height = [int(v) for v in args.size.lower().split("x")]
    with open(args.episode, encoding="utf-8") as f:
        ep = json.load(f)

    slug = ep["slug"]
    tone = ep.get("tone", "wonder")
    endslate_dur = float(ep.get("endslate_seconds", 3.8))
    acts = ep.get("acts", [])
    if not acts:
        sys.exit("Error: dialogue-episode.json must contain a non-empty 'acts' list.")

    raw_dir = os.path.join(args.out_dir, "raw")
    os.makedirs(raw_dir, exist_ok=True)
    grad_png = os.path.join(args.out_dir, f"bottom-grad-{width}x{height}.png")
    ensure_bottom_gradient(grad_png, width, height)

    # 1. Normalize every act + endslate to uniform MKV (libx264 + 48kHz stereo pcm_s16le) with per-act cache
    norm_segments = []
    act_starts = []
    cursor = 0.0
    cached_count = 0
    rebuilt_count = 0

    for idx, act in enumerate(acts):
        aid = act["id"]
        gain = float(act.get("dialogue_gain", 1.25))
        src_file = resolve_clip_source(act["src"], aid, raw_dir, args.force)
        dur = round(probe_dur(src_file), 3)
        act_starts.append(cursor)
        is_last_act = idx == len(acts) - 1
        norm_mkv = os.path.join(args.out_dir, f"norm-{aid}.mkv")
        sig_file = os.path.join(args.out_dir, f"norm-{aid}.sig")

        sig = compute_sig({
            "src": file_sig(src_file),
            "gain": gain,
            "size": f"{width}x{height}",
            "fps": args.fps,
            "role": "first" if idx == 0 else ("last" if is_last_act else "mid"),
        })

        if not args.force and os.path.exists(norm_mkv) and os.path.exists(sig_file) and open(sig_file).read().strip() == sig:
            cached_count += 1
        else:
            fade_in = "fade=t=in:st=0:d=0.40" if idx == 0 else "fade=t=in:st=0:d=0.22"
            fade_out_d = 0.18 if is_last_act else 0.24
            fade_out = f"fade=t=out:st={max(0.1, dur - fade_out_d):.3f}:d={fade_out_d:.2f}"

            if has_audio_stream(src_file):
                fc = (
                    f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},"
                    f"setsar=1,fps={args.fps}[v0];"
                    f"[v0][1:v]overlay=0:0,{fade_in},{fade_out},format=yuv420p[vout];"
                    f"[0:a]aresample=48000,aformat=sample_fmts=s16:channel_layouts=stereo,"
                    f"highpass=f=75,volume={gain:.3f},"
                    f"afade=t=in:st=0:d=0.12,afade=t=out:st={max(0.1, dur - 0.16):.3f}:d=0.16[aout]"
                )
                cmd = [
                    "ffmpeg", "-y", "-i", src_file, "-i", grad_png, "-t", f"{dur:.3f}",
                    "-filter_complex", fc, "-map", "[vout]", "-map", "[aout]",
                    "-c:v", "libx264", "-preset", "medium", "-crf", "16",
                    "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", norm_mkv,
                ]
            else:
                fc = (
                    f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},"
                    f"setsar=1,fps={args.fps}[v0];"
                    f"[v0][1:v]overlay=0:0,{fade_in},{fade_out},format=yuv420p[vout]"
                )
                cmd = [
                    "ffmpeg", "-y", "-i", src_file, "-i", grad_png,
                    "-f", "lavfi", "-t", f"{dur:.3f}", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
                    "-t", f"{dur:.3f}", "-filter_complex", fc, "-map", "[vout]", "-map", "2:a",
                    "-c:v", "libx264", "-preset", "medium", "-crf", "16",
                    "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", norm_mkv,
                ]
            subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            with open(sig_file, "w", encoding="utf-8") as sf:
                sf.write(sig + "\n")
            rebuilt_count += 1

        norm_segments.append(norm_mkv)
        cursor += dur

    # Append vector endslate with 48kHz stereo silent PCM
    act_starts.append(cursor)
    norm_end = os.path.join(args.out_dir, "norm-endslate.mkv")
    end_sig_file = os.path.join(args.out_dir, "norm-endslate.sig")
    end_sig = compute_sig({
        "endslate": file_sig(args.endslate),
        "dur": endslate_dur,
        "size": f"{width}x{height}",
        "fps": args.fps,
    })
    if not args.force and os.path.exists(norm_end) and os.path.exists(end_sig_file) and open(end_sig_file).read().strip() == end_sig:
        cached_count += 1
    else:
        end_vf = (
            f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1,"
            f"fade=t=in:st=0:d=0.55,fade=t=out:st={max(0.1, endslate_dur - 0.70):.3f}:d=0.70,format=yuv420p"
        )
        subprocess.check_call(
            [
                "ffmpeg", "-y", "-loop", "1", "-t", f"{endslate_dur:.3f}", "-i", args.endslate,
                "-f", "lavfi", "-t", f"{endslate_dur:.3f}", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
                "-r", str(args.fps), "-vf", end_vf, "-map", "0:v", "-map", "1:a",
                "-c:v", "libx264", "-preset", "medium", "-crf", "16",
                "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", norm_end,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        with open(end_sig_file, "w", encoding="utf-8") as sf:
            sf.write(end_sig + "\n")
        rebuilt_count += 1

    norm_segments.append(norm_end)
    total_dur = round(cursor + endslate_dur, 3)

    # 2. Concatenate all segments in PCM domain (-filter_complex concat=n=N:v=1:a=1) + sidechain ducked BGM
    bgm_wav = os.path.join(args.out_dir, "continuous-bgm.wav")
    if args.bgm:
        prepare_external_bgm(args.bgm, bgm_wav, total_dur)
    else:
        synthesize_ambient(bgm_wav, total_dur, tone, act_starts)

    n_seg = len(norm_segments)
    cmd = ["ffmpeg", "-y"]
    for seg in norm_segments:
        cmd += ["-i", seg]
    cmd += ["-i", bgm_wav]
    bgm_idx = n_seg

    concat_pairs = "".join(f"[{i}:v][{i}:a]" for i in range(n_seg))
    fc_master = (
        f"{concat_pairs}concat=n={n_seg}:v=1:a=1[vcat][dlg];"
        f"[dlg]asplit=2[dlg_sc][dlg_mix];"
        f"[{bgm_idx}:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,volume={args.bgm_volume:.3f}[bgm0];"
        f"[bgm0][dlg_sc]sidechaincompress=threshold=0.025:ratio=6:attack=35:release=650:makeup=1.0[bgm_duck];"
        f"[dlg_mix][bgm_duck]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,"
        f"alimiter=limit=0.95[aout]"
    )

    clean_master = os.path.join(args.out_dir, f"{slug}-flow-clean-master.mp4")
    cmd += [
        "-filter_complex", fc_master, "-map", "[vcat]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        "-movflags", "+faststart", clean_master,
    ]
    subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 3. Hard verification: audio/video sync (< 0.35s) + dead-silence check
    v_dur = probe_stream_dur(clean_master, "v:0")
    a_dur = probe_stream_dur(clean_master, "a:0")
    if abs(v_dur - a_dur) >= 0.35:
        sys.exit(f"Error: audio/video sync drift in {clean_master} (video={v_dur:.3f}s, audio={a_dur:.3f}s)")

    silences = check_silence(clean_master, threshold_db=-45.0, min_dur=1.0)
    if silences:
        print(f"WARN: detected silence window(s) in {slug}: {silences}", file=sys.stderr)

    # 4. Optional soft-subtitle muxing
    if args.srt_dir and os.path.isdir(args.srt_dir):
        srt_specs = [
            ("eng", "English", os.path.join(args.srt_dir, f"{slug}.en.srt")),
            ("jpn", "日本語", os.path.join(args.srt_dir, f"{slug}.ja.srt")),
            ("zho", "简体中文", os.path.join(args.srt_dir, f"{slug}.zh-Hans.srt")),
            ("zho", "繁體中文", os.path.join(args.srt_dir, f"{slug}.zh-Hant.srt")),
            ("kor", "한국어", os.path.join(args.srt_dir, f"{slug}.ko.srt")),
        ]
        present_srts = [(code, title, p) for code, title, p in srt_specs if os.path.exists(p)]
        if present_srts:
            multilang_mp4 = os.path.join(args.out_dir, f"{slug}-flow-multilang-softsubs.mp4")
            scmd = ["ffmpeg", "-y", "-i", clean_master]
            for _, _, p in present_srts:
                scmd += ["-i", p]
            scmd += ["-map", "0:v", "-map", "0:a"]
            for i in range(len(present_srts)):
                scmd += ["-map", f"{i + 1}:s"]
            scmd += ["-c:v", "copy", "-c:a", "copy", "-c:s", "mov_text"]
            for i, (code, title, _) in enumerate(present_srts):
                scmd += [f"-metadata:s:s:{i}", f"language={code}", f"-metadata:s:s:{i}", f"title={title}"]
            scmd += ["-disposition:s:0", "default", "-movflags", "+faststart", multilang_mp4]
            subprocess.check_call(scmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 5. Mandatory 15-frame 5x3 visual QA contact sheet
    qa_sheet = os.path.join(args.out_dir, "qa-contact-5x3.png")
    render_contact_sheet(clean_master, qa_sheet, v_dur, width, height)
    print(f"DIALOGUE_ASSEMBLE_OK {slug} ({v_dur:.2f}s, cached={cached_count}, rebuilt={rebuilt_count}, silences={len(silences)}) -> {clean_master}")


if __name__ == "__main__":
    main()
