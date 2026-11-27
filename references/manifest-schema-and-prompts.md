# Manifest Schemas, Character Bible & Google Flow Prompt Formulas

本文档定义角色与光影圣经（`bible.json`）、Mode VO（旁白史诗/长片模式）、Mode C（角色演戏对话模式）的 JSON 规范、内置音床预设与提示词公式。

---

## 1. 角色与光影圣经规范：`bible.json`（传给 `compile_prompts.py`）

跨多集或 10 分钟（70–80 镜）长片制作时，先建立统一的 `bible.json`，由 `compile_prompts.py` 自动注入每镜提示词并前置拦截「>2 张参考图」与「台词超词数」错误：

```json
{
  "style_anchor": "stylized hand-painted anime cinema aesthetic, rich atmospheric depth",
  "lighting_anchor": "deep twilight indigo shadows with warm amber lantern rim light",
  "aspect_suffix": "full-bleed 9:16 edge-to-edge, NO black bars, NO letterbox, NO borders, no text.",
  "non_humanoid_guard": false,
  "characters": {
    "luna": {
      "name": "Luna",
      "ingredient": "char-luna.png",
      "visual_tag": "this petite silver-haired lantern keeper wearing a weathered indigo cloak",
      "voice_tag": "crisp, expressive young female voice with playful urgency"
    },
    "pip": {
      "name": "Pip",
      "ingredient": "char-pip.png",
      "visual_tag": "this tiny clockwork brass owl with glowing amber glass eyes",
      "voice_tag": "dry, deadpan miniature mechanical voice"
    }
  },
  "locations": {
    "watchtower": {
      "ingredient": "loc-watchtower.png",
      "visual_tag": "this wind-swept cliffside stone watchtower lit by a swaying brass lantern"
    }
  }
}
```

### 占位符与结构化简写语法

1. **内联占位符**：在任意 `flow_prompt` 中写 `{{char:luna}}`、`{{voice:luna}}`、`{{loc:watchtower}}`，`compile_prompts.py` 会自动替换为对应描述词，并将关联的 `ingredient` 文件名记入该镜 `ingredients` 数组（超过 2 张自动报警/阻断）。
2. **Mode C 结构化简写**：分镜条目可省略手写 `flow_prompt`，直接填写 `"location": "watchtower"`、`"speaker": "luna"`、`"camera": "Medium vertical shot"`、`"action": "lifts the lantern in disbelief"`、`"line": "Wait—who lit the signal fire?!"`，脚本会自动拼出完整的带音色锚点与 `4.5s 对白 + 3s 反应` 护栏的标准英文 Prompt。

---

## 2. Mode VO 清单规范：`episodes.json` & `mapping.json`

`build_audio_and_srt.py`、`build_animatic.py` 与 `package_season.py` 共用 `episodes.json`：

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

### `mapping.json`（传给 `assemble_episode.py`）

将分镜 ID 映射到 Google Flow 签名 CDN 视频直链或本地 `.mp4` 路径（重抽某镜后只需替换该镜 URL，脚本会自动识别 UUID 变更并仅重编该镜）：

```json
{
  "s01": "https://flow-content.google/video/2da26bb9-4ab1-45b7-96ae-732a2604f615?Expires=...&KeyName=labs-flow-prod-cdn-key&Signature=...",
  "s02": "https://flow-content.google/video/1becbb76-938a-4569-a8b2-12602b4f0c29?Expires=...&KeyName=labs-flow-prod-cdn-key&Signature=..."
}
```

---

## 3. Mode C 角色演戏清单规范：`dialogue-episode.json`

传给 `assemble_dialogue_episode.py`，用于合成三幕微长镜（或经尾帧接力扩展的多段演戏片段）。若项目有原创主题音乐，推荐填写可选的 `bgm` 块以启用「按情绪切片 + 统一 RMS 归一化 + 平滑余弦 S 曲线动态包络」：

```json
{
  "ep": 1,
  "slug": "ep01",
  "title_en": "The Burnt Lantern",
  "title_ja": "焦げたランタン",
  "title_zh": "烧焦的提灯",
  "tone": "wonder",
  "endslate_seconds": 3.8,
  "bgm": {
    "src": "/path/to/project-theme.mp3",
    "start_seconds": 60.0,
    "target_rms_db": -18.0,
    "volume": 0.86,
    "cues": [
      [0.0, 0.16],
      [9.4, 0.06],
      [13.8, 0.72],
      [30.5, 0.22],
      [38.5, 0.05],
      [45.5, 0.54]
    ]
  },
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

### 动态 BGM 包络（`bgm.cues`）参考档位

`build_audio_and_srt.py`（Mode VO）与 `assemble_dialogue_episode.py`（Mode C）均支持在单集对象中声明 `bgm`（`src` 为空或省略时自动回退至内置 `tone` 合成音床）：

| 剧情段落 | 推荐 `cues` 增益 | 听感效果 |
|---|---|---|
| 冷面抖包袱 / 反派威胁 / 爆发前蓄力 | `0.04 – 0.08` | 短暂抽空背景乐，放大台词张力与喜剧/惊悚反差 |
| 常规对白 / 拌嘴交锋 | `0.14 – 0.22` | 轻柔铺底不抢人声，配合 `sidechaincompress` 清晰贴耳 |
| 轻松日常 / 探索过渡 | `0.28 – 0.40` | 活泼轻盈、推动情绪流动 |
| 蜕变爆发 / 战斗高潮 / 反转爽点 | `0.62 – 0.78` | 动作与交响精准撞点，形成影院级听觉起伏 |
| 品牌片尾落版（`endslate`） | `0.50 – 0.54` | 主题旋律温柔推起收尾，略低于人声且不突兀 |

---

## 4. 内置 `tone` 立体声氛围音床预设

`build_audio_and_srt.py` 与 `assemble_dialogue_episode.py` 均内置以下 8 种 48kHz 立体声调性音床（也可通过 `--bgm` 传入外部音乐）：

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

## 5. Ingredients、`Frames` 首尾帧与视频提示词公式

### 5.1 Ingredients 分阶段定妆母版提示词模板（严禁写 `dark lower third`）

每个角色及每次进化升级后的新阶段，都应先生成并定稿 **1 张单人 3/4 全身+清晰头部母版图**（切勿把多宫格三视图直接喂给 Flow `Ingredients`）：

```text
3/4 full-body character model portrait showing clear head/facial features and full body proportions,
[Subject / Environment core design], [consistent art style & lighting palette],
subject centered in the upper-middle frame with clean uncluttered space in the lower quarter,
full-bleed 9:16 edge-to-edge, NO black bars, NO letterbox, NO borders,
STRICTLY NO text, NO watermark, NO UI, NO split screen, NO multi-view grid.
```

- **非人类题材必加**：`STRICTLY NO humans, NO human faces, NO humanoid torso, NO mermaids.`
- **图文镜像一致（防跨幕变脸）**：`bible.json` 的 `visual_tag` 必须如实匹配定妆图实际五官与质感，不混写冲突物种词，必要时显式锁定眼型与皮肤质感（如 `exact face from reference image, big round eyes, smooth skin, NO slit reptile eyes, NO coarse scales`）。
- **动画风格题材必加**：固定画风锚点词，逐张 `read_file` 肉眼确认无写实漂移、无文字、无黑边后再上传；升级前后的各阶段在 `bible.json` 中分键建档（如 `hero_stage1` / `hero_stage2`），同一阶段内跨集严禁换图。

### 5.2 何时用 `Ingredients` vs 何时用 `Frames（首尾帧）`

| 场景 | 正确模式 | 挂图方式 |
|---|---|---|
| 常规叙事分镜 / 角色开口演戏 | `Ingredients / 素材` | 挂 **1–2 张**定妆图（严禁 ≥ 3 张防串色） |
| **同场超过 15s 继续演戏 / 局部重抽后 8s** | `Frames / 首尾帧`（**真视频尾帧接力法**） | 用 `extract_relay_frame.py` 取上一段清晰尾帧放进**首帧槽位**（**不放尾帧**），保持第 1 代满血清晰度且无果冻变形 |
| **跨阶段形态进化 / 破茧蜕变 / 时空平滑流转** | `Frames / 首尾帧` | 首帧放形态 A 定妆图，尾帧放形态 B 定妆图，描述流体蜕变光影动作 |

### 5.3 Mode VO 镜头五段式公式（8s）

1. **景别与运镜** + 2. **`"this ..."` 素材锚点** + 3. **单一 8s 物理/光影动作** + 4. **画风与防人形护栏** + 5. **固定后缀**：`full-bleed 9:16 edge-to-edge, NO black bars, NO letterbox, NO borders, no text.`

### 5.4 Mode C 角色开口演戏公式（首拍 8s + 续写/接力拍）

```text
[Shot scale & camera movement], inside [this environment / scene description],
[this Character A] [clear facial acting & physical gesture], speaking aloud in a [voice_tag from bible.json]:
"[Exact line <= 10-12 words]!"
Spoken dialogue finishes in the first 4.5 seconds, followed by 3 seconds of expressive reaction and subtle ambient sound,
[style_anchor], [lighting_anchor], full-bleed 9:16 edge-to-edge, NO black bars, NO letterbox, NO borders, no text.
```

---

## 6. 多语外置字幕排版速查表

| 语种 | 文件后缀 | 单行上限 | 最大行数 | 排版要点 |
|---|---|---|---|---|
| 英文（English） | `.en.srt` | ≤ 32 字符 | 2 行 | 按意群自然断行，避免介词或冠词孤立在行尾 |
| 日文（日本語） | `.ja.srt` | ≤ 16 全角字 | 2 行 | 贴合角色口吻，专有名词与人名全季统一写法 |
| 简体中文 | `.zh-Hans.srt` | ≤ 14 字 | 2 行 | 短句有力，与角色开口及情绪重音毫秒级对齐 |

---

## 7. 单集 YouTube / TikTok 伴随剧情文档模板（`<slug>-story.md`）

每集交付目录标配 6 个文件：`*-clean.mp4`、`*-multilang.mp4`、`.en/.ja/.zh-Hans.srt` 与 `<slug>-story.md`。文档需确保**只点开这一集的空降观众**读完简介就能立刻看懂，结构如下（按发布语种提供 EN / ZH / JA）：

```markdown
# Episode N — <English Title> /《中文标题》/《日本語タイトル》

## YouTube Description (Copy & Paste)
- **Previously on <Series>**（2 句前情提要：交代上集发生了什么、主角当前目标）
- **What Happens in Episode N**（3–4 句大白话本集剧情，不堆砌未解释术语）
- **Characters in This Episode**（本集出场人物列表：名字 + 颜色/外观特征 + 身份 + 若升级则标明新形态）
- **Coming Up Next (Episode N+1)**（1 句下集悬念引子 + 官网链接）

## TikTok / Shorts Caption (Short Copy & Paste)
- 2–3 句高钩子短文案 + 前情括号提示 + 官网与核心标签（EN / ZH / JA）
```
