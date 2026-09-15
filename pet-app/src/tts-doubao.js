/* 豆包语音合成 · 单向流式语音合成 HTTP（唯一适配的 TTS 接口）
   ==========================================================================
   文档：docs.volcengine.com/docs/6561/2528925（单向流式语音合成HTTP--豆包语音）
     POST https://openspeech.bytedance.com/api/v3/tts/unidirectional
     请求头：X-Api-Key（必选）· X-Api-Resource-Id（必选）· X-Api-Request-Id（必选，uuid）
       X-Api-Resource-Id 可选值：
         seed-tts-2.0  豆包语音合成大模型 2.0（音色库音色）
         seed-icl-2.0  豆包声音复刻大模型 2.0（复刻音色）
     请求体：{ req_params: { text, speaker, audio_params: { format, sample_rate, ... } } }
       复刻音色（seed-icl-2.0）需额外指定 req_params.model（默认 seed-tts-2.0-standard）
     响应：HTTP Chunked，每个分块一个 JSON：
       { code, message, data(合成音频 base64), sentence(时间戳), usage(计费字符) }
   密钥等敏感信息由用户在设置窗口输入，只存本机 pet-config.json。
   ========================================================================== */
'use strict';

const crypto = require('crypto');

const DOUBAO_TTS_URL = process.env.FAIRYPET_TTS_URL || 'https://openspeech.bytedance.com/api/v3/tts/unidirectional';
const RESOURCE_IDS = ['seed-tts-2.0', 'seed-icl-2.0'];

/* 组装请求头（文档必选项齐全）。返回 null = 缺 API Key（调用方回退纯文字）。 */
function authHeaders(cfg) {
  if (!cfg.doubaoApiKey) return null;
  return {
    'Content-Type': 'application/json',
    'X-Api-Key': cfg.doubaoApiKey,
    'X-Api-Resource-Id': RESOURCE_IDS.includes(cfg.doubaoResourceId) ? cfg.doubaoResourceId : 'seed-tts-2.0',
    'X-Api-Request-Id': crypto.randomUUID(),
  };
}

/* Chunked 响应里可能粘连多个 JSON 对象，做字符串/转义感知的流式切分后逐个解析。 */
function splitJsonObjects(raw) {
  const out = [];
  let depth = 0, start = -1, inStr = false, esc = false;
  for (let i = 0; i < raw.length; i++) {
    const c = raw[i];
    if (inStr) {
      if (esc) esc = false;
      else if (c === '\\') esc = true;
      else if (c === '"') inStr = false;
      continue;
    }
    if (c === '"') { inStr = true; continue; }
    if (c === '{') { if (depth === 0) start = i; depth++; }
    else if (c === '}') {
      depth--;
      if (depth === 0 && start >= 0) {
        try { out.push(JSON.parse(raw.slice(start, i + 1))); } catch { /* 跳过坏块 */ }
        start = -1;
      }
    }
  }
  return out;
}

/* 合成入口：text → mp3 Buffer。
   配置缺失/服务失败返回 null（内部已留日志），调用方回退纯文字。 */
async function synthesize(text, cfg, signal) {
  const headers = authHeaders(cfg);
  if (!headers) { console.warn('[tts] 请在设置里填写豆包 API Key'); return null; }
  const rid = headers['X-Api-Resource-Id'];
  if (!cfg.doubaoSpeaker) { console.warn('[tts] 未填写音色 ID（控制台音色库/复刻音色）'); return null; }

  const reqParams = {
    text,
    speaker: cfg.doubaoSpeaker,
    audio_params: {
      format: 'mp3',
      sample_rate: 24000,
      speech_rate: Math.round(cfg.doubaoSpeechRate || 0),   // -50(0.5x) ~ 100(2x)
    },
  };
  // 文档：复刻音色（seed-icl-2.0）需指定 model
  if (rid === 'seed-icl-2.0') reqParams.model = 'seed-tts-2.0-standard';

  const r = await fetch(DOUBAO_TTS_URL, {
    method: 'POST',
    headers,
    body: JSON.stringify({ req_params: reqParams }),
    signal,
  });
  if (!r.ok) {
    console.warn(`[tts] HTTP ${r.status}: ${(await r.text()).slice(0, 200)}`);
    return null;
  }
  let b64 = '';
  for (const obj of splitJsonObjects(await r.text())) {
    if (obj.data) b64 += obj.data;            // 有音频就收
    else if (obj.code !== 0 && obj.code !== 20000000) {
      // ⚠️ 豆包该接口的成功码是 20000000（实测），不是 0；无 data 且非成功码才算失败
      console.warn(`[tts] 服务返回错误 code=${obj.code}: ${obj.message || ''}`);
      return null;
    }
  }
  if (!b64) { console.warn('[tts] 响应中没有音频数据'); return null; }
  const buf = Buffer.from(b64, 'base64');
  if (buf.length < 1000) { console.warn(`[tts] 音频过短(${buf.length}B)，丢弃`); return null; }
  return buf;
}

module.exports = { synthesize };
