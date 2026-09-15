# Fairy 语音 · 豆包「单向流式语音合成 HTTP」（运行时 TTS）操作手册

> 对应文档：docs.volcengine.com/docs/6561/2528925（唯一适配的接口）。
> 桌宠把当前台词实时发给「豆包语音合成大模型」，用选定的音色读出来。密钥由用户在设置里输入，只存本机。

## 架构（src/tts-doubao.js）

```
桌宠说话 → 主进程 pet:ttsSpeak：
  ① 缓存命中（%APPDATA%/fairy-pet/voice-cache/*.mp3，md5 命名）→ 直接播（同一句第二次秒出）
  ② 未命中 → POST https://openspeech.bytedance.com/api/v3/tts/unidirectional
     响应为 HTTP Chunked，每块一个 JSON：{code, message, data(base64 mp3), sentence, usage}
     拼接所有 data → base64 解码 → mp3 落盘缓存 → 播放
打字先走不等人；音频就绪才开口；失败自动回退纯文字。
```

## 你需要准备的

1. 火山引擎控制台开通「豆包语音合成大模型 2.0」（或复刻 2.0），有免费字符额度；
2. **API Key**：控制台 > API Key 管理（新版控制台）；
3. **音色 ID**：
   - 用官方音色：控制台 > 音色库 挑一个（如 `zh_female_cancan_mars_bigtts`）；
   - 想要 Fairy 的声音：用「声音复刻」拿参考音频克隆一个音色，复制**复刻生成的音色 ID**。

## 桌宠设置（设置窗口 → 语音）

| 项 | 填什么 |
|---|---|
| API Key | 控制台的 API Key（密码框，只存本机） |
| 资源 ID | `seed-tts-2.0`（音色库音色）或 `seed-icl-2.0`（复刻音色） |
| 音色 ID | 上面选的音色对应的 ID |
| 语速 | -50（0.5 倍）~ 100（2 倍） |

协议细节（自动处理，无需关心）：
- 请求体 `{ req_params: { text, speaker, audio_params:{ format:"mp3", sample_rate:24000, speech_rate } } }`；
  资源 ID 为 `seed-icl-2.0`（复刻音色）时自动附带 `model: "seed-tts-2.0-standard"`（文档要求）；
- 请求头 `X-Api-Request-Id`（文档必选）自动生成 uuid。

## 常见问题

| 现象 | 原因 |
|---|---|
| `[tts] HTTP 401 ... Invalid X-Api-Key` | API Key 填错/为空 |
| `[tts] HTTP 403 ... requested resource not granted` | 资源 ID 对应的产品未在你的账号开通（去控制台开通/购买字符包） |
| `[tts] code=450000xx` | 看返回 message；常见是资源 ID 与音色不匹配（如 1.0 音色配了 seed-tts-2.0） |
| 无声但气泡正常 | 未填密钥/音色、服务异常——日志 `[tts]` 行有记录，自动回退纯文字 |
| 同一句第二遍没等 | 正常，已进缓存直接播放 |

## 注意

- 音色与音频来自火山引擎/字节跳动，按其服务条款使用；密钥自行保管，勿提交 git/外传。
