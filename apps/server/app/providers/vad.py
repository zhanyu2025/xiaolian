import abc
import os
from typing import Literal

import numpy as np
import structlog
import torch

logger = structlog.get_logger(__name__)


class VADProvider(abc.ABC):
    """
    语音活动检测 (VAD) 提供程序的抽象基类。
    定义了所有VAD提供程序必须遵循的统一接口。
    """

    @abc.abstractmethod
    def __init__(self, *args, **kwargs):
        """
        初始化VAD提供程序。
        具体的实现应在此处处理模型的加载和设置。
        """
        raise NotImplementedError

    @abc.abstractmethod
    def is_speech(self, audio_chunk: bytes) -> bool:
        """
        分析一个音频块，以确定它是否包含语音。

        参数:
            audio_chunk (bytes): 包含原始音频数据的字节对象。
                                 具体的实现应处理特定的音频格式（如采样率、通道数）。

        返回:
            bool: 如果检测到语音，则为 True，否则为 False。
        """
        raise NotImplementedError


class SileroVADProvider(VADProvider):
    """
    使用 Silero VAD 模型的 VAD 提供程序。

    这个提供程序执行无状态的、逐块的语音活动检测。
    它假定输入的音频是 16kHz、16位单声道的 PCM 格式。
    """

    _model: torch.jit.ScriptModule
    _threshold: float

    def __init__(
        self,
        model_name: str = "silero_vad",
        threshold: float = 0.5,
        device: Literal["cpu", "cuda"] = "cpu",
    ):
        """
        初始化并加载 Silero VAD 模型。

        参数:
            model_name (str): 从 hub 中加载的模型名称。
            threshold (float): 用于检测语音的概率阈值。
            device (str): 运行模型的设备（'cpu' 或 'cuda'）。
        """
        # 从环境变量读取模型目录的路径
        models_dir_path = os.getenv("MODELS_DIR_PATH")
        if not models_dir_path:
            raise ValueError("环境变量 MODELS_DIR_PATH 未设置。")

        # 构建模型的绝对路径
        model_path = os.path.join(models_dir_path, "snakers4_silero-vad")
        log = logger.bind(
            model_path=model_path,
            model_name=model_name,
            device=device,
        )

        if not os.path.isdir(model_path):
            log.error("VAD 模型目录不存在")
            raise FileNotFoundError(f"指定的VAD模型路径不存在: {model_path}")

        log.info("正在初始化 Silero VAD 提供程序")
        try:
            # 使用 torch.hub.load 从绝对路径加载模型
            self._model, _ = torch.hub.load(
                repo_or_dir=model_path,
                source="local",
                model=model_name,
                force_reload=False,
            )
            self._model.to(device)
            self._threshold = threshold
            self._model.reset_states()
            log.info("Silero VAD 模型加载成功")
        except Exception as e:
            log.error("加载 Silero VAD 模型失败", exc_info=e)
            raise

    def is_speech(self, audio_chunk: bytes) -> bool:
        """
        在原始的 16kHz、16位单声道 PCM 音频块中检测语音。

        参数:
            audio_chunk: 原始 PCM 数据的字节。为了获得最佳结果，块大小
                         应为 [256, 512, 768, 1024, 1536] 个采样点之一。

        返回:
            如果语音概率高于阈值，则为 True，否则为 False。
        """
        if not audio_chunk:
            return False

        try:
            audio_int16 = np.frombuffer(audio_chunk, dtype=np.int16)
            audio_float32 = audio_int16.astype(np.float32) / 32768.0
            audio_tensor = torch.from_numpy(audio_float32)

            with torch.no_grad():
                speech_prob = self._model(audio_tensor, 16000).item()

            return speech_prob >= self._threshold
        except Exception as e:
            logger.error("VAD 处理时发生错误", exc_info=e)
            return False
