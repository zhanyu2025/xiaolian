# Dockerfile for the Xiaolian Server Application (Final, Robust Version)

# --- Stage 1: Build Environment ---
# This stage creates a self-contained virtual environment with all dependencies.
FROM python:3.12-slim AS builder

# 1. Install system dependencies & uv.
RUN pip install uv

# 2. Create a non-root user for better security practices.
RUN useradd --create-home --shell /bin/bash appuser
WORKDIR /home/appuser

# 3. Create a virtual environment in a standard, non-conflicting directory.
# This prevents it from being overwritten by volume mounts in development.
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 4. 拷贝项目定义文件并安装依赖到虚拟环境。
#    此步骤不再依赖 uv.lock，而是直接从 pyproject.toml 安装，以确保 Docker 环境构建的独立性和准确性。
COPY pyproject.toml ./
COPY apps ./apps
#    使用 uv pip install 命令，它会实时解析 pyproject.toml 并安装 'server' 分支所需的所有依赖。
RUN uv pip install '.[server]'

# --- Stage 2: Production Environment ---
# This stage builds the final, lean image for running the application.
FROM python:3.12-slim

# 1. 不再需要安装任何额外的系统运行时依赖。

# 2. Create the same non-root user.
RUN useradd --create-home --shell /bin/bash appuser
USER appuser
WORKDIR /home/appuser

# 3. Copy the virtual environment from the builder stage.
COPY --from=builder --chown=appuser:appuser /opt/venv /opt/venv

# 4. Copy the application code.
COPY --chown=appuser:appuser apps/server/src ./src
COPY --chown=appuser:appuser apps/server/public ./public

# 5. Expose the application port.
EXPOSE 8000

# 6. Define the command to run the application using an ABSOLUTE PATH.
# This is the most robust way to ensure the correct executable is found,
# completely avoiding PATH issues and conflicts with volume mounts.
CMD ["/opt/venv/bin/uvicorn", "src.server:app", "--host", "0.0.0.0", "--port", "8000"]
