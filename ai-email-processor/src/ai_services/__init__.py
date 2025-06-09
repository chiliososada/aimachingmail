# src/ai_services/__init__.py
"""AI服务包"""

from .ai_client_manager import AIClientManager, ai_client_manager
from .extraction_service import ExtractionService, extraction_service

__all__ = [
    "AIClientManager",
    "ai_client_manager",
    "ExtractionService",
    "extraction_service",
]
