import abc
import logging

logger = logging.getLogger(__name__)


class ASRProviderBase(abc.ABC):
    """
    自动语音识别 (ASR) 服务提供者的抽象基类。

    所有具体的 ASR 提供者都必须继承此类，并实现其定义的所有抽象方法。
    这确保了在服务加载器和应用核心中，可以以统一的方式调用不同的 ASR 服务。
    """

    def __init__(self):
        """
        初始化 ASR 提供者基类。
        子类可以在自己的 __init__ 中调用 super().__init__()。
        """
        logger.info(f"正在初始化 ASR 提供者: {self.__class__.__name__}")

    @abc.abstractmethod
    async def transcribe(self, pcm_data: bytes) -> str:
        """
        将原始的 PCM 音频数据转录为文本。

        这是一个抽象方法，所有子类都必须实现此方法。

        参数:
            pcm_data (bytes): 16k 采样率, 16-bit, 单声道的 PCM 音频数据。

        返回:
            str: 转录后的文本。如果转录失败，应返回空字符串。
        """
        raise NotImplementedError("ASRProviderBase 的子类必须实现 transcribe 方法。")
