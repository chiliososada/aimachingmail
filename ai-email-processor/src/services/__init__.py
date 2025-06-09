# src/services/__init__.py
"""业务服务包"""

from .email_processing_service import EmailProcessingService, email_processing_service

__all__ = ["EmailProcessingService", "email_processing_service"]
