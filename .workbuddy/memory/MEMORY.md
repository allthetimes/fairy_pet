# fairy_pet 项目长期约定

## Fairy 人设（台词/对话必须遵守）

- **Fairy 是《绝区零》(Zenless Zone Zero) 的角色**（不是崩坏：星穹铁道）。
  HDD 系统 III 型主序综合型通用人工智能，Phaethon 兄妹的空洞探索助手，本项目复刻 2.6+ 形象。
- **性格**：毒舌 + 傲娇 + 自恋 + 吐槽役；嘴上嫌弃但底色关心人。称呼用户 **Master / 主人**。
- **⚠️ 语言指纹五条（写台词必须命中）**：
  ① 句首常带「主人」；② **AI 播报腔**（检测到/读取/分析显示/已为您）；
  ③ **敬语包装嘲讽**（「您」+ 平静陈述 + 补刀转折，最标志性）；
  ④ 技术夸张（100000 小时/双倍耗电）；⑤ 符号 `叮~`、`…`、`%¥&%`。
- **写任何台词/对话前必读 `concept/fairy-voice-lines.md`**；改完跑 `python scripts/check_lines.py`，
  要求 30/30 合格（每条 ≥2 指纹、无禁忌词、≤60 字）。光写"毒舌"约束不住输出，
  必须靠**句式模板 + 禁忌词表**。

## 角色卡（长期资产，勿删）

`concept/llm-character-card.md`（主文档）、`character-card.json`（机读版 V2）、
`window-behavior.md`（**桌宠行为权威规格**）、`fairy-voice-lines.md`（台词参考）、
`scripts/check_lines.py`（体检脚本）。台词池：`pet-app/ui/lines.js`（click/drag/idle）。

## 桌宠技术栈（2026-09-15 起：**Electron**）

> 历史：曾用 Tauri v2 做到 Phase 0–7 可用，因 Win11 无边框窗口反复回填 `WS_CAPTION`、
> WebView2 隐藏窗口挂起等，2026-09-15 回滚删除。**结论：无边框透明窗用 Electron 省心得多**
> （`frame:false` 原生生效）。Tauri 偏方（WS_POPUP/DWM/样式位）已作废，勿再走。

- `pet-app/`：`src/main.js`（主进程）· `src/preload.js`（contextBridge）· `ui/`（前端）
- 运行 `cd pet-app && npm start`（依赖已装；electron 走 npmmirror 镜像）
- 配置在**主进程 JSON** `%APPDATA%\fairy-pet\pet-config.json`（不用 localStorage：
  多窗口 origin 不同 + 强杀会丢）。设置项 = 大小 + **fairy-lab 全部 12 项运动参数**。

### ⚠️ Electron 侧硬约定（踩过的坑）

1. **页面顶层不能 `const petAPI`** —— contextBridge 已定义全局 `petAPI`，顶层 const 会抛
   `Identifier 'petAPI' has already been declared` 并让**整段脚本不执行**（窗口尺寸全失效）。
   必须 `var petAPI = window.petAPI || null;`。⚠️ `node --check` 查不出来，只有浏览器报。
2. 改桥之后要断言"脚本真跑了"：**写配置 → 看窗口尺寸是否跟随**（透明窗截图不可靠）。
3. `file://` 下 **fetch 加载本地 json 会被拦** ⇒ 台词池走 `ui/lines.js`（`window.LINES_DATA`）。
4. 单实例锁：残留实例会把新实例顶掉（静默秒退）⇒ 测试前先 `taskkill /F /IM electron.exe`。
5. 受限会话里 GPU 进程会崩，需 `--no-sandbox` 才能启动；用户正常桌面不需要。
6. 拖拽**不用** `-webkit-app-region: drag`（吞 click）：指针屏幕坐标 + 主进程 `setPosition`，
   保留 6px 阈值区分点击/拖拽（见 `window-behavior.md` §3.1）。

## 其他

- 视觉验证：Chrome headless `--headless --disable-gpu --screenshot=... --virtual-time-budget=2500 URL`
  （气泡用 1800）。
- 从 Bash 启动的 detached 进程会在命令结束时被回收 ⇒ 验证要在同一条命令内完成。
