# src/email_processor.py
"""重构后的邮件处理器 - 主入口点，负责协调各个服务组件"""

import asyncio
import logging
from typing import List

from src.config import Config
from src.database.database_manager import db_manager
from src.database.email_repository import email_repository
from src.services.email_processing_service import email_processing_service
from src.ai_services.ai_client_manager import ai_client_manager
from src.models.data_models import EmailProcessingResult

# 设置日志
logger = logging.getLogger(__name__)


class EmailProcessor:
    """重构后的邮件处理器主类 - 简化版本，职责更明确"""

    def __init__(self, db_config: dict = None):
        """
        初始化邮件处理器

        Args:
            db_config: 数据库配置，如果为None则使用默认配置
        """
        self.db_config = db_config or Config.get_db_config()
        self.email_processing_service = email_processing_service
        self.email_repo = email_repository

        logger.info("EmailProcessor initialized with modular architecture")

    async def initialize(self):
        """初始化处理器和所有依赖服务"""
        try:
            # 初始化数据库连接
            db_manager.db_config = self.db_config
            await db_manager.initialize()

            logger.info("EmailProcessor initialization completed successfully")

        except Exception as e:
            logger.error(f"Failed to initialize EmailProcessor: {e}")
            raise

    async def close(self):
        """关闭处理器和清理资源"""
        try:
            # 关闭AI客户端
            await ai_client_manager.close_all_clients()

            # 关闭数据库连接
            await db_manager.close()

            logger.info("EmailProcessor closed successfully")

        except Exception as e:
            logger.error(f"Error during EmailProcessor cleanup: {e}")

    async def process_all_tenants(self) -> List[EmailProcessingResult]:
        """处理所有活跃租户的邮件"""
        all_results = []

        try:
            # 获取所有活跃租户
            tenant_ids = await self.email_repo.get_active_tenant_ids()
            logger.info(f"Found {len(tenant_ids)} active tenants")

            for tenant_id in tenant_ids:
                try:
                    logger.info(f"Processing emails for tenant: {tenant_id}")

                    # 处理租户邮件
                    tenant_results = (
                        await self.email_processing_service.process_emails_for_tenant(
                            tenant_id
                        )
                    )
                    all_results.extend(tenant_results)

                    logger.info(
                        f"Processed {len(tenant_results)} emails for tenant {tenant_id}"
                    )

                except Exception as e:
                    logger.error(f"Error processing emails for tenant {tenant_id}: {e}")
                    continue

            logger.info(f"Total processed emails: {len(all_results)}")
            return all_results

        except Exception as e:
            logger.error(f"Error in process_all_tenants: {e}")
            raise

    async def process_tenant(self, tenant_id: str) -> List[EmailProcessingResult]:
        """处理指定租户的邮件"""
        try:
            logger.info(f"Processing emails for tenant: {tenant_id}")

            results = await self.email_processing_service.process_emails_for_tenant(
                tenant_id
            )

            logger.info(f"Processed {len(results)} emails for tenant {tenant_id}")
            return results

        except Exception as e:
            logger.error(f"Error processing emails for tenant {tenant_id}: {e}")
            raise

    async def test_configuration(self) -> bool:
        """测试配置和连接"""
        try:
            logger.info("Testing EmailProcessor configuration...")

            # 测试数据库连接
            async with db_manager.get_connection() as conn:
                result = await conn.fetchval("SELECT 1")
                if result != 1:
                    raise Exception("Database connection test failed")

            logger.info("✅ Database connection: OK")

            # 测试AI服务配置
            Config.print_ai_service_mapping_info()

            logger.info("✅ EmailProcessor configuration test completed successfully")
            return True

        except Exception as e:
            logger.error(f"❌ Configuration test failed: {e}")
            return False


# 向后兼容的类型导出
from src.models.data_models import EmailType, ProcessingStatus


# 向后兼容的函数
async def main():
    """批处理用的主函数 - 重构版本"""
    # 验证配置
    try:
        Config.validate()
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        return

    # 打印分离式AI配置信息
    logger.info("启动分离式AI邮件处理系统")
    Config.print_ai_service_mapping_info()

    processor = EmailProcessor()

    try:
        # 初始化处理器
        await processor.initialize()

        # 测试配置
        config_ok = await processor.test_configuration()
        if not config_ok:
            logger.error("Configuration test failed, aborting...")
            return

        # 处理所有租户的邮件
        results = await processor.process_all_tenants()

        # 统计结果
        success_count = sum(
            1 for r in results if r.processing_status == ProcessingStatus.PROCESSED
        )
        error_count = sum(
            1 for r in results if r.processing_status == ProcessingStatus.ERROR
        )

        logger.info(
            f"Processing completed: {success_count} successful, {error_count} errors"
        )

    except Exception as e:
        logger.error(f"Error in main processing: {e}")
        raise
    finally:
        await processor.close()


if __name__ == "__main__":
    # 设置日志格式
    logging.basicConfig(
        level=getattr(logging, Config.LOGGING["level"]),
        format=Config.LOGGING["format"],
    )

    asyncio.run(main())
