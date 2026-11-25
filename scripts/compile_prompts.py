#!/usr/bin/env python3
"""
Compile episode/act prompts against a shared Character, Voice & Lighting Bible (`bible.json`):
- Injects consistent visual tags (`{{char:id}}`), voice timbre tags (`{{voice:id}}`),
  location descriptions (`{{loc:id}}`), global `style_anchor`, `lighting_anchor`, and
  mandatory full-bleed `NO black bars` suffix across 10-minute / multi-episode projects.
- Enforces Google Flow guardrails upfront:
  1. Max 2 Ingredients per shot (prevents character color-bleed in Omni 1.2 Flash)
  2. Spoken dialogue word budget check (<= 12 English words per 8s beat unless overridden)
  3. Automatic non-humanoid drift guard when `non_humanoid_guard: true`
- Outputs compiled manifest JSON and an operator-ready Markdown shot sheet (`--sheet-out`).
"""
import argparse
import json
import re
import sys


PLACEHOLDER_RE = re.compile(r"\{\{(char|voice|loc):([a-zA-Z0-9_-]+)\}\}")


def count_en_words(text: str) -> int:
    cleaned = re.sub(r"[^\w'-]+", " ", text.strip())
    return len([w for w in cleaned.split() if w])


def compile_single_prompt(
    raw_prompt: str,
    entry: dict,
    bible: dict,
    max_words: int,
    strict: bool,
    context_label: str,
) -> tuple[str, list[str], list[str]]:
    warnings = []
    ingredients = list(entry.get("ingredients", []))
    chars = bible.get("characters", {})
    locs = bible.get("locations", {})

    def repl(match: re.Match) -> str:
        kind, key = match.group(1), match.group(2)
        if kind == "char":
            if key not in chars:
                sys.exit(f"Error [{context_label}]: unknown character '{{{{char:{key}}}}}' in bible.json")
            ing = chars[key].get("ingredient")
            if ing and ing not in ingredients:
                ingredients.append(ing)
            return chars[key]["visual_tag"]
        if kind == "voice":
            if key not in chars or "voice_tag" not in chars[key]:
                sys.exit(f"Error [{context_label}]: missing voice_tag for '{{{{voice:{key}}}}}' in bible.json")
            return chars[key]["voice_tag"]
        if kind == "loc":
            if key not in locs:
                sys.exit(f"Error [{context_label}]: unknown location '{{{{loc:{key}}}}}' in bible.json")
            ing = locs[key].get("ingredient")
            if ing and ing not in ingredients:
                ingredients.append(ing)
            return locs[key]["visual_tag"]
        return match.group(0)

    # Support structured Mode C shorthand if raw_prompt is omitted
    if not raw_prompt and entry.get("speaker") and entry.get("line"):
        sp = entry["speaker"]
        if sp not in chars:
            sys.exit(f"Error [{context_label}]: unknown speaker '{sp}' in bible.json")
        loc_key = entry.get("location", "")
        loc_desc = ""
        if loc_key:
            if loc_key not in locs:
                sys.exit(f"Error [{context_label}]: unknown location '{loc_key}' in bible.json")
            loc_desc = f"inside {locs[loc_key]['visual_tag']}, "
            if locs[loc_key].get("ingredient") and locs[loc_key]["ingredient"] not in ingredients:
                ingredients.append(locs[loc_key]["ingredient"])
        if chars[sp].get("ingredient") and chars[sp]["ingredient"] not in ingredients:
            ingredients.append(chars[sp]["ingredient"])

        cam = entry.get("camera", "Medium vertical cinema shot")
        action = entry.get("action", "reacts expressively")
        voice = chars[sp].get("voice_tag", "expressive natural voice")
        line = entry["line"].strip()
        raw_prompt = (
            f"{cam}, {loc_desc}{chars[sp]['visual_tag']} {action}, "
            f"speaking aloud in a {voice}: \"{line}\" "
            f"Spoken dialogue finishes in the first 4.5 seconds, leaving 3 seconds of expressive visual reaction"
        )
    else:
        raw_prompt = PLACEHOLDER_RE.sub(repl, raw_prompt)

    # Check spoken line word budget if quoted speech or explicit `line` exists
    spoken_candidates = []
    if entry.get("line"):
        spoken_candidates.append(entry["line"])
    else:
        spoken_candidates.extend(re.findall(r'"([^"]{3,})"', raw_prompt))

    beat_limit = int(entry.get("max_words", max_words))
    for line_txt in spoken_candidates:
        wc = count_en_words(line_txt)
        if wc > beat_limit:
            msg = f"[{context_label}] spoken line has {wc} words (> {beat_limit} limit, risk of 8s cutoff): \"{line_txt}\""
            if strict:
                sys.exit(f"Error {msg}")
            warnings.append(msg)

    # Enforce <= 2 Ingredients guardrail
    if len(ingredients) > 2:
        msg = (
            f"[{context_label}] {len(ingredients)} ingredients attached ({', '.join(ingredients)}). "
            f"Omni 1.2 Flash allows at most 2 ingredients per shot without color-bleed! "
            f"Keep <= 2 ingredients (e.g. location + 1 character, or 2 characters with text location)."
        )
        if strict:
            sys.exit(f"Error {msg}")
        warnings.append(msg)

    parts = [raw_prompt.rstrip(" .,")]
    style_anchor = bible.get("style_anchor", "").strip(" .,")
    lighting_anchor = bible.get("lighting_anchor", "").strip(" .,")
    if style_anchor and style_anchor.lower() not in raw_prompt.lower():
        parts.append(style_anchor)
    if lighting_anchor and lighting_anchor.lower() not in raw_prompt.lower():
        parts.append(lighting_anchor)
    if bible.get("non_humanoid_guard") and "no human" not in raw_prompt.lower():
        parts.append("purely non-humanoid, STRICTLY NO humans, NO human faces, NO mermaids")

    suffix = bible.get(
        "aspect_suffix",
        "full-bleed 9:16 edge-to-edge, NO black bars, NO letterbox, NO borders, no text.",
    ).strip()
    if "no black bars" not in raw_prompt.lower():
        parts.append(suffix)

    compiled = ", ".join(p for p in parts if p)
    if not compiled.endswith("."):
        compiled += "."
    return compiled, ingredients, warnings


def main():
    ap = argparse.ArgumentParser(description="Compile prompts with Character & Lighting Bible and validate Flow guardrails.")
    ap.add_argument("--bible", required=True, help="Path to bible.json")
    ap.add_argument("--manifest", required=True, help="Path to episodes.json or dialogue-episode.json")
    ap.add_argument("--out", required=True, help="Output path for compiled JSON")
    ap.add_argument("--sheet-out", default="", help="Optional Markdown shot-sheet path for browser execution")
    ap.add_argument("--max-words", type=int, default=12, help="Max English words per 8s spoken dialogue beat (default: 12)")
    ap.add_argument("--strict", action="store_true", help="Fail immediately on >2 ingredients or >max-words warnings")
    args = ap.parse_args()

    with open(args.bible, encoding="utf-8") as f:
        bible = json.load(f)
    with open(args.manifest, encoding="utf-8") as f:
        data = json.load(f)

    all_warnings = []
    sheet_lines = ["# Compiled Google Flow Shot Sheet", ""]

    episodes = data["episodes"] if isinstance(data, dict) and "episodes" in data else [data]
    for ep in episodes:
        slug = ep.get("slug", f"ep{ep.get('ep', 1):02d}")
        sheet_lines.append(f"## {slug} — {ep.get('title_en', '')} / {ep.get('title_zh', '')}".strip(" /—"))
        sheet_lines.append("")
        items = ep.get("scenes") or ep.get("acts") or []
        for item in items:
            sid = item["id"]
            label = f"{slug}:{sid}"
            compiled, ings, warns = compile_single_prompt(
                item.get("flow_prompt", ""), item, bible, args.max_words, args.strict, label
            )
            item["flow_prompt"] = compiled
            if ings:
                item["ingredients"] = ings
                if not item.get("flow_mode"):
                    item["flow_mode"] = f"Ingredients ({', '.join(ings)})"
            all_warnings.extend(warns)
            mode_str = item.get("flow_mode") or ("Ingredients (" + ", ".join(ings) + ")" if ings else "Text to Video")
            sheet_lines.append(f"- **`{sid}`** [{mode_str}]")
            sheet_lines.append(f"  `{compiled}`")
        sheet_lines.append("")

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    if args.sheet_out:
        with open(args.sheet_out, "w", encoding="utf-8") as f:
            f.write("\n".join(sheet_lines).rstrip() + "\n")

    for w in all_warnings:
        print(f"WARN {w}", file=sys.stderr)

    print(f"COMPILE_OK warnings={len(all_warnings)} out={args.out}")


if __name__ == "__main__":
    main()
