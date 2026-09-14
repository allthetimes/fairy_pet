# Fairy 桌面宠物 · 未完成事项 / 接力指南

> 本文件是**接力上下文**，不是最终规格。最终规格在 `concept/visual-spec.md`，
> 本文件只回答一件事："下次开新会话来接着做，最少需要知道哪些、现在卡在哪、下一步怎么走"。
>
> 最后更新：2026-09-15（**读图能力核验：不可用 → 按用户指令暂停**；桌宠工程已删除，回到纯视觉复刻）
> 当前里程碑：**M2 视觉复刻收尾**（只做「还原动画」这一件事，桌宠/工程部分已移除）
>
> ⏸️ **接力者先看这条**：本文件 §2.1 的全部工作都依赖"能看图"。
> 2026-09-14 已核验本环境的模型**没有**图像输入能力（含唯一有凭证的供应商整条线，详见 §2.2）。
> **恢复工作的第 0 步是换到 image-capable 模型/provider，否则不要继续做视觉校准。**

---

## 0. 一句话状态

- **已完成**：用 SVG 程序化复刻了 Fairy 2.6+ 的**几何**（圆心、5 圈环、4 根尖齿合并成单 path、中央高光球、扫描线、底盘渐变）
- **已完成**：整体呼吸脉冲 ±2.8% / 0.9s（来自 2.6+ 游戏 1080p 实测）
- **部分完成**：虹膜独立胀缩（方向证实存在，幅度 ±1.8% 是保守默认，可调）
- **未完成**：① 用**3 个新下载的 B 站视频**做二次对比校准；② 量化对比**当前模型 vs in-game 头像**的差异并修复
- **已移除（2026-09-15）**：桌宠工程（`pet-app/`）及 Tauri/Electron 工程规划 —— 用户决定回到纯视觉复刻，只保留「还原动画」相关产出
- **被环境阻断（2026-09-14 已定性，不要再试）**：本 session 的模型 `deepseek-v4-flash`
  **不支持读 PNG/JPG**。且**不是"换个模型就行"** —— 唯一有凭证的供应商 `deepseek-official`
  整个模型目录只有 flash / pro 两个，`input` 都只有 `["text"]`。**必须换带 vision 的 provider（= 换 API key）**。
  → 核验方法见 §2.2。

---

## 1. 当前已完成的产出（不要重做）

| 路径 | 角色 | 状态 |
|---|---|---|
| `concept/visual-spec.md` | **终极规格 + 配色 LUT + 两个 SVG 坑说明** | ✅ 完成 |
| `dev/fairy-lab.html` | 单文件矢量复刻（含状态机、滑块面板、SMIL 动画） | ✅ 完成 |
| `analysis/hd_avatar.png` | 2.6+ 游戏 1080p 头像清洁裁切（604×604，圆心 334.4,331.2） | ✅ 完成 |
| `scripts/{measure,notch_spec,layer_mask,polar_unwrap,analyze_fairy,compare_spec,inspect_concept,chroma_key,extract_asset,iris_compare,eye_track,iris_rotate,video_tool,measure_ingame}.py` | 一整套量化分析工具链 | ✅ 完成 |
| `.workbuddy/memory/2026-09-13.md` | 今日完整 log（12 KB） | ✅ 完成 |
| `~/.workbuddy/skills/procedural-sprite-from-reference/` | 「程序化复刻矢量」技能 | ✅ 已沉淀 |

外部依赖**已经装好**（不要再走 install 流程）：
- `yt-dlp` + `imageio-ffmpeg`（含 ffmpeg 7.1 二进制）
- Python venv：`C:\Users\allthetimes\.workbuddy\binaries\python\envs\default\Scripts\python.exe`
- Chrome：`C:\Program Files\Google\Chrome\Application\chrome.exe`
- 提示：渲染层验证走 HTTP+headless Chrome（沙箱代理会劫持 127.0.0.1，用 `--no-proxy-server` + `http://localhost`）

---

## 2. 🔴 未完成 — 优先级排序

### 2.1「找更多资料 → 重新校准」（用户最新指令）🔥 **本次接力首要任务**

#### 已下载但**没分析**的素材

```
reference/video2/BV1J9R2BNEpU.mp4      95 MB  2.7 版本相关
reference/video2/BV1dKuS69Et1.mp4      36 MB  3.1 夏活
reference/video2/BV1QXj76mEaR.mp4       4 MB  2026-06-20 短视频
```

**这些是关键新料**：要把它们的 Fairy 镜头抠出来再测一次，
验证 2.6+ 时期的虹膜状态数（睁眼 / 半闭 / 全闭 / 故障态？）、
呼吸频率是否真的稳定在 0.9s、颜色是否有后期调整。

#### `hd_avatar.png`（in-game 1080p）已量但**还没合进模型**

实测到的 in-game 中心 + 环边界：

| 实测半径 (px) | 实测颜色 | 对应 wiki 2.6 u | 当前模型半径（u×100） |
|---|---|---|---|
| 0–35 | `#262F88`（暗中心） | 0–0.165 | 0–21.5 |
| 35–37 | 浅薄夹层 `#6A7BB8` | 0.165–0.174 | —— 漏！ |
| 37–55 | 蓝色环 `#4470C4` | 0.174–0.259 | 21.5–30.6 |
| 55–58 | 浅薄夹层 `#B0B5D8` | 0.259–0.273 | —— 漏！ |
| 58–85 | 浅紫蓝 `#8A94C8` | 0.273–0.400 | 30.6–44.7 |
| 85–87 | 浅薄夹层 `#9DA3C4` | 0.400–0.410 | —— 漏！ |
| **88–127** | **粗白主环 `#D1CCD7`** | **0.415–0.598** | **44.7–64.5** |
| 127–130 | 浅夹层 | 0.598–0.612 | —— 漏！ |
| 130–200 | 暗靛蓝 + 高饱和外蓝 | 0.612–0.941 | 64.5–100 |

**问题清单**（不要直接重画，先把这几个搞清楚）：
1. **薄夹层**（35–37、55–58、85–87、127–130 in-game）：是抗锯齿伪影还是真实设计层？
   - 验证方法：换更小分辨率的同一帧，看同样 r 上是否仍有；或者取 raw 源数据
2. **白环外径**：当前模型 64.5，in-game 64.5 也是 0.598×212.5/100 ≈ 127 px——**完全对** ✓
3. **粗白环内外边界**：当前 64.5 是外缘，内缘是 44.7。in-game 127 vs 88 → 比例 1.50，
   当前模型 1.44——**当前白环窄了约 4%**
4. **外圈蓝起止**：in-game 130–200 (70 px)，当前模型 78.1–100 (21.9 u×R/100)，
   in-game 是 212.5×(0.612~0.941)=131–200 px → **当前外蓝完全对 ✓**
5. **暗靛蓝带**：in-game 介于白环与外蓝之间（130~131 几乎相邻）——当前模型 64.5→78.1 (13.6 u)
   → 比 in-game 看到的窄约 6 px。**当前靛蓝带偏宽**
6. **暗中心**：in-game 0–35，比例 0.165；当前模型 0–21.5 = 0.101 → **当前中心瞳孔偏小**

详细数据在 `scripts/hd_hd_avatar.json`（如果丢了，重新跑 `scripts/measure_ingame.py`）。

#### 接下来具体动作

```bash
V="C:/Users/allthetimes/.workbuddy/binaries/python/envs/default/Scripts/python.exe"

# A. 把 3 个新视频各抽 8~16 帧关键帧
"$V" scripts/video_tool.py frames reference/video2/BV1J9R2BNEpU.mp4 analysis/v2_1 --fps 2 --tile 8
"$V" scripts/video_tool.py frames reference/video2/BV1dKuS69Et1.mp4 analysis/v2_2 --fps 2 --tile 8
"$V" scripts/video_tool.py frames reference/video2/BV1QXj76mEaR.mp4  analysis/v2_3 --fps 2 --tile 8

# B. 从分镜图找头像出现的区段（每个视频可能只占 20~40 秒的镜头）
"$V" scripts/video_tool.py frames reference/video2/BV1J9R2BNEpU.mp4 analysis/v2_1_seq \
  --ss 50 --t 30 --fps 5 --crop 1500,200,500,500
# 然后人眼看分镜图（用脚本生成 + 给时间戳标注）找出 Fairy 入镜段

# C. 对每个 Fairy 镜头，测径向 profile
"$V" scripts/measure_ingame.py analysis/fairy_v2_1.png  # 类比 hd_avatar
# 输出每个半径的平均色 + 边界检测

# D. 重新比对：综合 wiki 2.6 + in-game + v2.1/v2.2/v2.3 + 当前模型
"$V" scripts/compare_spec.py                              # 当前 → wiki 对比
# 写一个 multi_reference_diff.py 对 4 张图做总览
```

### 2.2 「读图能力缺失」— **2026-09-14 已核验为不可用，已按用户指令暂停** ⏸️

**用户 2026-09-14 指令**：「读取 md 文件，继续未完成的项目，**一定要有读图能力，没有的话暂停**」。
→ 核验结论：**没有** → **已暂停**，未对任何视觉产物做盲改。

#### 核验证据（3 条独立证据，结论一致）

| # | 检查 | 结果 |
|---|---|---|
| 1 | 直接 `read_image analysis/hd_avatar.png` | `Error: … model "deepseek-v4-flash" does not declare image input` |
| 2 | `~/.dsh/settings.yaml` → `agent-default-model` | `provider: deepseek-official` / `model: deepseek-v4-flash` |
| 3 | `…/pi-ai/dist/providers/data/deepseek.json` 全量枚举 | 只有 `deepseek-v4-flash` / `deepseek-v4-pro`，**两者 `input` 皆仅 `["text"]`** |

#### ⚠️ 关键结论：换模型救不了，得换 provider

第 3 条是决定性的。唯一有凭证的供应商（`.credentials.yaml` 里只有一把 `DEEPSEEK_API_KEY`）
**整个目录里没有任何 image-capable 模型**，所以 `deepseek-v4-pro` 同样不能读图。

harness 自带的其它 provider 目录（openrouter / opencode / anthropic / google / qwen …）里
**有大量** `input:["text","image"]` 的模型，但本 session **没有对应 API key**。

**恢复工作的第 0 步（硬前提）**：换到 image-capable 模型 —— 要么给 session 配上
带 vision 的 provider key，要么切到一个默认模型支持图像的 profile。
`profiles/web/cordis.patch.yml` 当前是空 `[]`，`cordis.yml` 无 model 覆盖，
所以没有隐藏的自定义 vision provider 可用。

#### 数值路线的定位（保留，但降级为辅助）

数值工具（`measure.py` / `measure_ingame.py` / `compare_spec.py` → CSV/JSON）**不是读图的替代品**，
只是"看图之后做精确量化"的辅助。09-13 的经验已经说明：纯数值推形状会反复翻车
（亮度阈值低估宽度 1.5~2°、互相关测转速自相矛盾）。
→ 所以**不要**在无读图能力时继续推进 §2.1 的视觉校准。

仍待补的闭环工具（**放到恢复之后做**）：
- `scripts/fairy_diff_report.py`：输入参考 PNG + 我方 model 截图（headless Chrome 起 `dev/fairy-lab.html?bare=1`），
  输出径向 profile 对照 / 每半径色差 / SSIM·L2 总分 / 关键半径 fit 误差。

### 2.2b 09-13 未登记的遗留脚本（本次体检发现）🔍

`scripts/scan_fairy_segments.py`（09:51）**没写进 09-13 的 log**，且**没跑通**：

- `analysis/scan_v2_3/_scan.log` 头部写 `fps=0.5` / `threshold_method=ratio=0.7`，
  但**当前源码写出来的格式完全不同**（integral-SSD + `min+40%`）→ **日志与脚本版本对不上**。
- 只落盘 2 帧 → `BV1QXj76mEaR.mp4` 可解码内容 ≈ 4 秒。
- 打分无区分度（86.22 / 86.55）→ 用 `hd_avatar.png` 的**圆形** ROI 当模板，
  却在**矩形**窗口上算 SSD，圆外背景把分数淹平。
- `BV1J9R2BNEpU.mp4`（95MB）、`BV1dKuS69Et1.mp4`（36MB）**完全没扫过**。

→ **别信这个脚本的输出**；修法见 §3.9。而它本来就该由"抽帧拼版 → 人眼看"来替代 ——
这正是读图能力的地方。

### 2.3 角色卡（LLM 友好） ✅ **已完成（2026-09-14，保留中）**

四份均已建好，作为独立产物保留（不依赖桌宠工程）：
- `concept/llm-character-card.md` — 角色设定（身份 / 自我认知 / 人称 / 语言指纹 / 语气 / 情境反应 / 范例对话 / 禁忌清单 / LLM 接入说明）✅
- `concept/window-behavior.md` — 桌宠行为配置（窗口 / 状态机 / 交互响应 / 台词系统 / 系统控制 / 设置窗 / 性能 / LLM 接口契约）✅
- `concept/character-card.json` — **机读版（Character Card V2 规范）**，将来接 LLM 直接可用 ✅
- `concept/fairy-voice-lines.md` — 台词风格参考（语言指纹 + 官方原句摘录 + 反面清单）✅

> 注：以上角色卡/台词产物 2026-09-15 用户决定**保留**（虽然桌宠工程已删，它们仍是 Fairy 人设的独立产出）。

**⚠️ 上面原假设已被推翻**：不再走"温和慵懒甜美助手"路线。
用户 2026-09-14 明确要求"发言要符合人设"，查证官方游戏内台词后确认：
Fairy 的真实人设是 **AI 播报腔 + 毒舌 + 傲娇 + 自恋 + 吐槽役**，关心藏在技术话术里。
她的核心语言特征是「主人」称呼 + 系统播报腔 + **敬语包装嘲讽**（用「您」+ 平静陈述 + 补刀转折）。

### 2.5 一键发版脚本（用户 9-11 约定） 🚀 **未开工**

约定：**「开始推送」= 推送代码 + 发布 Release**，必须两半都做。
- 复用 `tiny_alarm/scripts/release.mjs` 当脚手架
- 流程：版本号 → `git tag` → `git push --tags` → `electron-builder` → 上传 Release → 校验产物 SHA-256

---

## 3. 🟡 已知坑 / 必须避开

### 3.1 SVG `transform-origin` 在 SVG 元素上不可靠

齿轮旋转若用 CSS `animation: rotate(...)`，`transform-origin: center` + `transform-box: view-box` **实测仍无效**，
齿轮会绕远在画外的点公转。**只用 `<animateTransform>` SMIL**，它以用户坐标 (0,0) 为基准。
→ 详见 `visual-spec.md` §8.5 坑一。

### 3.2 克隆 SVG 时重复 id 让填充变黑

克隆 `<defs>` 与原 svg 同名时，`url(#grad)` 解析到第一个匹配项；
若克隆体在 `display:none` 子树里 → paint server 不可见 → 渲染变黑。
**必须**给克隆体所有 `id` 加前缀并同步重写 `url(...)` 引用。
→ 详见 `visual-spec.md` §8.5 坑二。

### 3.3 量化测量不要用亮度阈值

`lum<62` 判"深色"会**系统性低估宽度 1.5~2°**（一侧偏亮时会吞掉边缘像素）。
**改用色系边界**（如靛蓝层 `B<178 且 B-R>55`），且两边用同一判据量。
→ 详见 `concept/visual-spec.md` §3 表 + `analysis/notch_*.png`。

### 3.4 互相关测转速不可靠

`iris_rotate.py` 在对称图形上给出自相矛盾的角度。
**改用**：(a) 归一化尺寸差分；(b) 单一标志半径的角向扫描；(c) 帧间固定角度对齐。

### 3.5 shadcn/trash/rm 必须用专用工具

文件清理走 `cp` + 备份，不要 `rm -rf`；参考 `personal_files_safety` 段。

### 3.6 国内下载 python wheel 要带清华镜像

否则 30MB+ 的 yt-dlp 会卡 5 分钟以上。

### 3.7 Chrome headless 截透明底

加 `--default-background-color=00000000`，且必须走 `http://localhost` 而非 `127.0.0.1`（沙箱代理劫持）。

### 3.8 「读图能力」必须先核验，不能假设 ⭐

`read_image` 在无图像输入的模型上会**直接报错**，不会静默降级。
**30 秒核验法（3 条）**：
1. `read_image` 随便读一张 PNG → 看是否报 `does not declare image input`；
2. 看 `~/.dsh/settings.yaml` 的 `agent-default-model`；
3. 查 `…/pi-ai/dist/providers/data/<provider>.json` 里该 model 的 `input` 数组有没有 `"image"`。

→ **第 3 条最重要**：能区分「这个模型不行」和「这家供应商根本没有 vision 模型」。
后者换模型也救不了，**必须换 provider（= 换 API key）**。

### 3.9 圆形模板别用矩形 SSD 匹配

`scan_fairy_segments.py` 拿 `hd_avatar.png` 的圆形 ROI 当模板，却在**矩形**窗口上算 SSD，
圆外背景把分数淹平（实测 86.22 vs 86.55，**完全无区分度**）。
→ 要么改成**圆形掩膜内归一化** SSD，要么老实用「抽帧拼版 + 人眼看」（后者才是读图的正用法）。

### 3.10 脚本改版后旧日志会骗人

`analysis/scan_v2_3/_scan.log` 的格式与当前 `scan_fairy_segments.py` 源码**不一致**
（日志 `threshold_method=ratio=0.7` vs 源码 `min+40%`）。
→ 拿日志下结论前，先确认日志和脚本是同一版本。

### 3.11 本仓库还不是 git 仓库

`git -C E:\mypro\fairy_pet rev-parse` → `fatal: not a git repository`。
§2.5 的「一键发版」前必须先 `git init` + 建远端。

---

## 4. 🟢 当前模型 `dev/fairy-lab.html` 的可调项（不用重画，滑块就行）

实装面板里有这些滑块，运行时实时改：
- 呼吸周期（0.6–1.2 s，默认 0.9）
- 呼吸幅度（0–5%，默认 2.8）
- 虹膜幅度（0–5%，默认 1.8）
- 闪烁最小/最大间隔
- 故障态触发概率

URL 钩子：
- `?compare=1` — 出三方对比（wiki 2.6 / wiki 1.0 / 模型）
- `?bare=1` — 透明底（给脚本截图）
- `?core=N` — 强制核心直径 px（默认 250）
- `?freeze=N` — 冻结到 N 秒（依赖 SVG `pauseAnimations` + `setCurrentTime`）
- `?autoblink=N` — 强制 N 秒眨一次（debug 用）
- `?half=H&tip=T` — 强制尖齿半角与顶端 u（批量扫参）

---

## 5. 🧭 推荐的下一步工作流（用户重新上线时）

> ⏸️ **2026-09-14 状态：停在第 0 步。** 用户指令是「没有读图能力就暂停」，已照办。

```
0. ⛔【硬前提，不做就别往下走】换到 image-capable 模型 / provider
      —— 本 session 唯一有 key 的 deepseek-official 全线无 vision 模型（§2.2）
1. 跟 2.1 节做 A→D（3 个新视频抽帧 → 拼版 → 人眼定位 Fairy 出镜段）
   注意：BV1QXj76mEaR.mp4 只有 ~4 秒可用；另外两个大视频完全没碰
   注意：scan_fairy_segments.py 没跑通、别信它的输出（§2.2b / §3.9）
2. 把 2.2 节的 fairy_diff_report.py 写完（半小时能搞定）
3. 校准 visual-spec.md  →  同步到 fairy-lab.html  →  保存 _clean.html
4. 写 LLM 角色卡（2.3 已有初版）+ 截图给用户评审
5. git init 先补上（§3.11）→ 再 release.mjs（如需要发版）
```

---

## 6. 速查：关键文件路径速记

| 用途 | 路径 |
|---|---|
| 终极规格 | `E:\mypro\fairy_pet\concept\visual-spec.md` |
| 单文件复刻 | `E:\mypro\fairy_pet\dev\fairy-lab.html` |
| 09-13 log | `E:\mypro\fairy_pet\.workbuddy\memory\2026-09-13.md` |
| **09-14 log（读图核验 + 暂停点）** | `E:\mypro\fairy_pet\.workbuddy\memory\2026-09-14.md` |
| in-game 头像 | `E:\mypro\fairy_pet\analysis\hd_avatar.png` |
| wiki 2.6 立绘 | `E:\mypro\fairy_pet\reference\fairy_2.6.png` |
| 三个新视频 | `E:\mypro\fairy_pet\reference\video2\*.mp4` |
| 未跑通的扫描脚本 | `E:\mypro\fairy_pet\scripts\scan_fairy_segments.py` |
| 完整脚本 | `E:\mypro\fairy_pet\scripts\` |
| 已沉淀技能 | `~/.workbuddy/skills/procedural-sprite-from-reference\` |
| 复用工程 | `E:\mypro\tiny_alarm\` (Electron 34 + Vite 6 + TS) |
| Python venv | `C:\Users\allthetimes\.workbuddy\binaries\python\envs\default\Scripts\python.exe` |
| Chrome | `C:\Program Files\Google\Chrome\Application\chrome.exe` |
| **本 session 设置** | `C:\Users\allthetimes\.dsh\settings.yaml`（含 `agent-default-model`） |
| **供应商模型目录** | `D:\devApp\nvm\v22.23.0\node_modules\@deepseek-ai\dsh\node_modules\@earendil-works\pi-ai\dist\providers\data\` |
