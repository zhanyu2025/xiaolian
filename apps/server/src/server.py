import asyncio
import datetime
import logging
import os
import wave

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

# --- 1. 基本配置 ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="实时语音AI助手服务器 (纯PCM)")

# --- 2. 常量与路径 ---
SAMPLE_RATE = 16000
CHANNELS = 1
AUDIO_FORMAT_WIDTH = 2  # 16-bit PCM (s16)
RECORDINGS_DIR = "/app/recordings"

# 确保在容器中录音目录存在
os.makedirs(RECORDINGS_DIR, exist_ok=True)


# --- 3. 统一的纯PCM音频端点 ---
@app.websocket("/audio")
async def audio_handler(websocket: WebSocket):
    """
    处理一个发送纯PCM音频流的WebSocket连接。
    这个端点是健壮的，能够处理来自任何客户端（CLI或Web）的原始音频数据。
    它实现了一个服务器端缓冲，以确保写入WAV文件的数据块大小是规整的。
    """
    await websocket.accept()
    logger.info(f"客户端已连接: {websocket.client}")

    # --- 文件和缓冲区初始化 ---
    wf: wave.Wave_write | None = None
    filename = ""
    # 即使客户端进行了缓冲，服务器端缓冲也是一个好习惯，可以平滑网络抖动带来的数据块大小不一的问题。
    buffer = bytearray()
    BUFFER_SIZE_TO_WRITE = 4096  # 每累积4KB写入一次文件

    try:
        if websocket.client:
            client_id = f"{websocket.client.host}_{websocket.client.port}"
        else:
            client_id = "unknown_client"
        base_filename = (
            f"pcm_recording_{client_id}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
        )
        filename = os.path.join(RECORDINGS_DIR, base_filename)

        # 初始化WAV文件写入器
        wf = wave.open(filename, "wb")
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(AUDIO_FORMAT_WIDTH)
        wf.setframerate(SAMPLE_RATE)
        logger.info(f"录音将保存到: {filename}")

        # --- 主处理循环 ---
        while True:
            # 1. 接收来自客户端的原始PCM数据块
            pcm_data = await websocket.receive_bytes()
            if not pcm_data:
                continue

            # 2. 将数据加入缓冲区
            buffer.extend(pcm_data)

            # 3. 当缓冲区累积到足够大时，写入文件并清空
            if len(buffer) >= BUFFER_SIZE_TO_WRITE:
                await asyncio.to_thread(wf.writeframes, buffer)
                buffer.clear()

    except WebSocketDisconnect:
        logger.info(f"客户端已正常断开: {websocket.client}")
    except Exception as e:
        logger.error(f"音频处理中发生未知错误: {e}", exc_info=True)
    finally:
        # --- 清理 ---
        if wf:
            # 将缓冲区中剩余的任何数据写入文件
            if buffer:
                logger.info(f"连接关闭，正在写入剩余的 {len(buffer)} 字节...")
                await asyncio.to_thread(wf.writeframes, buffer)

            await asyncio.to_thread(wf.close)
            logger.info(f"WAV文件已保存: {filename}")
        else:
            logger.warning("本次连接没有创建WAV文件。")
        logger.info("连接已关闭。")


# --- 4. 静态文件服务 ---
# 在Docker容器中，我们的静态文件位于 /app/public
public_files_path = "/app/public"
app.mount("/", StaticFiles(directory=public_files_path, html=True), name="static")
