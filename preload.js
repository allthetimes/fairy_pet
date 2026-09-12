'use strict';
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('fairyAPI', {
  dragStart: () => ipcRenderer.send('drag-start'),
  dragEnd: () => ipcRenderer.send('drag-end'),
  setIgnoreMouse: (ignore) => ipcRenderer.send('set-ignore-mouse', ignore),
  openMenu: () => ipcRenderer.send('context-menu'),
  getConfig: () => ipcRenderer.invoke('get-config'),
  setConfig: (patch) => ipcRenderer.invoke('set-config', patch),
  quit: () => ipcRenderer.send('quit'),
  onCommand: (cb) => ipcRenderer.on('command', (_e, name) => cb(name)),
  // 全屏光标位置广播（30Hz），用于视线跟随
  onCursorMove: (cb) => ipcRenderer.on('cursor-pos', (_e, p) => cb(p)),
  setCursorBroadcast: (enable) => ipcRenderer.send('cursor-broadcast', !!enable),
});
