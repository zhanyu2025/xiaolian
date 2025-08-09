import io
import logging
import os
import sys
import time

import psutil

# 尝试导入 FunASR 的核心模块。
# 把它放在文件的顶部可以提前知道依赖是否缺失。
try:
    from funasr import AutoModel
    from funasr.utils.postprocess_utils import rich_transcription_postprocess
except ImportError:
    logging.error(
        "FunASR 库未安装或找不到。请运行 'pip install funasr modelscope torch torchaudio'。"
    )
    AutoModel = None
    rich_transcription_postprocess = None


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
            logger.info(f"FunASR 初始化输出:\n{captured_output}")
        self._output.close()


class FunASRService:
    """
    一个服务类，用于使用 FunASR 模型处理自动语音识别 (ASR)。
    该实现参考了 xiaozhi-server 的健壮实现。
    """

    def __init__(self, model_path: str):
        """
        初始化 FunASR 服务。

        参数:
            model_path (str): SenseVoice 模型的本地路径。这是必需的参数。
        """
        if not model_path or not os.path.exists(model_path):
            raise ValueError(f"模型路径无效或不存在: {model_path}")

        # 检查内存，这是一个好的健壮性实践
        min_mem_gb = 2
        min_mem_bytes = min_mem_gb * 1024 * 1024 * 1024
        total_mem = psutil.virtual_memory().total
        if total_mem < min_mem_bytes:
            logger.warning(
                f"可用内存不足 {min_mem_gb}G (当前: {total_mem / (1024 * 1024):.2f} MB)，"
                "启动 FunASR 可能会失败或运行缓慢。"
            )

        self.model_path = model_path
        self.model = None
        self._load_model()

    def _load_model(self):
        """
        私有方法，用于从指定的本地路径加载 SenseVoice 模型。
        """
        if not AutoModel:
            logger.error("无法加载模型，因为 FunASR 库导入失败。")
            return

        logger.info(f"正在从本地路径初始化 FunASR 模型: {self.model_path}...")
        try:
            # 捕获 FunASR 的原生 print 输出，并重定向到 logger
            with CaptureOutput():
                self.model = AutoModel(
                    model=self.model_path,
                    vad_model="fsmn-vad",
                    vad_kwargs={"max_single_segment_time": 30000},
                    disable_update=True,  # 禁止模型运行时自动更新
                    hub="hf",
                    # 如果有可用的 GPU，可以取消下面的注释来使用 CUDA
                    # device="cuda:0",
                )
            logger.info(f"FunASR 模型从 '{self.model_path}' 加载成功。")
        except Exception as e:
            logger.error(f"从本地路径加载 FunASR 模型失败: {e}", exc_info=True)

    def transcribe(self, pcm_data: bytes) -> str:
        """
        将原始的 PCM 音频数据转录为文本。

        参数:
            pcm_data (bytes): 16k 采样率, 16-bit, 单声道的 PCM 音频数据。

        返回:
            str: 转录后的文本。如果转录失败，则返回空字符串。
        """
        if not self.model:
            logger.error("FunASR 模型未加载，无法进行转录。")
            return ""

        if not pcm_data:
            logger.warning("输入的音频数据为空，跳过转录。")
            return ""

        logger.info(f"收到 {len(pcm_data)} 字节的音频数据，开始转录...")
        start_time = time.time()
        try:
            # 直接将 bytes 数据传递给 model.generate
            result = self.model.generate(
                input=pcm_data,
                cache={},
                language="auto",
                use_itn=True,  # 应用反文本正则化 (例如, “一百”转为“100”)
                batch_size_s=60,
            )

            if not result or not isinstance(result, list) or "text" not in result[0]:
                logger.warning(f"转录结果格式不符合预期: {result}")
                return ""

            # 使用富文本后处理，可以得到更整洁的标点和格式
            if rich_transcription_postprocess:
                text = rich_transcription_postprocess(result[0].get("text", ""))
            else:
                text = result[0].get("text", "")

            end_time = time.time()
            duration = end_time - start_time
            logger.info(f"转录成功 (耗时: {duration:.3f}s)。结果: '{text}'")
            return text

        except Exception as e:
            logger.error(f"转录过程中发生严重错误: {e}", exc_info=True)
            return ""
