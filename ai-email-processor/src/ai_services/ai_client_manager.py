# src/ai_services/ai_client_manager.py
"""AI客户端管理器 - 统一管理所有AI提供商客户端"""

import logging
from typing import Dict, Optional, Tuple, Any
import httpx
from openai import AsyncOpenAI

from src.config import Config
from src.no_auth_processor import NoAuthCustomAPIProcessor

logger = logging.getLogger(__name__)


class AIClientManager:
    """AI客户端管理器 - 统一管理和初始化AI客户端"""

    def __init__(self):
        self.clients: Dict[str, Any] = {}
        self.configs: Dict[str, Dict] = {}

    def initialize_client(
        self, service_type: str, use_fallback: bool = False
    ) -> Tuple[Any, Dict]:
        """初始化指定服务类型的AI客户端

        Args:
            service_type: 服务类型 ('classification', 'extraction', 'attachment')
            use_fallback: 是否使用后备提供商

        Returns:
            Tuple[client, config]: 客户端实例和配置
        """
        cache_key = f"{service_type}_{'fallback' if use_fallback else 'primary'}"

        # 检查缓存
        if cache_key in self.clients:
            return self.clients[cache_key], self.configs[cache_key]

        # 获取配置
        config = Config.get_ai_config_for_service(service_type, use_fallback)
        provider_name = config.get("provider_name")

        logger.info(f"初始化 {cache_key} AI客户端: {provider_name}")

        # 初始化客户端
        client = self._create_client(config)

        if client:
            self.clients[cache_key] = client
            self.configs[cache_key] = config
            logger.info(f"{cache_key} AI客户端初始化成功")
        else:
            logger.error(f"{cache_key} AI客户端初始化失败")

        return client, config

    def _create_client(self, config: Dict) -> Optional[Any]:
        """根据配置创建AI客户端"""
        provider_name = config.get("provider_name")
        api_key = config.get("api_key")
        require_auth = config.get("require_auth", True)

        if provider_name == "openai":
            if api_key:
                return AsyncOpenAI(api_key=api_key)

        elif provider_name == "deepseek":
            api_base_url = config.get("api_base_url")
            timeout = config.get("timeout", 120.0)
            if api_key and api_base_url:
                return httpx.AsyncClient(
                    base_url=api_base_url,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    timeout=timeout,
                )

        elif provider_name == "custom":
            api_base_url = config.get("api_base_url")
            timeout = config.get("timeout", 120.0)

            if api_base_url:
                if require_auth and api_key:
                    return httpx.AsyncClient(
                        base_url=api_base_url,
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                        },
                        timeout=timeout,
                    )
                elif not require_auth:
                    default_model = config.get("default_model", "default")
                    return NoAuthCustomAPIProcessor(
                        api_base_url=api_base_url,
                        default_model=default_model,
                        timeout=timeout,
                    )

        elif provider_name == "custom_no_auth":
            api_base_url = config.get("api_base_url")
            timeout = config.get("timeout", 120.0)
            default_model = config.get("default_model", "default")

            if api_base_url:
                return NoAuthCustomAPIProcessor(
                    api_base_url=api_base_url,
                    default_model=default_model,
                    timeout=timeout,
                )

        logger.error(f"不支持的AI提供商或配置不完整: {provider_name}")
        return None

    def get_client(
        self, service_type: str, use_fallback: bool = False
    ) -> Tuple[Any, Dict]:
        """获取客户端（带缓存）"""
        return self.initialize_client(service_type, use_fallback)

    async def close_all_clients(self):
        """关闭所有httpx客户端"""
        for client in self.clients.values():
            if isinstance(client, httpx.AsyncClient):
                await client.aclose()

        self.clients.clear()
        self.configs.clear()
        logger.info("所有AI客户端已关闭")


# 全局客户端管理器实例
ai_client_manager = AIClientManager()
