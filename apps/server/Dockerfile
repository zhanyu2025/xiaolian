# ==============================================================================
# 阶段 1: base (基础镜像)
# 一个只包含最核心运行时库和通用配置的、精简的基础镜像。
# ==============================================================================
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1

# [运行时修复] 安装 'libgomp1'，即 GNU OpenMP 运行时库。
# PyTorch 在运行时需要此库来进行并行计算，修复 "OSError: libgomp.so.1" 错误。
RUN apt-get update && \
    apt-get install -y --no-install-recommends libgomp1 && \
    rm -rf /var/lib/apt/lists/*

# [最佳实践] 创建一个非 root 用户 'xiaolian'，并为其设置一个标准的家目录。
# 用户的家目录 (/home/xiaolian) 与应用的工作目录分离，职责更清晰。
RUN useradd --create-home --home-dir /home/xiaolian --shell /bin/bash xiaolian


# ==============================================================================
# 阶段 2: builder (构建器)
# 此阶段继承自 base，负责构建应用和安装所有依赖。
# ==============================================================================
FROM base AS builder

# 为构建过程设置环境变量
ENV UV_LINK_MODE=copy

# 设置应用的工作目录，它独立于用户的主目录。
WORKDIR /home/xiaolian/server

# 安装我们的包管理器 uv
RUN pip install uv

# --- 依赖安装 ---
# 选择性地只复制解决依赖所需的文件。
COPY uv.lock ./
COPY apps/server/pyproject.toml ./

# 安装 Python 依赖。不使用 `--locked` 标志，允许 uv 在 Linux 容器中
# 智能地重新解析任何平台特定的包。
RUN uv sync

# --- 应用代码 ---
# 在依赖安装完成后，复制应用源代码。
COPY apps/server/app ./app

# --- 最后准备 ---
# 创建空目录作为卷的挂载点。
RUN mkdir -p models public recordings
# 为到目前为止创建的所有文件和目录设置正确的所有权。
RUN chown -R xiaolian:xiaolian /home/xiaolian/server


# ==============================================================================
# 阶段 3: production (生产镜像)
# 这是最终将要运行的、最小化且安全的镜像。
# ==============================================================================
FROM base AS production

# 设置应用的工作目录。
WORKDIR /home/xiaolian/server

# --- 从 builder 阶段复制产物 ---
# 1. 包含所有已安装依赖的虚拟环境。
COPY --from=builder --chown=xiaolian:xiaolian /home/xiaolian/server/.venv ./.venv
# 2. 应用源代码。
COPY --from=builder --chown=xiaolian:xiaolian /home/xiaolian/server/app ./app

# --- 最终配置 ---
# 在最终镜像中重新创建挂载点并设置所有权。
# 这确保了即使没有卷被挂载，目录也存在且权限正确。
RUN mkdir -p models public recordings && chown -R xiaolian:xiaolian /home/xiaolian/server

# 在运行应用前，切换到非 root 用户。
USER xiaolian

# 将虚拟环境的可执行文件目录添加到系统的 PATH 中。
ENV PATH="/home/xiaolian/server/.venv/bin:$PATH"

# 暴露应用将要监听的端口。
EXPOSE 8000

# 定义运行应用的命令。
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
