import asyncio
import pathlib
from contextlib import asynccontextmanager

import structlog
from app.logging.config import setup_logging
from app.logging.middleware import StructlogRequestMiddleware
from app.providers.asr import ASRProvider, SenseVoiceASRProvider
from app.providers.llm import LLMProvider, OpenAILLMProvider
from app.providers.tts import EdgeTTSProvider, TTSProvider
from app.providers.vad import SileroVADProvider, VADProvider
from app.services.pipeline import VoicePipeline
from fastapi import Depends, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

setup_logging()

logger = structlog.get_logger(__name__)


class AppState:
    """
    一个简单的类，用于在FastAPI应用的整个生命周期中存储和管理加载好的模型实例。
    """

    vad_provider: VADProvider | None = None
    asr_provider: ASRProvider | None = None
    llm_provider: LLMProvider | None = None
    tts_provider: TTSProvider | None = None


app_state = AppState()


# --- 4. FastAPI 生命周期 ---
@asynccontextmanager
async def lifespan(_: FastAPI):
    """
    FastAPI 应用的生命周期管理器，负责在应用启动时加载模型。
    """
    logger.info("应用启动，开始加载模型和初始化客户端...")
    init_tasks = [
        asyncio.to_thread(SileroVADProvider),
        asyncio.to_thread(SenseVoiceASRProvider),
        asyncio.to_thread(EdgeTTSProvider),
        asyncio.to_thread(OpenAILLMProvider),
    ]
    results = await asyncio.gather(*init_tasks, return_exceptions=True)

    provider_names = ["VAD", "ASR", "TTS", "LLM"]
    provider_attrs = ["vad_provider", "asr_provider", "tts_provider", "llm_provider"]
    has_error = False

    # 类型安全地处理并发任务的结果
    for name, attr, result in zip(provider_names, provider_attrs, results, strict=False):
        if isinstance(result, Exception):
            logger.fatal(f"加载 {name} 提供程序时发生严重错误", exc_info=result)
            has_error = True
        else:
            setattr(app_state, attr, result)

    if has_error:
        logger.fatal("由于一个或多个核心服务提供程序加载失败，应用可能无法正常工作。")
    else:
        logger.info("所有模型和客户端均已成功初始化，服务准备就绪。")

    yield

    logger.info("应用关闭，清理资源...")


app = FastAPI(lifespan=lifespan)
app.add_middleware(StructlogRequestMiddleware)


def get_pipeline() -> VoicePipeline:
    """
    依赖注入函数，为每个连接创建并提供一个 VoicePipeline 实例。
    """
    if not all(
        [
            app_state.vad_provider,
            app_state.asr_provider,
            app_state.llm_provider,
            app_state.tts_provider,
        ]
    ):
        logger.error("应用未正确初始化，一个或多个服务提供商不可用。")
        raise RuntimeError("应用未正确初始化，一个或多个服务提供商不可用。")

    # 使用 assert 来向 Pyright 保证，在此代码点之后，
    # provider 实例绝对不可能是 None。
    assert app_state.vad_provider is not None
    assert app_state.asr_provider is not None
    assert app_state.llm_provider is not None
    assert app_state.tts_provider is not None

    return VoicePipeline(
        vad_provider=app_state.vad_provider,
        asr_provider=app_state.asr_provider,
        llm_provider=app_state.llm_provider,
        tts_provider=app_state.tts_provider,
    )


@app.websocket("/audio")
async def websocket_handler(
    websocket: WebSocket,
    pipeline: VoicePipeline = Depends(get_pipeline),
):
    """
    WebSocket 通信端点。
    """
    await websocket.accept()
    logger.info("接收到新的 WebSocket 连接")
    try:
        await pipeline.run(websocket)
    except WebSocketDisconnect:
        logger.info("客户端主动断开了 WebSocket 连接")
    except Exception as e:
        logger.error("WebSocket 连接中发生意外错误", exc_info=e)
    finally:
        logger.info("WebSocket 连接已关闭")


current_file_path = pathlib.Path(__file__).parent
public_files_path = current_file_path.parent / "public"

app.mount("/", StaticFiles(directory=public_files_path, html=True), name="static")
