/* 内存测量台（仅用于排查，不属于应用运行路径）
   用法：electron scripts/measure_pet_mem.js --page=<绝对路径> [--css=<注入的CSS>] [--opaque=1] [--wait=9000]
   输出：每个进程（Browser/Renderer/GPU/Utility）的 workingSetSize + 合计 */
'use strict';
const { app, BrowserWindow } = require('electron');

function arg(name, def) {
  const hit = process.argv.find(a => a.startsWith('--' + name + '='));
  return hit ? hit.slice(name.length + 3) : def;
}
const page   = arg('page');
const css    = arg('css', '');
const opaque = arg('opaque', '0') === '1';
const wait   = parseInt(arg('wait', '9000'), 10);

app.commandLine.appendSwitch('no-sandbox');

app.whenReady().then(async () => {
  const win = new BrowserWindow({
    width: 500, height: 600,
    frame: false,
    transparent: !opaque,
    backgroundColor: opaque ? '#1b2340' : '#00000000',
    hasShadow: false, resizable: false, alwaysOnTop: true, show: true,
    webPreferences: { contextIsolation: true, backgroundThrottling: false },
  });
  await win.loadFile(page);
  if (css) await win.webContents.insertCSS(css);
  setTimeout(() => {
    const m = app.getAppMetrics();
    let total = 0;
    for (const p of m) {
      const mb = p.memory.workingSetSize / 1024;
      total += mb;
      const cpu = p.cpu ? p.cpu.percentCPUUsage.toFixed(1) : '-';
      console.log(`  ${String(p.type).padEnd(9)} rss=${mb.toFixed(1).padStart(7)} MB   cpu=${cpu}%`);
    }
    console.log(`  ── 合计 ${total.toFixed(0)} MB / ${m.length} 进程`);
    app.exit(0);
  }, wait);
});
