/* FairyPet · Electron 主进程
   ==========================================================================
   R1 窗口表现 : 无边框 + 背景透明 + 始终置顶 + 拖拽（屏幕坐标，保留点击判别）+ 按百分比缩放
   R4 基础控制 : 托盘菜单（显示/隐藏 · 设置 · 退出）+ Alt+F1 全局快捷键 + 单实例
   R6 性能稳定 : 隐藏时前端暂停 SMIL；backgroundThrottling=false（可见但无焦点时不降频）
   R7 任务栏   : 主窗进任务栏（skipTaskbar:false）+ JumpList「设置」任务
                 （右键任务栏图标 → 设置；`--settings` 二次启动也打开设置）
   配置来源   : 主进程 JSON（userData/pet-config.json），多窗口共享，避免 localStorage 的 origin 差异
   ========================================================================== */
'use strict';

// ⚠️ 环境自检：若宿主 shell 带着 ELECTRON_RUN_AS_NODE=1（WorkBuddy/CI 等环境常见），
// electron.exe 会以纯 Node 模式启动，require('electron') 拿到的是 npm 包而非 API，
// 报错是晦涩的 "Cannot read properties of undefined (reading 'requestSingleInstanceLock')"。
// 这里把根因翻译成人话，并给出解法。
if (!process.versions.electron) {
  console.error('[FairyPet] 检测到 ELECTRON_RUN_AS_NODE=1（或以纯 Node 启动）。');
  console.error('[FairyPet] 请清除该环境变量后重试，例如：env -u ELECTRON_RUN_AS_NODE electron .');
  process.exit(1);
}

const { app, BrowserWindow, ipcMain, Tray, Menu, screen, globalShortcut, nativeImage } = require('electron');
const path = require('path');
const fs = require('fs');
const crypto = require('crypto');
const { pathToFileURL } = require('url');   // ⚠️ 别删：音频缓存路径转 file:/// URL 必需（漏了会 ReferenceError）
const doubaoTTS = require('./tts-doubao');   // 豆包语音合成适配层（网络细节都在这个模块里）

const APP_ID = 'com.allthetimes.fairypet';
const BASE_W = 500, BASE_H = 600;      // 100% 时的窗口逻辑尺寸
const SCALE_MIN = 0.5, SCALE_MAX = 2.0;
const MARGIN = 24;                     // 距屏幕右下角边距
const UI_DIR = process.env.FAIRYPET_UI_DIR || path.join(__dirname, '..', 'ui');
// ⚠️ FAIRYPET_UI_DIR 仅供开发/排查使用（指向另一份 ui 副本做 A/B，比如内存测量）
const ICON_ICO = path.join(__dirname, '..', 'build', 'icon.ico');
const ICON_PNG = path.join(__dirname, '..', 'build', 'icon.png');

let petWin = null;
let settingsWin = null;
let tray = null;
let drag = null;                       // { winX, winY, cursorX, cursorY }
let ttsAbort = null;                   // 进行中的 TTS 请求（新说话作废旧合成）

/* ───────────────────────── 配置 ───────────────────────── */
/* 12 项运动参数 = fairy-lab 全部滑块；默认值 = 2026-09-14 校准值 */
const DEFAULT_CFG = {
  scale: 1,
  // 几何
  rOuter: 100, indOuter: 78.1, whiteOuter: 62.2, whiteInner: 41.5,
  iris: 14.9, tip: 93.0, half: 12.5, glint: 14.1,
  // 动效
  scan: 2.2, gear: 18.13, breath: 0.867, breathStr: 100,
  // 语法/行为
  idleMin: 25, autoStart: false,
  // 语音（运行时 TTS）：豆包语音合成（src/tts-doubao.js）。
  // 密钥/音色等敏感信息全部由用户在设置窗口输入，只存在本机 pet-config.json。
  voiceOn: true, voiceVolume: 80,
  doubaoApiKey: '',                // 火山控制台 > API Key 管理（敏感，用户自填，只存本机）
  doubaoResourceId: 'seed-tts-2.0',  // seed-tts-2.0(音色库音色) | seed-icl-2.0(复刻音色)
  doubaoSpeaker: '',               // 音色 ID（音色库或复刻生成的）
  doubaoSpeechRate: 0,             // -50(0.5x) ~ 100(2x)
};
let cfg = { ...DEFAULT_CFG };

const cfgFile = () => path.join(app.getPath('userData'), 'pet-config.json');

function loadCfg() {
  try {
    const raw = JSON.parse(fs.readFileSync(cfgFile(), 'utf8'));
    cfg = { ...DEFAULT_CFG, ...raw };
  } catch {
    cfg = { ...DEFAULT_CFG };
  }
}
function saveCfg() {
  try { fs.writeFileSync(cfgFile(), JSON.stringify(cfg, null, 2)); }
  catch (e) { console.warn('[cfg] 保存失败:', e.message); }
}
function broadcastCfg() {
  if (petWin && !petWin.isDestroyed()) petWin.webContents.send('settings-changed', cfg);
}

/* ───────────────────────── 窗口 ───────────────────────── */
function createPetWindow() {
  const wa = screen.getPrimaryDisplay().workAreaSize;
  petWin = new BrowserWindow({
    width: BASE_W,
    height: BASE_H,
    x: wa.width - BASE_W - MARGIN,
    y: wa.height - BASE_H - MARGIN,
    frame: false,              // R1 无边框
    transparent: !process.env.FAIRYPET_OPAQUE,   // R1 背景透明（FAIRYPET_OPAQUE=1 仅用于排查对比）
    backgroundColor: process.env.FAIRYPET_OPAQUE ? '#1b2340' : '#00000000',
    resizable: false,
    hasShadow: false,          // 避免窗口阴影露出方框
    skipTaskbar: false,        // R7 需要任务栏后台入口
    alwaysOnTop: true,
    show: false,
    title: 'FairyPet',
    icon: ICON_ICO,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      backgroundThrottling: false,   // R6 可见但无焦点时不降频
    },
  });
  // 置顶级别拉高，避免被普通窗口压住
  petWin.setAlwaysOnTop(true, 'screen-saver');
  // FAIRYPET_PAGE_QUERY（开发用）：给页面注入 URL 参数，如 '?say=click' 用于自动化验证
  petWin.loadFile(path.join(UI_DIR, 'index.html'),
    process.env.FAIRYPET_PAGE_QUERY ? { search: process.env.FAIRYPET_PAGE_QUERY } : undefined);
  petWin.once('ready-to-show', () => petWin.show());
  petWin.on('closed', () => { petWin = null; });
  petWin.on('blur', () => { drag = null; });   // 拖拽兜底：失焦即结束
  // 渲染进程异常退出（GPU/内存/被外部杀掉）时留下原因，便于排查
  petWin.webContents.on('render-process-gone', (_e, d) => {
    console.error('[renderer] 退出:', d.reason, 'exitCode=', d.exitCode);
  });
  petWin.webContents.on('console-message', (_e, level, msg, line, src) => {
    if (level >= 2) console.warn(`[renderer] ${msg}  (${src}:${line})`);
  });
}

/* 缩放到 s（保持右下角锚点不动，视觉上"就地变大"） */
function applyWindowScale(s) {
  if (!petWin || petWin.isDestroyed()) return;
  s = Math.min(SCALE_MAX, Math.max(SCALE_MIN, Number(s) || 1));
  const b = petWin.getBounds();
  const w = Math.round(BASE_W * s), h = Math.round(BASE_H * s);
  petWin.setBounds({ x: b.x + (b.width - w), y: b.y + (b.height - h), width: w, height: h });
}

function showPet() {
  if (!petWin || petWin.isDestroyed()) return;
  petWin.show();
  petWin.webContents.send('pet-shown');
}
function hidePet() {
  if (!petWin || petWin.isDestroyed()) return;
  petWin.webContents.send('pet-hidden');   // 先让前端暂停 SMIL（R6）
  petWin.hide();
}
function togglePet() {
  if (!petWin || petWin.isDestroyed()) return;
  petWin.isVisible() ? hidePet() : showPet();
}

function openSettings() {
  if (settingsWin && !settingsWin.isDestroyed()) {
    settingsWin.show();
    settingsWin.focus();
    return;
  }
  settingsWin = new BrowserWindow({
    width: 520,
    height: 640,
    title: 'FairyPet 设置',
    icon: ICON_ICO,
    resizable: true,
    minimizable: false,
    maximizable: false,
    autoHideMenuBar: true,
    show: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  settingsWin.loadFile(path.join(UI_DIR, 'settings.html'),
    process.env.FAIRYPET_SETTINGS_QUERY ? { search: process.env.FAIRYPET_SETTINGS_QUERY } : undefined);
  settingsWin.once('ready-to-show', () => settingsWin.show());
  settingsWin.on('closed', () => { settingsWin = null; });
}

/* ───────────────────────── 托盘 / 快捷键 / 任务栏 ───────────────────────── */
function createTray() {
  const icon = nativeImage.createFromPath(fs.existsSync(ICON_ICO) ? ICON_ICO : ICON_PNG);
  tray = new Tray(icon.isEmpty() ? nativeImage.createEmpty() : icon);
  tray.setToolTip('FairyPet');
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: '显示 / 隐藏', click: togglePet },
    { label: '设置', click: openSettings },
    { type: 'separator' },
    { label: '退出', click: () => app.exit(0) },
  ]));
  tray.on('click', togglePet);   // 左键单击 = 显示/隐藏
}

function setupJumpList() {
  // R7: 右键任务栏图标 → 自定义任务「设置」（点击后带 --settings 二次启动 → 单实例接力打开设置窗）
  try {
    app.setJumpList([{
      type: 'tasks',
      items: [{
        type: 'task',
        title: '设置',
        description: '打开 FairyPet 设置',
        program: process.execPath,
        args: '--settings',
        iconPath: process.execPath,
        iconIndex: 0,
      }],
    }]);
  } catch (e) {
    console.warn('[jumplist] 设置失败:', e.message);
  }
}

/* ───────────────────────── IPC ───────────────────────── */
function registerIpc() {
  // 拖拽（R1）：指针捕获 + 屏幕坐标增量 → 主进程移动窗口
  ipcMain.on('pet:dragStart', (_e, { x, y }) => {
    if (!petWin || petWin.isDestroyed()) return;
    const b = petWin.getBounds();
    drag = { winX: b.x, winY: b.y, cursorX: x, cursorY: y };
  });
  ipcMain.on('pet:dragMove', (_e, { x, y }) => {
    if (!drag || !petWin || petWin.isDestroyed()) return;
    petWin.setPosition(Math.round(drag.winX + (x - drag.cursorX)), Math.round(drag.winY + (y - drag.cursorY)));
  });
  ipcMain.on('pet:dragEnd', () => { drag = null; });

  // 配置读写（R7 设置窗）
  ipcMain.handle('pet:getConfig', () => cfg);
  ipcMain.handle('pet:setConfig', (_e, patch) => {
    cfg = { ...cfg, ...(patch || {}) };
    saveCfg();
    if ('scale' in (patch || {})) applyWindowScale(cfg.scale);
    broadcastCfg();
    return cfg;
  });

  // 语音（运行时 TTS）：豆包语音合成。合成逻辑在 src/tts-doubao.js，这里只做缓存与调度。
  ipcMain.handle('pet:ttsSpeak', async (_e, { text, force, kind }) => {
    if (!text) return '';
    // 语音开关只管日常播报；「测试」是用户显式点击的诊断行为，开关关着也放行
    if (!cfg.voiceOn && kind !== 'test') return '';
    // 运行时缓存：同一句话第二次就是零延迟
    // 缓存放项目目录（用户 09-15 要求）：pet-app/voice-cache/
    // ⚠️ 若将来打包发布（安装到 Program Files），需改回 app.getPath('userData')，否则安装目录不可写
    const cacheDir = process.env.FAIRYPET_VOICE_CACHE
      || path.join(__dirname, '..', 'voice-cache');
    try { fs.mkdirSync(cacheDir, { recursive: true }); } catch { /* ignore */ }
    const cache = path.join(cacheDir,
      `tts_${crypto.createHash('md5').update(text).digest('hex').slice(0, 16)}.mp3`);
    if (!force && fs.existsSync(cache)) return pathToFileURL(cache).href;   // ⚠️ 必须 pathToFileURL：'file://'+Windows路径 形态不标准，部分环境 <audio> 加载失败
    try {
      if (ttsAbort) ttsAbort.abort();                 // 新请求作废旧请求
      ttsAbort = new AbortController();
      const buf = await doubaoTTS.synthesize(text, cfg, ttsAbort.signal);
      if (!buf) return '';                            // 配置缺失/服务失败：模块内已留日志，回退纯文字
      fs.writeFileSync(cache, buf);
      console.log(`[tts] 已合成并缓存: ${path.basename(cache)} (${(buf.length / 1024).toFixed(0)}KB)`);
      return pathToFileURL(cache).href;   // ⚠️ 必须 pathToFileURL：'file://'+Windows路径 形态不标准，部分环境 <audio> 加载失败
    } catch (e) {
      console.log(`[tts] 合成失败（回退纯文字）: ${e.message}`);
      return '';
    }
  });

  // 窗口控制
  ipcMain.on('pet:openSettings', openSettings);
  ipcMain.on('pet:toggle', togglePet);
  ipcMain.on('pet:quit', () => app.exit(0));
  ipcMain.on('pet:setSize', (_e, s) => applyWindowScale(s));

  // 开机自启（R4/R7 设置里的系统项）
  ipcMain.handle('pet:getAutostart', () => !!app.getLoginItemSettings().openAtLogin);
  ipcMain.handle('pet:setAutostart', (_e, on) => {
    app.setLoginItemSettings({ openAtLogin: !!on });
    cfg.autoStart = !!on;
    saveCfg();
    return cfg.autoStart;
  });
}

/* ───────────────────────── 启动 ───────────────────────── */
if (!app.requestSingleInstanceLock()) {
  // 已有实例：交给它处理（--settings 打开设置，否则唤出桌宠）
  app.quit();
} else {
  app.on('second-instance', (_e, argv) => {
    if ((argv || []).includes('--settings')) openSettings();
    else showPet();
  });

  app.whenReady().then(() => {
    app.setAppUserModelId(APP_ID);   // 任务栏图标分组/图标正确显示
    loadCfg();
    registerIpc();
    createPetWindow();
    createTray();
    setupJumpList();

    // R4 全局快捷键 Alt+F1 显示/隐藏（失败不致命）
    try {
      const ok = globalShortcut.register('Alt+F1', togglePet);
      if (!ok) console.warn('[快捷键] Alt+F1 注册失败（可能被其它程序占用）');
    } catch (e) {
      console.warn('[快捷键] 注册异常:', e.message);
    }

    // 开机自启状态同步（配置里存了期望值）
    try { app.setLoginItemSettings({ openAtLogin: !!cfg.autoStart }); } catch { /* ignore */ }

    // R7: 任务栏 JumpList 的「设置」任务在程序**未运行**时会先拉起程序再传 --settings
    //     ⇒ 首次启动也要处理这个参数，否则点了只是打开桌宠、设置窗不出现。
    if (process.argv.includes('--settings')) openSettings();

    // 性能测量模式（开发/排查用）：FAIRYPET_MEASURE=<毫秒> → 采样后打印各进程内存/CPU 并退出。
    // 输出形如 METRIC type=GPU pid=... rss=...MB peak=...MB cpu=...%
    const measureMs = parseInt(process.env.FAIRYPET_MEASURE || '', 10);
    if (measureMs > 0) {
      setTimeout(() => {
        try {
          for (const m of app.getAppMetrics()) {
            const mem = m.memory || {};
            const rss = (mem.workingSetSize || 0) / 1024;
            const peak = (mem.peakWorkingSetSize || 0) / 1024;
            const cpu = m.cpu ? m.cpu.percentCPUUsage.toFixed(1) : '-';
            console.log(`METRIC type=${m.type} pid=${m.pid} rss=${rss.toFixed(1)}MB peak=${peak.toFixed(1)}MB cpu=${cpu}%`);
          }
        } catch (e) {
          console.error('METRIC 采样失败:', e && e.message);
        }
        app.exit(0);
      }, measureMs);
    }
  });

  app.on('window-all-closed', () => { /* 桌宠常驻，不退出 */ });
  app.on('will-quit', () => globalShortcut.unregisterAll());
}
