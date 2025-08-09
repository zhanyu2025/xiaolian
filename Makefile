# 小练语音助手 Makefile
# 为项目提供集中、简化的命令管理。

SHELL := /bin/bash
VENV_DIR := .venv

.PHONY: help dev setup venv lock install server-up server-down server-build server-logs client format clean

# ==============================================================================
#                          主要开发命令
# ==============================================================================

help:
	@echo "╔══════════════════════════════════════════════════════════════════╗"
	@echo "║                   🎙️  小练语音助手 - Makefile                     ║"
	@echo "╚══════════════════════════════════════════════════════════════════╝"
	@echo ""
	@echo "用法: make [命令]"
	@echo ""
	@echo "--- 核心开发工作流 ---"
	@echo "  dev                - (推荐) 一键设置并启动开发环境。"
	@echo "  client             - (常用) 启动 TUI 客户端。"
	@echo "  server-down        - 停止并移除所有服务容器。"
	@echo ""
	@echo "--- 环境与依赖管理 ---"
	@echo "  setup              - (首次使用) 设置完整的开发环境。"
	@echo "  lock               - (重要) 在编辑 pyproject.toml 后重新生成 uv.lock 文件。"
	@echo "  install            - 根据 uv.lock 文件同步本地依赖。"
	@echo ""
	@echo "--- 其他命令 ---"
	@echo "  server-build       - 强制重新构建并启动服务。"
	@echo "  server-logs        - 实时跟踪服务端日志。"
	@echo "  format             - 使用 Ruff 格式化所有代码。"
	@echo "  clean              - 清理所有自动生成的文件。"
	@echo ""

dev: setup server-build
	@echo ""
	@echo "✅ 开发环境已就绪！"
	@echo "   - 服务端已在后台运行。"
	@echo "   - 请运行 'make client' 来启动 TUI 客户端。"
	@echo "   - 请运行 'make server-logs' 来查看服务端日志。"
	@echo "   - 请运行 'make server-down' 来停止服务端。"

# ==============================================================================
#                          子命令实现
# ==============================================================================

setup: venv lock install

venv:
	@if [ ! -d "$(VENV_DIR)" ]; then \
		echo ">>> 正在创建 Python 虚拟环境..."; \
		uv venv; \
	fi

lock:
	@echo ">>> 正在锁定所有依赖 -> uv.lock..."
	uv lock

install:
	@echo ">>> 正在根据 uv.lock 同步开发环境..."
	uv sync --all-extras

server-up:
	@echo ">>> 正在以分离模式启动服务端容器..."
	docker-compose up -d

server-down:
	@echo ">>> 正在停止并移除服务端容器..."
	docker-compose down

server-build:
	@echo ">>> 正在重新构建并启动服务端容器..."
	docker-compose up --build -d

server-logs:
	@echo ">>> 正在跟踪服务端日志 (按 Ctrl+C 停止)..."
	docker-compose logs -f

client: venv
	@echo ">>> 正在启动 TUI 客户端..."
	uv run python -m apps.cli.src.main

format:
	@echo ">>> 正在使用 Ruff 格式化代码..."
	uv run ruff format .

clean:
	@echo ">>> 正在清理临时文件..."
	find . -type f -name '*.pyc' -delete
	find . -type d -name '__pycache__' -exec rm -rf {} +
	rm -rf apps/cli/recordings apps/server/recordings
	rm -f uv.lock
	@echo "清理完成。"
