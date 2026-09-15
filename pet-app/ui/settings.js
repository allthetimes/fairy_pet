/* FairyPet 设置窗口逻辑
   链路：滑块 → petAPI.setConfig(patch) → 主进程落盘 + 广播 settings-changed → 主窗实时应用
   ⚠️ 配置存在主进程（userData/pet-config.json），不再用 localStorage：
      多窗口 origin 不同 + 强杀进程会丢设置。 */
'use strict';

const api = window.petAPI;

/* 滑块 → 配置键映射（12 项运动参数 + 大小 + 台词间隔 + 语音） */
const SPEC = [
  { id: 'pScale',      key: 'scale',      fmt: v => v + '%',    store: v => v / 100, load: v => v * 100 },
  { id: 'pROuter',     key: 'rOuter',     fmt: v => v.toFixed(1) },
  { id: 'pIndOuter',   key: 'indOuter',   fmt: v => v.toFixed(1) },
  { id: 'pWhiteOuter', key: 'whiteOuter', fmt: v => v.toFixed(1) },
  { id: 'pWhiteInner', key: 'whiteInner', fmt: v => v.toFixed(1) },
  { id: 'pIris',       key: 'iris',       fmt: v => v.toFixed(1) },
  { id: 'pTip',        key: 'tip',        fmt: v => v.toFixed(1) },
  { id: 'pHalf',       key: 'half',       fmt: v => v.toFixed(1) },
  { id: 'pGlint',      key: 'glint',      fmt: v => v.toFixed(1) },
  { id: 'pBreath',     key: 'breath',     fmt: v => v.toFixed(3) },
  { id: 'pBreathStr',  key: 'breathStr',  fmt: v => String(v) },
  { id: 'pGear',       key: 'gear',       fmt: v => v.toFixed(2) },
  { id: 'pScan',       key: 'scan',       fmt: v => v.toFixed(1) },
  { id: 'pIdleMin',    key: 'idleMin',    fmt: v => v + 's' },
  { id: 'pSpeechRate', key: 'doubaoSpeechRate', fmt: v => String(v) },
  { id: 'pVoiceVol',   key: 'voiceVolume',fmt: v => String(v) },
];

const DEF = {
  scale: 1, rOuter: 100, indOuter: 78.1, whiteOuter: 62.2, whiteInner: 41.5,
  iris: 14.9, tip: 93, half: 12.5, glint: 14.1,
  breath: 0.867, breathStr: 100, gear: 18.13, scan: 2.2, idleMin: 25,
  voiceOn: true, voiceVolume: 80,
  doubaoApiKey: '', doubaoResourceId: 'seed-tts-2.0', doubaoSpeaker: '', doubaoSpeechRate: 0,
};

let cfg = { ...DEF };

function refreshUI() {
  for (const s of SPEC) {
    const el = document.getElementById(s.id);
    const lb = document.getElementById('v' + s.id.slice(1));
    const raw = cfg[s.key];
    const v = (typeof raw === 'number') ? (s.load ? s.load(raw) : raw) : DEF[s.key];
    el.value = v;
    lb.textContent = s.fmt(parseFloat(el.value));
  }
  refreshDoubaoFields();
  refreshVoice();
  api.getAutostart().then(on => {
    const b = document.getElementById('btnAutostart');
    b.textContent = on ? '已开启' : '关闭';
    b.classList.toggle('on', on);
  }).catch(() => {});
}

/* 滑块 input → 写配置（主进程负责广播给桌宠窗） */
for (const s of SPEC) {
  const el = document.getElementById(s.id);
  const lb = document.getElementById('v' + s.id.slice(1));
  el.addEventListener('input', () => {
    const v = parseFloat(el.value);
    lb.textContent = s.fmt(v);
    api.setConfig({ [s.key]: s.store ? s.store(v) : v });
  });
}

/* 开机自启 */
document.getElementById('btnAutostart').addEventListener('click', async () => {
  const on = await api.getAutostart();
  const now = await api.setAutostart(!on);
  const b = document.getElementById('btnAutostart');
  b.textContent = now ? '已开启' : '关闭';
  b.classList.toggle('on', now);
});

/* 语音开关 */
const btnVoice = document.getElementById('btnVoice');
function refreshVoice() {
  btnVoice.textContent = cfg.voiceOn ? '开' : '关';
  btnVoice.classList.toggle('on', !!cfg.voiceOn);
}
btnVoice.addEventListener('click', async () => {
  cfg = await api.setConfig({ voiceOn: !cfg.voiceOn });
  refreshVoice();
});

/* ---- 豆包语音合成字段（API Key 密码框 + 资源 ID 下拉 + 音色 ID） ---- */
const DOUBAO_PW   = ['doubaoApiKey'];
const DOUBAO_TEXT = ['doubaoSpeaker'];
for (const id of [...DOUBAO_PW, ...DOUBAO_TEXT]) {
  document.getElementById(id).addEventListener('change', (e) => {
    api.setConfig({ [id]: e.target.value.trim() });
  });
}
const selResource = document.getElementById('doubaoResourceId');
selResource.addEventListener('change', async (e) => {
  cfg = await api.setConfig({ doubaoResourceId: e.target.value });
});

function refreshDoubaoFields() {
  for (const id of [...DOUBAO_PW, ...DOUBAO_TEXT]) document.getElementById(id).value = cfg[id] || '';
  selResource.value = cfg.doubaoResourceId || 'seed-tts-2.0';
}

/* ── 试听：用当前设置合成测试文本并直接播放（force 跳过缓存，改完参数立刻能听到新效果） ── */
const btnTest = document.getElementById('btnTestTts');
const testStatus = document.getElementById('ttsTestStatus');
let testAudio = null;
btnTest.addEventListener('click', async () => {
  let text = document.getElementById('ttsTestText').value.trim()
    || '你好，主人，语音模块测试成功。';
  // 测试不受语音开关限制（显式点击 = 诊断行为）；开关关着时拼接一句提醒，
  // 让语音自己播报「没开开关」，比干看设置页直观（用户 09-15 设计）
  const switchOff = !cfg.voiceOn;
  if (switchOff) text += '检测到您未开启语音开关，请确认。';
  if (!cfg.doubaoApiKey){ testStatus.textContent = '✗ 请先填 API Key'; return; }
  if (!cfg.doubaoSpeaker){ testStatus.textContent = '✗ 请先填音色 ID'; return; }
  btnTest.disabled = true;
  testStatus.textContent = switchOff ? '⏳ 合成中…（开关未开，将附带提醒）' : '⏳ 合成中…（一般 1~3 秒）';
  try {
    const url = await api.ttsSpeak(text, 'test', true);   // force=true：不吃旧缓存
    if (!url){ testStatus.textContent = '✗ 合成失败（看桌宠日志 [tts] 行）'; return; }
    if (testAudio){ try { testAudio.pause(); } catch(e){} }
    testAudio = new Audio(url);
    testAudio.volume = Math.min(1, Math.max(0, (cfg.voiceVolume ?? 80) / 100));
    testAudio.onended = () => { testStatus.textContent = '✓ 播放完毕'; };
    testAudio.onerror = () => { testStatus.textContent = '✗ 播放失败'; };
    testStatus.textContent = '▶ 播放中…';
    await testAudio.play();
  } catch (e) {
    testStatus.textContent = '✗ ' + (e.message || e);
  } finally {
    btnTest.disabled = false;
  }
});

/* 恢复默认 */
document.getElementById('btnReset').addEventListener('click', async () => {
  cfg = await api.setConfig({ ...DEF });
  refreshUI();
});

/* 隐藏 / 退出 */
document.getElementById('btnHide').addEventListener('click', () => api.toggle());
document.getElementById('btnQuit').addEventListener('click', () => api.quit());

/* 初始化 */
api.getConfig().then(c => {
  cfg = { ...DEF, ...c }; refreshUI();
  // 调试钩子: ?autottstest=1 → 配置就绪后自动点一次试听（验证 TTS 链路用；
  // ⚠️ 必须在 getConfig 之后——否则 cfg 还是默认值，密钥为空会被前置检查拦下）
  if (new URLSearchParams(location.search).get('autottstest') === '1') {
    setTimeout(() => btnTest.click(), 300);
  }
}).catch(() => refreshUI());

