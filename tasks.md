# 语音助手 MVP - 开发任务清单 (最终架构版)

本文档是基于我们对 `xiaozhi-server` 的深入分析，并结合 FastAPI 现代化特性，最终确定的开发蓝图。它将指导我们构建一个健壮、可扩展、配置驱动的语音助手。

## 核心架构原则

-   **提供者模式 (Provider Pattern)**: 每种 AI 能力 (ASR, VAD, LLM, TTS) 都由一个抽象基类和多个具体实现类构成，实现高度解耦。
-   **配置驱动 (Configuration Driven)**: 整个应用的行为由一个中央 `config.yaml` 文件定义，切换服务无需修改代码。
-   **一次性加载 (Load Once)**: 所有模型在服务器启动时，由一个统一的服务管理器（`ServiceManager`）加载一次，性能最佳。
-   **依赖注入 (Dependency Injection)**: 使用 FastAPI 的现代依赖注入系统，将服务管理器安全、优雅地提供给业务逻辑。
-   **状态隔离 (State Isolation)**: 每个 WebSocket 连接都由一个独立的 `ConnectionHandler` 实例处理，确保用户会话互不干扰。

---

## 里程碑一：奠定基石 - 架构搭建与 ASR 服务加载

**目标**: 构建项目的核心骨架，实现 Provider 模式、服务加载器，并验证 ASR 模型能在服务器启动时被成功加载。

-   **[ ] 任务 1.1: 创建目录结构与配置文件**
    -   创建 `xiaolian/apps/server/src/providers/` 目录。
    -   在 `providers/` 下创建 `asr/` 子目录。
    -   创建 `xiaolian/apps/server/src/config.yaml` 文件，并定义 `asr_providers` 和 `active_providers` 的基本结构。

-   **[ ] 任务 1.2: 定义 ASR Provider**
    -   创建 `providers/asr/base.py`，定义 `ASRProviderBase` 抽象基类，包含 `async def transcribe(...)` 方法。
    -   创建 `providers/asr/fun.py`，定义 `class FunASRProvider(ASRProviderBase)`。
    -   将我们之前最终确定的、基于 `xiaozhi-server` 示例的健壮 FunASR 加载和处理逻辑，完整地移入 `FunASRProvider` 类中。

-   **[ ] 任务 1.3: 实现服务加载器 (`ServiceManager`)**
    -   创建 `xiaolian/apps/server/src/services.py` 文件。
    -   在其中定义 `class ServiceManager`。
    -   实现 `ServiceManager` 的 `__init__` 方法：
        -   读取 `config.yaml`。
        -   根据 `active_providers` 中的配置，动态地导入并实例化 `FunASRProvider` 类。
        -   将实例化后的服务保存在 `self.asr` 属性中。

-   **[ ] 任务 1.4: 搭建主应用并集成加载器**
    -   创建 `xiaolian/apps/server/src/app.py`。
    -   在**全局范围**（函数外部）实例化服务管理器：`service_manager = ServiceManager()`。这将触发所有模型的加载。
    -   定义一个简单的根路由 (`@app.get("/")`)，返回 "Server is running"。

-   **可验证成果**:
    -   在 `src` 目录下运行 `uvicorn app:app` 启动服务器。
    -   观察启动日志，应能看到 FunASR 模型被加载的完整日志流，并最终显示加载成功。**整个过程只在启动时发生一次**。服务器不应报错退出。

---

## 里程碑二：打通链路 - 实时 VAD -> ASR 语音转写

**目标**: 实现完整的实时音频处理管线。客户端的音频流能被 VAD 检测，然后由 ASR 转写，最终将文本发回客户端。

-   **[ ] 任务 2.1: 实现 VAD Provider**
    -   在 `providers/` 下创建 `vad/` 目录。
    -   创建 `providers/vad/base.py` (定义 `VADProviderBase`) 和 `providers/vad/silero.py` (定义 `SileroVADProvider`)。
    -   更新 `config.yaml`，添加 `vad_providers` 和对应的 `active_providers`。
    -   扩展 `ServiceManager`，使其也能加载 VAD 服务。

-   **[ ] 任务 2.2: 实现连接处理器 (`ConnectionHandler`)**
    -   创建 `xiaolian/apps/server/src/connection_handler.py`。
    -   定义 `class ConnectionHandler`，其构造函数接收一个 `ServiceManager` 实例。
    -   在 `ConnectionHandler` 中实现 `async def handle_audio_stream(self, websocket: WebSocket)` 方法。此方法将是处理单个客户端所有逻辑的核心。
        -   它会持续接收音频数据，送入 VAD Provider。
        -   当 VAD Provider 检测到一句完整的语音时，它会将音频数据块交给 ASR Provider。
        -   拿到 ASR 的转写文本后，通过传入的 `websocket` 对象，将文本发送回客户端。

-   **[ ] 任务 2.3: 实现 WebSocket 端点**
    -   在 `app.py` 中，定义 WebSocket 端点 `@app.websocket("/audio")`。
    -   在函数签名中使用 `Depends` 来注入我们全局的 `ServiceManager` 实例。
    -   当一个新连接建立时，**创建一个新的 `ConnectionHandler` 实例**。
    -   进入 `while True` 循环，持续将从 WebSocket 接收到的数据，喂给 `ConnectionHandler` 的处理方法。

-   **可验证成果**:
    -   启动服务器。用客户端连接 `/audio` 端点并发送连续的语音。
    -   客户端应该能一句一句地、实时地接收到服务器发回的转写文本。

---

## 里程碑三：赋予智慧 - 集成 LLM 实现语音问答

**目标**: 将语音转写服务升级为具备思考能力的 AI 问答机器人。

-   **[ ] 任务 3.1: 实现 LLM Provider** (基于 `tongyi`)。
-   **[ ] 任务 3.2: 扩展 `ConnectionHandler`**
    -   修改其处理逻辑：当从 ASR 拿到文本后，不再直接发回客户端，而是将其传递给 LLM Provider。
    -   将 LLM Provider 返回的**文本回答**，通过 WebSocket 发回客户端。

-   **可验证成果**:
    -   对语音助手提问（例如“你好，请介绍一下长城”），客户端能接收到来自通义千问的**文本回答**。

---

## 里程碑四：完整闭环 - 集成 TTS 实现语音对话

**目标**: 完成从“语音输入”到“语音输出”的完整对话流程，并支持 Web 客户端。

-   **[ ] 任务 4.1: 实现 TTS Provider** (基于 `edge`)。
-   **[ ] 任务 4.2: 完成 `ConnectionHandler` 最终逻辑**
    -   修改其处理逻辑：当从 LLM 拿到文本回答后，将其传递给 TTS Provider。
    -   TTS Provider 会返回音频数据流。将这些**音频 `bytes`** 通过 WebSocket 发回给客户端。

-   **[ ] 任务 4.3: 升级客户端**
    -   **CLI 客户端**: 需要能够处理从 WebSocket 收到的二进制音频数据，并使用 `pyaudio` 等库进行播放。
    -   **Web 客户端**:
        -   创建 `public` 目录及 `index.html`, `main.js`。
        -   在 `app.py` 中添加静态文件服务。
        -   在 `main.js` 中使用 Web Audio API 实现麦克风访问、WebSocket 通信，以及接收并播放音频流的逻辑。

-   **可验证成果**:
    -   通过 CLI 或 Web 客户端与语音助手对话，能直接**听到**助手的语音回答，实现流畅的语音交互。