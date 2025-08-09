import asyncio
import io
import logging
import os
import sys
import time

import psutil

# 尝试导入 FunASR 的核心模块。
try:
    from funasr import AutoModel
    from funasr.utils.postprocess_utils import rich_transcription_postprocess
except ImportError:
    logging.error("FunASR 库未安装或找不到。请运行 'pip install funasr==1.2.3' 等相关依赖。")
    AutoModel = None
    rich_transcription_postprocess = None

# 导入基类
from .base import ASRProviderBase

# 设置一个模块级的日志记录器
logger = logging.getLogger(__name__)


class CaptureOutput:
    """
    一个上下文管理器，用于捕获 FunASR 初始化时打印到标准输出的日志，
    并将其重定向到我们自己的日志系统中，以保持日志格式的统一。
    """

    def __enter__(self):
        self._original_stdout = sys.stdout
        self._output = io.StringIO()
        sys.stdout = self._output
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        sys.stdout = self._original_stdout
        captured_output = self._output.getvalue().strip()
        if captured_output:
            logger.info(f"FunASR 初始化原生输出:\n{captured_output}")
        self._output.close()


class FunASRProvider(ASRProviderBase):
    """
    使用本地 FunASR (SenseVoice) 模型进行语音识别的提供者。
    该实现基于 `trust_remote_code` 的本地模型加载方式。
    """

    def __init__(self, config: dict):
        """
        初始化 FunASR 提供者。

        参数:
            config (dict): 从 config.yaml 加载的配置字典，
                           应包含 'model_path' 键。
        """
        super().__init__()

        # 直接从配置中获取模型路径。我们期望它是一个容器内的绝对路径。
        self.model_path = config.get("model_path")
        if not self.model_path:
            raise ValueError("ASR 配置中缺少 'model_path' 键。")

        if not os.path.exists(self.model_path):
            raise ValueError(f"提供的模型路径无效或不存在: {self.model_path}")

        # 检查内存
        min_mem_gb = 2
        min_mem_bytes = min_mem_gb * 1024 * 1024 * 1024
        total_mem = psutil.virtual_memory().total
        if total_mem < min_mem_bytes:
            logger.warning(
                f"可用内存不足 {min_mem_gb}G (当前: {total_mem / (1024 * 1024):.2f} MB)，"
                "启动 FunASR 可能会失败或运行缓慢。"
            )

        self.model = None
        self._load_model()

    def _load_model(self):
        """
        私有方法，用于从指定的本地路径加载 SenseVoice 模型。
        """
        if not AutoModel:
            logger.error("无法加载模型，因为 FunASR 库导入失败。")
            return

        logger.info(
            f"正在从本地路径初始化 FunASR 模型 (trust_remote_code 模式): {self.model_path}..."
        )
        try:
            with CaptureOutput():
                self.model = AutoModel(
                    model=self.model_path,
                    vad_kwargs={"max_single_segment_time": 30000},
                    disable_update=True,
                )
            logger.info(f"FunASR 模型从 '{self.model_path}' 加载成功。")
        except Exception as e:
            logger.error(f"从本地路径加载 FunASR 模型失败: {e}", exc_info=True)

    def _transcribe_sync(self, pcm_data: bytes) -> str:
        """
        同步的转写核心逻辑。
        """
        if not self.model:
            logger.error("FunASR 模型未加载，无法进行转录。")
            return ""

        if not pcm_data:
            logger.warning("输入的音频数据为空，跳过转录。")
            return ""

        logger.info(f"收到 {len(pcm_data)} 字节的音频数据，开始同步转录...")
        start_time = time.time()

        try:
            result = self.model.generate(
                input=pcm_data,
                cache={},
                language="auto",
                use_itn=True,
                batch_size_s=60,
                merge_vad=True,
                merge_length_s=15,
            )

            if not result or not isinstance(result, list) or "text" not in result[0]:
                logger.warning(f"转录结果格式不符合预期: {result}")
                return ""

            text = result[0].get("text", "")
            if rich_transcription_postprocess:
                text = rich_transcription_postprocess(text)

            end_time = time.time()
            duration = end_time - start_time
            logger.info(f"转录成功 (耗时: {duration:.3f}s)。结果: '{text}'")
            return text

        except Exception as e:
            logger.error(f"同步转录过程中发生严重错误: {e}", exc_info=True)
            return ""

    async def transcribe(self, pcm_data: bytes) -> str:
        """
        将原始的 PCM 音频数据转录为文本 (异步接口)。
        """
        return await asyncio.to_thread(self._transcribe_sync, pcm_data)
