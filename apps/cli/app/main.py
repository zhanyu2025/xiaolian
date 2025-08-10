import argparse
import asyncio
import datetime
import logging
import os
import sys
import wave

import numpy as np
import websockets

try:
    import pyaudio
except ImportError:
    logging.basicConfig(level=logging.ERROR)
    logging.error("错误: PyAudio 库未安装。")
    logging.error("请先确保您已安装了 PortAudio (例如在macOS上运行 'brew install portaudio')。")
    logging.error("然后，请在您的虚拟环境中运行 'make install'。")
    sys.exit(1)

# --- 日志配置 ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - [CLI] %(message)s")
logger = logging.getLogger(__name__)

# --- 常量配置 ---
SAMPLE_RATE = 16000
AUDIO_FORMAT = pyaudio.paInt16
CHANNELS = 1
SAMPLES_PER_CHUNK = int(SAMPLE_RATE * 30 / 1000)  # 30ms chunks
RECORDINGS_DIR = os.path.join(os.path.dirname(__file__), "..", "recordings")
os.makedirs(RECORDINGS_DIR, exist_ok=True)


class AppState:
    """一个简单的类，用于在不同的异步任务之间共享状态。"""

    def __init__(self):
        self.status_text = "正在初始化..."
        self.vu_level = 0.0
        self.is_running = True


class MicrophoneProcessor:
    """
    负责从麦克风捕获音频，计算音量，并将音频数据放入队列以供网络发送和文件保存。
    """

    def __init__(self, state: AppState):
        self.p_audio = pyaudio.PyAudio()
        self.state = state
        self.loop = asyncio.get_event_loop()
        self.network_queue = asyncio.Queue()
        self.file_queue = asyncio.Queue()
        self.stream: pyaudio.Stream | None = None
        self.wave_file: wave.Wave_write | None = None
        self.wave_filename: str | None = None

    def _setup_wave_file(self):
        """配置并打开一个WAV文件用于录音。"""
        filename_base = f"cli_recording_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
        self.wave_filename = os.path.join(RECORDINGS_DIR, filename_base)
        try:
            wf = wave.open(self.wave_filename, "wb")
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(self.p_audio.get_sample_size(AUDIO_FORMAT))
            wf.setframerate(SAMPLE_RATE)
            self.wave_file = wf
            self.state.status_text = f"录音将保存到: {os.path.basename(self.wave_filename)}"
            logger.info(f"录音文件已准备就绪: {self.wave_filename}")
        except Exception as e:
            logger.error(f"无法创建录音文件 {self.wave_filename}: {e}")
            self.wave_file = None
            self.wave_filename = None

    def _pyaudio_callback(self, in_data, frame_count, time_info, status):
        """PyAudio的实时回调函数。警告：不要在此函数中执行任何阻塞操作！"""
        if self.state.is_running:
            audio_data = np.frombuffer(in_data, dtype=np.int16)
            rms = np.sqrt(np.mean(audio_data.astype(float) ** 2))
            vu_level = min(rms / 10000, 1.0)
            self.state.vu_level = self.state.vu_level * 0.7 + vu_level * 0.3

            self.loop.call_soon_threadsafe(self.network_queue.put_nowait, in_data)
            if self.wave_file:
                self.loop.call_soon_threadsafe(self.file_queue.put_nowait, in_data)

        return (None, pyaudio.paContinue)

    def start(self):
        """打开麦克风流并开始录音。"""
        self._setup_wave_file()
        self.stream = self.p_audio.open(
            format=AUDIO_FORMAT,
            channels=CHANNELS,
            rate=SAMPLE_RATE,
            input=True,
            frames_per_buffer=SAMPLES_PER_CHUNK,
            stream_callback=self._pyaudio_callback,
        )
        self.stream.start_stream()
        logger.info("麦克风已启动。")

    def stop(self):
        """停止并关闭麦克风流，释放所有资源。"""
        self.state.is_running = False
        if self.stream:
            if self.stream.is_active():
                self.stream.stop_stream()
            self.stream.close()
        self.p_audio.terminate()
        logger.info("麦克风已停止。")


async def network_task(mic: MicrophoneProcessor, state: AppState, uri: str):
    """处理WebSocket连接和数据发送。"""
    state.status_text = f"正在连接到 {uri}..."
    try:
        async with websockets.connect(uri) as websocket:
            state.status_text = "连接成功！正在实时传输音频..."
            logger.info("成功连接到 WebSocket 服务器")

            while state.is_running:
                try:
                    chunk = await asyncio.wait_for(mic.network_queue.get(), timeout=0.1)
                    await websocket.send(chunk)
                except asyncio.TimeoutError:
                    continue
    except ConnectionRefusedError:
        logger.error(f"无法连接到服务器 {uri}。请确认服务端正在运行。")
        state.status_text = "连接失败，请检查服务端状态。"
    except (
        websockets.exceptions.ConnectionClosedError,
        websockets.exceptions.InvalidURI,
    ) as e:
        logger.warning(f"WebSocket 连接错误: {e}")
        state.status_text = f"连接地址或状态错误: {e}"
    except Exception as e:
        logger.error(f"发生未知网络错误: {e}", exc_info=True)
        state.status_text = f"发生未知错误: {e}"
    finally:
        state.is_running = False  # 确保其他任务可以正常退出
        logger.info("网络任务结束。")


async def save_audio_task(mic: MicrophoneProcessor, state: AppState):
    """从队列中获取音频数据并将其写入WAV文件。"""
    if not mic.wave_file:
        return

    logger.info("文件保存任务已启动。")
    try:
        while state.is_running:
            try:
                data = await asyncio.wait_for(mic.file_queue.get(), timeout=0.1)
                mic.wave_file.writeframes(data)
            except asyncio.TimeoutError:
                continue
    finally:
        if mic.wave_file:
            mic.wave_file.close()
            logger.info(f"录音文件已成功保存和关闭: {mic.wave_filename}")


async def tui_task(state: AppState):
    """一个极简的、持续渲染状态和音量条的TUI循环。"""
    bar_width = 40
    sys.stdout.write("\n")
    while state.is_running:
        filled_len = int(bar_width * state.vu_level)
        bar = "█" * filled_len + "-" * (bar_width - filled_len)
        line = f"  状态: {state.status_text:<55} | 音量: [{bar}] {int(state.vu_level * 100):>3d}% "
        sys.stdout.write(f"\r{line}")
        sys.stdout.flush()
        try:
            await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            break
    sys.stdout.write("\n\n")


async def amain(args):
    """应用的主异步函数，负责初始化和协调所有任务。"""
    state = AppState()
    mic_processor = MicrophoneProcessor(state)

    print("\n--- 🎤 小练语音助手客户端 ---")
    print("    正在启动... (按 Ctrl+C 退出)")

    try:
        mic_processor.start()

        uri = f"ws://{args.host}:{args.port}/audio"

        all_tasks = asyncio.gather(
            tui_task(state),
            network_task(mic_processor, state, uri),
            save_audio_task(mic_processor, state),
        )
        await all_tasks

    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("捕获到中断信号 (Ctrl+C)。")
    finally:
        print("\n正在关闭...")
        state.is_running = False
        if mic_processor:
            mic_processor.stop()
        # 等待所有任务完成
        await asyncio.sleep(0.5)
        print("客户端已成功关闭。")


def main():
    parser = argparse.ArgumentParser(description="小练语音助手命令行客户端")
    parser.add_argument("--host", type=str, default="localhost", help="服务器主机")
    parser.add_argument("--port", type=int, default=8000, help="服务器端口")
    parser.add_argument(
        "--client_id", type=str, default="default_user", help="用于标识客户端的唯一ID"
    )
    args = parser.parse_args()

    try:
        asyncio.run(amain(args))
    except Exception as e:
        logger.error(f"发生未处理的错误: {e}", exc_info=True)
        print(f"\n发生未处理的错误: {e}")


if __name__ == "__main__":
    main()
