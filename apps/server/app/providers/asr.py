import abc
import asyncio
import os
from typing import Self

import structlog
from funasr import AutoModel

logger = structlog.get_logger(__name__)


class ASRProvider(abc.ABC):
    """自动语音识别 (ASR) 提供程序的抽象基类。"""

    @abc.abstractmethod
    def __init__(self, *args, **kwargs):
        """
        初始化ASR提供程序。
        具体的实现应在此处处理模型的加载和其他一次性设置。
        """
        raise NotImplementedError

    @abc.abstractmethod
    def stream_transcribe(self) -> "ASRStreamHandler":
        """
        创建并返回一个新的流式转录会话处理器。

        返回的处理器是一个异步上下文管理器，应被用于处理单个、连续的音频流。

        返回:
            一个实现了 ASRStreamHandler 接口的类的实例。
        """
        raise NotImplementedError


class ASRStreamHandler(abc.ABC):
    """
    ASR（自动语音识别）流处理器的抽象基类。

    此类设计用作异步上下文管理器，负责管理单个转录流的生命周期。
    """

    @abc.abstractmethod
    async def feed_audio(self, audio_chunk: bytes):
        """
        将原始音频块送入ASR流进行处理。

        参数:
            audio_chunk (bytes): 原始音频数据的字节对象。
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def get_finalized_transcript(self) -> str | None:
        """
        检查并返回一个已确认的最终转录片段（例如一个完整的句子）。

        此方法应为非阻塞的。如果自上次调用以来没有新的转录片段被确认，
        它应返回 None 或空字符串。

        返回:
            str | None: 如果有可用的最终转录文本，则返回该文本，否则返回 None。
        """
        raise NotImplementedError

    async def __aenter__(self) -> Self:
        """进入上下文，返回自身。"""
        return self

    @abc.abstractmethod
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """退出上下文，确保清理任何与流相关的资源。"""
        raise NotImplementedError


class SenseVoiceStreamHandler(ASRStreamHandler):
    """
    为 SenseVoice ASR 处理单个连续音频流的处理器。
    """

    def __init__(self, model, language: str = "auto", use_itn: bool = True):
        self._model = model
        self._language = language
        self._use_itn = use_itn
        self._cache = {}
        self._buffer = bytearray()
        self._finalized_transcript = None
        self.logger = logger.bind(stream_id=id(self))

    def _process_buffer(self, is_final: bool = False):
        """
        用于处理内部音频缓冲区的同步方法。
        """
        chunk_size = 9600
        while len(self._buffer) >= chunk_size or (is_final and len(self._buffer) > 0):
            chunk_to_process = self._buffer[:chunk_size]
            self._buffer = self._buffer[chunk_size:]
            final_flag_for_chunk = is_final and len(self._buffer) == 0

            try:
                result = self._model.generate(
                    input=bytes(chunk_to_process),
                    cache=self._cache,
                    language=self._language,
                    use_itn=self._use_itn,
                    is_final=final_flag_for_chunk,
                )
                if result and isinstance(result, list) and "text" in result[0]:
                    if final_flag_for_chunk:
                        self._finalized_transcript = result[0]["text"]
            except Exception as e:
                self.logger.error("ASR 模型 generate 失败", exc_info=e)
                break

    async def feed_audio(self, audio_chunk: bytes):
        """将音频附加到缓冲区并分块处理。"""
        self._buffer.extend(audio_chunk)
        await asyncio.to_thread(self._process_buffer, is_final=False)

    async def get_finalized_transcript(self) -> str | None:
        """如果最终转录可用，则返回它。"""
        if self._finalized_transcript:
            transcript = self._finalized_transcript
            self._finalized_transcript = None
            return transcript
        return None

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """将缓冲区中任何剩余的音频作为最后一段进行处理。"""
        self.logger.info("ASR 流正在结束，处理剩余音频。")
        await asyncio.to_thread(self._process_buffer, is_final=True)


class SenseVoiceASRProvider(ASRProvider):
    """
    使用 FunASR SenseVoice 模型的 ASR 提供程序。
    """

    _model = None

    def __init__(
        self,
        device: str = "cpu",
        **kwargs,
    ):
        """
        初始化并加载 SenseVoice 流式模型。
        """
        # 从环境变量读取模型目录的路径
        models_dir_path = os.getenv("MODELS_DIR_PATH")
        if not models_dir_path:
            raise ValueError("环境变量 MODELS_DIR_PATH 未设置。")

        # 构建模型的绝对路径
        model_path = os.path.join(models_dir_path, "SenseVoiceSmall")
        log = logger.bind(model_path=model_path, device=device)

        if not os.path.isdir(model_path):
            log.error("ASR 模型目录不存在")
            raise FileNotFoundError(f"指定的ASR模型路径不存在: {model_path}")

        if SenseVoiceASRProvider._model is None:
            log.info("正在初始化 SenseVoice ASR 提供程序")
            try:
                SenseVoiceASRProvider._model = AutoModel(
                    model=model_path,
                    device=device,
                    disable_update=True,
                    frontend_conf={"is_final": False},
                    **kwargs,
                )
                log.info("SenseVoice ASR 模型加载成功")
            except Exception as e:
                log.error("加载 SenseVoice 模型失败", exc_info=e)
                raise
        else:
            log.info("SenseVoice ASR 模型已经加载，跳过初始化")

        self._model = SenseVoiceASRProvider._model

    def stream_transcribe(self) -> SenseVoiceStreamHandler:
        """
        为转录会话创建一个新的流处理器。
        """
        logger.info("正在开始新的 ASR 转录流")
        return SenseVoiceStreamHandler(self._model)
