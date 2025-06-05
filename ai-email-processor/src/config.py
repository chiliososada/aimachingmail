# src/config.py
"""設定ファイル"""

import os
import logging
from typing import Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class Config:
    """アプリケーション設定"""

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

    # AI設定
    AI_PROVIDERS = {
        "openai": {
            "api_key": os.getenv("OPENAI_API_KEY"),
            "model_classify": os.getenv("OPENAI_MODEL_CLASSIFY", "gpt-3.5-turbo"),
            "model_extract": os.getenv("OPENAI_MODEL_EXTRACT", "gpt-4"),
            "temperature": float(
                os.getenv("OPENAI_TEMPERATURE", 0.1)
            ),  # 降低温度提高一致性
            "max_tokens": int(os.getenv("OPENAI_MAX_TOKENS", 300)),  # 增加token数量
            "timeout": float(os.getenv("OPENAI_TIMEOUT", 60.0)),
        },
        "deepseek": {
            "api_key": os.getenv("DEEPSEEK_API_KEY"),
            "api_base_url": os.getenv(
                "DEEPSEEK_API_BASE_URL", "https://api.deepseek.com"
            ),
            "model_classify": os.getenv("DEEPSEEK_MODEL_CLASSIFY", "deepseek-chat"),
            "model_extract": os.getenv("DEEPSEEK_MODEL_EXTRACT", "deepseek-chat"),
            "temperature": float(
                os.getenv("DEEPSEEK_TEMPERATURE", 0.1)
            ),  # 降低温度提高一致性
            "max_tokens": int(os.getenv("DEEPSEEK_MAX_TOKENS", 300)),  # 增加token数量
            "timeout": float(os.getenv("DEEPSEEK_TIMEOUT", 120.0)),
        },
        "custom": {
            "api_key": os.getenv("CUSTOM_API_KEY"),  # 允许为空
            "api_base_url": os.getenv("CUSTOM_API_BASE_URL"),
            "model_classify": os.getenv("CUSTOM_MODEL_CLASSIFY")
            or os.getenv("CUSTOM_DEFAULT_MODEL", "default"),
            "model_extract": os.getenv("CUSTOM_MODEL_EXTRACT")
            or os.getenv("CUSTOM_DEFAULT_MODEL", "default"),
            "require_auth": os.getenv("CUSTOM_REQUIRE_AUTH", "true").lower()
            == "true",  # 新增
            "default_model": os.getenv("CUSTOM_DEFAULT_MODEL", "default"),  # 新增
            "temperature": float(os.getenv("CUSTOM_TEMPERATURE", 0.1)),
            "max_tokens": int(os.getenv("CUSTOM_MAX_TOKENS", 300)),
            "timeout": float(os.getenv("CUSTOM_TIMEOUT", 120.0)),
        },
    }

    # 使用するAIプロバイダー
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
        # 分类置信度阈值
        "confidence_threshold": float(
            os.getenv("CLASSIFICATION_CONFIDENCE_THRESHOLD", 0.7)
        ),
        # 是否启用详细分类日志
        "enable_detailed_logging": os.getenv(
            "ENABLE_CLASSIFICATION_LOGGING", "true"
        ).lower()
        == "true",
        # 是否启用关键词分析
        "keyword_analysis_enabled": os.getenv(
            "KEYWORD_ANALYSIS_ENABLED", "true"
        ).lower()
        == "true",
        # 分类器超时时间（秒）
        "classification_timeout": int(os.getenv("CLASSIFICATION_TIMEOUT", 30)),
        # 垃圾邮件检测阈值
        "spam_keywords_threshold": int(os.getenv("SPAM_KEYWORDS_THRESHOLD", 2)),
        # 关键词分析权重
        "keyword_weights": {
            "high": float(os.getenv("KEYWORD_WEIGHT_HIGH", 3.0)),
            "medium": float(os.getenv("KEYWORD_WEIGHT_MEDIUM", 1.5)),
            "low": float(os.getenv("KEYWORD_WEIGHT_LOW", 0.5)),
        },
        # 内容提取配置
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
        """AI設定を取得"""
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
    def get_classification_config(cls) -> Dict[str, Any]:
        """分类器配置を取得"""
        return cls.CLASSIFICATION

    @classmethod
    def get_email_processing_config(cls) -> Dict[str, Any]:
        """メール処理設定を取得"""
        return cls.EMAIL_PROCESSING

    @classmethod
    def validate(cls):
        """設定の検証"""
        errors = []

        # 必須設定の確認
        if not cls.DATABASE["password"]:
            errors.append("Database password is not set")

        if cls.DEFAULT_AI_PROVIDER not in cls.AI_PROVIDERS:
            errors.append(
                f"Default AI provider '{cls.DEFAULT_AI_PROVIDER}' is not defined in AI_PROVIDERS."
            )
        else:
            default_provider_config = cls.AI_PROVIDERS[cls.DEFAULT_AI_PROVIDER]

            # 只有当require_auth为true时才检查API key
            if cls.DEFAULT_AI_PROVIDER == "custom":
                require_auth = default_provider_config.get("require_auth", True)
                if require_auth and not default_provider_config.get("api_key"):
                    errors.append(
                        f"API key for custom provider is required when CUSTOM_REQUIRE_AUTH=true."
                    )
            else:
                # 其他提供商仍然需要API key
                if not default_provider_config.get("api_key"):
                    errors.append(
                        f"API key for the default AI provider '{cls.DEFAULT_AI_PROVIDER}' is not set."
                    )

            # 验证需要api_base_url的提供商
            if cls.DEFAULT_AI_PROVIDER in ["deepseek", "custom"]:
                if not default_provider_config.get("api_base_url"):
                    errors.append(
                        f"API base URL for {cls.DEFAULT_AI_PROVIDER} is not set."
                    )

        # 暗号化キーの確認
        if not cls.ENCRYPTION_KEY:
            errors.append("Encryption key is not set")

        # 分类器配置验证
        classification_config = cls.CLASSIFICATION

        # 验证置信度阈值
        confidence_threshold = classification_config["confidence_threshold"]
        if not 0.0 <= confidence_threshold <= 1.0:
            errors.append(
                f"Classification confidence threshold must be between 0.0 and 1.0, got {confidence_threshold}"
            )

        # 验证超时时间
        classification_timeout = classification_config["classification_timeout"]
        if classification_timeout < 5:
            errors.append(
                f"Classification timeout must be at least 5 seconds, got {classification_timeout}"
            )

        # 验证垃圾邮件检测阈值
        spam_threshold = classification_config["spam_keywords_threshold"]
        if spam_threshold < 1:
            errors.append(
                f"Spam keywords threshold must be at least 1, got {spam_threshold}"
            )

        # 验证关键词权重
        keyword_weights = classification_config["keyword_weights"]
        if not all(w > 0 for w in keyword_weights.values()):
            errors.append("All keyword weights must be positive")

        # 验证内容提取配置
        content_config = classification_config["content_extraction"]
        if content_config["max_length"] < 500:
            errors.append("Content max length should be at least 500 characters")

        if content_config["head_length"] >= content_config["max_length"]:
            errors.append("Head length should be less than max length")

        if errors:
            raise ValueError(f"Configuration errors: {', '.join(errors)}")

    @classmethod
    def print_classification_info(cls):
        """打印分类器配置信息（用于调试）"""
        print("=== 邮件分类器配置信息 ===")
        print(f"AI Provider: {cls.DEFAULT_AI_PROVIDER}")

        ai_config = cls.get_ai_config()
        print(f"AI Model (Classify): {ai_config.get('model_classify')}")
        print(f"AI Model (Extract): {ai_config.get('model_extract')}")
        print(f"AI Temperature: {ai_config.get('temperature')}")
        print(f"AI Max Tokens: {ai_config.get('max_tokens')}")
        print(f"AI Timeout: {ai_config.get('timeout')}s")

        if ai_config.get("api_base_url"):
            print(f"AI Base URL: {ai_config.get('api_base_url')}")

        classification_config = cls.get_classification_config()
        print(f"\n分类器设置:")
        print(f"置信度阈值: {classification_config['confidence_threshold']}")
        print(f"详细日志: {classification_config['enable_detailed_logging']}")
        print(f"关键词分析: {classification_config['keyword_analysis_enabled']}")
        print(f"分类超时: {classification_config['classification_timeout']}s")
        print(f"垃圾邮件阈值: {classification_config['spam_keywords_threshold']}")

        print(f"\n关键词权重:")
        for level, weight in classification_config["keyword_weights"].items():
            print(f"  {level}: {weight}")

        print(f"\n内容提取配置:")
        for key, value in classification_config["content_extraction"].items():
            print(f"  {key}: {value}")


# 配置验证函数
def validate_configuration():
    """验证所有配置"""
    try:
        Config.validate()
        print("✅ 配置验证通过")
        return True
    except ValueError as e:
        print(f"❌ 配置验证失败: {e}")
        return False


if __name__ == "__main__":
    # 当直接运行config.py时，验证配置并打印信息
    print("🔧 配置验证和信息显示")
    print("=" * 50)

    if validate_configuration():
        print("\n" + "=" * 50)
        Config.print_classification_info()
    else:
        print("\n请检查并修正配置错误")
