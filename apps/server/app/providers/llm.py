import abc
import os

import structlog
from openai import AsyncOpenAI, OpenAIError

logger = structlog.get_logger(__name__)


class LLMProvider(abc.ABC):
    """
    大语言模型 (LLM) 提供程序的抽象基类。
    定义了所有LLM提供程序必须遵循的统一接口。
    """

    @abc.abstractmethod
    def __init__(self, *args, **kwargs):
        """
        初始化LLM提供程序。
        对于基于API的提供程序，这里通常会配置API密钥和HTTP客户端。
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def chat(self, text: str) -> str:
        """
        向LLM发送文本查询并获取响应。

        参数:
            text (str): 要发送给模型的用户输入文本。

        返回:
            str: 包含LLM响应的字符串。
                 此方法应等待完整的响应返回。
        """
        raise NotImplementedError


class OpenAILLMProvider(LLMProvider):
    """
    使用 openai 库与兼容OpenAI API的服务进行交互的LLM提供程序。
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str = "gpt-3.5-turbo",
        system_prompt: str = "你是一个乐于助人的助手。",
    ):
        """
        初始化 OpenAILLMProvider。

        参数:
            api_key (str, optional): OpenAI API密钥。如果未提供，将尝试从环境变量 `OPENAI_API_KEY` 读取。
            base_url (str, optional): API的基地址。用于连接本地模型或代理。如果未提供，将尝试从 `OPENAI_BASE_URL` 读取，否则使用官方API地址。
            model (str): 要使用的模型名称，例如 "gpt-4", "gpt-3.5-turbo"。
            system_prompt (str): 对话开始前设置的系统提示词。
        """
        # 优先使用传入的参数，否则从环境变量中读取，这是一种常见的灵活配置方式
        final_api_key = api_key or os.getenv("OPENAI_API_KEY")
        final_base_url = base_url or os.getenv("OPENAI_BASE_URL")

        log = logger.bind(model=model, base_url=final_base_url or "官方 OpenAI")
        log.info("正在初始化 OpenAILLMProvider")

        if not final_api_key:
            # 对于需要密钥的官方服务，如果没有提供密钥会失败。
            # 但很多本地模型（如Xinference, vLLM）不需要密钥，因此我们只打印警告而不是直接报错。
            log.warn(
                "未提供 OpenAI API 密钥。如果连接到需要身份验证的远程服务，后续操作可能会失败。"
            )
            # 为了让 `openai` 库在连接本地服务时不报错，可以传递一个非空的假密钥
            final_api_key = "no-key-provided"

        # 初始化异步的OpenAI客户端
        self._client = AsyncOpenAI(
            api_key=final_api_key,
            base_url=final_base_url,
        )
        self._model = model
        self._system_prompt = system_prompt

    async def chat(self, text: str) -> str:
        """
        向OpenAI兼容的API发送聊天请求。

        参数:
            text (str): 用户的输入。

        返回:
            str: LLM生成的回复文本。如果发生错误或输入为空，则返回错误信息或空字符串。
        """
        if not text:
            return ""

        log = logger.bind(text=text[:50] + "...")
        log.info("正在向LLM发送文本")
        try:
            # 构建发送给API的消息结构
            messages = [
                {"role": "system", "content": self._system_prompt},
                {"role": "user", "content": text},
            ]

            # 发起异步API调用
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
            )

            # 从返回结果中提取文本内容
            content = response.choices[0].message.content or ""
            log.info("从LLM接收到回复", response=content[:50] + "...")
            return content.strip()

        except OpenAIError as e:
            # 捕获并记录所有来自openai库的API错误
            log.error("OpenAI API 调用出错", exc_info=e)
            return f"抱歉，调用语言模型时遇到了一个错误：{e}"
        except Exception as e:
            # 捕获其他未知异常
            log.error("处理LLM响应时发生未知错误", exc_info=e)
            return "抱歉，处理您的请求时遇到了一个未知错误。"
