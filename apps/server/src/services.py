import importlib
import logging
import os

import yaml

# 设置一个模块级的日志记录器
logger = logging.getLogger(__name__)


class ServiceManager:
    """
    服务管理器 (ServiceManager) 负责在应用启动时，
    根据 config.yaml 的配置，动态加载并初始化所有必需的 AI 服务提供者。
    它确保了模型只被加载一次，并提供了一个统一的访问点。
    """

    def __init__(self, config_path: str = "config.yaml"):
        """
        初始化服务管理器。

        参数:
            config_path (str): 相对于 'src' 目录的配置文件路径。
        """
        # 初始化所有服务属性为 None
        self.asr = None
        self.vad = None
        self.llm = None
        self.tts = None

        # --- 1. 定位并加载配置文件 ---
        src_dir = os.path.dirname(os.path.abspath(__file__))
        self.config_file_path = os.path.join(src_dir, config_path)

        if not os.path.exists(self.config_file_path):
            raise FileNotFoundError(f"核心配置文件未找到: {self.config_file_path}")

        logger.info(f"正在从 {self.config_file_path} 加载服务配置...")
        with open(self.config_file_path, encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

        # --- 2. 加载所有被激活的服务 ---
        self._load_active_services()

    def _load_active_services(self):
        """
        一个总控方法，根据配置文件中的 'active_providers' 部分，加载所有服务。
        """
        active_providers = self.config.get("active_providers", {})
        if not active_providers:
            logger.warning("配置文件中未定义 'active_providers'，将不会加载任何服务。")
            return

        # 动态加载 ASR 服务
        if "asr" in active_providers:
            asr_provider_name = active_providers["asr"]
            self.asr = self._load_provider("asr_providers", asr_provider_name)

        # 未来可以取消注释来加载其他服务
        # if "vad" in active_providers:
        #     vad_provider_name = active_providers["vad"]
        #     self.vad = self._load_provider("vad_providers", vad_provider_name)

    def _load_provider(self, provider_type: str, provider_name: str):
        """
        一个通用的工厂方法，用于加载指定类型的单个服务提供者。
        此方法经过重构，对配置错误更具健壮性。

        参数:
            provider_type (str): 提供者的类型 (例如, 'asr_providers')。
            provider_name (str): 要加载的具体提供者的名称 (例如, 'funasr_local')。

        返回:
            一个实例化的 Provider 对象，如果加载失败则返回 None。
        """
        logger.info(f"准备加载 {provider_type} -> {provider_name}...")

        # --- 1. 从配置中获取提供者的完整定义 ---
        provider_definitions = self.config.get(provider_type, {})
        provider_definition = provider_definitions.get(provider_name)

        if not provider_definition:
            logger.error(
                f"在配置文件的 '{provider_type}' 中找不到提供者 '{provider_name}' 的定义。"
            )
            return None

        class_path = provider_definition.get("class_path")
        provider_params = provider_definition.get("config", {})

        if not class_path:
            logger.error(f"提供者 '{provider_name}' 的定义中缺少 'class_path'。")
            return None

        # --- 2. 安全地解析模块路径和类名 ---
        try:
            module_path, class_name = class_path.rsplit(".", 1)
        except ValueError:
            logger.error(
                f"提供者 '{provider_name}' 的 'class_path' 格式无效: '{class_path}'。"
                "它必须包含一个 '.' 来分隔模块和类名。"
            )
            return None

        # --- 3. 动态导入模块并实例化类 ---
        try:
            # 修正：使用相对导入。
            # '.' + module_path 创建一个相对路径 (例如, '.providers.asr.fun')，
            # package=__package__ 告诉 importlib 相对于哪个包来解析。
            # __package__ 在这里的值是 'src' (或 'apps.server.src')，这正是我们需要的锚点。
            module = importlib.import_module(f".{module_path}", package=__package__)
            ProviderClass = getattr(module, class_name)

            logger.info(f"正在实例化 {class_name}...")
            # 将 'config' 字典作为关键字参数传递给 Provider 类的构造函数
            provider_instance = ProviderClass(config=provider_params)

            logger.info(f"服务 '{provider_name}' ({class_name}) 加载并实例化成功。")
            return provider_instance

        except ImportError:
            logger.error(f"动态导入模块 '{module_path}' 失败。", exc_info=True)
        except AttributeError:
            logger.error(f"在模块 '{module_path}' 中找不到类 '{class_name}'。", exc_info=True)
        except Exception:
            logger.error(f"实例化类 '{class_name}' 时发生未知错误。", exc_info=True)

        return None
