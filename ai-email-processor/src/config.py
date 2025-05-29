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
            "model_extract": os.getenv("OPENAI_MODEL_EXTRACT", "gpt-4"),
            "temperature": float(os.getenv("OPENAI_TEMPERATURE", 0.3)),
            "max_tokens": int(os.getenv("OPENAI_MAX_TOKENS", 1000)),
        },
        "deepseek": {
            "api_key": os.getenv("DEEPSEEK_API_KEY"),
            "model": os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
            "temperature": float(os.getenv("DEEPSEEK_TEMPERATURE", 0.3)),
            "max_tokens": int(os.getenv("DEEPSEEK_MAX_TOKENS", 1000)),
        },
    }

    # 使用するAIプロバイダー
    DEFAULT_AI_PROVIDER = os.getenv("DEFAULT_AI_PROVIDER", "openai")

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
    def get_ai_config(cls, provider: Optional[str] = None) -> Dict[str, Any]:
        """AI設定を取得"""
        provider = provider or cls.DEFAULT_AI_PROVIDER
        return cls.AI_PROVIDERS.get(provider, cls.AI_PROVIDERS["openai"])

    @classmethod
    def validate(cls):
        """設定の検証"""
        errors = []

        # 必須設定の確認
        if not cls.DATABASE["password"]:
            errors.append("Database password is not set")

        if (
            not cls.AI_PROVIDERS["openai"]["api_key"]
            and not cls.AI_PROVIDERS["deepseek"]["api_key"]
        ):
            errors.append("At least one AI provider API key must be set")

        if not cls.ENCRYPTION_KEY:
            errors.append("Encryption key is not set")

        if errors:
            raise ValueError(f"Configuration errors: {', '.join(errors)}")
