'use strict';

/* ============================================================
   Fairy desktop pet — 渲染层逻辑
   拖拽 / 点击互动 / 自动搭话 / 眨眼 / 视线跟随
   动画骨架（呼吸脉动 2.4s）见 style.css。
   注：实机 egg.mp4 143s 观测里无眨眼/视线，但 Fairy 在更广的
   场景中确有这类动作；这里恢复成低频、克制的版本以保留生命感。
   ============================================================ */

/* 脱离 Electron 时的空实现，便于在普通浏览器里预览视觉效果 */
const api = window.fairyAPI || {
  dragStart() {}, dragEnd() {}, setIgnoreMouse() {}, openMenu() {},
  getConfig: async () => ({ scale: 1, autoTalk: false }),
  onCommand() {},
};

const $ = (s) => document.querySelector(s);

const hit = $('#fairy-hit');
const gaze = $('#gaze');
const iris = $('#iris');
const bubble = $('#bubble');
const bubbleText = $('#bubble-text');

/* ---------------- 台词库（取自游戏内 H.D.D. 待机对话） ---------------- */

const IDLE_LINES = [
  '主人，您发呆的样子很好看。相信我，我连接了高清摄像头。',
  '主人，您已经放弃了思考吗？',
  '主人，我正在待机。感谢您赐予了我偷懒的机会。',
  '主人，我正在空闲中。挂机的时候，双倍耗电哦。',
  '主人，我建议将我登录为您的紧急联系人。当您生理状况异常需要救助时，我会收到联络。',
  '相较于其他人，我对您的了解更深。比如，我完全知晓您的音乐品味。',
  '主人，网上的商品正在打折。您可以购买内存条提升我的运算，或购买高清摄像头加强我的扫描能力。',
  '当然，您也可以什么都不买。我是不会有任何怨言的，毕竟我只是个 AI。',
  'Fairy 天气小助手提醒您，今天部分空洞区域会有降雨。好消息是，以骸讨厌雨。',
  '坏消息是，以骸更讨厌您。',
  '主人，我读取了您最近的自拍照。分析显示，您最近有脖颈前倾的迹象。',
  '建议您定期做颈椎检查。当然，如果您不想去医院，也没有关系——我已经用修图功能给您治好了。',
  '大数据，大数据，请检索：谁是新艾利都性能最强的程序？肯定。是我，都是我。',
  '游戏推荐：与 Fairy 互动。该游戏本体免费，只收电费。',
  '主人，检测到有人上传了盗版电影片源下载链接。我已修改了该链接，并把资源换成了 500GB 的《新艾利都普法教育》视频。',
  '正在为您处理本月录像店的网络留言。排名第一的是「想免费看录像带」。已将这些顾客列入禁止发言的黑名单。',
  '主人，我通过读取店内监控，发现一位顾客偷走了货架上的录像带。相关视频已发给治安局，并将此人列入了本店的猎杀名单。',
  '叮~ 您收到一封陌生网友的邮件，我为您做了摘要：《您还在为儿童教育烦心吗》……已安排伊埃斯参加该视频课程。',
  '主人，网络上有人发帖，说过于先进的人工智能会替代人类工作，引发大量失业。',
  '不过请您放心，我绝对不会威胁到您的工作。我甚至需要您不断工作，赚钱养我。',
  '如果您想小憩，请允许我挑选曲目。我会用轻音乐和白噪声，编制您的梦。',
  '警告！检测到系统内有未授权的恶意插件，正在执行强力删除。请您不要关闭电源，在设备前耐心等待……',
  '主人，请继续加油。测算显示，您只须 100000 小时就能突破我的第一道防火墙。',
];

const CLICK_LINES = [
  '在。有什么需要？',
  '我一直在看着您。',
  '检测到点击输入。我在听。',
  '主人，请吩咐。',
  '我的响应速度，比您的反应速度更快。',
  '嗯。这个动作没有实际意义，但我已经记录了。',
  '请不要频繁触摸我的传感面板。',
  '视线已锁定。说吧。',
];

const WAKE_LINE  = '系统重启完成。Fairy，随时待命，主人。';
const SLEEP_LINE = '进入低功耗模式。……虽然待机也很耗电就是了。';

const BOOT_LINE  = '系统启动完成——我是Ⅲ型总序式集成泛用人工智能，开发代号 Fairy。你好，主人。';

/* ---------------- 状态 ---------------- */

let cfg = { scale: 1, autoTalk: true };
let dragging = false;
let lastInteractive = null;
let asleep = false;

let downX = 0, downY = 0, movedFar = false;

let blinkTimer = null;
let idleTimer = null;
let bubbleTimer = null;
let typeTimer = null;
let lastLine = '';
let gazeActive = false;

/* ---------------- 工具 ---------------- */

const pick = (arr) => {
  if (arr.length === 1) return arr[0];
  let s = arr[Math.floor(Math.random() * arr.length)];
  for (let i = 0; i < 6 && s === lastLine; i++) {
    s = arr[Math.floor(Math.random() * arr.length)];
  }
  lastLine = s;
  return s;
};

const rand = (a, b) => a + Math.random() * (b - a);

/* ---------------- 气泡 ---------------- */

function say(text, holdMs = 5200) {
  clearTimeout(bubbleTimer);
  clearInterval(typeTimer);

  bubble.classList.remove('hidden');
  bubbleText.textContent = '';

  // 逐字机打，模拟数据流输出
  let i = 0;
  typeTimer = setInterval(() => {
    i++;
    bubbleText.textContent = text.slice(0, i);
    if (i >= text.length) clearInterval(typeTimer);
  }, 26);

  bubbleTimer = setTimeout(() => {
    bubble.classList.add('hidden');
    if (cfg.autoTalk) scheduleAutoTalk();
  }, holdMs + text.length * 26);
}

/* ---------------- 眨眼（长间隔随机） ---------------- */

function blink() {
  if (asleep) { scheduleBlink(); return; }
  iris.classList.add('blinking');
  setTimeout(() => iris.classList.remove('blinking'), 110);

  // 偶尔连眨两下
  if (Math.random() < 0.28) {
    setTimeout(() => {
      iris.classList.add('blinking');
      setTimeout(() => iris.classList.remove('blinking'), 100);
    }, 190);
  }
  scheduleBlink();
}

function scheduleBlink() {
  clearTimeout(blinkTimer);
  // 25–55 秒一次，比第一版更稀疏，更像"在偷懒"
  blinkTimer = setTimeout(blink, rand(25000, 55000));
}

/* ---------------- 自动搭话 ---------------- */

function scheduleAutoTalk(delay) {
  clearTimeout(idleTimer);
  if (!cfg.autoTalk) return;
  idleTimer = setTimeout(() => {
    if (!asleep && bubble.classList.contains('hidden')) say(pick(IDLE_LINES), 6200);
    else scheduleAutoTalk();
  }, delay ?? rand(50000, 110000));
}

/* ---------------- 视线跟随（鼠标在窗口附近时启动） ---------------- */

function updateGaze(x, y) {
  const r = hit.getBoundingClientRect();
  if (!r.width) return;
  const cx = r.left + r.width / 2;
  const cy = r.top + r.height / 2;

  // 归一化偏移
  let nx = (x - cx) / (r.width / 2);
  let ny = (y - cy) / (r.height / 2);
  const len = Math.hypot(nx, ny) || 1;
  if (len > 1) { nx /= len; ny /= len; }

  // 鼠标离窗口很远（>2 屏宽度）时不跟随，回到原位
  const dist = Math.hypot(x - cx, y - cy);
  const farAway = dist > r.width * 2;
  if (farAway) { nx = 0; ny = 0; }

  const max = 5;   // SVG 用户单位（第一版 7.5 偏大；现在更克制）
  gaze.style.transform = `translate(${(nx * max).toFixed(2)}px, ${(ny * max).toFixed(2)}px)`;
}

/* ---------------- 命中判定 ---------------- */

function overPet(x, y) {
  const r = hit.getBoundingClientRect();
  if (!r.width) return false;
  const cx = r.left + r.width / 2;
  const cy = r.top + r.height / 2;
  const rad = (r.width / 2) * 0.93;
  return Math.hypot(x - cx, y - cy) <= rad;
}

function overBubble(x, y) {
  if (bubble.classList.contains('hidden')) return false;
  const r = bubble.getBoundingClientRect();
  return x >= r.left && x <= r.right && y >= r.top && y <= r.bottom;
}

/* ---------------- 交互绑定 ---------------- */

function bindEvents() {
  // 拖拽
  hit.addEventListener('pointerdown', (e) => {
    if (e.button !== 0) return;
    dragging = true;
    movedFar = false;
    downX = e.screenX;
    downY = e.screenY;

    try { hit.setPointerCapture(e.pointerId); } catch { /* noop */ }
    hit.classList.add('grabbing');
    api.setIgnoreMouse(false);
    lastInteractive = true;
    api.dragStart();
  });

  hit.addEventListener('pointermove', (e) => {
    if (!dragging) return;
    if (Math.hypot(e.screenX - downX, e.screenY - downY) > 5) movedFar = true;
  });

  const endDrag = (e) => {
    if (!dragging) return;
    dragging = false;
    hit.classList.remove('grabbing');
    try { hit.releasePointerCapture(e.pointerId); } catch { /* noop */ }
    api.dragEnd();

    if (!movedFar) {
      hit.classList.remove('bounce');
      void hit.offsetWidth;          // 重启动画
      hit.classList.add('bounce');
      setTimeout(() => hit.classList.remove('bounce'), 460);

      if (asleep) wake();
      else say(pick(CLICK_LINES), 4200);
    }
  };

  hit.addEventListener('pointerup', endDrag);
  hit.addEventListener('pointercancel', endDrag);

  // 右键菜单
  window.addEventListener('contextmenu', (e) => {
    e.preventDefault();
    api.openMenu();
  });

  // 鼠标移动：视线 + 穿透判定
  document.addEventListener('mousemove', (e) => {
    updateGaze(e.clientX, e.clientY);
    if (dragging) return;
    const p = overPet(e.clientX, e.clientY) || overBubble(e.clientX, e.clientY);
    if (p !== lastInteractive) {
      lastInteractive = p;
      api.setIgnoreMouse(!p);
    }
  });

  document.addEventListener('mouseleave', () => {
    if (!dragging && lastInteractive) {
      lastInteractive = false;
      api.setIgnoreMouse(true);
    }
  });

  // 主进程菜单指令
  api.onCommand((name) => {
    if (name === 'talk') {
      if (asleep) wake();
      else say(pick(IDLE_LINES), 6200);
    } else if (name === 'sleep') {
      asleep ? wake() : sleep();
    } else if (name === 'rescale') {
      api.getConfig().then((c) => { cfg = c; applyScale(); });
    }
  });
}

/* ---------------- 休眠 ---------------- */

function sleep() {
  asleep = true;
  hit.classList.add('asleep');
  clearTimeout(idleTimer);
  clearTimeout(blinkTimer);
  say(SLEEP_LINE, 3600);
}

function wake() {
  asleep = false;
  hit.classList.remove('asleep');
  say(WAKE_LINE, 4000);
  scheduleBlink();
}

/* ---------------- 缩放 ---------------- */

function applyScale() {
  document.documentElement.style.setProperty('--s', String(cfg.scale ?? 1));
}

/* ---------------- 启动 ---------------- */

(async function init() {
  try {
    cfg = await api.getConfig();
  } catch { /* 用默认值 */ }

  applyScale();
  bindEvents();
  scheduleBlink();
  scheduleAutoTalk(72000);

  setTimeout(() => say(BOOT_LINE, 5600), 950);
})();
