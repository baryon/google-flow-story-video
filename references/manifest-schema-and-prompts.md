# Manifest Schema & Google Flow Prompt Templates

## 1. `episodes.json` Manifest Schema

`build_audio_and_srt.py` 与 `package_season.py` 共用同一份 `episodes.json` 分集清单：

```json
{
  "episodes": [
    {
      "ep": 1,
      "slug": "ep01",
      "title_zh": "一瞥成灵",
      "title_en": "One Glance Made Her Real",
      "title_ja": "ひと目で、魂は宿る",
      "tone": "mythic",
      "scenes": [
        {
          "id": "s01",
          "lead_in": 0.40,
          "pad_after": 0.70,
          "vo": "She was supposed to be an empty puppet. Until you looked at her.",
          "en": "She was supposed to be an empty puppet.\nUntil you looked at her.",
          "ja": "彼女はただの傀儡のはずだった。\nあなたが見つめるまでは。",
          "zh": "她本该只是一具无灵的傀儡。\n直到你看向了她。",
          "flow_mode": "Ingredients to Video (hero-stage1.jpg)",
          "flow_prompt": "Extreme macro underwater cinema shot in pitch-dark abyssal teal water, this tiny translucent glowing emerald-gold spore suspended in the center suddenly opens her luminous eyes wide, sending a circular shockwave of emerald-gold bioluminescent light outward, volumetric water particles, dark calm lower third, vertical 9:16, no text."
        }
      ]
    }
  ]
}
```

### 字段说明

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `ep` | `number` | 是 | 集数序号（从 `1` 开始） |
| `slug` | `string` | 是 | 分集目录标识（如 `"ep01"`） |
| `title_en` / `title_ja` / `title_zh` | `string` | 推荐 | 英 / 日 / 中分集标题，用于生成 YouTube 章节与交付清单 |
| `tone` | `string` | 否 | 内置立体声氛围音床预设名，默认 `"mythic"` |
| `scenes[].id` | `string` | 是 | 镜号（如 `"s01"`..`"s09"`），需与 `mapping.json` 键名一致 |
| `scenes[].vo` | `string` | 是 | 送入 `edge-tts` 的英文旁白原文（单行纯文本） |
| `scenes[].lead_in` | `number` | 否 | 镜头切入后到旁白开口前的留白秒数，默认 `0.32` |
| `scenes[].pad_after` | `number` | 否 | 旁白结束到切下一镜前的尾音留白秒数，默认 `0.65` |
| `scenes[].en` / `ja` / `zh` | `string` | 推荐 | 对应 `.en.srt` / `.ja.srt` / `.zh-Hans.srt` 的双行排版字幕文本（可选扩展 `zh_hant`、`ko`） |
| `scenes[].flow_mode` | `string` | 否 | 记录该镜使用 `Text to Video` 还是挂载哪张 Ingredient，便于浏览器代理执行 |
| `scenes[].flow_prompt` | `string` | 否 | 发送给 Google Flow 的英文生成提示词 |

### 内置 `tone` 氛围音床预设（`build_audio_and_srt.py`）

未指定 `--bgm` 外部音频时，脚本会按 `tone` 自动合成 48kHz 立体声氛围铺底与节点空灵钟琴：

| `tone` 值 | 调性与声学特征 | 适用剧情 |
|---|---|---|
| `mythic` | D 大调五度空灵共鸣 | 起源、苏醒、古老传说 |
| `resilient` | A 小调深沉推进 + 尾段低频共鸣 | 受挫、死而复生、绝境求生 |
| `evolution` | C 大调明亮上扬 | 形态蜕变、成长、首次融合 |
| `wonder` | B 调神秘晶莹泛音 | 秘境探索、奇观揭示、异界集市 |
| `battle` | A 多利亚调式 + 41Hz 超低频震动 | 强敌对决、战术博弈、弹反 |
| `revenge` | G 小调冷冽紧迫 + 41Hz 超低频震动 | 伏击、限时追猎、夺回失物 |
| `climax` | A 大调宏大交响共鸣 + 超低频震动 | 终局大战、加冕登顶 |
| `finale` | C 大调开阔余韵 | 踏出新手村、迈向更广阔世界 |

---

## 2. `mapping.json` Schema（`assemble_episode.py`）

每集的 `mapping.json` 将分镜 ID（`s01`..`s09`）映射到 **Google Flow 签名 CDN 视频直链**（`https://flow-content.google/video/...`）或**本地 `.mp4` 路径**：

```json
{
  "s01": "https://flow-content.google/video/2da26bb9-4ab1-45b7-96ae-732a2604f615?Expires=...&KeyName=labs-flow-prod-cdn-key&Signature=...",
  "s02": "https://flow-content.google/video/1becbb76-938a-4569-a8b2-12602b4f0c29?Expires=...&KeyName=labs-flow-prod-cdn-key&Signature=..."
}
```

---

## 3. Ingredients 定妆图提示词与防人形漂移清单

生图阶段准备全季共享的 6–8 张 Ingredients 参考图时，遵循以下模板：

```text
[Subject / Environment core design], [lighting & material texture],
centered in the upper-middle frame, dark calm lower third reserved for clean composition,
vertical 9:16 aspect ratio, cinematic concept art,
STRICTLY NO text, NO watermark, NO UI.
```

若世界观为非人类灵体、异兽、器灵或机械生命，**必须追加防人形漂移约束**：

```text
STRICTLY NO humans, NO human faces, NO humanoid torso, NO mermaids.
```

生成后必须逐张读取图像检查：一旦出现人类五官、人形剪影或多余文字，立即重抽，不得直接上传至 Google Flow。

---

## 4. Google Flow（`Omni 1.2 Flash`）五段式视频提示词公式

每个 8 秒镜头的 `flow_prompt` 建议采用以下五段结构：

1. **景别与运镜**：`Extreme macro cinema shot` / `Sweeping wide vertical diving shot` / `Slow pull-back reveal shot`
2. **Ingredient 锚点指代**（挂载参考图时必填）：用 `"this ..."` 明确指向所挂素材（如 `"this tiny translucent glowing emerald-gold spore"`、`"inside this sheltered cove"`）。
3. **单一核心动作节拍**：只描述 **1 个**适合在 8 秒内完成的物理或光影变化（如 `"suddenly opens her luminous eyes wide, sending a circular shockwave of emerald-gold light outward"`），避免在单镜塞入 3–4 个连续剧情转折。
4. **世界观防漂移约束**（未挂角色图但涉及生灵时必填）：加入 `"purely non-humanoid, no humans, no human faces"`。
5. **构图与干净母带固定后缀**：
   ```text
   dark calm lower third, vertical 9:16, no text.
   ```

---

## 5. 多语外置字幕排版速查表

| 语种 | 文件后缀 | 单行上限 | 最大行数 | 排版要点 |
|---|---|---|---|---|
| 英文（English） | `.en.srt` | ≤ 32 字符 | 2 行 | 按意群自然断行，避免介词或冠词孤立在行尾 |
| 日文（日本語） | `.ja.srt` | ≤ 16 全角字 | 2 行 | 保持叙事文学感，专有名词全季统一片假名或汉字写法 |
| 简体中文 | `.zh-Hans.srt` | ≤ 14 字 | 2 行 | 短句有力，行内可用空格或标点停顿，与旁白重音对齐 |
