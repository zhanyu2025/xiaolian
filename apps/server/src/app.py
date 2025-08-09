import datetime
import logging
import os
import wave

from fastapi import Depends, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

# 导入我们新的服务管理器和依赖注入工具
from .services import ServiceManager

# --- 1. 日志与基本配置 ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# --- 2. 核心服务加载 ---
# 在服务器启动时，只执行一次：
# 实例化服务管理器，它会自动读取 config.yaml 并加载所有模型。
logger.info("应用开始启动，正在初始化服务管理器...")
try:
    service_manager = ServiceManager()
    logger.info("服务管理器初始化成功。")
except Exception as e:
    logger.exception("服务管理器初始化失败！应用无法启动。错误: %s", e)
    # 在生产环境中，这里应该退出程序
    service_manager = None


# --- 3. FastAPI 应用与依赖注入 ---
app = FastAPI(title="小练 - AI语音助手")


def get_service_manager():
    """一个 FastAPI 依赖项，用于在请求处理函数中获取服务管理器实例。"""
    return service_manager


# --- 4. 常量与路径 ---
SAMPLE_RATE = 16000
CHANNELS = 1
AUDIO_FORMAT_WIDTH = 2  # 16-bit PCM
RECORDINGS_DIR = "recordings"
os.makedirs(RECORDINGS_DIR, exist_ok=True)


# --- 5. WebSocket 端点定义 ---
# 关键：这个具体的路由必须定义在通用的静态文件挂载之前。
@app.websocket("/audio")
async def audio_handler(
    websocket: WebSocket, services: ServiceManager = Depends(get_service_manager)
):
    """
    处理一个发送纯 PCM 音频流的 WebSocket 连接。
    它会接收完整的音频流，然后在连接关闭后进行处理。
    """
    await websocket.accept()
    logger.info(f"客户端已连接: {websocket.client}")
    buffer = bytearray()

    if not services or not services.asr:
        logger.error("ASR 服务不可用，无法处理请求。")
        await websocket.close(code=1011, reason="ASR service not available")
        return

    try:
        # 主处理循环：接收所有数据块并存入缓冲区
        while True:
            pcm_data = await websocket.receive_bytes()
            if not pcm_data:
                continue
            buffer.extend(pcm_data)

    except WebSocketDisconnect:
        logger.info(f"客户端已正常断开: {websocket.client}")
    except Exception as e:
        logger.error(f"音频处理中发生未知错误: {e}", exc_info=True)
    finally:
        # --- 清理与处理 ---
        logger.info("连接关闭，开始进行清理和后续处理...")
        if buffer:
            combined_pcm_data = bytes(buffer)
            logger.info(f"共收到 {len(combined_pcm_data)} 字节的音频数据。")

            # 1. 使用注入的服务进行转写
            text = await services.asr.transcribe(pcm_data=combined_pcm_data)
            logger.info(f"语音识别完成。识别结果: '{text}'")

            # 2. (可选) 保存调试音频文件
            try:
                if websocket.client:
                    client_id = f"{websocket.client.host}_{websocket.client.port}"
                else:
                    client_id = "unknown_client"
                base_filename = f"pcm_recording_{client_id}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
                filename = os.path.join(RECORDINGS_DIR, base_filename)
                with wave.open(filename, "wb") as wf:
                    wf.setnchannels(CHANNELS)
                    wf.setsampwidth(AUDIO_FORMAT_WIDTH)
                    wf.setframerate(SAMPLE_RATE)
                    wf.writeframes(combined_pcm_data)
                logger.info(f"调试音频文件已保存: {filename}")
            except Exception as e:
                logger.error(f"保存调试音频文件失败: {e}", exc_info=True)

        else:
            logger.warning("本次连接没有收到任何音频数据。")
        logger.info("连接处理流程结束。")


# --- 6. 静态文件服务 ---
# 这个通用的挂载必须在所有具体的 API 端点之后定义。
public_dir = "public"
if os.path.exists(public_dir):
    logger.info(f"正在从 '{public_dir}' 目录挂载静态文件...")
    app.mount("/", StaticFiles(directory=public_dir, html=True), name="static")
else:
    logger.warning(f"未找到 '{public_dir}' 目录，Web UI 将不可用。")


# --- 7. Uvicorn 启动入口 ---
if __name__ == "__main__":
    import uvicorn

    src_dir = os.path.dirname(os.path.abspath(__file__))
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=[src_dir],
    )
