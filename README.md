# 🎙️ 小练 (Xiaolian) - 实时语音AI助手

小练是一个实时的语音AI助手项目，包含一个强大的服务端和一个轻量级的文本用户界面（TUI）客户端。它利用 WebSocket 技术进行低延迟的音频流传输。

## ✨ 功能特性

- **实时音频流**：基于 `WebSockets` 实现客户端与服务端之间的低延迟双向音频流。
- **高性能Web服务**：使用 `FastAPI` 构建异步、高性能的 API 服务，由 `Uvicorn` 驱动。
- **容器化部署**：通过 `Docker` 和 `docker-compose` 提供一键式的服务端部署，保证环境一致性。
- **便捷的开发体验**：`Makefile` 封装了所有常用命令，简化了环境设置、依赖管理和应用启停流程。
- **现代化的Python工具链**：使用 `uv` 进行极速的依赖管理和虚拟环境创建。代码质量由 `Ruff` 和 `Pyright` 保驾护航。
- **可扩展架构**：将服务端 (`server`) 和客户端 (`cli`) 应用分离，方便独立开发和部署。

## 📂 项目结构

```
.
├── apps/                  # 所有源代码的根目录
│   ├── cli/               # TUI 客户端应用
│   └── server/            # FastAPI 服务端应用
│       ├── Dockerfile     # 服务端的 Docker 镜像定义
│       └── recordings/    # (自动创建) 用于存放录音文件
├── docker-compose.yml     # Docker Compose 配置，用于编排服务
├── Makefile               # 项目管理命令的快捷入口
├── pyproject.toml         # 项目元数据和依赖定义 (PEP 621)
├── README.md              # 你正在阅读的文档
└── uv.lock                # 由 uv 生成的精确依赖锁定文件
```

## 🚀 快速开始

在开始之前，请确保你的系统已经安装了以下软件：

- Python (>=3.10, <3.13)
- [Docker](https://www.docker.com/) 和 Docker Compose
- [uv](https://github.com/astral-sh/uv) (Python 包安装和管理工具)

### 1. 设置并启动开发环境

我们强烈推荐使用 `make` 命令来管理项目。首次启动，只需一个命令即可完成所有设置并启动服务：

```bash
make dev
```

该命令会自动执行以下操作：
1.  检查并创建 Python 虚拟环境 (`.venv`)。
2.  根据 `pyproject.toml` 生成/更新 `uv.lock` 锁文件。
3.  使用 `uv` 安装所有本地开发依赖。
4.  使用 `docker-compose` 构建并以后台模式启动服务端容器。

当看到以下输出时，代表服务已经准备就绪：
```
✅ Development environment is ready!
   - The server is running in the background.
   - Run 'make client' to start the TUI client.
   - Run 'make server-logs' to view server logs.
   - Run 'make server-down' to stop all services.
```

### 2. 运行客户端

打开一个新的终端窗口，运行以下命令来启动 TUI 客户端并与服务端进行实时语音交互：

```bash
make client
```

### 3. 查看服务日志

如果你想实时查看服务端容器的输出日志，可以运行：

```bash
make server-logs
```
按 `Ctrl+C` 停止查看。

### 4. 停止服务

当你完成开发时，可以运行以下命令来停止并移除服务端容器：

```bash
make server-down
```

## 🛠️ Makefile 命令详解

`Makefile` 是本项目的工作中枢。运行 `make help` 可以查看所有可用命令的列表。

- `make dev`: (推荐) 一键设置并启动完整的开发环境。
- `make client`: 启动 TUI 客户端。
- `make server-down`: 停止并移除所有服务容器。
- `make setup`: (首次运行) 完整设置本地开发环境（创建虚拟环境、锁定并安装依赖）。
- `make lock`: (重要) 在修改 `pyproject.toml` 后，重新生成 `uv.lock` 文件。
- `make install`: 根据 `uv.lock` 文件同步本地开发环境的依赖。
- `make server-build`: 强制重新构建并启动服务端容器。
- `make server-logs`: 实时查看服务端日志。
- `make format`: 使用 `Ruff` 格式化所有代码。
- `make clean`: 清理所有自动生成的文件（如 `__pycache__`、录音文件和 `uv.lock`）。