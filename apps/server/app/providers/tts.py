import abc
from collections.abc import AsyncGenerator

import edge_tts
import structlog

logger = structlog.get_logger(__name__)


class TTSProvider(abc.ABC):
    """
    文本到语音 (TTS) 提供程序的抽象基类。
    定义了所有TTS提供程序必须遵循的统一接口。
    """

    @abc.abstractmethod
    def __init__(self, *args, **kwargs):
        """
        初始化TTS提供程序。
        具体的实现应在此处处理客户端或凭据的配置，或加载本地模型。
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def stream(self, text: str) -> AsyncGenerator[bytes, None]:
        """
        从文本合成语音并流式传输音频数据。

        这个方法应该是一个异步生成器，当音频块可用时立即产生它们。

        参数:
            text (str): 需要被合成为语音的文本。

        产生 (Yields):
            bytes: 代表合成音频块的字节。
                   音频的格式（例如 MP3、WAV）由具体实现决定。
        """
        # 'yield' 语句是必需的，即使在抽象方法中也是如此，
        # 以便解释器能将其接口识别为生成器函数。
        yield b""


class EdgeTTSProvider(TTSProvider):
    """
    使用 edge-tts 库的TTS提供程序。
    它通过调用微软的 Edge TTS 服务来流式生成高质量的语音。
    """

    def __init__(self, voice: str = "zh-CN-XiaoxiaoNeural", rate: str = "+0%", volume: str = "+0%"):
        """
        初始化 EdgeTTSProvider。

        参数:
            voice (str): 要使用的语音模型。可以在 `edge-tts --list-voices` 中查找可用的声音。
            rate (str): 语速调整，例如 "+10%" 或 "-5%"。
            volume (str): 音量调整，例如 "+10%" 或 "-5%"。
        """
        logger.info(
            "正在初始化 EdgeTTSProvider",
            voice=voice,
            rate=rate,
            volume=volume,
        )
        self._voice = voice
        self._rate = rate
        self._volume = volume
        # edge-tts 本身是轻量级的，不需要在初始化时加载重模型，
        # 真正的通信发生在调用 stream 方法时。

    async def stream(self, text: str) -> AsyncGenerator[bytes, None]:
        """
        流式合成语音。

        参数:
            text (str): 要合成的文本。

        产生 (Yields):
            bytes: MP3 格式的音频数据块。
        """
        if not text:
            # 如果文本为空，则直接返回，不产生任何内容
            return

        log = logger.bind(text=text[:30] + "...")
        log.info("开始为文本流式传输TTS")
        try:
            # 创建 Communicate 对象，这是 edge-tts 的核心
            communicate = edge_tts.Communicate(
                text, self._voice, rate=self._rate, volume=self._volume
            )

            # communicate.stream() 本身就是一个异步生成器
            async for chunk in communicate.stream():
                # edge-tts 会产生不同类型的块，我们只关心包含音频的块
                if chunk["type"] == "audio":
                    yield chunk["data"]

        except Exception as e:
            log.error("EdgeTTS 在流式处理中发生错误", exc_info=e)
            # 在出错时，我们可以选择产生一个空字节或只是停止生成器
            # 这里选择停止，调用方将知道流已结束。
