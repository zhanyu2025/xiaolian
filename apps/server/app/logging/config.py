import logging
import os
import sys

import structlog
from structlog.types import Processor

# --- 1. 环境配置 ---
# 从环境变量读取配置，如果未设置，则提供明智的默认值。
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_FORMATTER: str = os.getenv("LOG_FORMATTER", "console").lower()


# --- 2. 主配置函数 ---
def setup_logging():
    """
    配置 structlog 和标准库 logging，实现一个环境感知的、双模式的日志系统。

    该方案回归到了一个更简单、更直接的配置方法，
    专注于通过处理器链和主动接管 Uvicorn 日志记录器来实现核心目标。
    """

    # --- a. 定义 structlog 处理器链 ---
    # 这是一个日志记录在被最终渲染前所经过的处理管道。顺序非常重要。
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.stdlib.PositionalArgumentsFormatter(),
    ]

    # --- b. 根据环境选择最终的渲染器 ---
    final_renderer: Processor
    if LOG_FORMATTER == "json":
        # 生产环境：输出为机器可读的 JSON 格式。
        final_renderer = structlog.processors.JSONRenderer()
    else:
        # 开发环境：输出带色彩、为人类优化的控制台格式。
        final_renderer = structlog.dev.ConsoleRenderer(colors=True)

    # --- c. 配置 structlog ---
    # 这是 structlog 与标准库 logging 集成的关键步骤。
    structlog.configure(
        processors=[
            # 这个处理器是 structlog 与标准库 logging 集成的桥梁。
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # --- d. 配置标准库 logging ---
    # [核心修复] 创建一个自定义的格式化器，它使用我们上面定义的处理器链，
    # 并明确地将最终渲染器传递给 `processor` 参数。
    formatter = structlog.stdlib.ProcessorFormatter(
        # `foreign_pre_chain` 用于预处理来自标准库（非 structlog）的日志。
        # 我们让标准库日志也经过我们完整的处理链。
        foreign_pre_chain=shared_processors,
        # `processor` 参数是必需的，它指定了最终的渲染器。
        processor=final_renderer,
    )

    # 获取根日志记录器并清除任何可能由 Uvicorn 等库预先设置的处理器。
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(LOG_LEVEL)

    # 添加一个新的处理器，它将日志输出到标准输出，并使用我们自定义的格式化器。
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

    # --- e. 主动接管 Uvicorn 等库的日志记录器 ---
    # 这是实现日志格式完全统一的关键。
    for logger_name in ["uvicorn", "uvicorn.error", "uvicorn.access"]:
        uvicorn_logger = logging.getLogger(logger_name)
        # 清空它们自己的处理器
        uvicorn_logger.handlers.clear()
        # 告诉它们将日志“传播”给根记录器处理
        uvicorn_logger.propagate = True

    # --- f. 打印一条信息确认日志系统已配置完成 ---
    logger = structlog.get_logger("logging_config")
    logger.info("日志系统配置完成", formatter=LOG_FORMATTER, level=LOG_LEVEL)
