# src/models/__init__.py
"""数据模型包"""

from .data_models import (
    EmailType,
    ProcessingStatus,
    EmailData,
    ProjectStructured,
    EngineerStructured,
    SMTPSettings,
    AttachmentInfo,
    EmailProcessingResult,
)

__all__ = [
    "EmailType",
    "ProcessingStatus",
    "EmailData",
    "ProjectStructured",
    "EngineerStructured",
    "SMTPSettings",
    "AttachmentInfo",
    "EmailProcessingResult",
]
