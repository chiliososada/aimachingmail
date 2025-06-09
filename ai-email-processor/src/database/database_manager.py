# src/database/database_manager.py
"""数据库连接管理器"""

import logging
from typing import Dict, Optional
import asyncpg
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


class DatabaseManager:
    """数据库连接管理器"""

    def __init__(self, db_config: Dict):
        self.db_config = db_config
        self.db_pool: Optional[asyncpg.Pool] = None

    async def initialize(self):
        """初始化数据库连接池"""
        self.db_pool = await asyncpg.create_pool(**self.db_config)
        logger.info("Database pool created successfully")

    async def close(self):
        """关闭数据库连接池"""
        if self.db_pool:
            await self.db_pool.close()
            logger.info("Database pool closed")

    @asynccontextmanager
    async def get_connection(self):
        """获取数据库连接的上下文管理器"""
        if not self.db_pool:
            raise RuntimeError("Database pool not initialized")

        async with self.db_pool.acquire() as conn:
            yield conn

    @asynccontextmanager
    async def get_transaction(self):
        """获取数据库事务的上下文管理器"""
        async with self.get_connection() as conn:
            async with conn.transaction():
                yield conn


# 全局数据库管理器实例
db_manager = DatabaseManager({})  # 将在初始化时设置配置
