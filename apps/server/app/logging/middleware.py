import uuid

import structlog


class StructlogRequestMiddleware:
    """
    一个原始的 ASGI 中间件，用于在每个请求的上下文中注入一个唯一的请求ID。

    这对于追踪单个请求（无论是HTTP还是WebSocket）在其整个生命周期内的所有
    相关日志至关重要。
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        # 我们只关心 http 和 websocket 类型的作用域
        if scope["type"] not in ["http", "websocket"]:
            await self.app(scope, receive, send)
            return

        # 为新请求清理上下文变量，以防上一个请求的上下文意外泄漏
        structlog.contextvars.clear_contextvars()

        # 生成一个唯一的请求ID
        request_id = str(uuid.uuid4())

        # 将请求ID绑定到日志上下文中，在此作用域内后续的所有日志记录
        # 都会自动包含这个 "request_id" 字段。
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
        )

        await self.app(scope, receive, send)
