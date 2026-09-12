'use strict';

const { app, BrowserWindow, ipcMain, screen, Menu } = require('electron');
const path = require('path');
const fs = require('fs');

/* ============================================================
 * Fairy — 桌面宠物主进程
 * 透明 / 无边框 / 置顶 / 不占任务栏，鼠标在非角色区域时穿透
 * ============================================================ */

const WIN_W = 360;
const WIN_H = 380;

let win = null;
let dragTimer = null;
let dragOffset = { x: 0, y: 0 };
let mouseIgnored = true;
let watchdog = null;

const DEFAULTS = {
  x: null,            // null = 首次启动落在右下角
  y: null,
  scale: 1,
  alwaysOnTop: true,
  autoTalk: true,
  sound: true,
};

let cfg = { ...DEFAULTS };

const cfgFile = () => path.join(app.getPath('userData'), 'fairy-pet-config.json');
const logFile = path.join(__dirname, 'fairy-startup.log');

function log(...args) {
  const line = `[${new Date().toISOString()}] ${args.join(' ')}\n`;
  try { fs.appendFileSync(logFile, line); } catch { /* 忽略 */ }
  try { process.stderr.write(line); } catch { /* noop */ }
}

try { fs.writeFileSync(logFile, ''); } catch { /* 忽略 */ }
log('main process boot');

function loadCfg() {
  try {
    Object.assign(cfg, JSON.parse(fs.readFileSync(cfgFile(), 'utf8')));
    log('config loaded from', cfgFile());
  } catch { log('using defaults (first run)'); }
}

let saveTimer = null;
function saveCfg() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {
    try { fs.writeFileSync(cfgFile(), JSON.stringify(cfg, null, 2)); } catch { /* 忽略写入失败 */ }
  }, 400);
}

function defaultPos() {
  const wa = screen.getPrimaryDisplay().workArea;
  return {
    x: wa.x + wa.width - WIN_W - 24,
    y: wa.y + wa.height - WIN_H - 6,
  };
}

/* ---------------- 窗口 ---------------- */

function createWindow() {
  const fallback = defaultPos();
  const x = Number.isFinite(cfg.x) ? cfg.x : fallback.x;
  const y = Number.isFinite(cfg.y) ? cfg.y : fallback.y;

  win = new BrowserWindow({
    width: WIN_W,
    height: WIN_H,
    x,
    y,
    frame: false,
    transparent: true,
    backgroundColor: '#00000000',
    alwaysOnTop: cfg.alwaysOnTop,
    skipTaskbar: true,
    resizable: false,
    maximizable: false,
    minimizable: false,
    fullscreenable: false,
    hasShadow: false,
    show: false,
    title: 'Fairy',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      backgroundThrottling: false,
    },
  });

  win.setAlwaysOnTop(cfg.alwaysOnTop, 'screen-saver');
  // 初始整窗穿透；鼠标移到角色/气泡上时由渲染进程通知解除
  win.setIgnoreMouseEvents(true, { forward: true });

  win.loadFile(path.join(__dirname, 'renderer', 'index.html'));

  win.once('ready-to-show', () => {
    win.show();
    const b = win.getBounds();
    log(`window ready at (${b.x},${b.y}) size ${b.width}x${b.height}`);
  });
  win.webContents.on('render-process-gone', (_e, d) =>
    log('FATAL: render-process-gone', d.reason));
  win.webContents.on('did-finish-load', () =>
    log('renderer loaded'));
  win.webContents.on('console-message', (_e, level, msg) => {
    if (level >= 2) log('renderer console:', level, msg);
  });
  win.on('closed', () => { win = null; log('window closed'); });

  // 启动后 1.5s 自动截图存盘，确认窗口渲染正常
  setTimeout(() => {
    if (!win) return;
    win.webContents.capturePage().then((img) => {
      try {
        const out = path.join(__dirname, 'fairy-boot-snapshot.png');
        fs.writeFileSync(out, img.toPNG());
        log('snapshot saved:', out);
      } catch (e) { log('snapshot failed:', e.message); }
    }).catch((e) => log('capture failed:', e.message));
  }, 1500);

  startWatchdog();
}

/* 保险：鼠标已离开窗口却仍处于"拦截"状态时，强制恢复穿透 */
function startWatchdog() {
  clearInterval(watchdog);
  watchdog = setInterval(() => {
    if (!win) return;
    if (dragTimer) return;                 // 拖拽中不动
    const p = screen.getCursorScreenPoint();
    const b = win.getBounds();
    const inside = p.x >= b.x && p.x < b.x + b.width &&
                   p.y >= b.y && p.y < b.y + b.height;
    if (!inside && !mouseIgnored) {
      mouseIgnored = true;
      win.setIgnoreMouseEvents(true, { forward: true });
    }
  }, 250);
}

/* ---------------- IPC ---------------- */

ipcMain.handle('get-config', () => cfg);

ipcMain.handle('set-config', (_e, patch) => {
  Object.assign(cfg, patch || {});
  if (win && 'alwaysOnTop' in (patch || {})) {
    win.setAlwaysOnTop(!!cfg.alwaysOnTop, 'screen-saver');
  }
  saveCfg();
  return cfg;
});

ipcMain.on('set-ignore-mouse', (_e, ignore) => {
  if (!win) return;
  const next = !!ignore;
  if (next === mouseIgnored) return;
  mouseIgnored = next;
  win.setIgnoreMouseEvents(next, { forward: true });
});

ipcMain.on('drag-start', () => {
  if (!win) return;
  const [wx, wy] = win.getPosition();
  const p = screen.getCursorScreenPoint();
  dragOffset = { x: p.x - wx, y: p.y - wy };

  clearInterval(dragTimer);
  dragTimer = setInterval(() => {
    if (!win) return;
    const c = screen.getCursorScreenPoint();
    win.setPosition(Math.round(c.x - dragOffset.x), Math.round(c.y - dragOffset.y));
  }, 16);
});

ipcMain.on('drag-end', () => {
  clearInterval(dragTimer);
  dragTimer = null;
  if (!win) return;
  const [x, y] = win.getPosition();
  cfg.x = x;
  cfg.y = y;
  saveCfg();
});

ipcMain.on('context-menu', () => {
  if (!win) return;

  const send = (name) => win && win.webContents.send('command', name);

  const menu = Menu.buildFromTemplate([
    { label: 'Fairy · Ⅲ型总序式集成泛用人工智能', enabled: false },
    { type: 'separator' },
    { label: '和我说句话', click: () => send('talk') },
    { label: '休眠 / 唤醒', click: () => send('sleep') },
    { label: '重置位置', click: () => {
        const p = defaultPos();
        cfg.x = p.x; cfg.y = p.y;
        win.setPosition(p.x, p.y);
        saveCfg();
      } },
    { type: 'separator' },
    { label: '总在最前面', type: 'checkbox', checked: cfg.alwaysOnTop, click: (item) => {
        cfg.alwaysOnTop = item.checked;
        win.setAlwaysOnTop(item.checked, 'screen-saver');
        saveCfg();
      } },
    { label: '自动搭话', type: 'checkbox', checked: cfg.autoTalk, click: (item) => {
        cfg.autoTalk = item.checked;
        saveCfg();
      } },
    { label: '大小', submenu: [0.7, 0.85, 1, 1.15].map((s) => ({
        label: `${Math.round(s * 100)}%`,
        type: 'radio',
        checked: Math.abs(cfg.scale - s) < 0.01,
        click: () => { cfg.scale = s; saveCfg(); send('rescale'); },
      })) },
    { type: 'separator' },
    { label: '退出 Fairy', click: () => { cfg.x = null; cfg.y = null; saveCfg(); app.quit(); } },
  ]);

  menu.popup({ window: win });
});

ipcMain.on('quit', () => app.quit());

/* ---------------- 生命周期 ---------------- */

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (win) { win.show(); win.focus(); }
  });

  app.whenReady().then(() => {
    loadCfg();
    createWindow();
    log('IPC handlers registered');
    app.on('activate', () => {
      if (BrowserWindow.getAllWindows().length === 0) createWindow();
    });
  });

  app.on('window-all-closed', () => app.quit());

  app.on('before-quit', () => {
    clearInterval(watchdog);
    clearInterval(dragTimer);
  });
}
