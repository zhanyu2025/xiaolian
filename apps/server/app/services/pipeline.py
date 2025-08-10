import asyncio

import structlog
from app.providers.asr import ASRProvider
from app.providers.llm import LLMProvider
from app.providers.tts import TTSProvider
from app.providers.vad import VADProvider
from fastapi import WebSocket, WebSocketDisconnect

# 获取一个模块级别的日志记录器
logger = structlog.get_logger(__name__)


class VoicePipeline:
    """
    语音处理流水线服务。

    这个类负责编排 VAD、ASR、LLM 和 TTS 四个模块，处理一个完整的实时语音对话会话。
    它的核心设计思想是使用 asyncio 的后台任务来处理耗时的LLM和TTS操作，
    并包含一个内部缓冲区来正确处理 VAD 模型的固定大小音频块输入。
    """

    # Silero VAD 在 16kHz 采样率下期望的音频块大小 (512个采样点 * 16位/采样点 / 8位/字节 = 1024字节)
    VAD_CHUNK_SIZE = 1024

    def __init__(
        self,
        vad_provider: VADProvider,
        asr_provider: ASRProvider,
        llm_provider: LLMProvider,
        tts_provider: TTSProvider,
    ):
        """
        初始化 VoicePipeline。

        参数:
            vad_provider: VAD 提供程序实例。
            asr_provider: ASR 提供程序实例。
            llm_provider: LLM 提供程序实例。
            tts_provider: TTS 提供程序实例。
        """
        self.vad = vad_provider
        self.asr = asr_provider
        self.llm = llm_provider
        self.tts = tts_provider
        self.active_llm_task: asyncio.Task | None = None
        # 为 VAD 创建一个内部缓冲区，以处理任意大小的输入音频流。
        self._vad_buffer = bytearray()

    async def run(self, websocket: WebSocket):
        """
        处理一个 WebSocket 连接的完整生命周期。

        参数:
            websocket: 客户端的 WebSocket 连接实例。
        """
        async with self.asr.stream_transcribe() as asr_stream:
            try:
                async for audio_chunk in websocket.iter_bytes():
                    # 1. 将音频块同时喂给 ASR 流处理器。
                    #    ASR 处理器有自己的内部缓冲和逻辑。
                    await asr_stream.feed_audio(audio_chunk)

                    # 2. 处理 VAD 的缓冲和分块逻辑。
                    #    将传入的音频块追加到 VAD 缓冲区。
                    self._vad_buffer.extend(audio_chunk)

                    # 当缓冲区中的数据足够进行一次 VAD 推理时，循环处理。
                    while len(self._vad_buffer) >= self.VAD_CHUNK_SIZE:
                        # 从缓冲区前端切出一个 VAD 模型期望大小的块。
                        vad_chunk = self._vad_buffer[: self.VAD_CHUNK_SIZE]
                        self._vad_buffer = self._vad_buffer[self.VAD_CHUNK_SIZE :]

                        # [核心修复] 将 bytearray 显式转换为 bytes 以满足类型检查。
                        if self.vad.is_speech(bytes(vad_chunk)):
                            # 实现“打断”(Barge-in)功能。
                            if self.active_llm_task and not self.active_llm_task.done():
                                logger.info("检测到用户说话，正在打断当前的TTS播放...")
                                self.active_llm_task.cancel()
                                self.active_llm_task = None

                    # 3. 检查 ASR 是否已经识别出了一段完整的句子。
                    transcript = await asr_stream.get_finalized_transcript()
                    if transcript:
                        logger.info("ASR识别到完整句子", transcript=transcript)

                        # 4. 创建后台任务来处理 LLM 和 TTS，不阻塞主循环。
                        self.active_llm_task = asyncio.create_task(
                            self._process_llm_and_tts(transcript, websocket)
                        )

            except WebSocketDisconnect:
                logger.info("客户端断开连接。")
            except Exception as e:
                logger.error("处理语音流时发生未知错误", exc_info=e)
            finally:
                # 5. 清理工作：如果连接关闭时仍有正在运行的任务，取消它。
                if self.active_llm_task and not self.active_llm_task.done():
                    self.active_llm_task.cancel()
                logger.info("语音流水线会话结束。")

    async def _process_llm_and_tts(self, text: str, websocket: WebSocket):
        """
        后台任务：调用 LLM 获取回复，然后流式传输 TTS 音频回客户端。

        参数:
            text (str): ASR 识别出的文本。
            websocket: 客户端的 WebSocket 连接实例。
        """
        try:
            llm_response = await self.llm.chat(text)
            tts_stream = self.tts.stream(llm_response)

            async for tts_chunk in tts_stream:
                await websocket.send_bytes(tts_chunk)

            logger.info("TTS音频流发送完毕。")

        except asyncio.CancelledError:
            logger.info("LLM/TTS 任务被成功取消。")
        except Exception as e:
            logger.error("在LLM/TTS后台任务中发生错误", exc_info=e)
