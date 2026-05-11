# AI 音乐生成 Provider 配置指南

本文档记录 you2music 支持的 AI 音乐生成 Provider，包括 API 配置和使用方式。

**🚀 快速开始**：推荐使用 **MiniMax** 作为默认 Provider（国内直连），或使用 **ACE-Step 1.5**（100% 免费）。

---

## 目录

- [MiniMax](#minimax-官方-api) - 国内直连，支持人声+中英文歌词（默认）
- [ACE-Step 1.5](#ace-step-15) - 100% 免费，质量介于 Suno v4.5 和 v5 之间

---

## MiniMax (官方 API)

> **状态**: ✅ 已实现 | **推荐**: 国内用户 | **支持人声**: ✅ 是

MiniMax 官方音乐生成 API（music-2.6 模型），支持人声和中英文歌词，**国内可直接访问**。

**Base URL**

- 国内：`https://api.minimaxi.com`
- 国际/海外：`https://api.minimax.io`

**歌词（Lyrics）是否必填？**

- 开启人声（`vocals=true`）时，MiniMax 通常需要提供歌词；本项目在你不填歌词时会自动启用 `lyrics_optimizer=true`，由 MiniMax 自动生成歌词。
- 关闭人声（`vocals=false`）时，本项目会自动设置 `is_instrumental=true`，此时歌词可以不填。

### 特性

| 项目 | 详情 |
|------|------|
| 模型 | `music-2.6` |
| 国内访问 | ✅ 直连，无需代理 |
| 人声支持 | ✅ 是 |
| 歌词支持 | ✅ 中英文 |
| 最大时长 | 240 秒（4 分钟）|

### 获取步骤

1. **注册账户**
   - 国内：访问 [platform.minimaxi.com](https://platform.minimaxi.com) 注册并获取 API Key
   - 国际/海外：访问 [platform.minimax.io](https://platform.minimax.io) 注册并获取 API Key

2. **配置到项目**
   ```bash
   export MINIMAX_API_KEY="your-key-here"

   # 或配置文件 config/providers.local.json
   {
     "secrets": {
       "minimax_api_key": "your-key-here"
     }
   }
   ```

3. **切换默认 Provider**
   ```bash
   export AI_MUSIC_PROVIDER_DEFAULT="minimax"
   # 或在配置文件中设置 "default_provider": "minimax"
   ```

### API 参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `model` | 模型版本 | `music-2.6` |
| `sample_rate` | 采样率 | 44100 |
| `bitrate` | 比特率 | 256000 |
| `format` | 输出格式 | `mp3` |

### 相关链接

- [MiniMax 开发者平台](https://platform.minimax.io)
- [MiniMax 音乐生成 API 文档](https://platform.minimax.io/docs/api-reference/music-generation)

---

## ACE-Step 1.5

> **状态**: ✅ 已实现 | **推荐**: 所有用户 | **支持人声**: ✅ 是 | **费用**: **100% 免费**

ACE-Step 1.5 开源音乐生成模型，通过 acemusic.ai 云服务调用，质量介于 Suno v4.5 和 v5 之间。

**API 兼容性**: 使用 OpenAI 兼容 API (`/v1/chat/completions`)，音频以 base64 格式内嵌在响应中。

### 特性

| 项目 | 详情 |
|------|------|
| 模型 | `acemusic/acestep-v1.5-turbo`（默认）|
| 费用 | **100% 免费** |
| 质量 | 介于 Suno v4.5 和 v5 之间 |
| 速度 | A100 < 2秒/首，RTX 3090 < 10秒/首 |
| 人声支持 | ✅ 是 |
| 歌词支持 | ✅ 50+ 语言 |
| 最大时长 | 600 秒（10 分钟）|

### 获取步骤

1. **注册账户**
   - 访问 [acemusic.ai](https://acemusic.ai) 注册账户
   - 获取 API Key

2. **配置到项目**
   ```bash
   export ACESTEP_API_KEY="your-key-here"
   export ACESTEP_BASE_URL="https://api.acemusic.ai"

   # 或配置文件 config/providers.local.json
   {
     "secrets": {
       "acestep_api_key": "your-key-here"
     },
     "endpoints": {
       "acestep_base_url": "https://api.acemusic.ai"
     }
   }
   ```

> Note: `ACESTEP_BASE_URL` 必须是 `https://api.acemusic.ai`（API 域名）。如果误填为 `https://acemusic.ai`（官网域名），常见会触发 Cloudflare 403 / error code: 1010。

3. **切换默认 Provider**
   ```bash
   export AI_MUSIC_PROVIDER_DEFAULT="acestep"
   # 或在配置文件中设置 "default_provider": "acestep"
   ```

### API 参数

#### 基础参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `model` | 模型版本 | `acemusic/acestep-v1.5-turbo` |
| `audio_duration` | 时长（秒，3-600）| 30 |
| `audio_format` | 输出格式（mp3/wav/flac）| `mp3` |
| `vocal_language` | 歌词语言（zh/en/ja/ko/auto）| `zh` |
| `bpm` | 节拍速度（30-300）| 自动推断 |
| `key_scale` | 调性（如 C Major, Am）| 自动推断 |
| `time_signature` | 拍号（2/4, 3/4, 4/4, 6/8）| 自动推断 |
| `instrumental` | 纯音乐模式（无人声）| `false` |
| `thinking` | 思考模式（5Hz LM 增强质量）| `false` |
| `use_format` | 格式增强（LM 优化描述和歌词）| `false` |

#### 高级生成控制参数（高级模式）

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `inference_steps` | 推理步数（Turbo: 1-20，Base: 1-200）| 服务端默认 |
| `guidance_scale` | Prompt 引导系数（仅 base 模型）| 7.0 |
| `seed` | 种子值（可复现结果）| 随机 |
| `shift` | 时间步偏移因子 1.0-5.0（仅 base 模型）| 3.0 |
| `infer_method` | 推理方法（ode=确定性, sde=随机）| `ode` |
| `timesteps` | 自定义时间步（逗号分隔）| 自动 |

> **参数传递机制**: 音乐属性参数（duration/bpm/format/vocal_language/key_scale/time_signature/instrumental）通过 `audio_config` 嵌套对象传递，符合 OpenRouter API 规范。同时以顶层平铺参数双写，确保向后兼容。歌词通过 `lyrics` 顶层字段独立传递（同时保留在 `messages.content` 中）。

> **instrumental 说明**: 关闭人声（UI 中 vocals=false）时自动启用 `instrumental=true`，此时不生成人声轨道。

> **seed 说明**: 前端全局 seed 输入框的值会传递给 ACE-Step API。设置相同 seed 可获得更一致的结果。

### 相关链接

- [ACE-Step GitHub](https://github.com/ace-step/ACE-Step-1.5)
- [acemusic.ai](https://acemusic.ai)

---

## 配置优先级

配置按以下优先级加载（高优先级覆盖低优先级）：

1. 环境变量
2. `config/providers.local.json`
3. `config/providers.json`
4. 默认值

### 配置文件示例

```json
{
  "secrets": {
    "minimax_api_key": "your-minimax-key-here",
    "acestep_api_key": "your-acestep-key-here"
  },
  "endpoints": {
    "minimax_base_url": "https://api.minimaxi.com",
    "acestep_base_url": "https://api.acemusic.ai"
  },
  "default_provider": "minimax",
  "enabled_providers": ["minimax", "acestep"]
}
```

---

## 常见问题

### Q: 哪个 Provider 推荐？

**A**:
- **国内用户**: MiniMax（国内直连，无需代理）
- **追求免费**: ACE-Step 1.5（100% 免费）
- **追求质量**: ACE-Step 1.5 XL（质量接近 Suno v5）

### Q: 如何切换 Provider？

**A**: 在 UI 界面选择 "Provider" 下拉框，或设置环境变量：

```bash
export AI_MUSIC_PROVIDER_DEFAULT="acestep"
```

### Q: ACE-Step 和 MiniMax 有什么区别？

**A**:

| 特性 | MiniMax | ACE-Step 1.5 |
|------|---------|-------------|
| 费用 | 需付费或查询免费额度 | **100% 免费** |
| 质量 | 高 | 介于 Suno v4.5 和 v5 |
| 国内访问 | ✅ 直连 | ✅ 直连 |
| 最大时长 | 240 秒 | 600 秒 |
| 推荐场景 | 国内稳定方案 | 免费测试、高质量 |

---

## 相关链接

- [MiniMax 开发者平台](https://platform.minimax.io) - 国内直连
- [ACE-Step GitHub](https://github.com/ace-step/ACE-Step-1.5) - 开源模型
- [acemusic.ai](https://acemusic.ai) - 免费云服务

---

*最后更新: 2026-05-11*
