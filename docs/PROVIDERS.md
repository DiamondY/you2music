# AI 音乐生成 Provider 指南

本项目仅支持 **ACE-Step 1.5 (acemusic.ai)** 作为音乐生成 Provider。

---

## ACE-Step 1.5

ACE-Step 1.5 是开源音乐生成模型，通过 `acemusic.ai` 云端服务提供 OpenAI 兼容 API：

- `POST /v1/chat/completions`
- `GET /v1/models`

### 配置

环境变量：

```bash
export ACESTEP_API_KEY="your-key-here"
export ACESTEP_BASE_URL="https://api.acemusic.ai"
```

或配置文件 `config/providers.local.json`：

```json
{
  "secrets": { "acestep_api_key": "your-key-here" },
  "endpoints": { "acestep_base_url": "https://api.acemusic.ai" }
}
```

> 注意：`ACESTEP_BASE_URL` 必须是 `https://api.acemusic.ai`（API 域名，不要带 `/v1`）。  
> 如果误填为 `https://acemusic.ai`（官网域名）可能触发 Cloudflare 403 / 1010。

### 任务类型（task_type）

ACE-Step 支持以下 `task_type`：

- `text2music`（默认）
- `cover`
- `repaint`
- `lego`
- `extract`
- `complete`

其中 `cover/repaint/lego/extract/complete` 需要提供源音频（src_audio）。

### 相关链接

- [ACE-Step GitHub](https://github.com/ace-step/ACE-Step-1.5)
- [acemusic.ai](https://acemusic.ai)
