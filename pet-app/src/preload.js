/* FairyPet · preload：渲染层与主进程之间唯一的桥
   渲染层拿到的就是 window.petAPI（contextIsolation:true，不暴露 Node） */
'use strict';

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('petAPI', {
  /* ---- 配置 ---- */
  getConfig: () => ipcRenderer.invoke('pet:getConfig'),
  setConfig: (patch) => ipcRenderer.invoke('pet:setConfig', patch),
  onSettingsChanged: (fn) => {
    const h = (_e, cfg) => fn(cfg);
    ipcRenderer.on('settings-changed', h);
    return () => ipcRenderer.removeListener('settings-changed', h);
  },

  /* ---- 窗口 / 拖拽（R1） ---- */
  dragStart: (x, y) => ipcRenderer.send('pet:dragStart', { x, y }),
  dragMove: (x, y) => ipcRenderer.send('pet:dragMove', { x, y }),
  dragEnd: () => ipcRenderer.send('pet:dragEnd'),
  setSize: (s) => ipcRenderer.send('pet:setSize', s),

  /* ---- 语音（运行时 TTS） ---- */
  ttsSpeak: (text, kind, force) => ipcRenderer.invoke('pet:ttsSpeak', { text, kind, force }),

  /* ---- 控制（R4/R7） ---- */
  openSettings: () => ipcRenderer.send('pet:openSettings'),
  toggle: () => ipcRenderer.send('pet:toggle'),
  quit: () => ipcRenderer.send('pet:quit'),
  getAutostart: () => ipcRenderer.invoke('pet:getAutostart'),
  setAutostart: (on) => ipcRenderer.invoke('pet:setAutostart', on),

  /* ---- 显隐事件（R6 暂停/恢复动画） ---- */
  onPetHidden: (fn) => {
    const h = () => fn();
    ipcRenderer.on('pet-hidden', h);
    return () => ipcRenderer.removeListener('pet-hidden', h);
  },
  onPetShown: (fn) => {
    const h = () => fn();
    ipcRenderer.on('pet-shown', h);
    return () => ipcRenderer.removeListener('pet-shown', h);
  },
});
