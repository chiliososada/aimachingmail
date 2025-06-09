# scripts/test_system.py
"""系统测试脚本 - 测试重构后的系统各个组件"""

import sys
import os
import asyncio
import logging

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.config import Config
from src.email_processor import EmailProcessor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_configuration():
    """测试系统配置"""
    logger.info("🔧 Testing system configuration...")

    try:
        Config.validate()
        logger.info("✅ Configuration validation passed")

        Config.print_ai_service_mapping_info()
        return True

    except Exception as e:
        logger.error(f"❌ Configuration test failed: {e}")
        return False


async def test_database_connection():
    """测试数据库连接"""
    logger.info("🗄️ Testing database connection...")

    try:
        processor = EmailProcessor()
        await processor.initialize()

        # 测试连接
        from src.database.database_manager import db_manager

        async with db_manager.get_connection() as conn:
            result = await conn.fetchval("SELECT 1")
            if result == 1:
                logger.info("✅ Database connection successful")
                success = True
            else:
                logger.error("❌ Database connection failed")
                success = False

        await processor.close()
        return success

    except Exception as e:
        logger.error(f"❌ Database connection test failed: {e}")
        return False


async def test_ai_services():
    """测试AI服务配置"""
    logger.info("🤖 Testing AI services...")

    try:
        from src.ai_services.ai_client_manager import ai_client_manager

        # 测试分类服务
        classification_client, classification_config = ai_client_manager.get_client(
            "classification"
        )
        if classification_client:
            logger.info(
                f"✅ Classification service: {classification_config.get('provider_name')}"
            )
        else:
            logger.error("❌ Classification service initialization failed")

        # 测试提取服务
        extraction_client, extraction_config = ai_client_manager.get_client(
            "extraction"
        )
        if extraction_client:
            logger.info(
                f"✅ Extraction service: {extraction_config.get('provider_name')}"
            )
        else:
            logger.error("❌ Extraction service initialization failed")

        # 测试附件处理服务
        attachment_client, attachment_config = ai_client_manager.get_client(
            "attachment"
        )
        if attachment_client:
            logger.info(
                f"✅ Attachment service: {attachment_config.get('provider_name')}"
            )
        else:
            logger.error("❌ Attachment service initialization failed")

        await ai_client_manager.close_all_clients()
        return True

    except Exception as e:
        logger.error(f"❌ AI services test failed: {e}")
        return False


async def test_email_processing():
    """测试邮件处理流程（不实际发送邮件）"""
    logger.info("📧 Testing email processing workflow...")

    try:
        processor = EmailProcessor()
        await processor.initialize()

        # 获取活跃租户列表
        from src.database.email_repository import email_repository

        tenant_ids = await email_repository.get_active_tenant_ids()

        if tenant_ids:
            logger.info(f"✅ Found {len(tenant_ids)} active tenants")

            # 测试SMTP设置获取
            settings_list = await email_repository.get_smtp_settings(tenant_ids[0])
            if settings_list:
                logger.info(
                    f"✅ Found {len(settings_list)} SMTP settings for first tenant"
                )
            else:
                logger.warning("⚠️ No SMTP settings found for first tenant")
        else:
            logger.warning("⚠️ No active tenants found")

        await processor.close()
        return True

    except Exception as e:
        logger.error(f"❌ Email processing test failed: {e}")
        return False


async def main():
    """主测试函数"""
    logger.info("🚀 Starting system tests...")

    tests = [
        ("Configuration", test_configuration),
        ("Database Connection", test_database_connection),
        ("AI Services", test_ai_services),
        ("Email Processing Workflow", test_email_processing),
    ]

    results = []

    for test_name, test_func in tests:
        logger.info(f"\n{'='*50}")
        logger.info(f"Running: {test_name}")
        logger.info(f"{'='*50}")

        try:
            result = await test_func()
            results.append((test_name, result))
        except Exception as e:
            logger.error(f"Test {test_name} crashed: {e}")
            results.append((test_name, False))

    # 打印测试总结
    logger.info(f"\n{'='*50}")
    logger.info("TEST SUMMARY")
    logger.info(f"{'='*50}")

    passed = 0
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        logger.info(f"{test_name}: {status}")
        if result:
            passed += 1

    logger.info(f"\nOverall: {passed}/{len(results)} tests passed")

    if passed == len(results):
        logger.info("🎉 All tests passed! System is ready.")
        return True
    else:
        logger.error("💥 Some tests failed. Please check the configuration.")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
