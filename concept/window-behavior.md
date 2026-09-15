# Fairy 桌宠 · 行为配置

> **用途**：桌宠行为的权威规格。改交互、加功能前先读这里。
> **配套**：`concept/llm-character-card.md`（角色设定）、`concept/character-card.json`（机读角色卡）。
> **状态**：Phase 0–7 **已实现**（2026-09-14）；Phase 8 眼睛跟踪未做。
> **实现位置**：`pet-app/src-tauri/`（Rust 侧）、`pet-app/ui/`（前端）。

---

## 1. 窗口

| 项 | 值 | 说明 |
|---|---|---|
| 尺寸 | 420 × 420 | 圆盘 400px 居中，四周留气泡余量 |
| 透明 | `transparent: true` | 背景完全透明，只显示环形核 |
| 边框 | `decorations: false` | 无标题栏、无边框 |
| 置顶 | `alwaysOnTop: true` | 常驻最前 |
| 任务栏 | `skipTaskbar: true` | 不占任务栏 |
| 缩放 | `resizable: false` | 固定尺寸 |
| 阴影 | `shadow: false` | 避免方框阴影外露 |
| 拖拽 | 全窗口可拖 | 手动实现，见 §3.1 |

## 2. 状态机

保留 fairy-lab 的状态能力，桌宠实际使用的只有前两个：

| 状态 | 触发 | 视觉 |
|---|---|---|
| `idle` | 默认 | 呼吸 + 齿轮旋转 + 扫描线 + 高光球漂移 |
| `closed` | 单击切换 | 叠加闭眼帽檐（端点固定、底缘按实测波形开合） |
| `talking` | 说话时 | 整体 brightness ↑ + 齿轮/辉光加速（`setRates(true)`） |
| `clicked` | 单击瞬间 | `clickpunch` 缩放弹跳 0.42s |
| `glitch` | 保留（未接触发器） | RGB 分离故障效果 0.6s |

**切换规则**：单击 → `idle` ⇄ `closed` **直接切换**（不做眨眼过渡，符合 §12.8 的要求）。

## 3. 交互响应

### 3.1 点击 vs 拖拽的区分（核心机制）

不使用 `data-tauri-drag-region`（它会吞掉 click 事件）。改用手动判别：

```
mousedown  → 记录起点 (x, y)
mousemove  → 位移 > 6px  ⇒ 判定为拖拽：startDragging() + setRates(true) + sayDrag()
mouseup    → 位移 ≤ 6px  ⇒ 判定为点击：setState 切换 + say('click')
```

**阈值 6px** 是经验值：小于它容易把"手抖的点击"误判为拖拽，大于它拖拽响应会很迟滞。

### 3.2 响应表

| 操作 | 视觉反馈 | 台词 | 节流 |
|---|---|---|---|
| **单击** | 切换闭眼/睁眼 + clickpunch 弹跳 | `say('click')` | 无 |
| **悬停** | `.pet:hover .float{filter:brightness(1.15)}` | 无 | — |
| **拖拽** | 齿轮/辉光转速加快 + 光标变 grabbing | `say('drag')` | **8s** |
| **空闲** | 无变化 | `say('idle')` | 见 §4.2 |
| **右键** | 阻止系统菜单（正式菜单在托盘里） | 无 | — |

**hover 用 `filter: brightness()` 而不是 transform** —— 避开 SVG `transform-origin` 的坑（见 `visual-spec.md` 坑 ①）。

## 4. 台词系统

### 4.1 台词池

| 类别 | 条数 | 位置 | 语气要点 |
|---|---|---|---|
| `click` | 10 | `pet-app/ui/lines.json` | 播报式应答 + 顺口吐槽 |
| `drag` | 8 | 同上 | 技术腔抗议位移 |
| `idle` | 12 | 同上 | 观察式独白 + 藏起来的关心 |

- **内容受 `concept/llm-character-card.md` 约束**（语言指纹五条 + 禁忌清单）。
- 池子为空或加载失败时用 `index.html` 里的 `FALLBACK` 兜底句。
- **避免连续重复**：`pick()` 会重抽，直到与上一条不同。

### 4.2 打字机与气泡

| 项 | 值 |
|---|---|
| 打字速度 | 35 ms / 字 |
| 停留时间 | 打字完成后 4 s 自动淡出 |
| 淡出过渡 | opacity 0.28s |
| 气泡位置 | 圆盘上方（`bottom:100%` 略压住圆盘），水平居中 |
| 气泡宽度 | `width:max-content` + `max-width: 440px·s`（09-15 从 320 加宽；⚠️ abspos+left:50% 必须显式 width:max-content，否则收缩宽度被"left 后剩余 200px"卡死，max-width 永不生效） |
| 防顶部裁切 | `clampBubble()`：打字期间逐帧量高，超高时整体下移（多压圆盘），保证 top ≥ 8px |
| 最大宽度 | 440px·s，超长自动换行（**不要用 nowrap**，会让长句溢出） |
| 点击穿透 | `pointer-events: none` —— 气泡显示期间仍可拖拽/点击 |
| 样式状态 | **临时样式**：深色半透明 + 青蓝描边。等用户提供游戏内截图后仿照重做 |

### 4.3 触发频率

| 类别 | 规则 |
|---|---|
| click | 每次点击必触发 |
| drag | 8s 节流（`lastDragSay`） |
| idle | 随机等待 `CFG.idleMin` ~ `CFG.idleMin + 35` 秒，循环 |

## 5. 系统控制

| 功能 | 实现 |
|---|---|
| 托盘菜单 | 显示/隐藏、设置、退出 |
| 全局快捷键 | **Alt+F1** 显示/隐藏 |
| 单实例 | 二次启动聚焦已有主窗（`single-instance` 插件） |
| 隐藏时省电 | Rust `emit('pet-hidden')` → 前端 `svg.pauseAnimations()` |
| 显示时恢复 | `emit('pet-shown')` → `unpauseAnimations()` |
| 空闲降帧 | 失焦 **5 分钟** → 暂停扫描线 + 辉光（保留呼吸核心）；`mousemove/mousedown/keydown/focus` 任一交互恢复 |
| 开机自启 | `tauri-plugin-autostart`，设置窗口内开关 |

**注意**：SMIL 没有单元素 pause，空闲降帧用 `beginElement()` / `endElement()` 控制起停。

## 6. 设置窗口

独立 `WebviewWindow`（460×500，普通有框窗口，惰性创建）。

| 滑块 | 范围 | 默认 | 存储键 |
|---|---|---|---|
| 呼吸周期 | 0.3 – 3 s | 0.867 | `pet.breath` |
| 呼吸强度 | 0 – 200 % | 100 | `pet.breathStr` |
| 齿轮周期 | 6 – 24 s | 18.13 | `pet.gear` |
| 空闲台词间隔 | 15 – 120 s | 25 | `pet.idleMin` |

**通信链路**：
```
滑块 input → localStorage 持久化
          → emit('settings-changed', payload)
          → 主窗 listen → 更新 CFG → applyBreath() / applyGear() / scheduleIdle()
```
主窗启动时从 `localStorage` 恢复 `CFG`。

## 7. 性能与稳定性

| 指标 | 实测 / 目标 |
|---|---|
| 冷启动内存 | **~72 MB** |
| 30 秒后内存 | ~72 MB（**+4KB，噪声级**） |
| 隐藏状态 | SMIL 全停，CPU 接近 0 |
| 失焦 5 分钟后 | 停扫描线+辉光，仅保留呼吸 |
| 长时间运行目标 | 2 小时无泄漏、反复显隐 50 次不异常 |

## 8. 对 LLM 的接口契约（未来接入用）

**当前状态**：未接入（用户 2026-09-14 决定先做随机台词输出）。当前用 §4.1 的随机池代替。

接入时需遵守：

| 项 | 约定 |
|---|---|
| 接口形态 | OpenAI 兼容（见 `UNFINISHED.md` §2.4 M7） |
| System 内容 | `concept/character-card.json` 的 `system_prompt` + `description` + `personality` |
| Few-shot | `mes_example` 字段 |
| 输出长度 | **≤ 60 字**（气泡限 3 行内） |
| 后处理 | 剥离 markdown、剥离旁白括号（「（小声）」这类自语除外） |
| 频率 | 受 `CFG.idleMin` 节流，禁止连续输出 |
| 失败降级 | 回落 `lines.json` 随机池（沿用现有 FALLBACK 机制） |
| 触发场景 | 初期只接 `click` 与 `idle`；`drag` 台词保留随机池（拖拽时不便等 LLM 响应） |

## 9. 未实现 / 待办

- **Phase 8 眼睛跟踪鼠标**：全局 `mousemove` → 高光球微移 + 深眼小角度偏转。用户要求放最后（怕影响现有动画）。
  ⚠️ 实现时注意：SMIL rotate 不能与 JS 直接叠加，需用外层 `<g>` 包裹后走 CSS transform。
- **正式气泡样式**：等用户提供游戏内截图/视频后仿照。
- **打包发布**：`cargo tauri build` 出安装包（图标已就绪），配合一键发版脚本（见 `UNFINISHED.md` §2.5）。
