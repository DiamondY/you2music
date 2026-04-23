# AI 音乐生成 Provider 配置指南

本文档记录 you2music 支持的所有 AI 音乐生成 Provider，包括 API 配置和免费额度获取方式。

---

## 目录

- [ElevenLabs](#elevenlabs) - 推荐，支持人声
- [Suno](#suno) - 第三方 API，支持人声
- [Replicate](#replicate) - MiniMax Music 等模型
- [fal.ai](#falai) - Stable Audio
- [Stability AI](#stability-ai) - 官方 API

---

## ElevenLabs

> **状态**: ✅ 已实现 | **推荐**: 是 | **支持人声**: 是

ElevenLabs Music API 是本项目的主要 Provider，支持完整歌曲生成（含人声）、Composition Plan、Stems 分离和 Inpainting。

### 免费额度

| 项目 | 详情 |
|------|------|
| 免费额度 | 每月 **10,000 credits** |
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

### 注意事项

- ⚠️ Suno 官方无公开 API
- ⚠️ 第三方 API 可能不稳定
- ⚠️ 遵守第三方服务商的使用条款

---

## Replicate

> **状态**: ✅ 已实现 | **推荐**: 是 | **支持人声**: 部分模型支持

通过 Replicate 平台运行开源音乐生成模型。

### 免费额度

| 项目 | 详情 |
|------|------|
| 新用户 | 注册即送免费 credits |
| Try for Free | 部分模型可免费运行有限次数 |
| 信用卡 | 首次试用不需要 |

### 支持的音乐模型

| 模型 | 说明 | 人声支持 |
|------|------|---------|
| `minimax/music-1.5` | 完整歌曲生成 | ✅ 是 |
| `minimax/music-2.5` | 完整歌曲生成 | ✅ 是 |
| `stability-ai/stable-audio-2.5` | Stable Audio | ❌ 否 |
| `riffusion/riffusion` | Riffusion | ❌ 否 |

### 获取步骤

1. **注册账户**
   - 访问 [replicate.com](https://replicate.com)
   - 使用 GitHub 账号或邮箱注册

2. **获取 API Token**
   - 访问 [replicate.com/account/api-tokens](https://replicate.com/account/api-tokens)
   - 创建新的 API Token

3. **配置到项目**
   ```bash
   export REPLICATE_API_TOKEN="your-token-here"

   # 或配置文件
   {
     "secrets": {
       "replicate_api_token": "your-token-here"
     }
   }
   ```

### 价格参考

- 约 $0.005-0.02 per generation（取决于模型）

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

**A**: ElevenLabs 或 Replicate

- **ElevenLabs**: 每月 10,000 credits 免费额度，支持人声
- **Replicate**: 新用户有免费额度，可测试多种模型

### Q: 如何切换 Provider？

**A**: 在 UI 界面选择 "Provider" 下拉框，或设置环境变量：

```bash
export AI_MUSIC_PROVIDER_DEFAULT="suno"
```

### Q: 免费额度用完了怎么办？

**A**:
1. ElevenLabs: 等待下月重置，或升级付费计划
2. Replicate: 添加付款方式，按量付费
3. Suno 第三方: 切换到其他服务商或付费

---

## 相关链接

- [ElevenLabs 官网](https://elevenlabs.io/)
- [ElevenLabs API 文档](https://elevenlabs.io/docs/api-reference)
- [Replicate 官网](https://replicate.com/)
- [Replicate AI Music Models](https://replicate.com/collections/ai-music-generation)
- [musicapi.ai (Suno API)](https://musicapi.ai/suno-api)
- [fal.ai](https://fal.ai/)
- [Stability AI](https://stability.ai/)

---

*最后更新: 2025-04*
