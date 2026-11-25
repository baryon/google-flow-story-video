#!/usr/bin/env python3
"""
Package all finished episodes into a clean upload folder (`episodes/epXX/`),
losslessly concatenate the full-season compilation movie (`full-movie/`),
time-shift and merge all external .srt subtitle tracks, and generate README.txt with YouTube Chapters.
"""
import argparse
import json
import os
import re
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


def parse_srt_ts(ts: str) -> float:
    h, m, s_ms = ts.split(":")
    s, ms = s_ms.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def fmt_srt_ts(sec: float) -> str:
    ms = int(round(sec * 1000))
    h, rem = divmod(ms, 3600000)
    m, rem = divmod(rem, 60000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def fmt_yt_ts(sec: float) -> str:
    total_s = int(round(sec))
    h, rem = divmod(total_s, 3600)
    m, s = divmod(rem, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"


def main():
    ap = argparse.ArgumentParser(description="Package season episodes and lossless full-season compilation.")
    ap.add_argument("--manifest", required=True, help="Path to episodes manifest JSON")
    ap.add_argument("--masters-dir", required=True, help="Directory containing <slug>/<slug>-flow-clean-master.mp4")
    ap.add_argument("--audio-dir", required=True, help="Directory containing <slug>/<slug>.<lang>.srt")
    ap.add_argument("--series-slug", required=True, help="Prefix for output filenames, e.g. my-story-s1")
    ap.add_argument("--site-url", default="", help="Official website URL for README")
    ap.add_argument("--out-dir", required=True, help="Target delivery folder")
    args = ap.parse_args()

    require_bin("ffmpeg")
    require_bin("ffprobe")

    with open(args.manifest, encoding="utf-8") as f:
        data = json.load(f)
    episodes = data["episodes"] if isinstance(data, dict) and "episodes" in data else data

    for ep in episodes:
        slug = ep["slug"]
        expected = os.path.join(args.masters_dir, slug, f"{slug}-flow-clean-master.mp4")
        if not os.path.exists(expected):
            sys.exit(f"Error: missing episode master: {expected}")

    eps_dest = os.path.join(args.out_dir, "episodes")
    full_dest = os.path.join(args.out_dir, "full-movie")
    os.makedirs(eps_dest, exist_ok=True)
    os.makedirs(full_dest, exist_ok=True)

    lang_meta = [
        ("en", "eng", "English"),
        ("ja", "jpn", "日本語"),
        ("zh-Hans", "zho", "简体中文"),
        ("zh-Hant", "zho", "繁體中文"),
        ("ko", "kor", "한국어"),
    ]

    concat_files = []
    merged_srts = {lang: [] for lang, _, _ in lang_meta}
    srt_counters = {lang: 1 for lang, _, _ in lang_meta}
    yt_chapters = []
    offset = 0.0

    for ep in episodes:
        n = ep["ep"]
        slug = ep["slug"]
        code = f"{args.series_slug}-{slug}"
        ep_out = os.path.join(eps_dest, slug)
        os.makedirs(ep_out, exist_ok=True)

        clean_src = os.path.join(args.masters_dir, slug, f"{slug}-flow-clean-master.mp4")
        multi_src = os.path.join(args.masters_dir, slug, f"{slug}-flow-multilang-softsubs.mp4")
        clean_dst = os.path.join(ep_out, f"{code}-clean.mp4")
        shutil.copy2(clean_src, clean_dst)
        if os.path.exists(multi_src):
            shutil.copy2(multi_src, os.path.join(ep_out, f"{code}-multilang.mp4"))

        dur = probe_dur(clean_dst)
        chapter_label = f"{fmt_yt_ts(offset)} Episode {n}: {ep.get('title_en', slug)}"
        if ep.get("title_zh"):
            chapter_label += f" / {ep['title_zh']}"
        yt_chapters.append(chapter_label)
        concat_files.append(os.path.abspath(clean_dst))

        for lang, _, _ in lang_meta:
            s_src = os.path.join(args.audio_dir, slug, f"{slug}.{lang}.srt")
            if not os.path.exists(s_src):
                continue
            shutil.copy2(s_src, os.path.join(ep_out, f"{code}.{lang}.srt"))
            with open(s_src, encoding="utf-8") as sf:
                raw = sf.read().strip()
            for block in re.split(r"\n\s*\n", raw):
                lines = block.strip().splitlines()
                if len(lines) < 3:
                    continue
                t0_s, t1_s = lines[1].split(" --> ")
                t0 = parse_srt_ts(t0_s.strip()) + offset
                t1 = parse_srt_ts(t1_s.strip()) + offset
                text = "\n".join(lines[2:])
                idx = srt_counters[lang]
                merged_srts[lang].append(f"{idx}\n{fmt_srt_ts(t0)} --> {fmt_srt_ts(t1)}\n{text}\n")
                srt_counters[lang] += 1

        offset += dur

    present_full_srts = []
    for lang, code_iso, title in lang_meta:
        if merged_srts[lang]:
            srt_path = os.path.join(full_dest, f"{args.series_slug}-full.{lang}.srt")
            with open(srt_path, "w", encoding="utf-8") as f:
                f.write("\n".join(merged_srts[lang]))
            present_full_srts.append((code_iso, title, srt_path))

    concat_list = os.path.join(full_dest, ".concat.txt")
    with open(concat_list, "w", encoding="utf-8") as f:
        for p in concat_files:
            f.write(f"file '{p}'\n")

    full_clean = os.path.join(full_dest, f"{args.series_slug}-full-clean.mp4")
    subprocess.check_call(
        [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list,
            "-c", "copy", "-movflags", "+faststart", full_clean,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    os.remove(concat_list)

    if present_full_srts:
        full_multi = os.path.join(full_dest, f"{args.series_slug}-full-multilang.mp4")
        cmd = ["ffmpeg", "-y", "-i", full_clean]
        for _, _, p in present_full_srts:
            cmd += ["-i", p]
        cmd += ["-map", "0:v", "-map", "0:a"]
        for i in range(len(present_full_srts)):
            cmd += ["-map", f"{i + 1}:s"]
        cmd += ["-c:v", "copy", "-c:a", "copy", "-c:s", "mov_text"]
        for i, (c_iso, title, _) in enumerate(present_full_srts):
            cmd += [f"-metadata:s:s:{i}", f"language={c_iso}", f"-metadata:s:s:{i}", f"title={title}"]
        cmd += ["-disposition:s:0", "default", "-movflags", "+faststart", full_multi]
        subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    readme_lines = [f"{args.series_slug} — Complete Delivery Package"]
    if args.site_url:
        readme_lines.append(f"Website: {args.site_url}")
    readme_lines += [
        "",
        "=== YouTube Chapters ===",
        *yt_chapters,
        "",
        "=== Episode Titles (EN | JA | ZH) ===",
        *[
            f"EP {ep['ep']:02d} | {ep.get('title_en', '')} | {ep.get('title_ja', '')} | {ep.get('title_zh', '')}"
            for ep in episodes
        ],
    ]
    with open(os.path.join(args.out_dir, "README.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(readme_lines) + "\n")

    print(f"PACKAGE_OK total={fmt_yt_ts(offset)} dir={args.out_dir}")


if __name__ == "__main__":
    main()
