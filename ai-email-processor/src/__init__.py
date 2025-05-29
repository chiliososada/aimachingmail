# src/__init__.py
"""AI Email Processor Package"""

__version__ = "1.0.0"
__author__ = "AI Matching System"

# パッケージレベルのインポート
from .email_processor import EmailProcessor, EmailType, ProcessingStatus
from .scheduler import EmailScheduler
from .config import Config
from .deepseek_processor import DeepSeekProcessor

__all__ = [
    "EmailProcessor",
    "EmailType",
    "ProcessingStatus",
    "EmailScheduler",
    "Config",
    "DeepSeekProcessor",
]
