# scripts/configuration_checker.py
"""配置检查器 - 详细检查系统配置"""

import sys
import os
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.config import Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def check_ai_providers():
    """检查AI提供商配置"""
    logger.info("🤖 Checking AI provider configurations...")

    for service_type in ["classification", "extraction", "attachment"]:
        logger.info(f"\n📋 {service_type.upper()} Service:")

        try:
            # 检查主要提供商
            config = Config.get_ai_config_for_service(service_type)
            provider = config.get("provider_name")
            logger.info(f"  Primary provider: {provider}")

            # 检查后备提供商
            fallback_config = Config.get_ai_config_for_service(
                service_type, use_fallback=True
            )
            fallback_provider = fallback_config.get("provider_name")
            logger.info(f"  Fallback provider: {fallback_provider}")

            # 检查必要配置
            if provider in ["deepseek", "openai"]:
                api_key = config.get("api_key")
                if api_key:
                    logger.info(f"  ✅ API key configured")
                else:
                    logger.error(f"  ❌ API key missing for {provider}")

            if provider in ["deepseek", "custom", "custom_no_auth"]:
                api_base_url = config.get("api_base_url")
                if api_base_url:
                    logger.info(f"  ✅ API base URL: {api_base_url}")
                else:
                    logger.error(f"  ❌ API base URL missing for {provider}")

        except Exception as e:
            logger.error(f"  ❌ Error checking {service_type}: {e}")


def check_database_config():
    """检查数据库配置"""
    logger.info("🗄️ Checking database configuration...")

    db_config = Config.get_db_config()

    required_fields = ["host", "port", "database", "user", "password"]
    for field in required_fields:
        value = db_config.get(field)
        if value:
            # 不显示密码的完整值
            display_value = "***" if field == "password" else value
            logger.info(f"  ✅ {field}: {display_value}")
        else:
            logger.error(f"  ❌ {field}: Missing")


def check_encryption():
    """检查加密配置"""
    logger.info("🔐 Checking encryption configuration...")

    encryption_key = Config.ENCRYPTION_KEY
    if encryption_key:
        logger.info(f"  ✅ Encryption key configured (length: {len(encryption_key)})")
    else:
        logger.error("  ❌ Encryption key missing")


def main():
    """主检查函数"""
    logger.info("🔧 Starting configuration check...")

    try:
        # 基本配置验证
        Config.validate()
        logger.info("✅ Basic configuration validation passed")
    except ValueError as e:
        logger.error(f"❌ Configuration validation failed: {e}")
        return False

    # 详细检查
    check_database_config()
    check_encryption()
    check_ai_providers()

    # 打印配置总览
    logger.info("\n📊 Configuration Overview:")
    Config.print_ai_service_mapping_info()

    logger.info("\n🎉 Configuration check completed!")
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
