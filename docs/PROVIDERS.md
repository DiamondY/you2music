# AI 音乐生成 Provider 配置指南

本文档记录 you2music 支持的所有 AI 音乐生成 Provider，包括 API 配置和免费额度获取方式。

**🚀 快速开始**：推荐使用 **Replicate + MiniMax Music**，新用户免费额度可生成约 50-200 首带人声歌曲。

---

## 目录

- [Replicate](#replicate) - ⭐ 默认推荐，支持人声+中英文歌词
- [MiniMax](#minimax-官方-api) - 国内直连，支持人声+中英文歌词
- [ElevenLabs](#elevenlabs) - 支持人声（需付费套餐）
- [Suno](#suno) - 第三方 API，支持人声
- [fal.ai](#falai) - Stable Audio（纯器乐）
- [Stability AI](#stability-ai) - 官方 API（纯器乐）

---

## ElevenLabs

> **状态**: ✅ 已实现 | **推荐**: 否（需付费） | **支持人声**: 是

ElevenLabs Music API 支持完整歌曲生成（含人声）、Composition Plan、Stems 分离和 Inpainting。

> ⚠️ **注意**：免费账号调用 ElevenLabs **Music API** 会返回 `HTTP 402 paid_plan_required`。即使账号有免费 credits，也不代表有 Music API 访问权限；需要付费套餐。

### 免费额度

| 项目 | 详情 |
|------|------|
| 免费额度 | 视账号套餐而定（免费账号通常无 Music API 访问权限） |
| 约等于 | ~10 分钟音频（Multilingual 模型）|
| | ~20 分钟音频（Flash 模型，0.5 credits/字符）|
| 重置周期 | 每月重置，不累积 |
| 信用卡 | 不需要 |

### 免费版限制

- 无商业许可（需注明来源）
- 音质限制：128 kbps
- 有限的 projects 和 voices
- 无即时声音克隆

### 获取步骤

1. **注册账户**
   - 访问 [elevenlabs.io](https://elevenlabs.io/)
   - 或直接访问 [elevenlabs.io/app/sign-up](https://elevenlabs.io/app/sign-up)
   - 使用 Google 账号或邮箱注册

2. **获取 API Key**
   - 登录后访问 [elevenlabs.io/app/settings/api-keys](https://elevenlabs.io/app/settings/api-keys)
   - 点击 "Create API Key"
   - 复制生成的 API Key

3. **配置到项目**
   ```bash
   # 方式 1: 环境变量
   export ELEVENLABS_API_KEY="your-api-key-here"

   # 方式 2: 配置文件 (config/providers.local.json)
   {
     "secrets": {
       "elevenlabs_api_key": "your-api-key-here"
     }
   }
   ```

### 特殊功能

| 功能 | 说明 |
|------|------|
| Composition Plan | 段落级别控制，支持 Intro/Verse/Chorus 等 |
| Stems 分离 | 分离人声和伴奏 |
| Inpainting | Enterprise 功能，段落重新生成 |

---

## Suno

> **状态**: ✅ 已实现 | **推荐**: 是 | **支持人声**: 是

通过第三方 API 服务（如 musicapi.ai、sunoapi.org）访问 Suno 音乐生成能力。

### 免费额度

| 项目 | 详情 |
|------|------|
| Suno 官方 | 每日 50 credits（约 10 首歌），网页端 |
| 第三方 API | 各平台不同，通常有免费额度 |
| 第三方价格 | 约 $0.10-0.12 per song |

### 第三方 API 服务商

| 服务商 | Base URL | 免费额度 |
|--------|----------|---------|
| musicapi.ai | `https://api.musicapi.ai` | 有免费层 |
| sunoapi.org | `https://api.sunoapi.org` | 注册送免费额度 |
| evolink.ai | `https://api.evolink.ai` | Playground 测试 |

### 获取步骤

1. **选择第三方服务商**
   - 推荐 [musicapi.ai](https://musicapi.ai/suno-api)
   - 注册账户

2. **获取 API Key**
   - 在服务商平台获取 API Key

3. **配置到项目**
   ```bash
   # 环境变量
   export SUNO_API_KEY="your-api-key-here"
   export SUNO_BASE_URL="https://api.musicapi.ai"

   # 或配置文件
    {
      "secrets": {
        "suno_api_key": "your-api-key-here"
      },
      "endpoints": {
        "suno_base_url": "https://api.musicapi.ai"
      }
    }
    ```

### 接口约定（默认 musicapi.ai）

本项目内置的 Suno provider 默认按以下第三方 API 约定调用（以 `SUNO_BASE_URL` 为 base）：

- 生成任务：`POST /suno/generate`
- 查询任务：`GET /suno/task/{task_id}`

不同第三方服务商可能路径不同，可在请求里通过 `provider_params` 覆盖（高级参数）：

- `generate_path`：生成接口 path 或完整 URL（默认 `/suno/generate`）
- `task_path_template`：任务查询 URL 模板（默认 `/suno/task/{task_id}`，支持 `{task_id}` 占位符）
- `poll_interval_s`：轮询间隔秒数（默认 2.0）
- `max_wait_s`：轮询最长等待秒数（默认 300）

### 注意事项

- ⚠️ Suno 官方无公开 API
- ⚠️ 第三方 API 可能不稳定
- ⚠️ 遵守第三方服务商的使用条款

---

## Replicate

> **状态**: ✅ 已实现 | **推荐**: 是（默认） | **支持人声**: ✅ MiniMax music 支持

通过 Replicate 平台运行 AI 音乐生成模型。**推荐使用 MiniMax Music 模型**，支持人声和中英文歌词，新用户有免费额度。

### 免费额度

| 项目 | 详情 |
|------|------|
| 新用户 | 注册即送 **免费 credits**（约 $5-10）|
| Try for Free | 部分模型可免费运行有限次数 |
| 信用卡 | 首次试用不需要 |
| 免费额度可生成 | 约 50-200 首歌曲（MiniMax music）|

### 支持的音乐模型

| 模型 | 说明 | 人声支持 | 推荐度 |
|------|------|---------|--------|
| `minimax/music-1.5` | 完整歌曲生成（最多 4 分钟）| ✅ 是 | ⭐⭐⭐ 推荐 |
| `minimax/music-1` | 完整歌曲生成 | ✅ 是 | ⭐⭐ |
| `stability-ai/stable-audio-2.5` | Stable Audio（纯器乐/音效）| ❌ 否 | ⭐ |
| `riffusion/riffusion` | Riffusion | ❌ 否 | ⭐ |

### MiniMax Music 特性

- **支持人声**：生成带人声的完整歌曲
- **中英文歌词**：可在歌词框输入中文或英文歌词
- **风格控制**：通过 `style_strength` 参数控制风格强度（0.0-1.0）
- **输出格式**：MP3

### 获取步骤

1. **注册账户**
   - 访问 [replicate.com](https://replicate.com)
   - 使用 GitHub 账号或邮箱注册
   - **无需信用卡**即可获得免费额度

2. **获取 API Token**
   - 访问 [replicate.com/account/api-tokens](https://replicate.com/account/api-tokens)
   - 创建新的 API Token

3. **配置到项目**
   ```bash
   export REPLICATE_API_TOKEN="your-token-here"

   # 或配置文件 config/providers.local.json
   {
     "secrets": {
       "replicate_api_token": "your-token-here"
     }
   }
   ```

4. **使用 MiniMax Music**
   - 在 UI 中选择 Provider: `replicate`
   - Model 默认已设置为 `minimax/music-1.5`
   - 输入音乐风格描述和歌词
   - 开启「人声」开关

### 价格参考

- MiniMax music: 约 $0.05-0.10 per song
- Stable Audio: 约 $0.01-0.02 per generation

---

## fal.ai

> **状态**: ✅ 已实现 | **推荐**: 否 | **支持人声**: 否

通过 fal.ai 的队列 API 运行 Stable Audio 等模型。

### 免费额度

| 项目 | 详情 |
|------|------|
| 免费额度 | 需查证，建议联系官方 |
| 定价 | 按使用量付费 |

### 获取步骤

1. **注册账户**
   - 访问 [fal.ai](https://fal.ai)
   - 注册账户

2. **获取 API Key**
   - 在 Dashboard 获取 FAL_KEY

3. **配置到项目**
   ```bash
   export FAL_KEY="your-key-here"
   ```

---

## Stability AI

> **状态**: ✅ 已实现 | **推荐**: 否 | **支持人声**: 否

Stability AI 官方的 Stable Audio API。

### 免费额度

| 项目 | 详情 |
|------|------|
| 免费额度 | 需查证 |
| 定价 | 按使用量付费 |

### 获取步骤

1. **注册账户**
   - 访问 [stability.ai](https://stability.ai)
   - 注册并申请 API 访问

2. **获取 API Key**
   - 在账户设置中获取

3. **配置到项目**
   ```bash
   export STABILITY_API_KEY="your-key-here"
   ```

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
    "elevenlabs_api_key": "xi_xxx...",
    "suno_api_key": "xxx...",
    "replicate_api_token": "r8_xxx..."
  },
  "endpoints": {
    "elevenlabs_base_url": "https://api.elevenlabs.io",
    "suno_base_url": "https://api.musicapi.ai",
    "replicate_base_url": "https://api.replicate.com"
  },
  "default_provider": "elevenlabs",
  "enabled_providers": ["elevenlabs", "suno", "replicate"]
}
```

---

## 常见问题

### Q: 哪个 Provider 推荐用于开发测试？

**A**: **Replicate + MiniMax Music**（默认）

- **Replicate**: 新用户有免费额度，无需信用卡，支持人声+中英文歌词
- **ElevenLabs**: 支持人声与高级能力，但 Music API 需要付费套餐（免费账号会 402）

### Q: 如何切换 Provider？

**A**: 在 UI 界面选择 "Provider" 下拉框，或设置环境变量：

```bash
export AI_MUSIC_PROVIDER_DEFAULT="replicate"
```

### Q: 免费额度用完了怎么办？

**A**:
1. Replicate: 添加付款方式，按量付费（约 $0.05-0.10/首）
2. ElevenLabs: 等待下月重置，或升级付费计划
3. Suno 第三方: 切换到其他服务商或付费

### Q: 国内用户如何使用 Replicate？

**A**: Replicate 在国内可能需要配置代理。在 `config/providers.local.json` 中配置：

```json
{
  "proxy": {
    "http": "http://127.0.0.1:7890",
    "https": "http://127.0.0.1:7890"
  }
}
```

或者使用 **MiniMax 官方 API**（国内直连，无需代理）：

```bash
export MINIMAX_API_KEY="your-minimax-key-here"
export AI_MUSIC_PROVIDER_DEFAULT="minimax"
```

### Q: Replicate 和 MiniMax 官方 API 有什么区别？

**A**:

| 特性 | Replicate + MiniMax Music | MiniMax 官方 API |
|------|---------------------------|-----------------|
| 模型 | music-1.5 | music-2.6 |
| 国内访问 | ❌ 需代理 | ✅ 直连 |
| 免费额度 | ✅ 新用户免费 | 需确认 |
| 推荐场景 | 国际用户 | 国内用户 |

---

## MiniMax (官方 API)

> **状态**: ✅ 已实现 | **推荐**: 国内用户 | **支持人声**: ✅ 是

MiniMax 官方音乐生成 API（music-2.6 模型），支持人声和中英文歌词，**国内可直接访问**。

### 特性

| 项目 | 详情 |
|------|------|
| 模型 | `music-2.6` |
| 国内访问 | ✅ 直连，无需代理 |
| 人声支持 | ✅ 是 |
| 歌词支持 | ✅ 中英文 |

### 获取步骤

1. **注册账户**
   - 访问 [platform.minimax.io](https://platform.minimax.io)
   - 注册并获取 API Key

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

### 相关链接

- [MiniMax 开发者平台](https://platform.minimax.io)
- [MiniMax 音乐生成 API 文档](https://platform.minimax.io/docs/api-reference/music-generation)

---

## 相关链接

- [Replicate 官网](https://replicate.com/) - 默认推荐
- [Replicate MiniMax Music 1.5](https://replicate.com/minimax/music-1.5) - 推荐模型
- [MiniMax 开发者平台](https://platform.minimax.io) - 国内直连
- [ElevenLabs 官网](https://elevenlabs.io/)
- [ElevenLabs API 文档](https://elevenlabs.io/docs/api-reference)
- [Replicate AI Music Models](https://replicate.com/collections/ai-music-generation)
- [musicapi.ai (Suno API)](https://musicapi.ai/suno-api)
- [fal.ai](https://fal.ai/)
- [Stability AI](https://stability.ai/)

---

*最后更新: 2026-04-23*
