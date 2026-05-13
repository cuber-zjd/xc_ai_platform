"""
LLM 工厂 - 数据库驱动 + 熔断降级

核心功能：
1. 按模型名称调用：get_model_by_name("DeepSeek-V3")
2. 按模型级别调用：get_model_by_level(level=2)
3. 按能力标签调用：get_model(capability="complex-reasoning")
4. 熔断降级：某模型连续失败后自动标记熔断，切换到同级或下级模型
5. 带缓存的模型配置加载，避免频繁查库

使用示例：
    # 按名称
    llm = await LLMFactory.get_model_by_name("DeepSeek-V3")

    # 按级别（自动选最高优先级）
    llm = await LLMFactory.get_model_by_level(level=2)

    # 按能力（推荐，最灵活）
    llm = await LLMFactory.get_model(capability="complex-reasoning")

    # 带熔断的安全调用
    result = await LLMFactory.safe_invoke(messages, capability="general")
"""

import asyncio
import time
from enum import Enum
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI

from app.core.config import settings
from app.core.logger import logger

# LangFuse 可观测性集成
try:
    from langfuse.langchain import CallbackHandler as LangfuseCallbackHandler
except ImportError:
    try:
        from langfuse import CallbackHandler as LangfuseCallbackHandler
    except ImportError:
        LangfuseCallbackHandler = None  # type: ignore
        logger.warning("LangFuse CallbackHandler 不可用，链路追踪已禁用")


# ============================================================
# 熔断器
# ============================================================


class CircuitState(str, Enum):
    """熔断器状态"""

    CLOSED = "closed"  # 正常（允许请求）
    OPEN = "open"  # 熔断（拒绝请求）
    HALF_OPEN = "half_open"  # 半开（允许探测请求）


class CircuitBreaker:
    """
    模型级别的熔断器

    状态转换：
    - CLOSED: 正常工作，记录失败次数
    - OPEN: 失败次数达到阈值，拒绝所有请求，等待恢复时间
    - HALF_OPEN: 恢复时间到期，允许一次探测请求
        - 探测成功 → CLOSED
        - 探测失败 → OPEN（重置恢复时间）
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        recovery_timeout: int = 60,
    ):
        """
        Args:
            failure_threshold: 连续失败次数阈值，达到后触发熔断
            recovery_timeout: 熔断恢复超时时间（秒），超时后进入半开状态
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time: float = 0
        self.state = CircuitState.CLOSED

    @property
    def is_available(self) -> bool:
        """判断当前模型是否可用"""
        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            # 检查是否已过恢复超时，可以进入半开状态
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                logger.info("熔断器进入半开状态，允许探测请求")
                return True
            return False

        # HALF_OPEN: 允许一次探测
        return True

    def record_success(self) -> None:
        """记录成功调用"""
        if self.state == CircuitState.HALF_OPEN:
            logger.info("半开探测成功，熔断器恢复为关闭状态")
        self.failure_count = 0
        self.state = CircuitState.CLOSED

    def record_failure(self) -> None:
        """记录失败调用"""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.state == CircuitState.HALF_OPEN:
            # 半开状态下失败，重新进入熔断
            self.state = CircuitState.OPEN
            logger.warning("半开探测失败，熔断器重新打开")
        elif self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            logger.warning(
                f"连续失败 {self.failure_count} 次，触发熔断 "
                f"(恢复超时: {self.recovery_timeout}s)"
            )


# ============================================================
# 模型配置缓存
# ============================================================


class ModelConfigCache:
    """
    模型配置缓存

    从数据库加载模型配置后缓存在内存中，设定 TTL 过期后重新加载。
    避免每次调用 LLM 都查库。
    """

    def __init__(self, ttl_seconds: int = 300):
        """
        Args:
            ttl_seconds: 缓存生存时间（秒），默认 5 分钟
        """
        self.ttl_seconds = ttl_seconds
        self._cache: dict[str, Any] = {}  # key → (data, timestamp)
        self._lock = asyncio.Lock()

    def get(self, key: str) -> Any | None:
        """获取缓存，过期返回 None"""
        if key in self._cache:
            data, ts = self._cache[key]
            if time.time() - ts < self.ttl_seconds:
                return data
            # 过期，删除
            del self._cache[key]
        return None

    def set(self, key: str, data: Any) -> None:
        """设置缓存"""
        self._cache[key] = (data, time.time())

    def invalidate(self, key: str | None = None) -> None:
        """使缓存失效"""
        if key is None:
            self._cache.clear()
        elif key in self._cache:
            del self._cache[key]


# ============================================================
# LLM 工厂（核心）
# ============================================================


class LLMFactory:
    """
    LLM 工厂 - 数据库驱动 + 熔断降级

    所有模型调用都应通过此工厂，禁止直接实例化 ChatOpenAI 等。
    """

    # 模型级别的熔断器（模型名称 → CircuitBreaker）
    _circuit_breakers: dict[str, CircuitBreaker] = {}

    # 模型配置缓存
    _config_cache = ModelConfigCache(ttl_seconds=300)

    # 熔断器默认参数
    FAILURE_THRESHOLD = 3  # 连续失败 3 次触发熔断
    RECOVERY_TIMEOUT = 60  # 熔断后 60 秒尝试恢复

    @classmethod
    def _get_circuit_breaker(cls, model_name: str) -> CircuitBreaker:
        """获取或创建模型的熔断器"""
        if model_name not in cls._circuit_breakers:
            cls._circuit_breakers[model_name] = CircuitBreaker(
                failure_threshold=cls.FAILURE_THRESHOLD,
                recovery_timeout=cls.RECOVERY_TIMEOUT,
            )
        return cls._circuit_breakers[model_name]

    @classmethod
    def _create_langfuse_callbacks(cls) -> list:
        """创建 LangFuse 追踪回调"""
        callbacks = []
        if LangfuseCallbackHandler is not None:
            import os

            try:
                # 新版 LangFuse CallbackHandler 不再直接接受 secret_key 和 host 参数
                # 而是通过环境变量读取，因此我们在这里将其注入到环境变量中
                os.environ["LANGFUSE_PUBLIC_KEY"] = settings.LANGFUSE_PUBLIC_KEY
                os.environ["LANGFUSE_SECRET_KEY"] = settings.LANGFUSE_SECRET_KEY
                os.environ["LANGFUSE_HOST"] = settings.LANGFUSE_HOST
                os.environ["LANGFUSE_DEBUG"] = "False"

                handler = LangfuseCallbackHandler()
                callbacks.append(handler)
                logger.info(f"LangFuse 追踪器已就绪 (Host: {settings.LANGFUSE_HOST})")
            except Exception as e:
                logger.warning(f"LangFuse 初始化失败: {e}")
        else:
            logger.warning(
                "LangFuse CallbackHandler 未加载，请检查是否安装了 langfuse 库"
            )
        return callbacks

    @classmethod
    def _build_llm(
        cls,
        model_code: str,
        api_key: str,
        base_url: str,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        streaming: bool = True,
        json_mode: bool = False,
        enable_reasoning: bool = False,
    ) -> BaseChatModel:
        """
        根据配置构建 LLM 实例

        内部方法，不直接暴露给业务层。
        """
        callbacks = cls._create_langfuse_callbacks()

        model_kwargs: dict[str, Any] = {}
        if json_mode:
            # 兼容性处理：部分模型不支持 json_object (例如 doubao-seed-2-0-pro)
            # 如果模型代码中包含 doubao-seed-2-0-pro，则跳过 response_format 设置，依赖 Prompt 约束
            if "doubao-seed-2-0-pro" in model_code:
                logger.debug(f"模型 {model_code} 不支持 json_object，已跳过 response_format 设置")
            else:
                model_kwargs["response_format"] = {"type": "json_object"}

        # 思考模式处理 (兼容 DeepSeek 和 火山引擎)
        if "extra_body" not in model_kwargs:
            model_kwargs["extra_body"] = {}

        if enable_reasoning:
            model_kwargs["extra_body"]["include_reasoning"] = True
            model_kwargs["extra_body"]["thinking"] = {"type": "enabled"}
        else:
            # 显式关闭思考，提高响应速度 (火山引擎特有)
            model_kwargs["extra_body"]["thinking"] = {"type": "disabled"}

        llm = ChatOpenAI(
            model=model_code,
            temperature=temperature,
            api_key=api_key,
            base_url=base_url,
            max_tokens=max_tokens,
            streaming=streaming,
            stream_usage=True, # 确保流式输出时返回 token 统计
            callbacks=callbacks if callbacks else None,
            model_kwargs=model_kwargs,
        )
        return llm

    # --------------------------------------------------------
    # 数据库驱动的模型获取
    # --------------------------------------------------------

    @classmethod
    async def _load_all_models(cls, model_type: str = "chat") -> list:
        """从数据库加载所有启用的模型配置（带缓存）"""
        cache_key = f"all_models_{model_type}"
        cached = cls._config_cache.get(cache_key)
        if cached is not None:
            return cached

        from app.db.session import async_session
        from app.services.system.model_service import model_service

        async with async_session() as session:
            models = await model_service.get_all_enabled_models(
                session, model_type=model_type
            )

        cls._config_cache.set(cache_key, models)
        logger.debug(f"加载了 {len(models)} 个 {model_type} 类型的模型配置")
        return models

    @classmethod
    async def get_model_by_name(
        cls,
        model_name: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        streaming: bool = True,
        json_mode: bool = False,
        enable_reasoning: bool = False,
    ) -> BaseChatModel:
        """
        按模型名称获取 LLM 实例

        Args:
            model_name: 模型显示名称（对应 sys_model.model_name）
            temperature: 覆盖默认温度
            max_tokens: 覆盖默认最大 Token 数
            streaming: 是否流式
            json_mode: 是否 JSON 输出模式

        Returns:
            配置好的 LLM 实例

        Raises:
            ValueError: 模型不存在或被禁用
        """
        from app.db.session import async_session
        from app.services.system.model_service import model_service

        # 先检查缓存
        cache_key = f"model_name_{model_name}"
        model_config = cls._config_cache.get(cache_key)

        if model_config is None:
            async with async_session() as session:
                model_config = await model_service.get_model_by_name(
                    session, model_name
                )
            if model_config is None:
                raise ValueError(f"模型 '{model_name}' 不存在或已禁用")
            cls._config_cache.set(cache_key, model_config)

        temp = (
            temperature if temperature is not None else model_config.default_temperature
        )

        return cls._build_llm(
            model_code=model_config.model_code,
            api_key=model_config.api_key,
            base_url=model_config.base_url,
            temperature=temp,
            max_tokens=(
                max_tokens if max_tokens is not None else model_config.max_tokens
            ),
            streaming=streaming,
            json_mode=json_mode,
            enable_reasoning=enable_reasoning,
        )

    @classmethod
    async def get_model_by_level(
        cls,
        level: int = 3,
        model_type: str = "chat",
        temperature: float | None = None,
        streaming: bool = True,
        json_mode: bool = False,
        enable_reasoning: bool = False,
    ) -> BaseChatModel:
        """
        按模型级别获取 LLM 实例（自动选择该级别优先级最高的可用模型）

        Args:
            level: 模型级别 1=顶级 2=高级 3=标准 4=轻量
            model_type: 模型类型
            temperature: 覆盖默认温度
            streaming: 是否流式
            json_mode: 是否 JSON 输出模式

        Returns:
            配置好的 LLM 实例
        """
        all_models = await cls._load_all_models(model_type)

        # 筛选指定级别且未被熔断的模型
        for model_config in all_models:
            if model_config.model_level != level:
                continue
            cb = cls._get_circuit_breaker(model_config.model_name)
            if cb.is_available:
                temp = (
                    temperature
                    if temperature is not None
                    else model_config.default_temperature
                )
                return cls._build_llm(
                    model_code=model_config.model_code,
                    api_key=model_config.api_key,
                    base_url=model_config.base_url,
                    temperature=temp,
                    max_tokens=model_config.max_tokens,
                    streaming=streaming,
                    json_mode=json_mode,
                    enable_reasoning=enable_reasoning,
                )

        raise ValueError(f"级别 {level} 无可用模型（可能全部熔断）")

    @classmethod
    async def get_model(
        cls,
        capability: str = "general",
        model_type: str = "chat",
        temperature: float | None = None,
        streaming: bool = True,
        json_mode: bool = False,
        enable_reasoning: bool = False,
    ) -> BaseChatModel:
        """
        按能力标签获取 LLM 实例（推荐入口）

        自动选择匹配能力标签中优先级最高的未熔断模型。

        Args:
            capability: 能力标签 complex-reasoning / general / fast / code
            model_type: 模型类型
            temperature: 覆盖默认温度
            streaming: 是否流式
            json_mode: 是否 JSON 输出模式

        Returns:
            配置好的 LLM 实例
        """
        all_models = await cls._load_all_models(model_type)

        # 按能力筛选 + 未熔断
        for model_config in all_models:
            if model_config.capability != capability:
                continue
            cb = cls._get_circuit_breaker(model_config.model_name)
            if cb.is_available:
                temp = (
                    temperature
                    if temperature is not None
                    else model_config.default_temperature
                )
                return cls._build_llm(
                    model_code=model_config.model_code,
                    api_key=model_config.api_key,
                    base_url=model_config.base_url,
                    temperature=temp,
                    max_tokens=model_config.max_tokens,
                    streaming=streaming,
                    json_mode=json_mode,
                    enable_reasoning=enable_reasoning,
                )

        # 没找到匹配能力的，降级到 general
        if capability != "general":
            logger.warning(f"能力 '{capability}' 无可用模型，降级到 general")
            return await cls.get_model(
                capability="general",
                model_type=model_type,
                temperature=temperature,
                streaming=streaming,
                json_mode=json_mode,
                enable_reasoning=enable_reasoning,
            )

        raise ValueError(f"无可用的 {model_type} 模型（capability={capability}）")

    # --------------------------------------------------------
    # 带熔断降级的安全调用
    # --------------------------------------------------------

    @classmethod
    async def safe_invoke(
        cls,
        messages: list[BaseMessage],
        capability: str = "general",
        model_type: str = "chat",
        temperature: float | None = None,
        json_mode: bool = False,
        enable_reasoning: bool = False,
        max_retries: int = 3,
    ) -> Any:
        """
        带熔断降级的安全调用

        自动处理模型故障，按以下顺序尝试：
        1. 匹配能力标签的最高优先级模型
        2. 同级别其他模型
        3. 下级模型
        4. 全部失败后抛出异常

        Args:
            messages: 消息列表
            capability: 能力标签
            model_type: 模型类型
            temperature: 温度
            json_mode: JSON 模式
            max_retries: 最大重试模型数

        Returns:
            LLM 响应

        Raises:
            RuntimeError: 所有候选模型均不可用
        """
        all_models = await cls._load_all_models(model_type)
        tried_names: list[str] = []
        last_error: Exception | None = None

        # 构建候选模型列表：先匹配能力，再按级别排序
        candidates = []

        # 1. 优先匹配能力标签的模型
        for m in all_models:
            if m.capability == capability:
                candidates.append(m)

        # 2. 加入其他模型作为降级候选（按级别排序）
        for m in all_models:
            if m not in candidates:
                candidates.append(m)

        # 限制尝试次数
        candidates = candidates[:max_retries]

        for model_config in candidates:
            cb = cls._get_circuit_breaker(model_config.model_name)

            # 跳过已熔断的模型
            if not cb.is_available:
                logger.debug(f"模型 {model_config.model_name} 已熔断，跳过")
                continue

            try:
                temp = (
                    temperature
                    if temperature is not None
                    else model_config.default_temperature
                )
                llm = cls._build_llm(
                    model_code=model_config.model_code,
                    api_key=model_config.api_key,
                    base_url=model_config.base_url,
                    temperature=temp,
                    max_tokens=model_config.max_tokens,
                    streaming=False,  # safe_invoke 不使用流式
                    json_mode=json_mode,
                    enable_reasoning=enable_reasoning,
                )

                logger.info(
                    f"尝试调用模型: {model_config.model_name} "
                    f"(级别={model_config.model_level}, 优先级={model_config.priority})"
                )
                response = await llm.ainvoke(messages)

                # 成功，重置熔断器
                cb.record_success()
                logger.info(f"模型 {model_config.model_name} 调用成功")
                return response

            except Exception as e:
                # 失败，记录熔断
                cb.record_failure()
                tried_names.append(model_config.model_name)
                last_error = e
                logger.warning(
                    f"模型 {model_config.model_name} 调用失败: {e}，"
                    f"熔断状态: {cb.state.value}，"
                    f"已尝试: {tried_names}"
                )

        # 全部失败
        error_msg = (
            f"所有候选模型均调用失败，已尝试: {tried_names}。" f"最后错误: {last_error}"
        )
        logger.error(error_msg)
        raise RuntimeError(error_msg)

    # --------------------------------------------------------
    # 管理接口
    # --------------------------------------------------------

    @classmethod
    def get_circuit_breaker_status(cls) -> dict[str, dict[str, Any]]:
        """获取所有模型的熔断器状态（用于监控）"""
        status = {}
        for name, cb in cls._circuit_breakers.items():
            status[name] = {
                "state": cb.state.value,
                "failure_count": cb.failure_count,
                "last_failure_time": cb.last_failure_time,
                "is_available": cb.is_available,
            }
        return status

    @classmethod
    def reset_circuit_breaker(cls, model_name: str | None = None) -> None:
        """
        重置熔断器

        Args:
            model_name: 指定模型名称，None 表示重置所有
        """
        if model_name is None:
            cls._circuit_breakers.clear()
            logger.info("已重置所有模型的熔断器")
        elif model_name in cls._circuit_breakers:
            cls._circuit_breakers[model_name] = CircuitBreaker(
                failure_threshold=cls.FAILURE_THRESHOLD,
                recovery_timeout=cls.RECOVERY_TIMEOUT,
            )
            logger.info(f"已重置模型 {model_name} 的熔断器")

    @classmethod
    def invalidate_cache(cls) -> None:
        """使模型配置缓存失效（模型配置变更后调用）"""
        cls._config_cache.invalidate()
        logger.info("模型配置缓存已清除")
