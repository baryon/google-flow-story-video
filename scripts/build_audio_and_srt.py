#!/usr/bin/env python3
"""
Generate neural voiceover, exact timeline.json, external multi-language .srt files,
and custom stereo ambient (or external BGM) audio masters for one or more episodes.
"""
import argparse
import json
import math
import os
import shutil
import struct
import subprocess
import sys
import wave


def require_bin(name: str):
    if not shutil.which(name):
        sys.exit(f"Error: required binary '{name}' not found in PATH.")


def resolve_tts_cmd() -> list[str]:
    if shutil.which("edge-tts"):
        return ["edge-tts"]
    if shutil.which("uvx"):
        return ["uvx", "--from", "edge-tts", "edge-tts"]
    sys.exit("Error: neither 'edge-tts' nor 'uvx' found in PATH. Install edge-tts (`pipx install edge-tts` or install `uv`).")


def probe_duration(path: str) -> float:
    out = subprocess.check_output(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", path,
        ],
        text=True,
    ).strip()
    return float(out)


def srt_time(sec: float) -> str:
    ms = int(round(sec * 1000))
    h, rem = divmod(ms, 3600000)
    m, rem = divmod(rem, 60000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def synthesize_ambient(out_wav: str, total_dur: float, tone: str, scene_starts: list[float]):
    sr = 48000
    n = int(total_dur * sr)
    buf = bytearray(n * 4)

    chords = {
        "mythic":    [73.42, 110.0, 146.83, 220.0, 293.66, 369.99],
        "resilient": [55.0, 82.41, 110.0, 164.81, 220.0, 261.63],
        "evolution": [65.41, 98.00, 130.81, 196.00, 261.63, 329.63],
        "wonder":    [61.74, 92.50, 123.47, 185.00, 246.94, 311.13],
        "battle":    [55.0, 82.41, 110.0, 146.83, 220.0, 261.63],
        "revenge":   [49.00, 73.42, 98.00, 146.83, 196.00, 233.08],
        "climax":    [55.0, 82.41, 110.0, 164.81, 220.0, 277.18],
        "finale":    [65.41, 98.00, 130.81, 196.00, 261.63, 329.63],
    }
    freqs = chords.get(tone, chords["mythic"])
    chime_cues = [
        (scene_starts[0] + 0.8, [freqs[4] * 2, freqs[5] * 2], 2.2, 0.13),
        (scene_starts[min(5, len(scene_starts) - 1)] + 0.6, [freqs[3] * 2, freqs[4] * 2, freqs[5] * 2], 3.0, 0.14),
        (scene_starts[-1], [freqs[2] * 2, freqs[3] * 2, freqs[4] * 2], 3.6, 0.15),
    ]
    rumble_start = scene_starts[-2] if len(scene_starts) >= 2 else max(0.0, total_dur - 8.0)

    for i in range(n):
        t = i / sr
        env = min(1.0, t / 1.1) * min(1.0, max(0.0, (total_dur - t) / 1.4))
        breath = 0.72 + 0.28 * math.sin(2 * math.pi * 0.12 * t)
        pad_l = 0.0
        pad_r = 0.0
        for idx_f, f in enumerate(freqs):
            w = [0.24, 0.18, 0.16, 0.10, 0.07, 0.05][idx_f]
            det = 0.18 * math.sin(2 * math.pi * (0.07 + idx_f * 0.03) * t)
            pad_l += w * math.sin(2 * math.pi * (f + det) * t)
            pad_r += w * math.sin(2 * math.pi * (f - det) * t + 0.4 * idx_f)

        sig_l = pad_l * 0.21 * breath
        sig_r = pad_r * 0.21 * breath

        for tc, notes, decay, amp in chime_cues:
            dt = t - tc
            if 0.0 <= dt < decay + 0.8:
                c_env = (1.0 - math.exp(-dt * 42.0)) * math.exp(-dt / (decay * 0.42))
                for k, nf in enumerate(notes):
                    cv = math.sin(2 * math.pi * nf * dt) * (0.62 ** k)
                    sig_l += amp * c_env * cv * (0.85 if k % 2 == 0 else 0.55)
                    sig_r += amp * c_env * cv * (0.55 if k % 2 == 0 else 0.85)

        dt_r = t - rumble_start
        if tone in ("battle", "revenge", "climax", "resilient") and 0.0 <= dt_r < 4.5:
            r_env = math.sin(math.pi * min(1.0, dt_r / 4.2))
            rum = math.sin(2 * math.pi * 41.2 * t) * 0.20 + math.sin(2 * math.pi * 43.0 * t) * 0.14
            sig_l += rum * r_env
            sig_r += rum * r_env

        out_l = max(-0.95, min(0.95, sig_l * env))
        out_r = max(-0.95, min(0.95, sig_r * env))
        struct.pack_into("<hh", buf, i * 4, int(out_l * 32767), int(out_r * 32767))

    with wave.open(out_wav, "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(buf)


def _measure_wav_rms_db(wav_path: str) -> float:
    with wave.open(wav_path, "rb") as wf:
        raw = wf.readframes(wf.getnframes())
    if not raw:
        return -60.0
    samples = struct.unpack(f"<{len(raw) // 2}h", raw)
    rms = math.sqrt(sum(s * s for s in samples) / max(1, len(samples))) / 32768.0
    return 20.0 * math.log10(max(rms, 1e-6))


def _eval_cosine_envelope(t: float, keyframes: list[tuple[float, float]]) -> float:
    if t <= keyframes[0][0]:
        return keyframes[0][1]
    for i in range(len(keyframes) - 1):
        t0, g0 = keyframes[i]
        t1, g1 = keyframes[i + 1]
        if t <= t1:
            u = (t - t0) / max(1e-6, t1 - t0)
            s = 0.5 - 0.5 * math.cos(math.pi * u)
            return g0 + (g1 - g0) * s
    return keyframes[-1][1]


def prepare_external_bgm(
    bgm_src: str,
    out_wav: str,
    total_dur: float,
    start_seconds: float = 0.0,
    target_rms_db: float | None = -18.0,
    cues: list[list[float]] | list[tuple[float, float]] | None = None,
):
    """Prepare a 48kHz stereo external BGM bed with optional slice start, uniform RMS normalization,
    smooth piecewise cosine S-curve dynamic cues, and boundary fades."""
    tmp_slice = out_wav + ".slice.wav"
    tmp_norm = out_wav + ".norm.wav"
    try:
        cmd_slice = ["ffmpeg", "-y", "-stream_loop", "-1"]
        if start_seconds > 0.0:
            cmd_slice += ["-ss", f"{start_seconds:.3f}"]
        cmd_slice += [
            "-i", bgm_src, "-t", f"{total_dur:.3f}",
            "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", tmp_slice,
        ]
        subprocess.check_call(cmd_slice, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        fade_out_st = max(0.1, total_dur - 1.6)
        af_parts = ["aresample=48000", "aformat=channel_layouts=stereo"]
        if target_rms_db is not None:
            cur_db = _measure_wav_rms_db(tmp_slice)
            gain_db = max(-12.0, min(14.0, target_rms_db - cur_db))
            af_parts.append(f"volume={gain_db:.2f}dB")
            af_parts.append("alimiter=limit=0.92")
        af_parts.append("afade=t=in:st=0:d=1.0")
        af_parts.append(f"afade=t=out:st={fade_out_st:.3f}:d=1.6")

        stage_out = tmp_norm if cues else out_wav
        subprocess.check_call(
            [
                "ffmpeg", "-y", "-i", tmp_slice,
                "-af", ",".join(af_parts),
                "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", stage_out,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        if cues:
            kfs = sorted((float(k[0]), max(0.0, float(k[1]))) for k in cues)
            with wave.open(tmp_norm, "rb") as wf:
                sr = wf.getframerate()
                nframes = wf.getnframes()
                raw_bytes = wf.readframes(nframes)
            pcm = struct.unpack(f"<{nframes * 2}h", raw_bytes)
            buf = bytearray(len(raw_bytes))
            for i in range(nframes):
                g = _eval_cosine_envelope(i / sr, kfs)
                l = max(-32767, min(32767, int(pcm[2 * i] * g)))
                r = max(-32767, min(32767, int(pcm[2 * i + 1] * g)))
                struct.pack_into("<hh", buf, i * 4, l, r)
            with wave.open(out_wav, "wb") as wf:
                wf.setnchannels(2)
                wf.setsampwidth(2)
                wf.setframerate(sr)
                wf.writeframes(buf)
    finally:
        for tmp_p in (tmp_slice, tmp_norm):
            if os.path.exists(tmp_p):
                os.unlink(tmp_p)


def main():
    ap = argparse.ArgumentParser(description="Build neural VO, timeline.json, multi-lang SRTs, and audio master.")
    ap.add_argument("--manifest", required=True, help="Path to episodes manifest JSON")
    ap.add_argument("--out-dir", required=True, help="Output base directory")
    ap.add_argument("--voice", default="en-GB-SoniaNeural", help="edge-tts voice name")
    ap.add_argument("--rate", default="-6%", help="edge-tts speaking rate")
    ap.add_argument("--pitch", default="-3Hz", help="edge-tts pitch offset")
    ap.add_argument("--bgm", default="", help="Optional external BGM audio file (loops/fades to episode length)")
    ap.add_argument("--bgm-volume", type=float, default=0.85, help="Background bed volume multiplier (default: 0.85)")
    ap.add_argument("--endslate-seconds", type=float, default=3.8, help="Duration of final brand end slate")
    args = ap.parse_args()

    require_bin("ffmpeg")
    require_bin("ffprobe")
    tts_base = resolve_tts_cmd()

    with open(args.manifest, encoding="utf-8") as f:
        data = json.load(f)
    episodes = data["episodes"] if isinstance(data, dict) and "episodes" in data else data
    os.makedirs(args.out_dir, exist_ok=True)

    lang_specs = [
        ("en", "en"),
        ("ja", "ja"),
        ("zh", "zh-Hans"),
        ("zh_hant", "zh-Hant"),
        ("ko", "ko"),
    ]

    for ep in episodes:
        slug = ep["slug"]
        ep_dir = os.path.join(args.out_dir, slug)
        os.makedirs(ep_dir, exist_ok=True)
        timeline = []
        cursor = 0.0

        for sc in ep["scenes"]:
            mp3_path = os.path.join(ep_dir, f"vo-{sc['id']}.mp3")
            subprocess.check_call(
                [
                    *tts_base,
                    "--voice", args.voice,
                    f"--rate={args.rate}",
                    f"--pitch={args.pitch}",
                    "--text", sc["vo"],
                    "--write-media", mp3_path,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            dur = probe_duration(mp3_path)
            lead_in = sc.get("lead_in", 0.32)
            pad_after = sc.get("pad_after", 0.65)
            start = cursor
            vo_start = start + lead_in
            vo_end = vo_start + dur
            end = vo_end + pad_after
            item = {
                "id": sc["id"],
                "start": round(start, 3),
                "end": round(end, 3),
                "voStart": round(vo_start, 3),
                "voEnd": round(vo_end, 3),
                "mp3": mp3_path,
                "flow_mode": sc.get("flow_mode", "Text to Video"),
                "flow_prompt": sc.get("flow_prompt", ""),
            }
            for lang_key, _ in lang_specs:
                if sc.get(lang_key):
                    item[lang_key] = sc[lang_key]
            timeline.append(item)
            cursor = end

        timeline.append({
            "id": "s_end",
            "start": round(cursor, 3),
            "end": round(cursor + args.endslate_seconds, 3),
            "voStart": None,
            "voEnd": None,
        })
        total_dur = round(cursor + args.endslate_seconds, 3)

        with open(os.path.join(ep_dir, "timeline.json"), "w", encoding="utf-8") as f:
            json.dump({
                "ep": ep["ep"],
                "slug": slug,
                "title_zh": ep.get("title_zh", ""),
                "title_en": ep.get("title_en", ""),
                "title_ja": ep.get("title_ja", ""),
                "tone": ep.get("tone", "mythic"),
                "totalDuration": total_dur,
                "scenes": timeline,
            }, f, indent=2, ensure_ascii=False)

        for lang_key, ext in lang_specs:
            lines = []
            idx = 1
            for item in timeline:
                if item["voStart"] is None or not item.get(lang_key):
                    continue
                lines.append(
                    f"{idx}\n{srt_time(item['voStart'])} --> {srt_time(item['voEnd'] + 0.14)}\n{item[lang_key]}\n"
                )
                idx += 1
            if lines:
                with open(os.path.join(ep_dir, f"{slug}.{ext}.srt"), "w", encoding="utf-8") as f:
                    f.write("\n".join(lines))

        amb_path = os.path.join(ep_dir, "ambient.wav")
        ep_bgm = ep.get("bgm") if isinstance(ep.get("bgm"), dict) else {}
        bgm_src = args.bgm or ep_bgm.get("src", "")
        bgm_start = float(ep_bgm.get("start_seconds", 0.0))
        bgm_rms = ep_bgm.get("target_rms_db", -18.0)
        bgm_cues = ep_bgm.get("cues") or None
        if bgm_src:
            prepare_external_bgm(
                bgm_src, amb_path, total_dur,
                start_seconds=bgm_start,
                target_rms_db=None if bgm_rms is None else float(bgm_rms),
                cues=bgm_cues,
            )
            eff_bgm_vol = float(ep_bgm.get("volume", 0.85 if bgm_cues else 0.42))
        else:
            synthesize_ambient(amb_path, total_dur, ep.get("tone", "mythic"), [item["start"] for item in timeline])
            eff_bgm_vol = args.bgm_volume

        cmd = ["ffmpeg", "-y", "-i", amb_path]
        filter_parts = [f"[0:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,volume={eff_bgm_vol:.3f}[amb]"]
        vo_labels = []
        for idx, item in enumerate(timeline):
            if item["voStart"] is None:
                continue
            cmd += ["-i", item["mp3"]]
            in_idx = len(vo_labels) + 1
            delay_ms = int(round(item["voStart"] * 1000))
            label = f"v{idx}"
            filter_parts.append(
                f"[{in_idx}:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
                f"highpass=f=85,equalizer=f=240:t=q:w=1.2:g=2.5,"
                f"aecho=0.8:0.85:55|110:0.18|0.09,"
                f"volume=1.35,adelay={delay_ms}|{delay_ms}[{label}]"
            )
            vo_labels.append(f"[{label}]")

        if bgm_src and vo_labels:
            filter_parts.append(
                f"{''.join(vo_labels)}amix=inputs={len(vo_labels)}:duration=longest:dropout_transition=0:normalize=0,"
                f"apad=whole_dur={total_dur:.3f},atrim=0:{total_dur:.3f},asplit=2[vo_sc][vo_mix]"
            )
            filter_parts.append(
                "[amb][vo_sc]sidechaincompress=threshold=0.02:ratio=5:attack=35:release=600:makeup=1.0[amb_duck]"
            )
            filter_parts.append(
                "[vo_mix][amb_duck]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,"
                "alimiter=limit=0.95[out]"
            )
        else:
            mix_inputs = "[amb]" + "".join(vo_labels)
            filter_parts.append(
                f"{mix_inputs}amix=inputs={len(vo_labels) + 1}:duration=first:dropout_transition=2:normalize=0,"
                f"alimiter=limit=0.95[out]"
            )
        master_wav = os.path.join(ep_dir, f"{slug}-audio-master.wav")
        cmd += ["-filter_complex", ";".join(filter_parts), "-map", "[out]", "-ar", "48000", "-ac", "2", master_wav]
        subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"AUDIO_OK {slug} ({total_dur}s)")


if __name__ == "__main__":
    main()
