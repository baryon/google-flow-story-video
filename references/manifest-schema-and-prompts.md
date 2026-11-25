# Manifest Schemas & Google Flow Prompt Formulas

本文档定义 Mode VO（旁白史诗模式）与 Mode C（角色演戏对话模式）的 JSON 数据规范、内置音床预设、提示词公式及字幕排版上限。

---

## 1. Mode VO 清单规范：`episodes.json` & `mapping.json`

`build_audio_and_srt.py` 与 `package_season.py` 共用 `episodes.json`：

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
          "flow_prompt": "Extreme macro underwater cinema shot in pitch-dark abyssal teal water, this tiny translucent glowing emerald-gold spore suspended in the center suddenly opens her luminous eyes wide, sending a circular shockwave of emerald-gold bioluminescent light outward, volumetric water particles, full-bleed 9:16 edge-to-edge, NO black bars, NO letterbox, NO borders, no text."
        }
      ]
    }
  ]
}
```

### `episodes.json` 字段说明

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `ep` | `number` | 是 | 集数序号（从 `1` 开始） |
| `slug` | `string` | 是 | 分集目录标识（如 `"ep01"`） |
| `title_en` / `title_ja` / `title_zh` | `string` | 推荐 | 英 / 日 / 中分集标题，用于生成 YouTube 章节与交付清单 |
| `tone` | `string` | 否 | 内置立体声氛围音床预设名，默认 `"mythic"` |
| `scenes[].id` | `string` | 是 | 镜号（如 `"s01"`..`"s09"`），需与 `mapping.json` 键名一致 |
| `scenes[].vo` | `string` | Mode VO 必填 | 送入 `edge-tts` 的英文旁白原文（单行纯文本） |
| `scenes[].lead_in` | `number` | 否 | 镜头切入后到旁白开口前的留白秒数，默认 `0.32` |
| `scenes[].pad_after` | `number` | 否 | 旁白结束到切下一镜前的尾音留白秒数，默认 `0.65` |
| `scenes[].en` / `ja` / `zh` | `string` | 推荐 | 对应 `.en.srt` / `.ja.srt` / `.zh-Hans.srt` 的双行字幕文本（可选 `zh_hant`、`ko`） |
| `scenes[].flow_mode` | `string` | 否 | 记录该镜使用 `Text to Video` 还是挂载哪 1–2 张 Ingredient |
| `scenes[].flow_prompt` | `string` | 否 | 发送给 Google Flow 的英文生成提示词 |

### `mapping.json`（传给 `assemble_episode.py`）

将分镜 ID 映射到 Google Flow 签名 CDN 视频直链（`https://flow-content.google/video/...`）或本地 `.mp4` 路径：

```json
{
  "s01": "https://flow-content.google/video/2da26bb9-4ab1-45b7-96ae-732a2604f615?Expires=...&KeyName=labs-flow-prod-cdn-key&Signature=...",
  "s02": "https://flow-content.google/video/1becbb76-938a-4569-a8b2-12602b4f0c29?Expires=...&KeyName=labs-flow-prod-cdn-key&Signature=..."
}
```

---

## 2. Mode C 角色演戏清单规范：`dialogue-episode.json`

传给 `assemble_dialogue_episode.py`，用于合成三幕微长镜（保留 Flow 原生角色口型对白 + 48kHz PCM 拼接 + 全程自动闪避 BGM）：

```json
{
  "ep": 1,
  "slug": "ep01",
  "title_en": "The Burnt Lantern",
  "title_ja": "焦げたランタン",
  "title_zh": "烧焦的提灯",
  "tone": "wonder",
  "endslate_seconds": 3.8,
  "acts": [
    {
      "id": "act1",
      "src": "https://flow-content.google/video/11111111-...?Expires=...&KeyName=labs-flow-prod-cdn-key&Signature=...",
      "dialogue_gain": 1.25
    },
    {
      "id": "act2",
      "src": "https://flow-content.google/video/22222222-...?Expires=...&KeyName=labs-flow-prod-cdn-key&Signature=...",
      "dialogue_gain": 1.25
    },
    {
      "id": "act3",
      "src": "https://flow-content.google/video/33333333-...?Expires=...&KeyName=labs-flow-prod-cdn-key&Signature=...",
      "dialogue_gain": 1.25
    }
  ]
}
```

> **提示**：全季打包时，只需把每集的元信息（`ep`、`slug`、`title_en`、`title_ja`、`title_zh`）列在顶层 `episodes.json` 中（`scenes` 可留空数组 `[]`），即可直接复用 `package_season.py` 一键生成全季无损合集与 YouTube 章节。

---

## 3. 内置 `tone` 立体声氛围音床预设

`build_audio_and_srt.py` 与 `assemble_dialogue_episode.py` 均内置以下 8 种 48kHz 立体声调性音床（也可通过 `--bgm` 传入自定义音乐文件）：

| `tone` 值 | 调性与声学特征 | 适用剧情 |
|---|---|---|
| `mythic` | D 大调五度空灵共鸣 | 起源、苏醒、古老传说 |
| `resilient` | A 小调深沉推进 + 尾段低频共鸣 | 受挫、死而复生、绝境求生 |
| `evolution` | C 大调明亮上扬 | 形态蜕变、成长、首次融合 |
| `wonder` | B 调神秘晶莹泛音 | 日常奇遇、秘境探索、吉卜力/皮克斯奇幻感 |
| `battle` | A 多利亚调式 + 41Hz 超低频震动 | 强敌对决、战术博弈、弹反 |
| `revenge` | G 小调冷冽紧迫 + 41Hz 超低频震动 | 伏击、限时追猎、夺回失物 |
| `climax` | A 大调宏大交响共鸣 + 超低频震动 | 终局大战、加冕登顶 |
| `finale` | C 大调开阔余韵 | 踏出起点、迈向更广阔世界 |

---

## 4. Ingredients 定妆图提示词与防漂移清单

准备全季共享的 6–8 张 Ingredients 参考图时，遵循以下模板（注意**不要写 `dark lower third`**，以免生图阶段带入底部硬黑边）：

```text
[Subject / Environment core design], [consistent art style & lighting palette],
subject centered in the upper-middle frame with clean uncluttered space in the lower quarter,
full-bleed 9:16 edge-to-edge, NO black bars, NO letterbox, NO borders,
STRICTLY NO text, NO watermark, NO UI.
```

- **非人类题材必加约束**：`STRICTLY NO humans, NO human faces, NO humanoid torso, NO mermaids.`
- **动画风格题材必加约束**：明确写出统一画风锚点（如 `stylized hand-painted anime film aesthetic` 或 `warm stylized 3D animated feature film look`），防止部分参考图漂移成写实真人摄影。
- 生成后必须逐张使用 `read_file` 肉眼检查，确认无黑边、无文字、无人形误画后再上传至 Google Flow。

---

## 5. Google Flow（`Omni 1.2 Flash`）视频提示词公式

### 5.1 通用硬约束（Mode VO 与 Mode C 均须遵守）

1. **单镜最多挂载 2 张 Ingredients 参考图**：严禁单镜挂 3 张及以上（如 `场景 + 主角 + 配角`），否则极易触发角色配色互染。单人镜挂 `场景 + 角色A`；双人戏挂 `角色A + 角色B` 并文字描述环境，或从 `场景 + 角色A` 首拍用 SceneBuilder `Extend / 続きを生成` 引入 `角色B`。
2. **固定防黑边结尾后缀**：
   ```text
   full-bleed 9:16 edge-to-edge, NO black bars, NO letterbox, NO borders, no text.
   ```

### 5.2 Mode VO 纯画面镜头五段式公式（8s）

1. **景别与运镜**：`Extreme macro cinema shot` / `Sweeping wide vertical diving shot` / `Slow pull-back reveal shot`
2. **Ingredient 锚点**：用 `"this ..."` 指向所挂参考图（如 `"this tiny translucent glowing emerald-gold spore"`）。
3. **单一核心动作**：只写 **1 个** 8 秒内可舒展完成的物理或光影变化，不堆砌多段转折。
4. **风格/物种护栏**：按需加入 `"purely non-humanoid, no humans, no human faces"` 或统一动画画风词。
5. **固定防黑边后缀**：`full-bleed 9:16 edge-to-edge, NO black bars, NO letterbox, NO borders, no text.`

### 5.3 Mode C 角色开口演戏公式（首拍 8s + SceneBuilder 续写拍）

- **首拍（8s，台词 ≤ 10–12 英文词）**：
  ```text
  [Shot scale & camera movement], inside [this environment / scene description],
  [this Character A] [clear facial acting & physical gesture], speaking aloud in a [voice timbre & emotion, e.g., crisp playful young female voice]:
  "[Exact line <= 10-12 words]!"
  Spoken dialogue finishes in the first 4.5 seconds, followed by 3 seconds of expressive reaction and subtle ambient sound,
  [consistent art style anchor], full-bleed 9:16 edge-to-edge, NO black bars, NO letterbox, NO borders, no text.
  ```
- **同幕 SceneBuilder 续写拍（`Extend` / `続きを生成` 1 次，`+7s`/`+8s`，尾钩可 `+10s`）**：
  ```text
  Seamless continuation in the same scene, camera [subtle push-in / pan to Character B],
  [Character B / Character A] reacts with [gesture/expression] and replies in a [voice timbre & emotion]:
  "[Exact reply <= 10-12 words]."
  Spoken dialogue in the first 4.5 seconds, leaving 2.5 seconds of dramatic reaction beat before cut,
  full-bleed 9:16 edge-to-edge, NO black bars, NO letterbox, NO borders, no text.
  ```

---

## 6. 多语外置字幕排版速查表

| 语种 | 文件后缀 | 单行上限 | 最大行数 | 排版要点 |
|---|---|---|---|---|
| 英文（English） | `.en.srt` | ≤ 32 字符 | 2 行 | 按意群自然断行，避免介词或冠词孤立在行尾 |
| 日文（日本語） | `.ja.srt` | ≤ 16 全角字 | 2 行 | 贴合角色口吻，专有名词与人名全季统一写法 |
| 简体中文 | `.zh-Hans.srt` | ≤ 14 字 | 2 行 | 短句有力，与角色开口及情绪重音毫秒级对齐 |
