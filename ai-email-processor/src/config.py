# src/config.py
"""設定ファイル - 分离式AI服务配置版本"""

import os
import logging
from typing import Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class Config:
    """アプリケーション設定 - 分离式AI配置"""

    # データベース設定
    DATABASE = {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", 5432)),
        "database": os.getenv("DB_NAME", "ai_matching"),
        "user": os.getenv("DB_USER", "postgres"),
        "password": os.getenv("DB_PASSWORD", ""),
        "min_size": int(os.getenv("DB_POOL_MIN", 10)),
        "max_size": int(os.getenv("DB_POOL_MAX", 20)),
    }

    # AI服务配置 - 支持分离式配置
    AI_PROVIDERS = {
        "openai": {
            "api_key": os.getenv("OPENAI_API_KEY"),
            "model_classify": os.getenv("OPENAI_MODEL_CLASSIFY", "gpt-3.5-turbo"),
            "model_extract": os.getenv("OPENAI_MODEL_EXTRACT", "gpt-4"),
            "temperature": float(os.getenv("OPENAI_TEMPERATURE", 0.1)),
            "max_tokens": int(os.getenv("OPENAI_MAX_TOKENS", 300)),
            "timeout": float(os.getenv("OPENAI_TIMEOUT", 60.0)),
        },
        "deepseek": {
            "api_key": os.getenv("DEEPSEEK_API_KEY"),
            "api_base_url": os.getenv(
                "DEEPSEEK_API_BASE_URL", "https://api.deepseek.com"
            ),
            "model_classify": os.getenv("DEEPSEEK_MODEL_CLASSIFY", "deepseek-chat"),
            "model_extract": os.getenv("DEEPSEEK_MODEL_EXTRACT", "deepseek-chat"),
            "temperature": float(os.getenv("DEEPSEEK_TEMPERATURE", 0.1)),
            "max_tokens": int(os.getenv("DEEPSEEK_MAX_TOKENS", 300)),
            "timeout": float(os.getenv("DEEPSEEK_TIMEOUT", 120.0)),
        },
        "custom": {
            "api_key": os.getenv("CUSTOM_API_KEY"),
            "api_base_url": os.getenv("CUSTOM_API_BASE_URL"),
            "model_classify": os.getenv("CUSTOM_MODEL_CLASSIFY")
            or os.getenv("CUSTOM_DEFAULT_MODEL", "default"),
            "model_extract": os.getenv("CUSTOM_MODEL_EXTRACT")
            or os.getenv("CUSTOM_DEFAULT_MODEL", "default"),
            "require_auth": os.getenv("CUSTOM_REQUIRE_AUTH", "true").lower() == "true",
            "default_model": os.getenv("CUSTOM_DEFAULT_MODEL", "default"),
            "temperature": float(os.getenv("CUSTOM_TEMPERATURE", 0.1)),
            "max_tokens": int(os.getenv("CUSTOM_MAX_TOKENS", 300)),
            "timeout": float(os.getenv("CUSTOM_TIMEOUT", 120.0)),
        },
        # 新增：无认证自定义API配置
        "custom_no_auth": {
            "api_base_url": os.getenv("CUSTOM_NO_AUTH_API_BASE_URL"),
            "default_model": os.getenv("CUSTOM_NO_AUTH_DEFAULT_MODEL", "default"),
            "temperature": float(os.getenv("CUSTOM_NO_AUTH_TEMPERATURE", 0.1)),
            "max_tokens": int(os.getenv("CUSTOM_NO_AUTH_MAX_TOKENS", 300)),
            "timeout": float(os.getenv("CUSTOM_NO_AUTH_TIMEOUT", 120.0)),
            "require_auth": False,  # 明确标记为无认证
        },
    }

    # 分离式AI服务配置 - 核心新功能
    AI_SERVICE_MAPPING = {
        # 邮件分类服务配置
        "classification": {
            "provider": os.getenv("AI_CLASSIFICATION_PROVIDER", "custom_no_auth"),
            "fallback_provider": os.getenv("AI_CLASSIFICATION_FALLBACK", "deepseek"),
        },
        # 数据提取服务配置
        "extraction": {
            "provider": os.getenv("AI_EXTRACTION_PROVIDER", "deepseek"),
            "fallback_provider": os.getenv("AI_EXTRACTION_FALLBACK", "openai"),
        },
        # 附件处理服务配置
        "attachment": {
            "provider": os.getenv("AI_ATTACHMENT_PROVIDER", "deepseek"),
            "fallback_provider": os.getenv("AI_ATTACHMENT_FALLBACK", "openai"),
        },
    }

    # 传统单一AI提供商配置（向后兼容）
    DEFAULT_AI_PROVIDER = os.getenv("DEFAULT_AI_PROVIDER", "deepseek").lower()

    # メール処理設定
    EMAIL_PROCESSING = {
        "batch_size": int(os.getenv("EMAIL_BATCH_SIZE", 50)),
        "interval_minutes": int(os.getenv("EMAIL_CHECK_INTERVAL", 10)),
        "retry_attempts": int(os.getenv("EMAIL_RETRY_ATTEMPTS", 3)),
        "retry_delay": int(os.getenv("EMAIL_RETRY_DELAY", 60)),
    }

    # 改进邮件分类器配置
    CLASSIFICATION = {
        "confidence_threshold": float(
            os.getenv("CLASSIFICATION_CONFIDENCE_THRESHOLD", 0.7)
        ),
        "enable_detailed_logging": os.getenv(
            "ENABLE_CLASSIFICATION_LOGGING", "true"
        ).lower()
        == "true",
        "keyword_analysis_enabled": os.getenv(
            "KEYWORD_ANALYSIS_ENABLED", "true"
        ).lower()
        == "true",
        "classification_timeout": int(os.getenv("CLASSIFICATION_TIMEOUT", 30)),
        "spam_keywords_threshold": int(os.getenv("SPAM_KEYWORDS_THRESHOLD", 2)),
        "keyword_weights": {
            "high": float(os.getenv("KEYWORD_WEIGHT_HIGH", 3.0)),
            "medium": float(os.getenv("KEYWORD_WEIGHT_MEDIUM", 1.5)),
            "low": float(os.getenv("KEYWORD_WEIGHT_LOW", 0.5)),
        },
        "content_extraction": {
            "max_length": int(os.getenv("CONTENT_MAX_LENGTH", 2000)),
            "head_length": int(os.getenv("CONTENT_HEAD_LENGTH", 800)),
            "tail_length": int(os.getenv("CONTENT_TAIL_LENGTH", 300)),
            "important_keywords_threshold": int(
                os.getenv("IMPORTANT_KEYWORDS_THRESHOLD", 2)
            ),
        },
    }

    # ロギング設定
    LOGGING = {
        "level": os.getenv("LOG_LEVEL", "INFO"),
        "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        "file": os.getenv("LOG_FILE", "email_processor.log"),
    }

    # セキュリティ設定
    ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "")

    @classmethod
    def get_db_config(cls) -> Dict[str, Any]:
        """データベース設定を取得"""
        return cls.DATABASE

    @classmethod
    def get_ai_config(cls, provider_name: Optional[str] = None) -> Dict[str, Any]:
        """AI設定を取得（向后兼容方法）"""
        provider_to_use = (provider_name or cls.DEFAULT_AI_PROVIDER).lower()

        if provider_to_use not in cls.AI_PROVIDERS:
            logger.warning(
                f"AI provider '{provider_to_use}' not found in config. Falling back to default '{cls.DEFAULT_AI_PROVIDER}'."
            )
            provider_to_use = cls.DEFAULT_AI_PROVIDER

        config = cls.AI_PROVIDERS[provider_to_use].copy()
        config["provider_name"] = provider_to_use
        return config

    @classmethod
    def get_ai_config_for_service(
        cls, service_type: str, use_fallback: bool = False
    ) -> Dict[str, Any]:
        """获取特定服务的AI配置 - 核心新方法"""
        if service_type not in cls.AI_SERVICE_MAPPING:
            logger.warning(
                f"Unknown service type: {service_type}, using default provider"
            )
            return cls.get_ai_config()

        service_config = cls.AI_SERVICE_MAPPING[service_type]
        provider_name = (
            service_config["fallback_provider"]
            if use_fallback
            else service_config["provider"]
        )

        if provider_name not in cls.AI_PROVIDERS:
            logger.error(
                f"Provider {provider_name} for service {service_type} not found in AI_PROVIDERS"
            )
            # 使用默认提供商作为最后的后备
            return cls.get_ai_config()

        config = cls.AI_PROVIDERS[provider_name].copy()
        config["provider_name"] = provider_name
        config["service_type"] = service_type

        logger.info(f"Using AI provider '{provider_name}' for service '{service_type}'")
        return config

    @classmethod
    def get_classification_config(cls) -> Dict[str, Any]:
        """分类器配置を取得"""
        return cls.CLASSIFICATION

    @classmethod
    def get_email_processing_config(cls) -> Dict[str, Any]:
        """メール処理設定を取得"""
        return cls.EMAIL_PROCESSING

    @classmethod
    def validate(cls):
        """設定の検証 - 分离式配置验证"""
        errors = []

        # 必須設定の確認
        if not cls.DATABASE["password"]:
            errors.append("Database password is not set")

        # 验证分离式AI服务配置
        for service_type, service_config in cls.AI_SERVICE_MAPPING.items():
            primary_provider = service_config["provider"]
            fallback_provider = service_config["fallback_provider"]

            # 验证主要提供商
            if primary_provider not in cls.AI_PROVIDERS:
                errors.append(
                    f"Primary AI provider '{primary_provider}' for service '{service_type}' is not defined"
                )
            else:
                # 验证主要提供商配置
                provider_config = cls.AI_PROVIDERS[primary_provider]
                if primary_provider == "custom_no_auth":
                    if not provider_config.get("api_base_url"):
                        errors.append(
                            f"API base URL for custom_no_auth provider (service: {service_type}) is not set"
                        )
                elif primary_provider in ["deepseek", "custom"]:
                    if not provider_config.get("api_base_url"):
                        errors.append(
                            f"API base URL for {primary_provider} (service: {service_type}) is not set"
                        )
                    if (
                        primary_provider == "custom"
                        and provider_config.get("require_auth", True)
                        and not provider_config.get("api_key")
                    ):
                        errors.append(
                            f"API key for custom provider (service: {service_type}) is required when auth is enabled"
                        )
                    elif primary_provider == "deepseek" and not provider_config.get(
                        "api_key"
                    ):
                        errors.append(
                            f"API key for DeepSeek (service: {service_type}) is not set"
                        )
                elif primary_provider == "openai":
                    if not provider_config.get("api_key"):
                        errors.append(
                            f"API key for OpenAI (service: {service_type}) is not set"
                        )

            # 验证后备提供商
            if fallback_provider not in cls.AI_PROVIDERS:
                errors.append(
                    f"Fallback AI provider '{fallback_provider}' for service '{service_type}' is not defined"
                )

        # 验证传统默认提供商（向后兼容）
        if cls.DEFAULT_AI_PROVIDER not in cls.AI_PROVIDERS:
            errors.append(
                f"Default AI provider '{cls.DEFAULT_AI_PROVIDER}' is not defined in AI_PROVIDERS"
            )

        # 暗号化キーの確認
        if not cls.ENCRYPTION_KEY:
            errors.append("Encryption key is not set")

        # 分类器配置验证
        classification_config = cls.CLASSIFICATION
        confidence_threshold = classification_config["confidence_threshold"]
        if not 0.0 <= confidence_threshold <= 1.0:
            errors.append(
                f"Classification confidence threshold must be between 0.0 and 1.0, got {confidence_threshold}"
            )

        classification_timeout = classification_config["classification_timeout"]
        if classification_timeout < 5:
            errors.append(
                f"Classification timeout must be at least 5 seconds, got {classification_timeout}"
            )

        spam_threshold = classification_config["spam_keywords_threshold"]
        if spam_threshold < 1:
            errors.append(
                f"Spam keywords threshold must be at least 1, got {spam_threshold}"
            )

        keyword_weights = classification_config["keyword_weights"]
        if not all(w > 0 for w in keyword_weights.values()):
            errors.append("All keyword weights must be positive")

        content_config = classification_config["content_extraction"]
        if content_config["max_length"] < 500:
            errors.append("Content max length should be at least 500 characters")

        if content_config["head_length"] >= content_config["max_length"]:
            errors.append("Head length should be less than max length")

        if errors:
            raise ValueError(f"Configuration errors: {', '.join(errors)}")

    @classmethod
    def print_ai_service_mapping_info(cls):
        """打印分离式AI服务配置信息"""
        print("=== 分离式AI服务配置信息 ===")
        print("\n🔧 服务映射配置:")

        for service_type, service_config in cls.AI_SERVICE_MAPPING.items():
            print(f"\n📋 {service_type.upper()} 服务:")
            print(f"  主要提供商: {service_config['provider']}")
            print(f"  后备提供商: {service_config['fallback_provider']}")

            # 显示主要提供商的详细配置
            primary_provider = service_config["provider"]
            if primary_provider in cls.AI_PROVIDERS:
                provider_config = cls.AI_PROVIDERS[primary_provider]
                print(f"  主要提供商配置:")
                if provider_config.get("api_base_url"):
                    print(f"    API URL: {provider_config['api_base_url']}")
                if provider_config.get("model_classify"):
                    print(f"    分类模型: {provider_config['model_classify']}")
                if provider_config.get("model_extract"):
                    print(f"    提取模型: {provider_config['model_extract']}")
                print(f"    需要认证: {provider_config.get('require_auth', True)}")
                print(f"    超时时间: {provider_config.get('timeout', 120)}秒")

    @classmethod
    def print_classification_info(cls):
        """打印分类器配置信息（向后兼容）"""
        print("=== 邮件分类器配置信息 ===")
        print(f"默认AI Provider: {cls.DEFAULT_AI_PROVIDER}")

        # 显示分离式配置
        cls.print_ai_service_mapping_info()

        # 显示分类器设置
        classification_config = cls.get_classification_config()
        print(f"\n📊 分类器设置:")
        print(f"置信度阈值: {classification_config['confidence_threshold']}")
        print(f"详细日志: {classification_config['enable_detailed_logging']}")
        print(f"关键词分析: {classification_config['keyword_analysis_enabled']}")
        print(f"分类超时: {classification_config['classification_timeout']}s")
        print(f"垃圾邮件阈值: {classification_config['spam_keywords_threshold']}")

        print(f"\n🔑 关键词权重:")
        for level, weight in classification_config["keyword_weights"].items():
            print(f"  {level}: {weight}")

        print(f"\n📄 内容提取配置:")
        for key, value in classification_config["content_extraction"].items():
            print(f"  {key}: {value}")


# 配置验证函数
def validate_configuration():
    """验证所有配置"""
    try:
        Config.validate()
        print("✅ 分离式AI配置验证通过")
        return True
    except ValueError as e:
        print(f"❌ 配置验证失败: {e}")
        return False


if __name__ == "__main__":
    # 当直接运行config.py时，验证配置并打印信息
    print("🔧 分离式AI配置验证和信息显示")
    print("=" * 60)

    if validate_configuration():
        print("\n" + "=" * 60)
        Config.print_classification_info()
    else:
        print("\n请检查并修正配置错误")
