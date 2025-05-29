# src/config.py
"""設定ファイル"""

import os
from typing import Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()


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
            "model_extract": os.getenv("OPENAI_MODEL_EXTRACT", "gpt-4"), # Used for both project and engineer
            "temperature": float(os.getenv("OPENAI_TEMPERATURE", 0.3)),
            "max_tokens": int(os.getenv("OPENAI_MAX_TOKENS", 2048)), # Increased for potentially larger extractions
        },
        "deepseek": {
            "api_key": os.getenv("DEEPSEEK_API_KEY"),
            "api_base_url": os.getenv("DEEPSEEK_API_BASE_URL", "https://api.deepseek.com"),
            "model_classify": os.getenv("DEEPSEEK_MODEL_CLASSIFY", "deepseek-chat"), # Assuming same model for now
            "model_extract": os.getenv("DEEPSEEK_MODEL_EXTRACT", "deepseek-chat"), # Assuming same model for now
            "temperature": float(os.getenv("DEEPSEEK_TEMPERATURE", 0.3)),
            "max_tokens": int(os.getenv("DEEPSEEK_MAX_TOKENS", 2048)), # Increased for potentially larger extractions
        },
    }

    # 使用するAIプロバイダー
    DEFAULT_AI_PROVIDER = os.getenv("DEFAULT_AI_PROVIDER", "openai").lower() # Ensure lowercase for consistency

    # メール処理設定
    EMAIL_PROCESSING = {
        "batch_size": int(os.getenv("EMAIL_BATCH_SIZE", 50)),
        "interval_minutes": int(os.getenv("EMAIL_CHECK_INTERVAL", 10)),
        "retry_attempts": int(os.getenv("EMAIL_RETRY_ATTEMPTS", 3)),
        "retry_delay": int(os.getenv("EMAIL_RETRY_DELAY", 60)),
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
            # Fallback to default if the specified provider is not found
            logger.warning(f"AI provider '{provider_to_use}' not found in config. Falling back to default '{cls.DEFAULT_AI_PROVIDER}'.")
            provider_to_use = cls.DEFAULT_AI_PROVIDER

        config = cls.AI_PROVIDERS[provider_to_use].copy() # Return a copy to prevent modification of original config
        config["provider_name"] = provider_to_use # Add provider_name to the returned dict
        return config

    @classmethod
    def validate(cls):
        """設定の検証"""
        errors = []

        # 必須設定の確認
        if not cls.DATABASE["password"]:
            errors.append("Database password is not set")

        # Validate the default provider
        if cls.DEFAULT_AI_PROVIDER not in cls.AI_PROVIDERS:
            errors.append(f"Default AI provider '{cls.DEFAULT_AI_PROVIDER}' is not defined in AI_PROVIDERS.")
        else:
            # Validate the configuration for the default provider
            default_provider_config = cls.AI_PROVIDERS[cls.DEFAULT_AI_PROVIDER]
            if not default_provider_config.get("api_key"):
                errors.append(f"API key for the default AI provider '{cls.DEFAULT_AI_PROVIDER}' is not set.")
            if cls.DEFAULT_AI_PROVIDER == "deepseek" and not default_provider_config.get("api_base_url"):
                errors.append(f"API base URL for DeepSeek is not set.")

        # Check if at least one provider has an API key if you want to allow switching
        # This is somewhat covered by validating the default provider, but you might add more checks
        # if you expect users to switch to other providers at runtime without a default.

        if not cls.ENCRYPTION_KEY:
            errors.append("Encryption key is not set")

        if errors:
            raise ValueError(f"Configuration errors: {', '.join(errors)}")
