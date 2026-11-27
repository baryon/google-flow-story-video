---
name: google-flow-story-video
description: >-
  End-to-end workflow for planning, scripting, generating, downloading, and mastering serialized
  story-driven videos and 10-minute long-form films with Google Flow (flow.google.com) in two
  battle-tested modes: Mode VO (cinematic narrator voiceover + pre-Flow animatic gate) and Mode C
  (Pixar/Ghibli-style native character dialogue acting in 3x15s micro-long-takes or Last-Frame
  Relay + sidechain auto-ducking BGM), backed by a programmatic Character & Lighting Bible and
  per-shot incremental rebuild cache. Use whenever the user asks to make promotional videos,
  animated short-drama series, 10-minute long videos, lore stories, or TikTok/Shorts/YouTube series
  with Google Flow.
---

# Google Flow 连续故事与长片全流程制作指南

本技能提供一套模块化的工业级 AI 视频生产流水线，同时支持 **60s 竖屏连载短剧**与 **10 分钟级章节式长片**，覆盖**旁白史诗模式（Mode VO）**与**角色开口演戏模式（Mode C）**两种核心工艺：从「角色与光影圣经」自动拼词、零积分有声故事板预审、Chrome 接管 Google Flow 生成、真视频尾帧接力、签名 CDN 直链下载，到单镜级热替换缓存合成与全季无损打包。

- 配套自动化脚本：`./scripts/`（全局安装默认位于 `~/.agents/skills/google-flow-story-video/scripts/`）
- 数据结构与提示词公式：[manifest-schema-and-prompts.md](./references/manifest-schema-and-prompts.md)
- 最小可运行示例：[bible.sample.json](./examples/bible.sample.json)、[episodes.sample.json](./examples/episodes.sample.json)、[dialogue-episode.sample.json](./examples/dialogue-episode.sample.json)、[mapping.sample.json](./examples/mapping.sample.json)、[sample-logo.svg](./examples/sample-logo.svg)

---

## 0. 整体架构与双模式选型（动工前必判）

开拍前先根据题材选定模式，**两者的音频与分镜先后顺序不同，严禁混串**：

| 维度 | Mode VO · 旁白史诗模式 | Mode C · 角色演戏动画模式 |
|---|---|---|
| **适用题材** | 世界观史诗宣传片、10 分钟章节式纪录/传说长片、预告片 | 皮克斯 / 吉卜力式连载短剧、人物互怼/搞笑/催泪对手戏 |
| **声音来源** | **声音先行**：`build_audio_and_srt.py` 先生成统一神经旁白测定毫秒级时长，再反推镜头时长 | **演戏先行**：保留 Google Flow 原生角色口型对白与笑声/惊呼，后期叠加全程自动闪避 BGM |
| **分镜时序** | 每集/每章 **8–9 个独立 8s 镜头**（单章 `60–75s`；8–10 章即 10 分钟长片） | **三幕 × 15–18s 微长镜**（每幕续写 1 次，单集 **`48–55s`**；超长重头戏用**真视频尾帧接力法**续拍） |
| **前置预审** | 5–10 分钟长片先跑 `build_animatic.py` 出零积分**有声动态故事板**审节奏 | 先审整季总纲 + 第 1 集三幕台词表 |
| **单集合成** | `scripts/assemble_episode.py`（支持单镜增量热替换） | `scripts/assemble_dialogue_episode.py`（支持单幕增量热替换） |
| **全片/全季打包** | 共用 `scripts/package_season.py` 零重编码无损秒拼 | 共用 `scripts/package_season.py` 零重编码无损秒拼 |

```mermaid
flowchart TD
  Plan["1. 总纲拆章 + 角色光影圣经\nbible.json + compile_prompts.py 自动拼词与防超限校验"] --> Assets["2. 共享定妆资产\nIngredients 肉眼质检 + render_endslates.mjs"]
  Assets --> Mode{"选择制作模式"}
  Mode -->|"Mode VO · 旁白史诗 / 10min 长片"| VO1["build_audio_and_srt.py 声音先行\n长片可选 build_animatic.py 故事板预审"]
  VO1 --> VO2["Google Flow 分章跑 8s 镜头\n单镜 <= 2 张参考图"]
  VO2 --> VO3["提取 flow-content.google 直链\nassemble_episode.py 单镜增量缓存秒拼"]
  Mode -->|"Mode C · 角色直接演戏"| C1["先出 9:16 跨集锁脸首帧关键帧 -> 肉眼过审\nGoogle Flow Frames 仅锁首帧 + 单次续写 / 尾帧接力"]
  C1 --> C2["提取直链 + assemble_dialogue_episode.py\n48kHz PCM 拼接 + 自动闪避 BGM + 零死寂校验"]
  VO3 --> QA["5x3 十五帧全片缩略图肉眼质检\npackage_season.py 秒拼 10min+ 全季/长片"]
  C2 --> QA
```

---

## 1. 故事怎么讲（分章模块化 × 角色光影圣经）

### 1.1 总纲拆章与双层连续结构

- **先立总纲，再拆 60s 独立章节/分集**：无论是 10 集连载短剧还是 **10 分钟级 AI 长片**，切忌一次性生成一整坨长提示词。一律先把 10 分钟拆成 **8–10 个独立章节（每章 `50–75s`）**，每章只打透一个核心冲突或奇观；上一章末尾 4 秒悬念直接咬合下一章前 3 秒开屏钩子。
- **建立结构化「角色与光影圣经（`bible.json`）」**：
  - 长片或多集连载写到第 7、8 章时，手写 Prompt 极易发生画风词、色温词及 **Mode C 角色音色词（`voice_tag`）** 漂移；
  - 将全局 `style_anchor`、`lighting_anchor` 以及每个角色的 `visual_tag` + `voice_tag` + `ingredient` 存入 `bible.json`，运行 `compile_prompts.py` 自动注入所有分镜，并**在开拍前自动拦截「单镜超过 2 张参考图」与「单拍台词超过 12 词」两类致命错误**：
    ```bash
    SKILL_DIR="${SKILL_DIR:-$HOME/.agents/skills/google-flow-story-video}"

    python3 "$SKILL_DIR/scripts/compile_prompts.py" \
      --bible bible.json \
      --manifest episodes.raw.json \
      --out episodes.json \
      --sheet-out ./build/flow-shotlist.md \
      --strict
    ```

### 1.2 两种模式的黄金时序与「真视频尾帧接力法」

#### A. Mode VO 单章四段式（60–75 秒 / 8–9 个 8s 镜头）

- **① 开屏即爽 Hook（`0–6s` / `s01`）**：首句台词 + 首帧画面直接甩出反常识冲突或奇观结果；
- **② 规则具象化 & 危机（`6–28s` / `s02`–`s04`）**：具象动作交代危机，禁止说明书式科普；
- **③ 高潮兑现（`28–55s` / `s05`–`s07`）**：蜕变爆发、看穿杀招反制或绝地夺回；
- **④ 余韵 + 钩子（`55–68s` / `s08`–`s09`）**：末句点出下一章悬念，切入 `3.8s` 品牌落版（10 分钟长片的中间章节可将 `--endslate-seconds` 设为 `0` 或保留章节过渡卡）。
- **旁白语速**：英文 **125–135 词/分钟**，每镜前留 `0.30–0.45s` 呼吸，后留 `0.60–0.85s` 尾音。

#### B. Mode C 三幕微长镜（48–55 秒）与突破 15s 的「真视频尾帧接力法」

- **常规三幕（每幕 `15–18s`）**：每幕首拍 `8s` + SceneBuilder `Extend / 继续生成 / 続きを生成` **最多续写 1 次**（`+7~8s`，第三幕长悬念可 `+10s`）；每拍英文台词 **≤ 10–12 词**（前 `4.5s` 说完，留 `2.5–3s` 表情反应防切词）。**严禁在 SceneBuilder 内连续续写第 2 次（第 3 拍 `24–26s` 画质显著变糊）**。
- **突破 15s 画质衰减的王牌：真视频尾帧接力法（Last-Frame Relay）**：
  - **切勿全片每镜生硬绑定静态首尾帧**（跨构图强行 `Frames` 过渡极易在中途产生五官融化变形，也会丧失场间剪辑呼吸）；
  - 当某场重头戏确实需要 **24–32 秒同片场连续演下去**，或某段后半拍抽崩了只想局部重跑后 8 秒时，运行 `extract_relay_frame.py` 从前一段高清视频尾部自动挑出最锐利、未淡入黑场的清晰尾帧：
    ```bash
    python3 "$SKILL_DIR/scripts/extract_relay_frame.py" \
      --src "https://flow-content.google/video/<prev-clip-uuid>?..." \
      --out ./.tmp-flow-ingredients/relay-act1b.png
    ```
  - 将 `relay-act1b.png` 上传至 Flow 的 **`Frames / 首尾帧 / フレーム` 模式首帧槽位（仅锁首帧，不放尾帧！）** 生成新一段满血清晰度的 `8s` 片段——既重置了第 1 代锐度，又做到崩哪 8 秒只返工哪 8 秒。

### 1.3 文案红线、叙事连贯与每集伴随剧情文档

1. **一集只讲一个核心事件 + 点名出场**：50s 单集信息密度克制，新角色首次出场必须由对话直接喊出名字与身份；前后两集的因果桥段必须在画面或台词中演清，不让观众靠脑补填坑。
2. 正片对白/旁白与字幕中**不出现**「下载、充值、福利、代码、AI、区块链」等出戏词；品牌 Logo 与官网域名（**开拍前必须向用户核准精确域名**）只放在落版。
3. 母带画面**零硬字幕、零 UI 贴片**，同步生成 `.en.srt`（单行 ≤ 32 字符）、`.ja.srt`（≤ 16 字）、`.zh-Hans.srt`（≤ 14 字），每次最多 2 行。
4. **每集标配「YouTube / TikTok 伴随剧情文档（`<slug>-story.md`）」**：每集交付目录除 2 个 MP4 和 3 份 `.srt` 外，必须附带一份可直接复制粘贴的 `<slug>-story.md`（含英/中/日三语 **YouTube 简介版**——前情提要、本集看点、本集出场人物与当前进化形态速认、下集预告与官网链接——及 **TikTok/Shorts 短文案+标签版**），确保空降单集的观众 10 秒读懂前因后果。

---

## 2. 视频怎么做（故事板预审 + 防黑边/防串色 + 秒级热替换合成）

### 2.1 全季共享资产：先锁关键帧（Keyframe-First）防变脸铁律与矢量片尾

1. **按「角色 × 成长/升级阶段」建档母版，并优先采用「先出 `9:16` 首帧关键帧 → 过审 → Flow `Frames` 动画化」（Keyframe-First）**：
   - **为什么不用 `Ingredients to Video` 硬扛全季连载**：`Ingredients` 本质是语义重画，每开一个新 Anchor 视频模型都会重新捏一次脸与头身比，跨幕/跨集光影或景别变化时极易漂移。
   - **黄金两段式锁脸流程（强烈推荐用于多集连载）**：
     1. **分阶段母版**：每个角色（及每次升级/进化后的新阶段）定稿 1 张干净的 `9:16` 单人 3/4 全身+清晰头部母版图（严禁直接向 Flow 传多宫格三视图）。
     2. **先出每幕 `9:16` 锁脸首帧关键帧（`kf-epXX-act{1,2,3}.png`）**：用高精度生图模型同时参考「角色标准母版 + **上一集最标准的一张剧照**」，把本幕所有同框出场角色与核心道具一次性画在 Frame 0 上。
     3. **上视频前的跨集脸部过审闸门**：将三幕首帧与上一集标准剧照拼成对比图 `read_file` 肉眼过审；哪怕五官或比例微漂 10% 也在生图阶段 10 秒重抽，**未过审绝不消耗 Flow 视频积分**。
     4. **进 Flow 用 `Frames`（仅锁首帧，尾帧留空）+ Extend 动画化**：Frame 0 像素锁死后，Flow 只需让角色开口演戏与自然运镜，跨幕/跨集稳定性跃升一个数量级。同场景跨幕继续搭配 `extract_relay_frame.py` 真视频尾帧接力。
   - **图文镜像一致铁律**：Prompt 必须严格如实描述首帧/定妆图里的真实五官与质感，**严禁写入与参考图冲突的物种词**（如参考图是光滑圆眼水灵却写 `dragon`，极易漂移成尖嘴鳄鱼脸），并显式加注防漂移护栏。
   - **跨集分阶段体检与精准热返修**：每完成一幕大剧情（如 5–10 集），按「进化阶段」抽取每集三幕拼成体检图，**只针对真正换脸/跑偏的少数幕**用 Keyframe-First 单独重抽并利用合成缓存秒级热替换，无需整季推倒重做。
   - **严禁黑边后缀**：图片与视频英文 Prompt 中**切勿单独写 `dark calm lower third`**（偶发触发 Flow 在 `y ≈ 998` 硬画黑底条），统一使用：
     ```text
     full-bleed 9:16 edge-to-edge, NO black bars, NO letterbox, NO borders, no text.
     ```
   - 非人类题材强制追加 `STRICTLY NO humans, NO human faces, NO humanoid torso, NO mermaids`；任何单幕若出现**吞掉核心因果台词**或**同阶段人物变脸**，严禁迁就，直接重抽该幕并用增量缓存热替换。
2. **用无头 Chrome 渲染官方矢量片尾（禁止用 AI 画品牌 Logo）**：
   ```bash
   node "$SKILL_DIR/scripts/render_endslates.mjs" \
     --logo /path/to/official-logo.svg \
     --series "THE BOOK OF LIFE" \
     --volume "VOLUME I" \
     --domain "example.com" \
     --count 10 \
     --out-dir ./build/endslates
   ```

### 2.2 长片省积分利器：前置「有声动态故事板预审（Animatic Gate）」

制作 5–10 分钟长片（约 75–80 镜，直接跑视频需近 2000 积分）前，先在跑完 `build_audio_and_srt.py` 后一键生成零视频积分的**有声动态故事板 MP4**：

```bash
python3 "$SKILL_DIR/scripts/build_animatic.py" \
  --timeline ./build/audio/ep01/timeline.json \
  --audio ./build/audio/ep01/ep01-audio-master.wav \
  --ingredients-dir ./build/ingredients \
  --endslate ./build/endslates/ep01-endslate.png \
  --srt-dir ./build/audio/ep01 \
  --out ./build/animatics/ep01-animatic.mp4
```

先审视听节奏与分镜切换，改词或换图零积分损耗；确认无误后再进 Google Flow 批量跑动态镜头。

### 2.3 单集母带合成与「单镜级增量缓存秒级热替换」

两套合成脚本均内置 **URL 身份追踪（`raw/<id>.url`）+ SHA-256 分镜签名缓存（`*.sig`）**：当某一镜抽崩重跑、更新了 `mapping.json` / `dialogue-episode.json` 中的单条 URL 后直接重跑脚本，**脚本会自动只重拉并重编改动的那一镜，其余未改镜头 0 毫秒跳过并无损秒拼新母带**（如需强制全量重编可加 `--force`）。

- **Mode VO 合成**：
  ```bash
  python3 "$SKILL_DIR/scripts/assemble_episode.py" \
    --timeline ./build/audio/ep01/timeline.json \
    --audio ./build/audio/ep01/ep01-audio-master.wav \
    --endslate ./build/endslates/ep01-endslate.png \
    --mapping ./build/flow/ep01/mapping.json \
    --srt-dir ./build/audio/ep01 \
    --out-dir ./build/masters/ep01
  ```
- **Mode C 角色演戏合成**（内置 48kHz PCM 解码拼接防 AAC 截断、原创主题曲统一 `-18 dB` RMS 归一化、**按剧情节点平滑余弦 S 曲线动态 BGM 包络** + `sidechaincompress` 对白自动闪避、`silencedetect=n=-45dB:d=1.0` 零死寂校验与音画同步 `< 0.35s` 硬断言）：
  ```bash
  python3 "$SKILL_DIR/scripts/assemble_dialogue_episode.py" \
    --episode ./build/flow/ep01/dialogue-episode.json \
    --endslate ./build/endslates/ep01-endslate.png \
    --srt-dir ./build/subs/ep01 \
    --out-dir ./build/masters/ep01
  ```
- **配乐与 Mode C 词级对齐最佳实践**：
  1. **原创主题曲优先 + 动态分镜包络**：若项目已有主题音乐，优先在 `dialogue-episode.json`（或 `episodes.json`）的 `bgm` 字段配置 `src`、`start_seconds`（按本集情绪切乐段）、`target_rms_db`（默认 `-18.0`，防跨集响度跳变）与 `cues: [[秒数, 增益], ...]`（内置合成音床仅作兜底）。参考区间：**抖包袱/反派威慑/爆发前蓄力抽空 `0.04–0.08`**，常规对白 `0.14–0.22`，欢快过渡 `0.28–0.40`，破茧/战斗高潮 `0.62–0.78`，品牌落版 `0.50–0.54`（略低于人声不喧宾夺主）。
  2. **原声时间戳对齐与尾词防截断**：拉回 Flow 原片后，先用原声转录（如 Whisper 词级时间戳）或尾部 RMS 波形核对每幕真实开口秒数，并检查末尾 `0.3s` 是否刚吐出半个词（若切词则用 `ffmpeg -t` 精准裁在上一句停顿处），再据此写入毫秒对齐 `.srt` 与 `bgm.cues`。
- **交付前强制质检**：两套脚本均自动生成 `qa-contact-5x3.png`（全片 15 帧 `5×3` 缩略图矩阵），交付前必须用 `read_file` 打开肉眼核查：**零黑边、零串色、零风格漂移、零人形误画**。

---

## 3. 怎么操作浏览器（连接 Chrome 与操控 Google Flow）

### 3.1 开启远程调试与 macOS `EPERM` 权限授权

1. 请用户在已登录 Google 账号的 Chrome 打开 **`chrome://inspect/#remote-debugging`**，开启远程调试（`Server running at: 127.0.0.1:9222`）。
2. 若读取 `DevToolsActivePort` 报 `EPERM: operation not permitted`，**严禁尝试绕过权限**；直接提示用户在 macOS「**系统设置 → 隐私与安全性 → 完全磁盘访问权限**」中勾选当前 Agent CLI（如 `~/.local/bin/agy`）与终端应用（`Terminal.app` / `iTerm.app` / `Herdr.app`）。

### 3.2 Google Flow 标准参数（英 / 中 / 日三语对照）

1. 右上角账户设置确认积分充足，将 **Visible watermark / 可见水印 / 可視透かし** 设为 **OFF**。
2. 新建或进入项目后，**先关闭底部输入框内的 `Flow Agent` / `Flow 智能体` / `Flow エージェント` 开关**。
3. 锁定参数：

| 配置项 | 推荐值（英 / 中 / 日界面文案） | 用途与选型原则 |
|---|---|---|
| 媒体类型 | `Video` / `视频` / `動画` | 视频生成模式 |
| 生成模式 | `Frames` / `首尾帧` / `フレーム`（**连载锁脸主力**，仅挂首帧）<br>`Ingredients` / `素材`（快速探索/单镜） | **多集连载强烈推荐 Keyframe-First + `Frames` 仅挂首帧（尾帧留空）**；24s+ 真视频尾帧接力同样仅挂首帧；跨阶段形态蜕变挂首尾两帧 |
| 模型选择 | **`Omni 1.2 Flash`** | `720p + 9:16 + 8s + x1` 每镜仅 **24 积分**，一致性与口型最佳 |
| 每次生成数 | **`x1`** | 省一半积分且速度快一倍；单镜崩了单独重抽后热替换即可 |
| 微长镜续写 | `SceneBuilder` → `Extend` / `继续生成` / `続きを生成` | **新建 SceneBuilder 场景默认是 `16:9`，续写前必须先点 `アスペクト比を切り替える` 切回 `9:16`！** 同幕最多续写 **1 次** |

### 3.3 防空挂首帧、防串色、防沙盒拦截与防风控操作纪律

1. **`Frames` 首帧强挂载断言（防静默退化成纯文生视频！）**：
   - 在 Flow 的 `フレーム / Frames` 弹窗里点选关键帧条目后，**必须确认点击弹窗内的 `プロンプトに追加 / Add to prompt`**，并在提交前检查底部输入栏 DOM：**首帧槽位（`開始`）必须包含真实缩略图（`startHasImg === true`）且尾帧槽位（`終了`）为空（`endHasImg === false`）**！未确认 `startHasImg === true` 严禁按回车，否则 Flow 会静默跑成无图纯文生视频导致角色彻底换脸。
   - **首幕早筛闸门**：第 1 幕 `8s` 首拍完成后先截图核对缩略图（既是 `9:16` 竖屏 `288×512` / 枚举 `1`，又精确匹配 `kf-act1.png`），确认锁脸无误再批量推进第 2、3 幕。
2. **单镜 ≤ 2 张参考图（`Ingredients` 模式防串色铁律）**：`Omni 1.2 Flash` 在 `Ingredients` 模式单镜挂 ≥ 3 张参考图极易发生角色配色互染。若同屏需要 ≥ 2 个角色加复杂场景，直接用 **Keyframe-First + `Frames` 仅锁首帧**，一次性全锁定且零串色。
3. **工作区临时目录上传与即时清理**：将定妆图、首帧关键帧或接力尾帧放入 `<workspace>/.tmp-flow-ingredients/`（或 `.tmp-flow-keyframes/`）完成 `upload_file` 上传后，**立即 `rm -rf` 清理临时目录**。
4. **8–12 秒自然提交间隔（防风控）**：每次提交保持 **8–12 秒**间隔、并发排队 ≤ 2 条；若遇 `Unusual activity detected / 检测到异常活动 / 通常とは異なるアクティビティが検出されました`，立即停止并请用户手动刷新，严禁绕过。
5. **双线并行**：复用同一 `browser` 子代理跑第 $N+1$ 章的同时，后台运行本地合成脚本压制第 $N$ 章。

---

## 4. 怎么下载（提取签名 CDN 直链，绕开浏览器下载坑）

不在 DevTools 下点网页下载按钮（避免落成 `~/Downloads/.com.google.Chrome.XXXXXX` 隐藏文件且无法访问 `chrome://downloads/` 导致串镜）。

1. 当章/当集镜头生成完成后，直接从 DevTools 网络日志或 `<video>.currentSrc` 提取有效期约 6 小时、免 Cookie 的签名 CDN 地址（`https://flow-content.google/video/<uuid>?Expires=...&KeyName=labs-flow-prod-cdn-key&Signature=...`），整理为 JSON 交给合成脚本自动 `curl -fsSL` 拉流并记录 URL 指纹。
2. 超过 6 小时签名过期（HTTP 403）时，回 Flow 项目页重新读取最新 `currentSrc` 即可（未改 UUID 的已下载原片不会重复拉取）。
3. 仅当页面改版无法读 `<video>` URL 时，才按严格镜号顺序间隔 3–5 秒点击下载，并用 `ls -tr ~/Downloads/.com.google.Chrome.*` + `ffprobe` 校验搬移。

---

## 5. 全季 / 10 分钟长片收官一键无损打包

8–10 个章节或全季各集全部质检通过后，运行 `package_season.py` 在数秒内完成零重编码无损拼接：

```bash
python3 "$SKILL_DIR/scripts/package_season.py" \
  --manifest episodes.json \
  --masters-dir ./build/masters \
  --audio-dir ./build/audio \
  --series-slug my-story-s1 \
  --site-url https://example.com \
  --out-dir ./dist/my-story-s1
```

自动输出各章/各集独立上传包（`episodes/`）、`ffmpeg -f concat -c copy` 秒级无损合集长片（`full-movie/`，自动累加每章精确时长顺延全片多语 `.srt`）以及带 **YouTube Chapters 章节时间轴**的 `README.txt`。
