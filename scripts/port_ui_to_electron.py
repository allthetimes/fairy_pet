#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一次性补丁：把 Tauri 版桌宠前端 (ui/index.html) 移植到 Electron。

改动点（都是"桥"层面，动画内核一行不动）：
  1. CFG 配置源：localStorage → 主进程 petAPI.getConfig()
  2. API 桥：getTAURI()/listen() → petAPI
  3. applyScale：Tauri win.setSize → petAPI.setSize
  4. 拖拽：Tauri startDragging → petAPI.dragStart/dragMove/dragEnd
  5. 右键：阻止默认 → petAPI.openSettings()
  6. settings-changed：payload 形状随主进程（完整 cfg）
  7. 新增 applyLabParams()：让设置窗的 12 项 lab 参数实时驱动内核
  8. 台词池：fetch(lines.json) → 内联 lines.js（file:// 下 fetch 会被拦）
"""
import io
import re
import sys
import pathlib

HTML = pathlib.Path(__file__).resolve().parent.parent / "pet-app" / "ui" / "index.html"
src = HTML.read_text(encoding="utf-8")
orig = src
report = []


def sub_once(pattern, repl, label, flags=0, count=1):
    """替换（正则，按字符串计数）——必须命中，否则报错，避免静默失效。"""
    global src
    new, n = re.subn(pattern, repl, src, count=count, flags=flags)
    if n == 0:
        report.append(f"  ✗ {label}：未命中")
        return False
    src = new
    report.append(f"  ✓ {label}")
    return True


# ── 1. CFG 配置源 ─────────────────────────────────────────────
sub_once(
    r"/\* CFG: 启动时从 localStorage 恢复；settings-changed 事件实时更新后调 applyBreath 等 \*/\n"
    r"const CFG = \{.*?\n\};",
    """/* CFG: 默认值（= fairy-lab 校准值）；启动时被主进程配置覆盖（Electron petAPI.getConfig） */
const CFG = {
  breath: 0.867, breathStr: 100, gear: 18.13, scan: 2.2, idleMin: 25, scale: 1,
  rOuter: 100, indOuter: 78.1, whiteOuter: 62.2, whiteInner: 41.5,
  iris: 14.9, tip: 93.0, half: 12.5, glint: 14.1,
};""",
    "CFG 配置源 → 主进程",
    flags=re.S,
)

# ── 2. API 桥 ────────────────────────────────────────────────
sub_once(
    r"function getTAURI\(\)\{.*?\n\}\n\n"
    r"/\* listen 桥: 浏览器调试环境无 __TAURI__ 时降级为空操作 \*/\n"
    r"function listen\(event, handler\)\{\n.*?\n\}",
    """/* --- Electron API 桥 ---
   preload 通过 contextBridge 暴露 window.petAPI；浏览器调试环境降级为空操作。 */
var petAPI = (typeof window !== 'undefined' && window.petAPI) || null;   // 必须是 var，见下

/* listen 桥: 事件名 → preload 注册函数 */
function listen(event, handler){
  if (!petAPI) return () => {};
  const reg = {
    'settings-changed': petAPI.onSettingsChanged,
    'pet-hidden':       petAPI.onPetHidden,
    'pet-shown':        petAPI.onPetShown,
  }[event];
  return reg ? (reg(handler) || (() => {})) : (() => {});
}""",
    "API 桥 → petAPI",
    flags=re.S,
)

# ── 3. applyScale 的 setSize ─────────────────────────────────
sub_once(
    r"  const t = getTAURI\(\);\n"
    r"  const win = t && t\.window && t\.window\.getCurrentWindow \? t\.window\.getCurrentWindow\(\) : null;\n"
    r"  const LS = t && t\.window \? t\.window\.LogicalSize : null;\n"
    r"  if \(win && LS\) \{\n"
    r"    try \{\n"
    r"      const p = win\.setSize\(new LS\(BASE_W \* s, BASE_H \* s\)\);\n"
    r"      if \(p && p\.catch\) p\.catch\(e => console\.warn\('\[scale\] setSize 失败:', e\)\);\n"
    r"      console\.log\('\[scale\] setSize ->', BASE_W \* s, BASE_H \* s\);\n"
    r"    \} catch \(e\) \{ console\.warn\('\[scale\] setSize 异常:', e\); \}\n"
    r"  \} else \{\n"
    r"    console\.warn\('\[scale\] Tauri window API 不可用（浏览器调试环境？）'\);\n"
    r"  \}",
    """  /* 窗口尺寸交给主进程（保持右下角锚点） */
  if (petAPI) petAPI.setSize(s);
  else console.warn('[scale] 非 Electron 环境，无窗口尺寸 API');""",
    "applyScale → petAPI.setSize",
    flags=re.S,
)

# ── 4a. mousemove：拖拽改为屏幕坐标驱动 ──────────────────────
sub_once(
    r"window\.addEventListener\('mousemove', \(e\) => \{.*?\n\}\);\n\nwindow\.addEventListener\('mouseup'",
    """window.addEventListener('mousemove', (e) => {
  if (!press) return;
  /* 拖拽中：把窗口跟到光标（主进程按屏幕坐标增量 setPosition）。
     ⚠️ Electron 没有 Tauri 那种"系统拖拽接管"，所以自己持续发坐标；
        光标一直压在窗口上 ⇒ mousemove 不会断。 */
  if (press.dragging) {
    if (e.buttons === 0) {          // 左键已松开 = 拖拽结束（兜底，主 mouseup 也会走一遍）
      press = null;
      setRates(false);
      if (petAPI) petAPI.dragEnd();
      return;
    }
    if (petAPI) petAPI.dragMove(e.screenX, e.screenY);
    return;
  }
  const dx = e.clientX - press.x, dy = e.clientY - press.y;
  if (Math.hypot(dx, dy) > DRAG_THRESHOLD) {
    press.dragging = true;
    setRates(true);                 // 拖拽态: 齿轮/辉光加速
    sayDrag();                      // 拖拽吐槽（8s 节流）
    if (petAPI) petAPI.dragStart(e.screenX, e.screenY);
    else console.warn('petAPI 不可用，无法拖动');
  }
});

window.addEventListener('mouseup'""",
    "拖拽 → petAPI.dragStart/dragMove",
    flags=re.S,
)

# ── 4b. mouseup：拖拽结束时通知主进程 ────────────────────────
sub_once(
    r"  if \(press && press\.dragging\) \{\n"
    r"    setRates\(false\);\s+// 恢复正常转速\n"
    r"  \}",
    """  if (press && press.dragging) {
    setRates(false);                // 恢复正常转速
    if (petAPI) petAPI.dragEnd();
  }""",
    "mouseup → petAPI.dragEnd",
)

# ── 5. 右键 → 设置 ───────────────────────────────────────────
sub_once(
    r"// 右键菜单在正式版里（Phase 5），先阻止默认菜单\n"
    r"petEl\.addEventListener\('contextmenu', \(e\) => e\.preventDefault\(\)\);",
    """/* 右键桌宠 → 打开设置窗（R7）；系统默认菜单一律拦掉 */
petEl.addEventListener('contextmenu', (e) => {
  e.preventDefault();
  if (petAPI) petAPI.openSettings();
});""",
    "右键 → 打开设置",
)

# ── 6. settings-changed 处理 ─────────────────────────────────
sub_once(
    r"  listen\('settings-changed', \(e\) => \{.*?\n  \}\);\n\} catch \(err\) \{ /\* 浏览器调试环境 \*/ \}",
    """  listen('settings-changed', (c) => {
    /* 主进程广播的是完整 cfg ⇒ 全量重放最稳（避免逐字段漏项） */
    Object.assign(CFG, c || {});
    applyLabParams(CFG);
    applyGear();
    applyBreath();
    applyScale(CFG.scale);
    scheduleIdle();
  });
} catch (err) { /* 浏览器调试环境 */ }""",
    "settings-changed → 全量重放",
    flags=re.S,
)

# ── 7. 台词池：fetch → 内联 ──────────────────────────────────
sub_once(
    r"fetch\('lines\.json'\)\.then\(r => r\.json\(\)\)\.then\(j => Object\.assign\(LINES, j\)\)\.catch\(\(\) => \{\}\);",
    """/* 台词池：由 lines.js 内联提供（file:// 下 fetch 会被 CORS 拦掉） */
if (typeof window.LINES_DATA === 'object' && window.LINES_DATA) Object.assign(LINES, window.LINES_DATA);""",
    "台词池 → 内联 lines.js",
)

# ── 8. 新增 applyLabParams + 配置引导 ────────────────────────
sub_once(
    r"// 初始化\nbuildIndigo\(\);\napplyBreath\(\);\napplyGear\(\);\napplyScale\(CFG\.scale\);",
    """/* ============ lab 运动参数应用（设置窗 12 项） ============
   一一对应 fairy-lab 的 bind()：半径类直接改属性，靛蓝层/尖齿改 P 后重建 path。 */
function updateGlint(rp){
  /* 高光位置与虹膜半径联动：实测锚点方向 (20.2,27.2)，间距 = r + 12.5（球内缘压过深眼 1.7u） */
  const c = document.querySelector('#glintG > circle');
  if (!c) return;
  const d = rp + 12.5;
  c.setAttribute('cx', (20.2 / 34.3 * d).toFixed(2));
  c.setAttribute('cy', (27.2 / 34.3 * d).toFixed(2));
}
function applyLabParams(c){
  const g = id => document.getElementById(id);
  // ① 半径类
  if (c.rOuter     != null) g('lyOuter')?.setAttribute('r', c.rOuter);
  if (c.whiteOuter != null) g('lyWhite')?.setAttribute('r', c.whiteOuter);
  if (c.whiteInner != null) g('lySlate')?.setAttribute('r', c.whiteInner);
  if (c.iris       != null) { g('irisPupil')?.setAttribute('r', c.iris); updateGlint(c.iris); }
  if (c.glint      != null) document.querySelector('#glintG > circle')?.setAttribute('r', c.glint);
  // ② 靛蓝环带 + 尖齿：改 P 后重建 path
  let rebuild = false;
  if (c.indOuter != null) { P.base = c.indOuter; rebuild = true; }
  if (c.tip      != null) { P.tip  = c.tip;      rebuild = true; }
  if (c.half     != null) { P.half = c.half;     rebuild = true; }
  if (rebuild) buildIndigo();
  // ③ 扫描线：图案高度 = 周期，位移 = 一个周期（无缝）
  if (c.scan != null){
    const pat = g('scanlines');
    if (pat){
      pat.setAttribute('height', c.scan);
      if (pat.firstElementChild) pat.firstElementChild.setAttribute('height', (c.scan / 2).toFixed(2));
      g('scanAnim')?.setAttribute('to', `0 ${c.scan}`);
    }
  }
}

/* ============ 初始化：先取主进程配置，再统一应用 ============ */
(async () => {
  if (petAPI) {
    try { Object.assign(CFG, await petAPI.getConfig()); }
    catch (e) { console.warn('[cfg] 读取主进程配置失败，用默认值:', e); }
  }
  buildIndigo();
  applyLabParams(CFG);
  applyBreath();
  applyGear();
  applyScale(CFG.scale);
})();""",
    "applyLabParams + 配置引导",
    flags=re.S,
)

# ── 9. 注入 lines.js ─────────────────────────────────────────
if "<script src=\"lines.js\">" not in src:
    m = re.search(r"\n<script>\n", src)
    if m:
        src = src[:m.start()] + '\n<script src="lines.js"></script>\n<script>\n' + src[m.end():]
        report.append("  ✓ 注入 lines.js")
    else:
        report.append("  ✗ 注入 lines.js：找不到主 <script> 标签")
else:
    report.append("  – lines.js 已注入")

if src != orig:
    HTML.write_text(src, encoding="utf-8")
    report.append(f"  ✓ 已写回 {HTML}  ({len(orig)} → {len(src)} 字符)")

print("补丁报告：")
print("\n".join(report))
bad = [r for r in report if "✗" in r]
sys.exit(1 if bad else 0)
