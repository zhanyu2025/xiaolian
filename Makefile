# 小练 - 项目管理文件
# 为项目提供集中、简化的命令管理。

SHELL := /bin/bash
VENV_DIR := .venv

.PHONY: help dev venv lock install up down build logs test client format clean

# ==============================================================================
#                          主要开发命令
# ==============================================================================

help:
	@echo "╔══════════════════════════════════════════════════════════════════╗"
	@echo "║                      🎙️  小练 - Makefile                         ║"
	@echo "╚══════════════════════════════════════════════════════════════════╝"
	@echo ""
	@echo "用法: make [命令]"
	@echo ""
	@echo "--- 核心开发工作流 ---"
	@echo "  dev                - (推荐) 一键设置并启动开发环境 (自动更新锁文件)。"
	@echo "  client             - (常用) 启动 TUI 客户端。"
	@echo "  down               - 停止并移除所有服务容器。"
	@echo ""
	@echo "--- 环境与依赖管理 ---"
	@echo "  lock               - (重要) 为所有应用更新/生成统一的锁文件。"
	@echo "  install            - 在本地同步/安装所有应用的依赖到根 .venv 中。"
	@echo ""
	@echo "--- 服务管理与测试 ---"
	@echo "  up                 - (后台) 启动服务容器 (不重新构建或更新锁)。"
	@echo "  build              - 强制重新构建并启动服务 (自动更新锁文件)。"
	@echo "  logs               - 实时跟踪服务端日志。"
	@echo "  test               - 在服务端容器内运行 ASR 模型加载测试。"
	@echo ""
	@echo "--- 其他命令 ---"
	@echo "  format             - 使用 Ruff 格式化所有代码。"
	@echo "  clean              - (危险) 彻底清理项目，包括 .venv、Docker 资源和所有构建产物。"
	@echo ""

dev: venv install build
	@echo ""
	@echo "✅ 开发环境已就绪！"
	@echo "   - 服务端已在后台运行。"
	@echo "   - 请运行 'make client' 来启动 TUI 客户端。"
	@echo "   - 请运行 'make logs' 来查看服务端日志。"
	@echo "   - 请运行 'make down' 来停止服务端。"

# ==============================================================================
#                          子命令实现
# ==============================================================================

venv:
	@if [ ! -d "$(VENV_DIR)" ]; then \
		echo ">>> 正在创建 Python 虚拟环境..."; \
		uv venv; \
	fi

lock:
	@echo ">>> 正在检查并更新 uv.lock..."
	uv lock

install: venv lock
	@echo ">>> 正在同步开发环境依赖 (工作区模式)..."
	uv sync

up:
	@echo ">>> 正在以分离模式启动服务端容器..."
	docker-compose up -d

down:
	@echo ">>> 正在停止并移除服务端容器..."
	docker-compose down --remove-orphans

build: lock
	@echo ">>> 正在重新构建并启动服务端容器..."
	docker-compose up --build -d

logs:
	@echo ">>> 正在跟踪服务端日志 (按 Ctrl+C 停止)..."
	docker-compose logs -f

test:
	@echo ">>> 正在服务端容器内运行 ASR 加載测试..."
	@echo "    如果测试失败，请确保服务已通过 'make dev' 启动。"
	docker-compose exec server python tests/test_asr_load.py

# 在 apps/cli 目录下运行命令，以创建独立的上下文并避免命名冲突。
client: install
	@echo ">>> 正在启动 TUI 客户端..."
	(cd apps/cli && uv run python -m app.main)

format:
	@echo ">>> 正在使用 Ruff 格式化所有代码..."
	uv run ruff format .

clean:
	@echo ">>> 正在彻底清理项目环境..."
	@echo "    - 停止并移除 Docker 容器、卷和镜像..."
	docker-compose down --rmi all -v --remove-orphans
	@echo "    - 清理本地文件产物..."
	rm -rf .venv
	rm -f uv.lock
	find . -type f -name '*.pyc' -delete
	find . -type d -name '__pycache__' -exec rm -rf {} +
	find . -type d -name '*.egg-info' -exec rm -rf {} +
	rm -rf apps/cli/recordings apps/server/recordings
	find apps -name "uv.lock" -delete
	@echo "✅ 清理完成！项目已恢复到初始状态。"
