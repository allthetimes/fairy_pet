# fairy_pet 项目长期约定

## Fairy 人设（台词/对话必须遵守）

- **Fairy 是《绝区零》(Zenless Zone Zero) 的角色**，不是崩坏：星穹铁道的（别搞混）。
  HDD 系统里的 III 型主序综合型通用人工智能，Phaethon 兄妹的空洞探索助手，2.6 版更新了形象（本项目复刻的就是 2.6+ 形象）。
- **性格**：毒舌（Deadpan Snarker）+ 傲娇 + 自恋（Insufferable Genius）+ 吐槽役；嘴上嫌弃但底色关心人（Jerk with a Heart of Gold）。
  对"第二助手"会吃醋、要证明自己更有用。慵懒、不耐烦、带电子生命的冷静感。称呼用户为 **Master / 主人**。
- **⚠️ 语言指纹五条（写台词必须命中）**：
  ① 句首常带「主人」；② **AI 播报腔**（检测到/读取/分析显示/已为您/正在执行）；
  ③ **敬语包装嘲讽**（用「您」+ 平静陈述 + 补刀转折，最标志性）；
  ④ 技术夸张（100000 小时/双倍耗电/电源变压器）；⑤ 符号 `叮~`、`…`、`%¥&%`。
- **台词风格参考文档：`concept/fairy-voice-lines.md`**（含官方原句摘录 + 反面清单）——
  **写任何台词/对话前必读**。别只凭"毒舌傲娇"标签想象她的说话方式。

## 角色卡（2026-09-14 建成）

| 文件 | 用途 |
|---|---|
| `concept/llm-character-card.md` | **角色卡主文档**（身份/自我认知/人称/语言指纹+句式模板/情境反应/范例对话/禁忌/LLM接入） |
| `concept/character-card.json` | **机读版**（Character Card V2），接 LLM 直接用 |
| `concept/window-behavior.md` | **桌宠行为规格**（窗口/状态机/交互/台词系统/系统控制/设置窗/LLM契约） |
| `concept/fairy-voice-lines.md` | 台词风格参考 + 官方原句 |
| `scripts/check_lines.py` | **台词体检脚本**：`python scripts/check_lines.py` 对照角色卡逐条打分 |

**改台词后必跑 `check_lines.py`**，要求 30/30 合格（每条 ≥2 条语言指纹、无禁忌词、≤60 字）。
角色卡的可执行部分是**句式模板 + 禁忌词表**（光写"毒舌"约束不住输出）。
- **不是**甜美卖萌系——2026-09-14 用户明确指出"发言要符合人设"，已重写 lines.json。
- 官方 Idle 台词风格参考：会认真讨论"成为虚拟偶像"这种事，冷面说笑话。
- 台词池位置：`pet-app/ui/lines.json`（click/drag/idle 三类）；兜底句在 `pet-app/ui/index.html` 的 FALLBACK。

## 桌宠构建速查

- **🔴 工作纪律（用户明确要求，务必遵守）**：**每次测试完必须关掉自己启动的测试进程**。
  不清理的后果很实在：① 桌宠的 Alt+F1 是**系统级全局热键**，残留进程会让用户新启动的实例
  `register` 失败而 **setup panic 崩溃**；② 用户看到的可能是**旧代码**的实例，
  导致"改了没效果"的误判（实测反复踩坑）。测完即杀，或干脆只编译、让用户自己启动。
- **⭐ "启动时有边框、隐藏后再显示就没有了"的确切原因**（日志实证）：
  Tauri 的**窗口显示流程会在 setup 之后又把 decorations 套回去**——
  日志里能看到样式在我两次重应用**之间**从 `0x14000000` 变回 `0x14cb0000`。
  而**经历一次「隐藏 → 再显示」后 Windows 重建窗口合成表面，之后就再也不会被覆盖**。
  ⇒ 解法：**启动后主动补一次 `hide()` → 等 250ms → `show()` + 重应用**，
  再跟几轮延迟重应用（400/1000/2000ms）。比单纯"多调几次样式"有效得多。
  注意 `hide/show` 必须经 `run_on_main_thread` 回到主线程执行。

- 环境：RUSTUP_HOME=`D:\rustup`、CARGO_HOME=`D:\rust`、MSVC 在 `D:\BuildTools`（PATH 加 toolchain bin，见 2026-09-14 log）。
- rustup 下载走中科大镜像（RUSTUP_DIST_SERVER），cargo 用官方源直连；本地代理 127.0.0.1:49495 会让 reqwest 报 tunnel error。
- **⭐ 改 `pet-app/ui/*` 后必须 `touch pet-app/src-tauri/src/main.rs` 再 `cargo build`**。
  cargo 不会因为 `../ui` 变化而重新编译 main.rs ⇒ `generate_context!` 宏不重新展开 ⇒
  **exe 里嵌入的仍是旧前端**（表现为"前端怎么改都没反应"，极其浪费时间）。
  build.rs 里写了 `rerun-if-changed=../ui` 也不够可靠。
- **capabilities 权限文件必须存在**（`src-tauri/capabilities/default.json`）。Tauri v2 默认不给前端
  任何窗口权限，缺了会**静默失败**（startDragging / listen / setSize 全废）。
  权限标识符可在 `gen/schemas/desktop-schema.json` 里 grep 校验。
- **`decorations:false` / `transparent` 在 Win11 上不生效**（`set_decorations` 返回 Ok 但样式位不变）
  ⇒ 用 Win32 API 强制改样式位（见 main.rs 的 `force_frameless`）。**不要动 WS_EX_LAYERED**
  （Tauri 的透明走 DWM/WebView2 合成，手动加会让窗口消失）。
- **⭐⭐ "点一下就冒出边框"的真正根因**：只剥 `WS_CAPTION` 不够，**必须连
  `WS_SYSMENU` / `WS_MINIMIZEBOX` / `WS_MAXIMIZEBOX` 一起剥掉**——
  留着它们，系统仍认为"该窗口有标题栏区域"，窗口一被激活就把标题栏画回来。
  正解：`style & !(WS_CAPTION|WS_THICKFRAME|WS_SYSMENU|WS_MINIMIZEBOX|WS_MAXIMIZEBOX)`
  → 得到 `0x14000000`（只剩 VISIBLE|CLIPSIBLINGS）。实测激活/失焦后样式稳定不变。
- **⚠️ 不要改 `WS_POPUP`**：虽然 POPUP 窗口没有非客户区，但会把窗口类型变掉，
  在 Tauri/Win11 上实测导致 WebView2 内容不渲染（窗口全透明）。**保持窗口类型，只剥样式位**。
- **⚠️ 不要调用 `DwmExtendFrameIntoClientArea`**：传 `-1` 会让 DWM 反而画出标题栏白条；
  传 `0` 会让窗口内容不显示。它会改变 DWM 对该窗口的合成方式，破坏 WebView2 透明合成。
- **⚠️ 不要在 `Resized`/`Moved` 事件里重应用样式**：`force_frameless` 内的
  `SetWindowPos(SWP_FRAMECHANGED)` 本身会触发这两个事件 ⇒ 递归。
- **⭐ `ImageGrab` 抓不到"纯透明无边框"窗口的任何内容**（连标题栏都抓不到，得到壁纸）。
  所以 **不能用屏幕截图判断"有没有边框/内容是否显示"**。
  反过来：**能抓到不透明内容时，说明那一刻窗口确实带上了不透明区域**。
  判断窗口是否真的在渲染 → 查 `msedgewebview2.exe` 进程是否存在 + 问用户。
- **⭐⭐ 最坑的一环：`WebviewWindow::hwnd()` 拿到的不是屏幕上那个顶层窗口！**
  实测它在 Tauri v2.11 + Win11 上返回的句柄**改样式毫无效果**（日志显示"改了"，窗口边框照旧），
  表现为"代码明明执行了但界面没变化"，极难自查。
  **解决**：改为 `resolve_main_hwnd()` —— 先试 `win.hwnd()`，
  再用 `FindWindowW(null, "FairyPet")` 按标题兜底找真实顶层窗口（当前实际生效的是后者）。
  **排查手法**：把 Rust 里用的 hwnd 打印出来，与 Python 侧 `FindWindowW` 的结果对比，
  不一致就说明句柄错了。**不要相信"代码跑了就等于作用到目标窗口了"。**
- **`IsWindowVisible=False` 但窗口仍在屏幕上**是正常的：直接 `SetWindowLongW` 去掉
  `WS_VISIBLE` 位不会立即隐藏窗口（要调 `ShowWindow` 才生效）。所以判断"窗口可见性"
  不能只看这个 API。
- **⭐⭐ 只去 `WS_CAPTION` 是不够的**：残留的 `WS_SYSMENU` / `WS_MINIMIZEBOX` / `WS_MAXIMIZEBOX`
  会让系统**仍然认为该窗口有标题栏区域** —— 表现为"启动时没边框，**一点击/一激活边框就冒出来**"。
  **正解：整体改成 `WS_POPUP`** ——
  `style = (style & (WS_VISIBLE | WS_CLIPSIBLINGS)) | WS_POPUP`
  → 得到 `0x94000000`（POPUP 窗口没有非客户区，系统从根上不会给它画标题栏/边框）。
  配合 `hook_window_events()`：在 `Focused` / `Resized` / `Moved` 事件上再补一刀做双保险。
- **⭐⭐⭐ 最狠的一招（治 DWM 合成层）**：`DwmExtendFrameIntoClientArea(hwnd, {-1,-1,-1,-1})`
  —— 把**整个窗口声明为客户区**，DWM 再无空间画标题栏/边框。返回 0 = 成功。
  只在 Win32 样式已干净、但**仍能看到框**时才需要它（`DWMWA_BORDER_COLOR` 等属性
  在部分窗口上 `DwmSetWindowAttribute` 返回 0 但读取报 E_INVALIDARG，实际未必生效）。
- **透明窗口无法程序化截图验证**：`ImageGrab` 只能抓到它后面的东西，
  `PrintWindow(PW_RENDERFULLCONTENT)` 得到**全白**。判断"边框有没有去掉"**只能靠人眼**。
- **`TerminateProcess` 强杀会丢 localStorage**：WebView2 来不及把设置落盘
  （实测用户的"桌宠大小 50%"被杀一次就没了）。**给用户改设置后，优先用托盘"退出"**；
  自己调试要强杀时，心里有数这是会丢设置的。
- **⭐ 窗口"外框"有三层，缺一层都还能看到框**：
  ① Win32 样式位 `WS_CAPTION`/`WS_THICKFRAME`/`WS_EX_APPWINDOW`；
  ② **Win11 DWM 合成层的 1px 边框 + 圆角** —— ⚠️ **它不计入 `GetWindowRect` 与 `GetClientRect` 的差值**，
     所以只看 Win32 尺寸会误判成"没有边框"。必须用 DWM API 关：
     `DwmSetWindowAttribute(h, DWMWA_BORDER_COLOR=34, DWMWA_COLOR_NONE=0xFFFFFFFE)`、
     `DWMWA_WINDOW_CORNER_PREFERENCE=33 → DWMWCP_DONOTROUND=1`、
     `DWMWA_NCRENDERING_POLICY=2 → DWMNCRP_DISABLED=1`（后两个可能读不回，属正常）；
  ③ 保证 `WS_VISIBLE` 在（改样式时丢了会变成"进程在跑但看不到窗口"）。
- **⭐ 样式会被 Tauri 覆盖**：窗口**首次显示后** Tauri/系统可能重新套用一次 decorations
  ⇒ `force_frameless` 必须在 **setup 里应用一次 + 显示后延迟多次重应用**
  （实测 120/400/1000/2500ms 四轮；不加这一段，标题栏会自己回来）。

- **WebView2 会节流后台窗口的 `setTimeout`**（桌宠无焦点时定时器可能长时间不触发）
  ⇒ 需要立即执行的初始化逻辑别放 setTimeout 里。`fetch` 还会被 CSP 拦，用 `new Image().src` 上报更稳。
- **⭐ 快捷键插件只能注册一次**：`main.rs` 里若在 Builder 链上 `.plugin(global_shortcut::Builder::new().build())`、
  又在 `setup` 里 `app.handle().plugin(...with_handler...)`，会因重复注册导致
  `HotKey already registered` → **setup panic → 进程启动即崩溃**。
  且 **Alt+F1 是系统级全局热键**：只要还有一个 fairy-pet 进程活着（哪怕是僵死的），
  新进程 `register` 就会失败 ⇒ **`register` 必须容错**（失败只打印警告，托盘菜单兜底），绝不能 `?` 传播。
- **僵死进程**：`taskkill` 报"没有此任务的实例在运行"但 `tasklist` 仍显示该进程 =
  进程已终止但句柄未释放（**锁住 exe + 占着全局热键**）。常规 taskkill 无解，
  用 `CARGO_TARGET_DIR=target_run cargo build` 换输出目录规避文件锁（代价是全量重编）。
- 编译/运行必须 `dangerouslyDisableSandbox: true`（沙箱拦 target 目录写入）。
- 链接错误 LNK1104（无法打开 fairy_pet.exe）= 有进程锁着 exe，先 taskkill（僵死见上条）。

- 渲染验证：Chrome headless `--headless --disable-gpu --screenshot=... --virtual-time-budget=2000`；
  agent-browser daemon 不稳定（eval 之间页面被重置），别用它。
  气泡截图 budget 用 1800（太大时 4s 停留期已过、气泡淡出，会误判）。
- 窗口样式/位置验证：Python ctypes 读 `GetWindowLongW(GWL_STYLE/GWL_EXSTYLE)` + `GetWindowRect`。

