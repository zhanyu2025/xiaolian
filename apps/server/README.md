# 🎙️ 小练 - 服务端

`apps/server` 目录包含了“小练”实时语音AI助手的核心服务端应用。

这是一个基于 FastAPI 的高性能异步应用，负责处理所有核心 AI 逻辑，并通过 WebSocket 与客户端进行低延迟的双向通信。关于本服务如何与客户端协同工作的全局架构，请参考**项目根目录 `README.md` 中的[架构概览](../../README.md#架构概览)**。

## 核心技术栈

- **Web 框架**: [FastAPI](https://fastapi.tiangolo.com/) - 用于构建高性能的异步 API。
- **ASGI 服务器**: [Uvicorn](https://www.uvicorn.org/) - 驱动 FastAPI 应用。
- **通信协议**: [WebSocket](https://developer.mozilla.org/en-US/docs/Web/API/WebSockets_API) - 用于实现客户端与服务端之间的实时双向音频流和数据传输。
- **结构化日志**: [Structlog](https://www.structlog.org/en/stable/) - 提供丰富的、上下文感知的日志记录，便于调试和监控。

## API 端点

本项目只提供一个核心的 WebSocket 端点来处理所有交互。

- **`GET /audio`**: 升级 HTTP 连接为 WebSocket 连接，开始一个实时的语音对话会话。客户端应通过此端点发送音频流，并接收服务端生成的 TTS 音频流。

## 环境变量配置

本服务通过根目录下的 `.env` 文件来加载环境变量。在启动服务前，请确保已在项目根目录创建 `.env` 文件，并包含以下变量：

```dotenv
# .env

# OpenAI API 密钥 (必需)
# 用于与 OpenAI 或任何兼容 OpenAI API 的语言模型服务进行交互。
OPENAI_API_KEY="sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

# OpenAI API 基地址 (可选)
# 如果你使用本地模型 (如 VLLM, Xinference) 或代理，请设置此变量。
# 默认为官方 OpenAI API 地址。
# OPENAI_BASE_URL="http://localhost:8080/v1"
```

## 运行与测试

本服务被设计为整个项目的一部分，并通过项目根目录的 `Makefile` 和 `docker-compose.yml` 进行统一管理。

- **启动开发环境**:
  ```bash
  # 在项目根目录运行
  make dev
  ```

- **查看服务日志**:
  ```bash
  # 在项目根目录运行
  make logs
  ```

- **运行 ASR 模型加载测试**:
  ```bash
  # 在项目根目录运行
  make test
  ```
